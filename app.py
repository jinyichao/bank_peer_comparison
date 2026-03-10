import os
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

from pdf_extractor import download_pdf_bytes, render_pages, page_count
from ai_parser import identify_relevant_pages, extract_metrics, generate_summary, extract_legal_content, identify_legal_pages
from data_processor import build_dataframe
from excel_exporter import to_excel_bytes
from config import MAX_SCAN_PAGES, SCAN_ZOOM, DETAIL_ZOOM, LEGAL_SCAN_ZOOM, LEGAL_DETAIL_ZOOM, LEGAL_SCAN_PAGES

load_dotenv()

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Singapore Bank Peer Comparison",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ── Login ────────────────────────────────────────────────────────────────────
_APP_USER = os.getenv("APP_USERNAME", "")
_APP_PASS = os.getenv("APP_PASSWORD", "")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>🤖 LEAD28 Transformers — Capstone Project</h1>", unsafe_allow_html=True)
    st.markdown("---")
    col_l, col_m, col_r = st.columns([1, 1, 1])
    with col_m:
        st.subheader("Login")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", use_container_width=True):
                if username == _APP_USER and password == _APP_PASS:
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
    st.stop()

st.markdown("<h2 style='text-align: center;'>🤖 LEAD28 Transformers — Capstone Project</h2>", unsafe_allow_html=True)

# ── Default values ───────────────────────────────────────────────────────────
DEFAULTS = {
    "DBS":  "https://www.dbs.com/iwov-resources/images/investors/quarterly-financials/2025/4Q25_CFO_presentation.pdf",
    "OCBC": "https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/investors/quarterly-results/2025/ocbc%20fy25%20results%20presentation.pdf",
    "UOB":  "https://www.uobgroup.com/investor-relations/assets/pdfs/investor/financial/2025/condensed-financial-statements-4q-2025.pdf",
}

api_key_input = os.getenv("DASHSCOPE_API_KEY", "")

# ── Session state ────────────────────────────────────────────────────────────
if "processing" not in st.session_state:
    st.session_state.processing = False

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "**📄 Auto Legal Document Extraction**\n"
        "1. Confirm or edit the legal document PDF URL\n"
        "2. Click **Extract**\n"
        "3. View the structured clauses from the MULTICURRENCY – CROSS BORDER section\n"
    )
    st.markdown("---")
    st.markdown(
        "**🏦 Singapore Bank Peer Comparison**\n"
        "1. Confirm or edit the bank PDF URLs\n"
        "2. Click **Compare Banks**\n"
        "3. Download the styled Excel report"
    )
    st.markdown("---")
    if st.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# ── Per-bank pipeline (no Streamlit calls — safe to run in threads) ──────────
def _process_bank(name: str, url: str, api_key: str) -> dict:
    """
    Full pipeline for one bank. Returns a result dict with keys:
      name, metrics, pages, error
    """
    try:
        pdf_bytes = download_pdf_bytes(url)
    except Exception as e:
        return {"name": name, "error": f"Could not download PDF: {e}"}

    total = page_count(pdf_bytes)
    scan_count = min(total, MAX_SCAN_PAGES)

    overview_images = render_pages(pdf_bytes, list(range(scan_count)), zoom=SCAN_ZOOM)

    try:
        relevant_indices = identify_relevant_pages(overview_images, api_key)
    except Exception as e:
        return {"name": name, "error": f"Page scan failed: {e}"}

    if name.upper() == "DBS" and 1 not in relevant_indices:
        relevant_indices = sorted(set(relevant_indices) | {1})

    detail_images = render_pages(pdf_bytes, relevant_indices, zoom=DETAIL_ZOOM)

    try:
        metrics = extract_metrics(detail_images, name, api_key)
    except Exception as e:
        return {"name": name, "error": f"Metric extraction failed: {e}"}

    return {"name": name, "metrics": metrics, "pages": relevant_indices, "error": None}


@st.cache_data(ttl=86400, show_spinner=False)   # cache for 24 hours, keyed by url
def _cached_process_bank(name: str, url: str, api_key: str) -> dict:
    return _process_bank(name, url, api_key)


# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📄 Auto Legal Document Extraction", "🏦 Singapore Bank Peer Comparison"])

# ── Tab 1: Auto Legal Document Extraction ────────────────────────────────────
with tab1:
    st.subheader("Auto Legal Document Extraction")
    st.markdown("##### MULTICURRENCY – CROSS BORDER Extraction")
    st.caption("Extracts the **MULTICURRENCY – CROSS BORDER** section of an ISDA Master Agreement.")

    legal_url = st.text_input(
        "Legal Document PDF URL",
        value="https://www.santander.co.uk/assets/s3fs-public/documents/isda_master_agreement_24_may_2019.pdf",
    )

    if st.button("Extract", type="primary", use_container_width=True):
        if not legal_url.strip():
            st.error("Please provide a PDF URL.")
        else:
            api_key = api_key_input.strip()
            if not api_key:
                st.error("Dashscope API key not found. Please set DASHSCOPE_API_KEY in your .env file.")
                st.stop()

            # ── Step 1: Download & identify relevant pages ───────────────────
            st.markdown("**Step 1 — Identifying relevant pages**")
            with st.spinner("Downloading PDF..."):
                try:
                    legal_pdf_bytes = download_pdf_bytes(legal_url.strip())
                except Exception as e:
                    st.error(f"Could not download PDF: {e}")
                    st.stop()

            legal_page_indices = [20, 21]  # pages 21 & 22 (0-based)
            page_labels = ", ".join(str(p + 1) for p in legal_page_indices)
            st.success(f"Relevant pages: {page_labels}")

            # ── Step 2: High-res extraction ──────────────────────────────────
            st.markdown("**Step 2 — Extracting key clauses**")
            with st.spinner("Rendering pages at high resolution..."):
                detail_images = render_pages(legal_pdf_bytes, legal_page_indices, zoom=LEGAL_DETAIL_ZOOM)

            with st.spinner("Extracting structured content..."):
                try:
                    legal_result = extract_legal_content(detail_images, api_key)
                except Exception as e:
                    st.error(f"Extraction failed: {e}")
                    st.stop()

            # ── Results ──────────────────────────────────────────────────────
            st.markdown("---")
            st.subheader("MULTICURRENCY – CROSS BORDER")

            if "error" in legal_result:
                st.warning("Could not parse structured output. Raw response:")
                st.text(legal_result.get("raw", ""))
            else:
                if legal_result.get("section_title"):
                    st.caption(legal_result["section_title"])

                if legal_result.get("parties"):
                    st.markdown("**Parties**")
                    parties = legal_result["parties"]
                    col_a, col_b = st.columns(2)
                    col_a.metric("Party A", parties.get("party_a") or "—")
                    col_b.metric("Party B", parties.get("party_b") or "—")
                    st.metric("Security Trustee", parties.get("security_trustee") or "—")

                if legal_result.get("provisions"):
                    st.markdown("**Provisions**")
                    for p in legal_result["provisions"]:
                        content = p.get("content", "")
                        paragraphs = [para.strip() for para in content.split("\n") if para.strip()]
                        # Use clause field; fall back to first line of content
                        clause_name = p.get("clause") or (paragraphs[0] if paragraphs else "Clause")
                        body = paragraphs[1:] if not p.get("clause") and paragraphs else paragraphs
                        with st.expander(clause_name):
                            st.markdown("\n\n".join(body))

                if legal_result.get("elections"):
                    st.markdown("**Elections**")
                    elections_data = {
                        e.get("item", ""): e.get("value", "") for e in legal_result["elections"]
                    }
                    st.table(elections_data)

                if legal_result.get("other"):
                    st.markdown("**Other**")
                    other = legal_result["other"]
                    paragraphs = [para.strip() for para in other.split("\n") if para.strip()]
                    st.markdown("\n\n".join(paragraphs))

# ── Tab 2: Singapore Bank Peer Comparison ────────────────────────────────────
with tab2:
    st.subheader("Singapore Bank Peer Comparison")
    st.caption("FY2025 Financial Results")

    # ── Bank URL inputs ──────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        bank1_name = st.text_input("Bank 1 Name", value="DBS")
        bank1_url  = st.text_input("Bank 1 PDF URL", value=DEFAULTS["DBS"])

    with col2:
        bank2_name = st.text_input("Bank 2 Name", value="OCBC")
        bank2_url  = st.text_input("Bank 2 PDF URL", value=DEFAULTS["OCBC"])

    with col3:
        bank3_name = st.text_input("Bank 3 Name", value="UOB")
        bank3_url  = st.text_input("Bank 3 PDF URL", value=DEFAULTS["UOB"])

    # ── Compare button ───────────────────────────────────────────────────────
    if st.button("Compare Banks", type="primary", use_container_width=True,
                 disabled=st.session_state.processing):
        api_key = api_key_input.strip()
        if not api_key:
            st.error("Dashscope API key not found. Please set DASHSCOPE_API_KEY in your .env file.")
            st.stop()

        banks = [
            (bank1_name.strip() or "Bank 1", bank1_url.strip()),
            (bank2_name.strip() or "Bank 2", bank2_url.strip()),
            (bank3_name.strip() or "Bank 3", bank3_url.strip()),
        ]
        banks = [(name, url) for name, url in banks if url]

        if not banks:
            st.error("Please provide at least one PDF URL.")
            st.stop()

        st.session_state.processing        = True
        st.session_state.pending_banks     = banks
        st.session_state.pending_api_key   = api_key
        st.rerun()

    if st.session_state.processing:
        banks   = st.session_state.pending_banks
        api_key = st.session_state.pending_api_key

        # ── Run all banks in parallel ────────────────────────────────────────
        progress = st.progress(0, text=f"Processing {len(banks)} banks in parallel...")
        completed = 0
        bank_results = {}
        errors = {}

        with ThreadPoolExecutor(max_workers=len(banks)) as executor:
            futures = {
                executor.submit(_cached_process_bank, name, url, api_key): name
                for name, url in banks
            }
            for future in as_completed(futures):
                result = future.result()
                name = result["name"]
                completed += 1
                progress.progress(
                    completed / len(banks),
                    text=f"Done: {name} ({completed}/{len(banks)})",
                )
                if result["error"]:
                    errors[name] = result["error"]
                else:
                    bank_results[name] = result

        progress.empty()

        if not bank_results:
            st.session_state.processing = False
            st.error("No data could be extracted. Check the URLs and your API key.")
            st.rerun()

        metrics_by_bank = {name: r["metrics"] for name, r in bank_results.items()}
        df = build_dataframe(metrics_by_bank)

        with st.spinner("Generating summary..."):
            try:
                summary_df = df[~(df == "N/A").all(axis=1)]
                bullets = generate_summary(summary_df, api_key)
            except Exception as e:
                st.warning(f"Could not generate summary: {e}")
                bullets = []

        st.session_state.errors      = errors
        st.session_state.page_info   = {n: r["pages"] for n, r in bank_results.items()}
        st.session_state.result_df   = df
        st.session_state.bullets     = bullets
        st.session_state.excel_bytes = to_excel_bytes(df, bullets)
        st.session_state.processing  = False
        st.rerun()

    # ── Display results (persisted in session state) ─────────────────────────
    if "result_df" in st.session_state:
        for name, msg in st.session_state.errors.items():
            st.error(f"{name}: {msg}")

        for name, pages in st.session_state.page_info.items():
            page_labels = ", ".join(str(p + 1) for p in pages)
            st.info(f"{name} — relevant pages: {page_labels} ({len(pages)} pages)")

        st.markdown("---")
        st.subheader("Peer Comparison Table")
        display_df = st.session_state.result_df
        display_df = display_df[~(display_df == "N/A").all(axis=1)]
        st.dataframe(display_df, use_container_width=True)

        if st.session_state.bullets:
            st.subheader("Key Takeaways")
            for bullet in st.session_state.bullets:
                st.markdown(f"- {bullet}")

        st.download_button(
            label="Download Excel",
            data=st.session_state.excel_bytes,
            file_name="bank_comparison_fy2025.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
