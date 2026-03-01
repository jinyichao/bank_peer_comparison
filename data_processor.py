import pandas as pd
from config import METRICS


def _fmt(value, unit: str) -> str:
    """Format a numeric value for display, or return 'N/A'."""
    if value is None:
        return "N/A"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "N/A"

    if unit == "SGD bn":
        return f"{v:.1f}"
    elif unit == "SGD m":
        return f"{v:,.0f}"
    elif unit == "%":
        return f"{v:.2f}"
    elif unit == "cents":
        return f"{v:.1f}"
    return str(value)


def build_dataframe(results: dict) -> pd.DataFrame:
    """
    results: {"DBS": {metric_key: value}, "OCBC": {...}, "UOB": {...}}
    Returns a fully string-typed DataFrame (Arrow-compatible) with formatted
    values and metric labels as the index.
    """
    bank_names = list(results.keys())
    index_labels = [f"{m['label']} ({m['unit']})" for m in METRICS]

    rows = []
    for metric in METRICS:
        key = metric["key"]
        row = [_fmt(results[bank].get(key), metric["unit"]) for bank in bank_names]
        rows.append(row)

    df = pd.DataFrame(rows, index=index_labels, columns=bank_names, dtype=str)
    return df
