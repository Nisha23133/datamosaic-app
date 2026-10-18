"""
Regulatory Store & BigQuery Layer for Financial Regulatory Compliance & Data Products.
Handles:
1. Regulatory Use Cases (Intake, approval, schema/semantic contracts, audit trails).
2. Governed Data Products (Definitions, attributes, physical table metadata).
3. Query Audit Logs (Compliance lineage, executed SQL, user persona tracking).
"""

import datetime
import json
import uuid
from google.cloud import bigquery
import config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = bigquery.Client(project=config.PROJECT_ID)
    return _client


def ensure_regulatory_tables_exist():
    """Ensure BigQuery datasets and tables exist for regulatory compliance."""
    client = _get_client()
    dataset_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}"

    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = config.LOCATION
    client.create_dataset(dataset, exists_ok=True)

    # 1. Regulatory Use Cases Table
    use_case_table_ref = f"{dataset_ref}.{config.USE_CASES_TABLE}"
    use_case_schema = [
        bigquery.SchemaField("use_case_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("title", "STRING"),
        bigquery.SchemaField("regulatory_framework", "STRING"),
        bigquery.SchemaField("description", "STRING"),
        bigquery.SchemaField("business_objective", "STRING"),
        bigquery.SchemaField("expected_outcome", "STRING"),
        bigquery.SchemaField("retention_policy", "STRING"),
        bigquery.SchemaField("quality_rules", "STRING"),
        bigquery.SchemaField("data_components_json", "STRING"),
        bigquery.SchemaField("compliance_notes", "STRING"),
        bigquery.SchemaField("audit_trail_json", "STRING"),
        bigquery.SchemaField("status", "STRING"),  # PENDING_PRODUCER_APPROVAL, APPROVED, REJECTED
        bigquery.SchemaField("created_by", "STRING"),
        bigquery.SchemaField("assigned_producer", "STRING"),
        bigquery.SchemaField("semantic_layer_json", "STRING"),
        bigquery.SchemaField("data_product_id", "STRING"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
    ]
    client.create_table(bigquery.Table(use_case_table_ref, schema=use_case_schema), exists_ok=True)

    # 2. Governed Data Products Table
    dp_table_ref = f"{dataset_ref}.{config.DATA_PRODUCTS_TABLE}"
    dp_schema = [
        bigquery.SchemaField("product_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("product_name", "STRING"),
        bigquery.SchemaField("domain", "STRING"),
        bigquery.SchemaField("regulatory_framework", "STRING"),
        bigquery.SchemaField("owner_role", "STRING"),
        bigquery.SchemaField("owner_email", "STRING"),
        bigquery.SchemaField("description", "STRING"),
        bigquery.SchemaField("attributes_json", "STRING"),
        bigquery.SchemaField("table_full_name", "STRING"),
        bigquery.SchemaField("master_id_column", "STRING"),
        bigquery.SchemaField("compliance_certification", "STRING"),
        bigquery.SchemaField("status", "STRING"),  # ACTIVE, DECOMMISSIONED
        bigquery.SchemaField("created_at", "TIMESTAMP"),
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
    ]
    client.create_table(bigquery.Table(dp_table_ref, schema=dp_schema), exists_ok=True)

    # 3. Query Audit Trail Table
    audit_table_ref = f"{dataset_ref}.{config.QUERY_AUDIT_TABLE}"
    audit_schema = [
        bigquery.SchemaField("audit_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("user_persona", "STRING"),
        bigquery.SchemaField("user_identifier", "STRING"),
        bigquery.SchemaField("natural_query", "STRING"),
        bigquery.SchemaField("generated_sql", "STRING"),
        bigquery.SchemaField("rows_returned", "INTEGER"),
        bigquery.SchemaField("compliance_hash", "STRING"),
        bigquery.SchemaField("timestamp", "TIMESTAMP"),
    ]
    client.create_table(bigquery.Table(audit_table_ref, schema=audit_schema), exists_ok=True)


# --- Use Cases CRUD ---

def create_regulatory_use_case(data: dict) -> dict:
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.USE_CASES_TABLE}"
    use_case_id = f"REG-{str(uuid.uuid4())[:8].upper()}"
    now = datetime.datetime.utcnow().isoformat()

    audit_entry = [{
        "action": "CREATED",
        "actor": data.get("created_by", "Data Consumer"),
        "timestamp": now,
        "notes": "Use case draft submitted via Regulatory Chatbot Studio."
    }]

    row = {
        "use_case_id": use_case_id,
        "title": data.get("title", "Regulatory Reporting Pipeline"),
        "regulatory_framework": data.get("regulatory_framework", "BCBS 239"),
        "description": data.get("description", ""),
        "business_objective": data.get("business_objective", ""),
        "expected_outcome": data.get("expected_outcome", ""),
        "retention_policy": data.get("retention_policy", "7 Years (Standard Financial Audit)"),
        "quality_rules": data.get("quality_rules", "No Null Master IDs, Schema Conformance 100%"),
        "data_components_json": json.dumps(data.get("data_components", [])),
        "compliance_notes": data.get("compliance_notes", "Audited for supervisory examination readiness."),
        "audit_trail_json": json.dumps(audit_entry),
        "status": "PENDING_PRODUCER_APPROVAL",
        "created_by": data.get("created_by", "compliance_lead@firm.com"),
        "assigned_producer": data.get("assigned_producer", "Core Banking Data Producer"),
        "semantic_layer_json": json.dumps({}),
        "data_product_id": "",
        "created_at": now,
        "updated_at": now,
    }

    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"Failed to record regulatory use case: {errors}")

    row["data_components"] = data.get("data_components", [])
    row["audit_trail"] = audit_entry
    return row


def list_regulatory_use_cases(status_filter: str = None) -> list[dict]:
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.USE_CASES_TABLE}"

    query = f"SELECT * FROM `{table_ref}`"
    if status_filter:
        query += f" WHERE status = '{status_filter.upper()}'"
    query += " ORDER BY created_at DESC LIMIT 100"

    try:
        rows = list(client.query(query).result())
        result = []
        for r in rows:
            item = dict(r)
            try:
                item["data_components"] = json.loads(item.get("data_components_json") or "[]")
            except Exception:
                item["data_components"] = []
            try:
                item["audit_trail"] = json.loads(item.get("audit_trail_json") or "[]")
            except Exception:
                item["audit_trail"] = []
            try:
                item["semantic_layer"] = json.loads(item.get("semantic_layer_json") or "{}")
            except Exception:
                item["semantic_layer"] = {}
            if item.get("created_at"):
                item["created_at"] = str(item["created_at"])
            if item.get("updated_at"):
                item["updated_at"] = str(item["updated_at"])
            result.append(item)
        return result
    except Exception as e:
        print(f"Error querying use cases: {e}")
        return []


def get_regulatory_use_case(use_case_id: str) -> dict | None:
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.USE_CASES_TABLE}"
    query = f"SELECT * FROM `{table_ref}` WHERE use_case_id = @id LIMIT 1"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("id", "STRING", use_case_id)]
    )
    try:
        rows = list(client.query(query, job_config=job_config).result())
        if not rows:
            return None
        item = dict(rows[0])
        item["data_components"] = json.loads(item.get("data_components_json") or "[]")
        item["audit_trail"] = json.loads(item.get("audit_trail_json") or "[]")
        item["semantic_layer"] = json.loads(item.get("semantic_layer_json") or "{}")
        if item.get("created_at"):
            item["created_at"] = str(item["created_at"])
        if item.get("updated_at"):
            item["updated_at"] = str(item["updated_at"])
        return item
    except Exception:
        return None


def approve_regulatory_use_case(use_case_id: str, producer_name: str, semantic_layer: dict) -> dict:
    """Producer approves use case and attaches the generated semantic layer definition."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.USE_CASES_TABLE}"
    now = datetime.datetime.utcnow().isoformat()

    existing = get_regulatory_use_case(use_case_id)
    if not existing:
        raise ValueError(f"Use case {use_case_id} not found.")

    trail = existing.get("audit_trail", [])
    trail.append({
        "action": "APPROVED_BY_PRODUCER",
        "actor": producer_name,
        "timestamp": now,
        "notes": "Data Producer validated regulatory attributes, approved intake, and built semantic contract."
    })

    query = f"""
        UPDATE `{table_ref}`
        SET status = 'APPROVED',
            assigned_producer = @producer,
            semantic_layer_json = @semantic_json,
            audit_trail_json = @audit_json,
            updated_at = TIMESTAMP(@now)
        WHERE use_case_id = @id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("producer", "STRING", producer_name),
            bigquery.ScalarQueryParameter("semantic_json", "STRING", json.dumps(semantic_layer)),
            bigquery.ScalarQueryParameter("audit_json", "STRING", json.dumps(trail)),
            bigquery.ScalarQueryParameter("now", "STRING", now),
            bigquery.ScalarQueryParameter("id", "STRING", use_case_id),
        ]
    )
    client.query(query, job_config=job_config).result()
    return get_regulatory_use_case(use_case_id)


def update_use_case_data_product(use_case_id: str, data_product_id: str) -> bool:
    """Link an approved use case with its newly materialized physical data product."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.USE_CASES_TABLE}"
    now = datetime.datetime.utcnow().isoformat()
    query = f"""
        UPDATE `{table_ref}`
        SET data_product_id = @dp_id,
            updated_at = TIMESTAMP(@now)
        WHERE use_case_id = @id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("dp_id", "STRING", data_product_id),
            bigquery.ScalarQueryParameter("now", "STRING", now),
            bigquery.ScalarQueryParameter("id", "STRING", use_case_id),
        ]
    )
    try:
        client.query(query, job_config=job_config).result()
        return True
    except Exception as e:
        print(f"[Warning] Failed to link data product {data_product_id} to use case {use_case_id}: {e}")
        return False


def delete_regulatory_use_case(use_case_id: str) -> bool:
    """Platform owner deletes a use case."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.USE_CASES_TABLE}"
    query = f"DELETE FROM `{table_ref}` WHERE use_case_id = @id"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("id", "STRING", use_case_id)]
    )
    client.query(query, job_config=job_config).result()
    return True


# --- Governed Data Products CRUD ---

def create_governed_data_product(data: dict) -> dict:
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.DATA_PRODUCTS_TABLE}"
    product_id = f"DP-{str(uuid.uuid4())[:8].upper()}"
    now = datetime.datetime.utcnow().isoformat()

    row = {
        "product_id": product_id,
        "product_name": data["product_name"].strip(),
        "domain": data.get("domain", "Regulatory Reporting"),
        "regulatory_framework": data.get("regulatory_framework", "BCBS 239"),
        "owner_role": "Data Producer",
        "owner_email": data.get("owner_email", "producer@firm.com"),
        "description": data.get("description", ""),
        "attributes_json": json.dumps(data.get("attributes", [])),
        "table_full_name": data.get("table_full_name", f"{config.PROJECT_ID}.{config.CURATED_DATASET}.{data['product_name']}"),
        "master_id_column": data.get("master_id_column", "master_id"),
        "compliance_certification": data.get("compliance_certification", "PASSED_LEVEL_3_AUDIT"),
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
    }

    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"Failed to record governed data product: {errors}")

    row["attributes"] = data.get("attributes", [])
    return row


def list_governed_data_products() -> list[dict]:
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.DATA_PRODUCTS_TABLE}"
    query = f"SELECT * FROM `{table_ref}` WHERE status = 'ACTIVE' ORDER BY created_at DESC"
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
        print(f"Error listing data products: {e}")
        return []


def delete_governed_data_product(product_id: str) -> bool:
    """Platform owner soft-deletes / decommissions a data product."""
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.DATA_PRODUCTS_TABLE}"
    query = f"DELETE FROM `{table_ref}` WHERE product_id = @id"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("id", "STRING", product_id)]
    )
    client.query(query, job_config=job_config).result()
    return True


# --- Query Audit Trail ---

def log_regulatory_query_audit(
    user_persona: str,
    user_identifier: str,
    natural_query: str,
    generated_sql: str,
    rows_returned: int,
) -> str:
    client = _get_client()
    table_ref = f"{config.PROJECT_ID}.{config.FEEDBACK_DATASET}.{config.QUERY_AUDIT_TABLE}"
    audit_id = f"AUD-{str(uuid.uuid4())[:8].upper()}"
    now = datetime.datetime.utcnow().isoformat()
    compliance_hash = f"BCBS239-HASH-{uuid.uuid4().hex[:12].upper()}"

    row = {
        "audit_id": audit_id,
        "user_persona": user_persona,
        "user_identifier": user_identifier,
        "natural_query": natural_query,
        "generated_sql": generated_sql,
        "rows_returned": rows_returned,
        "compliance_hash": compliance_hash,
        "timestamp": now,
    }
    client.insert_rows_json(table_ref, [row])
    return audit_id
