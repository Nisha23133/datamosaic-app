"""
Logs every AI recommendation and the user's approve/reject/correction
action to BigQuery. This log is what future-you retrieves as few-shot
examples to improve recommendations over time (see semantic_agent.py).
"""

from google.cloud import bigquery
import datetime
import config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = bigquery.Client(project=config.PROJECT_ID)
    return _client


def ensure_feedback_table_exists():
    """Creates the feedback dataset/table on first run if they don't exist."""
    client = _get_client()
    dataset_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}"

    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = config.LOCATION
    client.create_dataset(dataset, exists_ok=True)

    table_ref = f"{dataset_ref}.{config.FEEDBACK_TABLE}"
    schema = [
        bigquery.SchemaField("attribute_name", "STRING"),
        bigquery.SchemaField("sample_values", "STRING"),  # stored as JSON string
        bigquery.SchemaField("suggested_glossary_term", "STRING"),
        bigquery.SchemaField("suggested_domain", "STRING"),
        bigquery.SchemaField("suggested_subdomain", "STRING"),
        bigquery.SchemaField("suggested_source_application", "STRING"),
        bigquery.SchemaField("confidence_score", "FLOAT"),
        bigquery.SchemaField("user_action", "STRING"),       # approved / rejected / corrected
        bigquery.SchemaField("corrected_value", "STRING"),   # only set if corrected
        bigquery.SchemaField("timestamp", "TIMESTAMP"),
    ]
    table = bigquery.Table(table_ref, schema=schema)
    client.create_table(table, exists_ok=True)


def log_feedback(
    attribute_name: str,
    sample_values: list,
    suggested_glossary_term: str,
    suggested_domain: str,
    suggested_subdomain: str,
    suggested_source_application: str,
    confidence_score: float,
    user_action: str,
    corrected_value: str = "",
):
    """Insert one feedback row. Call ensure_feedback_table_exists() once at startup."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.FEEDBACK_TABLE}"

    row = {
        "attribute_name": attribute_name,
        "sample_values": str(sample_values),
        "suggested_glossary_term": suggested_glossary_term,
        "suggested_domain": suggested_domain,
        "suggested_subdomain": suggested_subdomain,
        "suggested_source_application": suggested_source_application,
        "confidence_score": confidence_score,
        "user_action": user_action,
        "corrected_value": corrected_value,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }

    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"Failed to log feedback: {errors}")


def get_similar_past_feedback(attribute_name: str, limit: int = 5) -> list[dict]:
    """
    Retrieve past corrected/approved examples for similar attribute names,
    used as few-shot context in recommendation_agent.py.
    Simple LIKE-based retrieval for the demo; swap for embedding-based
    retrieval once feedback volume justifies it.
    """
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.FEEDBACK_TABLE}"

    query = f"""
        SELECT attribute_name, suggested_glossary_term, suggested_domain,
               suggested_subdomain, suggested_source_application,
               user_action, corrected_value
        FROM `{table_ref}`
        WHERE user_action IN ('approved', 'corrected')
        ORDER BY timestamp DESC
        LIMIT {limit}
    """
    try:
        return [dict(row) for row in client.query(query).result()]
    except Exception:
        return []  # table may not exist yet on first run
