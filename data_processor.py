import pandas as pd
from config import METRICS


def build_dataframe(results: dict) -> pd.DataFrame:
    """
    results: {"DBS": {metric_key: value}, "OCBC": {...}, "UOB": {...}}
    Returns a DataFrame with metric labels as index and bank names as columns.
    """
    bank_names = list(results.keys())

    index_labels = [f"{m['label']} ({m['unit']})" for m in METRICS]

    rows = []
    for metric in METRICS:
        key = metric["key"]
        row = []
        for bank in bank_names:
            value = results[bank].get(key)
            if value is None:
                row.append("N/A")
            else:
                row.append(value)
        rows.append(row)

    df = pd.DataFrame(rows, index=index_labels, columns=bank_names)
    return df
