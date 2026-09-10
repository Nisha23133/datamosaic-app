"""
Parses an uploaded file (CSV, JSON, or XLSX) into a list of attributes,
each with a name, inferred type, and sample values — the raw input the
matching/recommendation pipeline works from.
"""

import json
import pandas as pd
from pathlib import Path


def parse_uploaded_file(file_path: str, sample_size: int = 5) -> list[dict]:
    """
    Returns: [{name, inferred_type, sample_values, null_pct, cardinality}, ...]
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(file_path)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    elif suffix == ".json":
        with open(file_path) as f:
            data = json.load(f)
        # Support both a list-of-records JSON and a single-object JSON
        df = pd.json_normalize(data if isinstance(data, list) else [data])
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    attributes = []
    total_rows = len(df)

    for col in df.columns:
        series = df[col]
        non_null = series.dropna()
        sample_values = non_null.head(sample_size).tolist()

        attributes.append({
            "name": col,
            "inferred_type": str(series.dtype),
            "sample_values": sample_values,
            "null_pct": round((total_rows - len(non_null)) / total_rows * 100, 1) if total_rows else 0,
            "cardinality": int(non_null.nunique()),
            "row_count": total_rows,
        })

    return attributes
