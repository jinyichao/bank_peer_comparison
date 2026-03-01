import os
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

from pdf_extractor import download_pdf_bytes, render_pages, page_count
from ai_parser import identify_relevant_pages, extract_metrics, generate_summary
from data_processor import build_dataframe
from excel_exporter import to_excel_bytes
from config import MAX_SCAN_PAGES, SCAN_ZOOM, DETAIL_ZOOM

load_dotenv()

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Singapore Bank Peer Comparison",
    page_icon="🏦",
    layout="wide",
)

st.title("🏦 Singapore Bank Peer Comparison")
st.caption("FY2025 Financial Results")

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
        "**Instructions**\n"
        "1. Confirm or edit the bank PDF URLs\n"
        "2. Click **Compare Banks**\n"
        "3. Download the styled Excel report"
    )

# ── Bank URL inputs ──────────────────────────────────────────────────────────
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

    detail_images = render_pages(pdf_bytes, relevant_indices, zoom=DETAIL_ZOOM)

    try:
        metrics = extract_metrics(detail_images, name, api_key)
    except Exception as e:
        return {"name": name, "error": f"Metric extraction failed: {e}"}

    return {"name": name, "metrics": metrics, "pages": relevant_indices, "error": None}


# ── Compare button ───────────────────────────────────────────────────────────
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

    # Store inputs in session state and rerun to render the disabled button
    st.session_state.processing = True
    st.session_state.pending_banks = banks
    st.session_state.pending_api_key = api_key
    st.rerun()

if st.session_state.processing:
    banks   = st.session_state.pending_banks
    api_key = st.session_state.pending_api_key

    # ── Run all banks in parallel ────────────────────────────────────────────
    progress = st.progress(0, text=f"Processing {len(banks)} banks in parallel...")
    completed = 0
    bank_results = {}
    errors = {}

    with ThreadPoolExecutor(max_workers=len(banks)) as executor:
        futures = {
            executor.submit(_process_bank, name, url, api_key): name
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

    # Show any per-bank errors
    for name, msg in errors.items():
        st.error(f"{name}: {msg}")

    # Show which pages were selected for each bank
    for name, result in bank_results.items():
        page_labels = ", ".join(str(p + 1) for p in result["pages"])
        st.info(f"{name} — relevant pages: {page_labels} ({len(result['pages'])} pages)")

    if not bank_results:
        st.error("No data could be extracted. Check the URLs and your API key.")
        st.stop()

    # ── Build and display table ──────────────────────────────────────────────
    metrics_by_bank = {name: r["metrics"] for name, r in bank_results.items()}
    df = build_dataframe(metrics_by_bank)

    st.markdown("---")
    st.subheader("Peer Comparison Table")
    st.dataframe(df, use_container_width=True)

    # ── AI summary ───────────────────────────────────────────────────────────
    with st.spinner("Generating summary..."):
        try:
            bullets = generate_summary(df, api_key)
        except Exception as e:
            st.warning(f"Could not generate summary: {e}")
            bullets = []

    if bullets:
        st.subheader("Key Takeaways")
        for bullet in bullets:
            st.markdown(f"- {bullet}")

    # ── Excel download ───────────────────────────────────────────────────────
    excel_bytes = to_excel_bytes(df, bullets)
    st.download_button(
        label="Download Excel",
        data=excel_bytes,
        file_name="bank_comparison_fy2025.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    # Re-enable the button now that processing is complete
    st.session_state.processing = False
