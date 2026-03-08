METRICS = [
    {"key": "net_interest_income",   "label": "Net Interest Income",                  "unit": "SGD m",  "is_ratio": False},
    {"key": "non_interest_income",   "label": "Non-Interest Income",                  "unit": "SGD m",  "is_ratio": False},
    {"key": "total_income",          "label": "Total Income",                          "unit": "SGD m",  "is_ratio": False},
    {"key": "operating_expenses",    "label": "Operating Expenses",                   "unit": "SGD m",  "is_ratio": False},
    {"key": "cost_to_income_ratio",  "label": "Cost-to-Income Ratio",                 "unit": "%",      "is_ratio": True},
    {"key": "total_allowances",      "label": "Total Allowances / Provisions",        "unit": "SGD m",  "is_ratio": False},
    {"key": "net_profit",            "label": "Net Profit (attr. to equity holders)", "unit": "SGD m",  "is_ratio": False},
    {"key": "nim",                   "label": "Net Interest Margin (NIM)",             "unit": "%",      "is_ratio": True},
    {"key": "roe",                   "label": "Return on Equity (ROE)",               "unit": "%",      "is_ratio": True},
    {"key": "roa",                   "label": "Return on Assets (ROA)",               "unit": "%",      "is_ratio": True},
    {"key": "eps_basic",             "label": "Earnings Per Share – Basic",           "unit": "cents",  "is_ratio": False},
    {"key": "cet1_ratio",            "label": "CET1 Capital Ratio",                   "unit": "%",      "is_ratio": True},
    {"key": "total_car",             "label": "Total Capital Adequacy Ratio",         "unit": "%",      "is_ratio": True},
    {"key": "npl_ratio",             "label": "Non-Performing Loan (NPL) Ratio",      "unit": "%",      "is_ratio": True},
    {"key": "loan_to_deposit_ratio", "label": "Loan-to-Deposit Ratio",               "unit": "%",      "is_ratio": True},
    {"key": "total_assets",          "label": "Total Assets",                          "unit": "SGD bn", "is_ratio": False},
    {"key": "total_loans",           "label": "Total Customer Loans",                 "unit": "SGD bn", "is_ratio": False},
    {"key": "customer_deposits",     "label": "Customer Deposits",                    "unit": "SGD bn", "is_ratio": False},
    {"key": "dividends_per_share",   "label": "Dividends Per Share",                  "unit": "cents",  "is_ratio": False},
]

# Qwen vision model via Alibaba Cloud Dashscope
# For users outside mainland China (e.g. Singapore), use the intl endpoint:
#   DASHSCOPE_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL_SCAN = "qwen3.5-flash"   # Pass 1: fast page identification
QWEN_MODEL = "qwen3.5-plus-2026-02-15"  # Pass 2: accurate metric extraction
DASHSCOPE_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# Pass 1 — page scan
MAX_SCAN_PAGES = 60     # Maximum pages to include in the overview scan
SCAN_ZOOM = 0.5         # Low-res thumbnails; small enough to keep the request fast
SCAN_BATCH_SIZE = 15    # Pages per parallel batch (4 concurrent calls for 60 pages)

# Pass 2 — metric extraction
DETAIL_ZOOM = 1.5       # High-res re-render of selected pages only
MAX_DETAIL_PAGES = 15   # Safety cap in case pass 1 selects too many pages

METRIC_KEYS = [m["key"] for m in METRICS]

# ── Legal document extraction ─────────────────────────────────────────────────
LEGAL_SCAN_ZOOM    = 0.5   # Low-res thumbnails for page scan
LEGAL_DETAIL_ZOOM  = 2.0   # High-res render for extraction
LEGAL_SCAN_PAGES   = 60    # Max pages to scan
LEGAL_SCAN_BATCH   = 15    # Pages per batch

# ── Pass 1 prompt — find relevant pages ───────────────────────────────────────
LEGAL_SCAN_PROMPT = """You are reviewing a legal document.

Each page is labelled [Page N] above its image.

Identify every page that contains the "MULTICURRENCY – CROSS BORDER" section heading or its clauses and provisions.

Return ONLY a JSON array of the relevant page numbers (integers), e.g. [21, 22].
No prose, no explanation — only the JSON array."""

# ── Pass 2 prompt — structured extraction ─────────────────────────────────────
LEGAL_SYSTEM_PROMPT = """You are a legal document analyst specialising in financial contracts and ISDA agreements.

You will receive high-resolution images of the pages containing the MULTICURRENCY – CROSS BORDER section. Extract and structure all content from that section.

Return your output as a valid JSON object with the following structure:
{
  "section_title": "the exact section heading as it appears",
  "parties": {"party_a": "...", "party_b": "...", "security_trustee": "..."},
  "provisions": [
    {"clause": "clause number or heading exactly as written in the document (e.g. '1. Specified Entity', 'Part 1')", "content": "full clause text"}
  ],
  "elections": [
    {"item": "election name", "value": "elected value or N/A"}
  ],
  "other": "any other relevant content not captured above"
}

Rules:
- Extract ALL text from the MULTICURRENCY – CROSS BORDER section faithfully
- Preserve clause numbers and structure
- If a field cannot be found, use null
- Return ONLY the JSON object — no prose, no markdown fences"""

LEGAL_USER_PROMPT = "Extract all content from the MULTICURRENCY – CROSS BORDER section on these pages."

# ── Pass 1 prompt ─────────────────────────────────────────────────────────────
PAGE_SCAN_PROMPT = """You are reviewing a Singapore bank financial report.

Each page is labelled [Page N] above its image.

Identify every page that contains a summary table with key financial metrics such as:
Net Interest Income, Non-Interest Income, Total Income, Operating Expenses,
Cost-to-Income Ratio, Net Profit, NIM, ROE, ROA, EPS, CET1, Capital Adequacy,
NPL Ratio, Loan-to-Deposit Ratio, Total Assets, Loans, Deposits, Dividends.

Exclude cover pages, table of contents, purely narrative text pages, and pages with only charts and no tables.

Return ONLY a JSON array of the relevant page numbers (integers), e.g. [3, 5, 12].
No prose, no explanation — only the JSON array."""

# ── Pass 2 prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a financial data extraction specialist for Singapore bank annual reports and financial statements.

You will receive high-resolution images of the key financial summary pages from a bank report. Extract specific financial metrics and return them as a strict JSON object.

Rules:
- Return ONLY a valid JSON object with exactly these keys: net_interest_income, non_interest_income, total_income, operating_expenses, cost_to_income_ratio, total_allowances, net_profit, nim, roe, roa, eps_basic, cet1_ratio, total_car, npl_ratio, loan_to_deposit_ratio, total_assets, total_loans, customer_deposits, dividends_per_share
- All monetary values in SGD millions (m) unless labelled as billions (bn) — for total_assets, total_loans, customer_deposits return values in SGD billions
- All ratio/percentage values as plain numbers (e.g. 14.5 for 14.5%)
- Use full-year (FY) figures, not quarterly, whenever both are present
- If a metric cannot be found, return null for that key
- Do not include any prose, markdown, or explanation — only the JSON object"""

USER_PROMPT = "Extract all financial metrics from these pages."

# ── Summary prompt ────────────────────────────────────────────────────────────
SUMMARY_PROMPT = """You are a financial analyst specialising in Singapore banks.

Below is a peer comparison table of key financial metrics for FY2025.

{table}

Write 4–5 concise bullet points summarising the most notable findings and differences across the banks. Focus on relative performance — who leads on profitability, efficiency, capital strength, asset quality, and balance sheet size. Be specific with numbers where relevant.

Return each bullet on its own line starting with a dash (-). No headers, no prose, just the bullets."""
