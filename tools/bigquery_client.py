"""
Generates and executes the physical model layer for a new data product:
takes approved attributes and their inferred types, builds a BigQuery
CREATE TABLE statement, and runs it — turning approved metadata into
an actual queryable table, not just a catalog entry.
"""

from google.cloud import bigquery
import re
import config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = bigquery.Client(project=config.PROJECT_ID)
    return _client


# Maps pandas dtypes (from tools/file_parser.py) to BigQuery column types.
_TYPE_MAP = {
    "int64": "INT64",
    "float64": "FLOAT64",
    "bool": "BOOL",
    "datetime64[ns]": "TIMESTAMP",
    "object": "STRING",  # pandas' default for text/mixed columns
}


def _bq_type(pandas_dtype: str) -> str:
    return _TYPE_MAP.get(pandas_dtype, "STRING")


def _sanitize_identifier(name: str) -> str:
    """BigQuery column/table names: letters, numbers, underscores only."""
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    if clean and clean[0].isdigit():
        clean = f"_{clean}"
    return clean or "unnamed_column"


def build_create_table_ddl(table_name: str, attributes: list[dict], dataset: str = None) -> str:
    """
    attributes: list of {name, inferred_type} — same shape produced by
    tools/file_parser.py.
    Returns the DDL string (also executed by create_physical_table).
    """
    dataset = dataset or config.CURATED_DATASET
    full_table = f"`{config.PROJECT_ID}.{dataset}.{_sanitize_identifier(table_name)}`"

    columns = []
    for attr in attributes:
        col_name = _sanitize_identifier(attr["name"])
        col_type = _bq_type(attr.get("inferred_type", "object"))
        columns.append(f"  {col_name} {col_type}")

    columns_sql = ",\n".join(columns)
    return f"CREATE TABLE IF NOT EXISTS {full_table} (\n{columns_sql}\n)"


def create_physical_table(product_name: str, attributes: list[dict], dataset: str = None) -> dict:
    """
    Builds and executes the CREATE TABLE statement for a new data product.
    Returns the DDL used, the full table name, and execution status.
    """
    dataset = dataset or config.CURATED_DATASET
    ddl = build_create_table_ddl(product_name, attributes, dataset)
    full_table_name = f"{config.PROJECT_ID}.{dataset}.{_sanitize_identifier(product_name)}"

    client = _get_client()
    try:
        client.query(ddl).result()
    except Exception as e:
        return {"status": "error", "message": str(e), "ddl": ddl}

    return {
        "status": "success",
        "table_full_name": full_table_name,
        "ddl": ddl,
    }
