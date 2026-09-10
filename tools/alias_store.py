"""
Persists the alias cache (raw attribute name -> canonical business term)
in BigQuery instead of an in-memory dict.

Why this matters: the in-memory version reset on every server restart
and wouldn't be shared across multiple deployed instances. This makes
every instance query the same single source of truth, so an approval
made once is visible everywhere, permanently, until explicitly revoked.
"""

from google.cloud import bigquery
import config

ALIAS_TABLE = "learned_aliases"
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = bigquery.Client(project=config.PROJECT_ID)
    return _client


def ensure_alias_table_exists():
    client = _get_client()
    dataset_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}"

    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = config.LOCATION
    client.create_dataset(dataset, exists_ok=True)

    table_ref = f"{dataset_ref}.{ALIAS_TABLE}"
    schema = [
        bigquery.SchemaField("raw_name", "STRING"),      # lowercased raw attribute name, primary lookup key
        bigquery.SchemaField("canonical_term", "STRING"),
    ]
    table = bigquery.Table(table_ref, schema=schema)
    client.create_table(table, exists_ok=True)


def get_alias(raw_attribute_name: str) -> str | None:
    """Fast point lookup — the exact-match fast path in the matching pipeline."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{ALIAS_TABLE}"
    key = raw_attribute_name.strip().lower()

    query = f"""
        SELECT canonical_term FROM `{table_ref}`
        WHERE raw_name = @raw_name
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("raw_name", "STRING", key)]
    )
    try:
        rows = list(client.query(query, job_config=job_config).result())
        return rows[0].canonical_term if rows else None
    except Exception:
        return None  # table may not exist yet on first-ever run


def register_alias(raw_attribute_name: str, canonical_term: str):
    """Insert or update the alias mapping. BigQuery has no native UPSERT
    via the streaming insert API, so delete-then-insert keeps it simple."""
    unregister_alias(raw_attribute_name)  # remove any existing mapping first
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{ALIAS_TABLE}"
    key = raw_attribute_name.strip().lower()

    errors = client.insert_rows_json(table_ref, [{"raw_name": key, "canonical_term": canonical_term}])
    if errors:
        raise RuntimeError(f"Failed to register alias: {errors}")


def unregister_alias(raw_attribute_name: str):
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{ALIAS_TABLE}"
    key = raw_attribute_name.strip().lower()

    query = f"DELETE FROM `{table_ref}` WHERE raw_name = @raw_name"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("raw_name", "STRING", key)]
    )
    try:
        client.query(query, job_config=job_config).result()
    except Exception:
        pass  # table/row may not exist yet — fine, nothing to delete


def list_aliases() -> list[dict]:
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{ALIAS_TABLE}"
    try:
        rows = client.query(f"SELECT raw_name, canonical_term FROM `{table_ref}`").result()
        return [{"raw_name": r.raw_name, "canonical_term": r.canonical_term} for r in rows]
    except Exception:
        return []
