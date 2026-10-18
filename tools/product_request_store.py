"""
Store and manage Data Product requests.
When a user wants to create a data product, it is logged here as a request
with requester details and business justification.
The Platform Owner reviews and approves the request before physical tables
are provisioned in BigQuery.
"""

from google.cloud import bigquery
import datetime
import json
import uuid
import config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = bigquery.Client(project=config.PROJECT_ID)
    return _client


def ensure_requests_table_exists():
    """Creates the requests dataset/table on startup if it doesn't exist."""
    client = _get_client()
    dataset_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}"

    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = config.LOCATION
    client.create_dataset(dataset, exists_ok=True)

    table_ref = f"{dataset_ref}.{config.REQUESTS_TABLE}"
    schema = [
        bigquery.SchemaField("request_id", "STRING"),
        bigquery.SchemaField("product_name", "STRING"),
        bigquery.SchemaField("domain", "STRING"),
        bigquery.SchemaField("requested_by", "STRING"),
        bigquery.SchemaField("business_justification", "STRING"),
        bigquery.SchemaField("attributes_json", "STRING"),  # JSON serialized list of attributes
        bigquery.SchemaField("status", "STRING"),          # PENDING, APPROVED, REJECTED
        bigquery.SchemaField("reviewer_notes", "STRING"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
        bigquery.SchemaField("table_full_name", "STRING"),
    ]
    table = bigquery.Table(table_ref, schema=schema)
    client.create_table(table, exists_ok=True)


def submit_product_request(
    product_name: str,
    domain: str,
    requested_by: str,
    business_justification: str,
    attributes: list[dict],
) -> dict:
    """Submits a new data product creation request for Platform Owner review."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.REQUESTS_TABLE}"
    request_id = str(uuid.uuid4())[:8]
    now = datetime.datetime.utcnow().isoformat()

    row = {
        "request_id": request_id,
        "product_name": product_name.strip(),
        "domain": domain.strip(),
        "requested_by": requested_by.strip(),
        "business_justification": business_justification.strip(),
        "attributes_json": json.dumps(attributes),
        "status": "PENDING",
        "reviewer_notes": "",
        "created_at": now,
        "updated_at": now,
        "table_full_name": "",
    }

    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"Failed to record data product request: {errors}")

    return {
        "request_id": request_id,
        "status": "PENDING",
        "product_name": product_name,
        "domain": domain,
        "requested_by": requested_by,
        "business_justification": business_justification,
        "attributes_count": len(attributes),
        "created_at": now,
    }


def list_product_requests(status_filter: str = None) -> list[dict]:
    """Lists submitted data product requests."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.REQUESTS_TABLE}"

    query = f"SELECT * FROM `{table_ref}`"
    if status_filter:
        query += f" WHERE status = '{status_filter.upper()}'"
    query += " ORDER BY created_at DESC LIMIT 50"

    try:
        rows = list(client.query(query).result())
        result = []
        for r in rows:
            item = dict(r)
            try:
                item["attributes"] = json.loads(item.get("attributes_json") or "[]")
            except Exception:
                item["attributes"] = []
            if item.get("created_at"):
                item["created_at"] = str(item["created_at"])
            if item.get("updated_at"):
                item["updated_at"] = str(item["updated_at"])
            result.append(item)
        return result
    except Exception as e:
        print(f"Error querying requests table: {e}")
        return []


def get_product_request(request_id: str) -> dict | None:
    """Fetch single request by ID."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.REQUESTS_TABLE}"
    query = f"SELECT * FROM `{table_ref}` WHERE request_id = @request_id LIMIT 1"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("request_id", "STRING", request_id)]
    )
    try:
        rows = list(client.query(query, job_config=job_config).result())
        if not rows:
            return None
        item = dict(rows[0])
        try:
            item["attributes"] = json.loads(item.get("attributes_json") or "[]")
        except Exception:
            item["attributes"] = []
        if item.get("created_at"):
            item["created_at"] = str(item["created_at"])
        if item.get("updated_at"):
            item["updated_at"] = str(item["updated_at"])
        return item
    except Exception:
        return None


def update_product_request_status(
    request_id: str,
    status: str,
    reviewer_notes: str = "",
    table_full_name: str = "",
):
    """Update the status of a request (APPROVED / REJECTED)."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.REQUESTS_TABLE}"
    now = datetime.datetime.utcnow().isoformat()

    query = f"""
        UPDATE `{table_ref}`
        SET status = @status,
            reviewer_notes = @reviewer_notes,
            table_full_name = @table_full_name,
            updated_at = TIMESTAMP(@now)
        WHERE request_id = @request_id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("status", "STRING", status),
            bigquery.ScalarQueryParameter("reviewer_notes", "STRING", reviewer_notes),
            bigquery.ScalarQueryParameter("table_full_name", "STRING", table_full_name),
            bigquery.ScalarQueryParameter("now", "STRING", now),
            bigquery.ScalarQueryParameter("request_id", "STRING", request_id),
        ]
    )
    client.query(query, job_config=job_config).result()


def delete_product_request(request_id: str) -> bool:
    """Delete an individual product request by its request_id."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.REQUESTS_TABLE}"
    query = f"DELETE FROM `{table_ref}` WHERE request_id = @request_id"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("request_id", "STRING", request_id)]
    )
    job = client.query(query, job_config=job_config)
    job.result()
    return True


def clear_all_product_requests() -> bool:
    """Delete all product requests from the log table."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.REQUESTS_TABLE}"
    query = f"DELETE FROM `{table_ref}` WHERE 1=1"
    job = client.query(query)
    job.result()
    return True
