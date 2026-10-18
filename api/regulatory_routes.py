"""
FastAPI Router for Financial Regulatory Reporting, 3-Persona Workflows,
AI Chatbot Use Case Intake, Semantic Layer Synthesis, Data Products, and BigQuery Query Hub.
"""

import time
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from google.cloud import bigquery

import config
from api.auth import verify_platform_owner_password
from tools.regulatory_store import (
    create_regulatory_use_case,
    list_regulatory_use_cases,
    get_regulatory_use_case,
    approve_regulatory_use_case,
    delete_regulatory_use_case,
    create_governed_data_product,
    list_governed_data_products,
    delete_governed_data_product,
    log_regulatory_query_audit,
)
from agents.regulatory_agents import (
    generate_use_case_from_chat,
    generate_semantic_layer_tool,
    generate_financial_sql_tool,
)

regulatory_router = APIRouter(prefix="/regulatory")


# --- 1. CHATBOT USE CASE INTAKE (Data Consumer) ---

class ChatbotMessageRequest(BaseModel):
    message: str
    chat_history: list[dict] = []
    persona: str = "Data Consumer"


@regulatory_router.post("/chat-intake")
def chat_intake(req: ChatbotMessageRequest):
    """
    Data Consumer chats with the regulatory intake assistant.
    Returns either guidance questions or an auto-constructed use case.
    """
    res = generate_use_case_from_chat(req.chat_history, req.message)
    return res


class ConfirmUseCaseRequest(BaseModel):
    title: str = "Regulatory Reporting Pipeline"
    regulatory_framework: str = "BCBS 239"
    description: str = ""
    business_objective: str = ""
    expected_outcome: str = ""
    retention_policy: str = "7 Years (Regulatory Audit Standard)"
    quality_rules: str = "0% null on master_id"
    data_components: list[str] = ["master_id", "legal_entity_name", "exposure_usd"]
    compliance_notes: str = "Audited for supervisory examination readiness."
    created_by: str = "compliance_analyst@firm.com"
    assigned_producer: str = "Core Risk Data Producer"


@regulatory_router.post("/use-cases/create")
async def create_use_case_endpoint(req_data: dict):
    """
    Registers the confirmed use case into BigQuery.
    Immediately becomes available in the Use Cases tab.
    Accepts arbitrary JSON dict so LLM key name variations never fail with 422.
    """
    try:
        # Sanitize data components
        raw_components = req_data.get("data_components", [])
        if isinstance(raw_components, str):
            components = [c.strip() for c in raw_components.split(",") if c.strip()]
        elif isinstance(raw_components, list):
            components = [str(c) for c in raw_components]
        else:
            components = ["master_id", "exposure_usd"]

        sanitized = {
            "title": str(req_data.get("title") or "Regulatory Reporting Pipeline"),
            "regulatory_framework": str(req_data.get("regulatory_framework") or "BCBS 239"),
            "description": str(req_data.get("description") or ""),
            "business_objective": str(req_data.get("business_objective") or ""),
            "expected_outcome": str(req_data.get("expected_outcome") or ""),
            "retention_policy": str(req_data.get("retention_policy") or "7 Years (Regulatory Audit Standard)"),
            "quality_rules": str(req_data.get("quality_rules") or "0% null on master_id"),
            "data_components": components,
            "compliance_notes": str(req_data.get("compliance_notes") or "Audited for supervisory examination readiness."),
            "created_by": str(req_data.get("created_by") or "compliance_analyst@firm.com"),
            "assigned_producer": str(req_data.get("assigned_producer") or "Core Risk Data Producer"),
        }
        created = create_regulatory_use_case(sanitized)
        return created
    except Exception as e:
        print(f"[ERROR] Failed to record regulatory use case: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record regulatory use case: {e}")


@regulatory_router.get("/use-cases")
def list_use_cases_endpoint(status: str = None):
    """List regulatory use cases across the enterprise."""
    return {"use_cases": list_regulatory_use_cases(status)}


@regulatory_router.get("/use-cases/{use_case_id}")
def get_use_case_endpoint(use_case_id: str):
    item = get_regulatory_use_case(use_case_id)
    if not item:
        raise HTTPException(status_code=404, detail="Use case not found.")
    return item


# --- 2. DATA PRODUCER APPROVAL & AUTOMATED SEMANTIC LAYER ---

class ProducerApprovalRequest(BaseModel):
    producer_name: str = "Risk Data Producer"
    persona: str = "Data Producer"
    custom_notes: str = ""
    semantic_layer: dict = {}


@regulatory_router.get("/use-cases/{use_case_id}/semantic-preview")
def preview_semantic_layer_endpoint(use_case_id: str):
    """
    Data Producer previews the draft AI-generated semantic layer in edit mode
    prior to final approval and registration.
    """
    use_case = get_regulatory_use_case(use_case_id)
    if not use_case:
        raise HTTPException(status_code=404, detail="Use case not found.")

    # Generate draft model if not already synthesized
    existing = use_case.get("semantic_layer")
    if existing and existing.get("model_name"):
        return {"semantic_layer": existing, "use_case": use_case}

    draft = generate_semantic_layer_tool(use_case)
    return {"semantic_layer": draft, "use_case": use_case}


@regulatory_router.post("/use-cases/{use_case_id}/approve")
def producer_approve_endpoint(use_case_id: str, req: ProducerApprovalRequest):
    """
    Exclusively Data Producer action:
    1. Validates caller persona is Data Producer.
    2. Takes the producer-reviewed and edited semantic layer contract.
    3. Saves final contract and marks use case as APPROVED with audit trail.
    """
    if req.persona.lower().strip() not in ("data producer", "producer"):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Only the Data Producer persona has authority to approve use cases and publish semantic layer models."
        )

    use_case = get_regulatory_use_case(use_case_id)
    if not use_case:
        raise HTTPException(status_code=404, detail="Use case not found.")

    # Use producer's edited semantic layer or generate fallback
    final_semantic_layer = req.semantic_layer
    if not final_semantic_layer or not final_semantic_layer.get("model_name"):
        final_semantic_layer = generate_semantic_layer_tool(use_case)

    # Commit approval & audit trail in BigQuery
    approved = approve_regulatory_use_case(
        use_case_id=use_case_id,
        producer_name=req.producer_name,
        semantic_layer=final_semantic_layer
    )
    return {
        "status": "APPROVED",
        "use_case_id": use_case_id,
        "semantic_layer": final_semantic_layer,
        "approved_use_case": approved,
    }


class CreateDataProductFromProducerRequest(BaseModel):
    use_case_id: str = ""
    product_name: str
    domain: str
    regulatory_framework: str
    description: str
    attributes: list[dict]  # [{name, inferred_type, definition, is_master_id}, ...]
    owner_email: str = "producer@firm.com"
    master_id_column: str = "master_id"


@regulatory_router.post("/data-products/create")
def producer_create_data_product(req: CreateDataProductFromProducerRequest):
    """
    Producer finalizes attributes & definitions and publishes the Governed Data Product:
    1. Creates the physical BigQuery table in `curated` dataset.
    2. Populates sample compliance records so it is instantly queryable.
    3. Records the data product metadata in the governance registry.
    """
    try:
        from tools.bigquery_client import create_physical_table
        from google.cloud import bigquery

        # 1. Ensure physical BigQuery table exists
        create_res = create_physical_table(
            product_name=req.product_name,
            attributes=req.attributes,
            dataset=config.CURATED_DATASET
        )
        if create_res.get("status") == "error":
            print(f"[Warning] Physical table creation returned: {create_res.get('message')}")

        # 2. Seed initial sample rows into the table if empty so queries return real data immediately
        client = bigquery.Client(project=config.PROJECT_ID)
        table_full_name = create_res.get("table_full_name") or f"{config.PROJECT_ID}.{config.CURATED_DATASET}.{req.product_name}"

        try:
            # Dynamically seed sample compliance rows matching whatever schema attributes were defined
            count_check = list(client.query(f"SELECT COUNT(1) as cnt FROM `{table_full_name}`").result())
            if count_check and count_check[0].cnt == 0:
                sample_entities = [
                    {"master_id": "MST-88201", "name": "Deutsche Morgan Fin Corp", "country": "DE", "rating": "AA", "exp": 45000000.0, "rwa": 32000000.0},
                    {"master_id": "MST-44109", "name": "Barclays Capital Sec LLC", "country": "GB", "rating": "A+", "exp": 125000000.0, "rwa": 85000000.0},
                    {"master_id": "MST-10928", "name": "Societe Generale Global Markets", "country": "FR", "rating": "A", "exp": 60000000.0, "rwa": 41000000.0},
                ]
                dynamic_sample_rows = []
                for idx, ent in enumerate(sample_entities):
                    row = {}
                    for attr in req.attributes:
                        col = attr.get("name")
                        typ = str(attr.get("inferred_type", "STRING")).upper()
                        col_l = col.lower()
                        if "master_id" in col_l:
                            row[col] = ent["master_id"]
                        elif "legal_entity" in col_l or "customer_name" in col_l or "name" in col_l:
                            row[col] = ent["name"]
                        elif "country" in col_l or "jurisdiction" in col_l or "geo" in col_l:
                            row[col] = ent["country"]
                        elif "rating" in col_l:
                            row[col] = ent["rating"]
                        elif "date" in col_l:
                            row[col] = "2026-10-18"
                        elif "currency" in col_l or "ccy" in col_l:
                            row[col] = "USD"
                        elif "exposure" in col_l or "rwa" in col_l or "amount" in col_l or "limit" in col_l or typ in ("NUMERIC", "FLOAT64", "INT64"):
                            val = ent["exp"] if "exposure" in col_l else (ent["rwa"] if "rwa" in col_l else 5000000.0 * (idx + 1))
                            row[col] = int(val) if typ == "INT64" else float(val)
                        elif typ == "BOOL":
                            row[col] = True
                        else:
                            row[col] = f"{col}_{idx + 1}"
                    dynamic_sample_rows.append(row)
                client.insert_rows_json(table_full_name, dynamic_sample_rows)
        except Exception as seed_err:
            print(f"[Notice] Seeding dynamic sample data into {table_full_name}: {seed_err}")

        # 3. Record in governance registry with explicit use_case_id linkage
        created = create_governed_data_product({
            "use_case_id": req.use_case_id,
            "product_name": req.product_name,
            "domain": req.domain,
            "regulatory_framework": req.regulatory_framework,
            "owner_email": req.owner_email,
            "description": req.description,
            "attributes": req.attributes,
            "master_id_column": req.master_id_column,
            "compliance_certification": f"VERIFIED_{req.regulatory_framework.split(' ')[0]}_LEVEL3",
            "table_full_name": table_full_name,
        })

        # 4. If linked to an approved use case, associate the data product in the use case record
        if req.use_case_id:
            try:
                from tools.regulatory_store import update_use_case_data_product
                update_use_case_data_product(req.use_case_id, created["product_id"])
            except Exception as link_err:
                print(f"[Notice] Linking use case to data product: {link_err}")

        return created
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create data product: {e}")


@regulatory_router.get("/data-products")
def list_products_endpoint():
    """List all active governed financial data products."""
    return {"data_products": list_governed_data_products()}


# --- 3. REGULATORY QUERY HUB (Consumer & Producer) ---

class FinancialQueryRequest(BaseModel):
    natural_query: str
    persona: str = "Data Consumer"
    user_identifier: str = "risk_analyst@firm.com"


@regulatory_router.post("/query/generate-and-run")
def query_hub_endpoint(req: FinancialQueryRequest):
    """
    1. Natural Language -> Compliant BigQuery SQL with Master ID resolution.
    2. Executes against BigQuery.
    3. Logs immutable Query Audit Trail for regulators.
    """
    client = bigquery.Client(project=config.PROJECT_ID)

    # 1. Fetch available data products/tables
    products = list_governed_data_products()
    available_tables = [
        {"table_name": p["product_name"], "dataset": config.CURATED_DATASET, "columns": p.get("attributes", [])}
        for p in products
    ]

    # 2. Generate compliant SQL via AI agent
    sql_res = generate_financial_sql_tool(req.natural_query, available_tables)

    # Check if AI requests clarification on table or attribute names
    if sql_res.get("needs_clarification"):
        return {
            "needs_clarification": True,
            "sql": "",
            "explanation": sql_res.get("explanation", "Could not locate exact table or attributes. Please select from available options below:"),
            "suggestions": sql_res.get("suggestions", []),
            "available_tables": [t["table_name"] for t in available_tables],
            "records": [],
            "row_count": 0,
            "execution_time_seconds": 0.0,
            "compliance_status": "CLARIFICATION_REQUIRED",
        }

    sql = sql_res.get("sql", "").strip()
    if not sql:
        return {
            "needs_clarification": True,
            "sql": "",
            "explanation": "No executable query could be formed. Please specify the target table or data point.",
            "suggestions": sql_res.get("suggestions", []),
            "available_tables": [t["table_name"] for t in available_tables],
            "records": [],
            "row_count": 0,
            "execution_time_seconds": 0.0,
            "compliance_status": "CLARIFICATION_REQUIRED",
        }

    # Safety check: Read-only only
    upper_sql = sql.upper()
    for forbidden in ["DELETE ", "DROP ", "UPDATE ", "INSERT ", "ALTER ", "TRUNCATE "]:
        if forbidden in upper_sql:
            raise HTTPException(status_code=400, detail="Only read-only SELECT queries are authorized in the Regulatory Query Hub.")

    # 3. Execute query
    start_time = time.time()
    try:
        job = client.query(sql)
        query_rows = list(job.result())
        records = [dict(r) for r in query_rows]
        elapsed = round(time.time() - start_time, 2)

        # Convert complex objects to strings for JSON
        for r in records:
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
                elif isinstance(v, (bytes, bytearray)):
                    r[k] = str(v)

        # 4. Log regulatory audit trail
        audit_id = log_regulatory_query_audit(
            user_persona=req.persona,
            user_identifier=req.user_identifier,
            natural_query=req.natural_query,
            generated_sql=sql,
            rows_returned=len(records),
        )

        return {
            "needs_clarification": False,
            "sql": sql,
            "explanation": sql_res.get("explanation", ""),
            "records": records,
            "row_count": len(records),
            "execution_time_seconds": elapsed,
            "audit_id": audit_id,
            "compliance_status": "CERTIFIED_AUDIT_LOGGED",
        }
    except Exception as e:
        # If BigQuery throws 404 or column mismatch, return interactive suggestions instead of 500
        return {
            "needs_clarification": True,
            "sql": sql,
            "explanation": f"BigQuery could not locate the exact table or column. Available tables: {', '.join([t['table_name'] for t in available_tables])}. (Details: {e})",
            "suggestions": [
                {
                    "suggested_table": t["table_name"],
                    "suggested_query": f"Retrieve all records carrying master_id from {t['table_name']}",
                    "available_columns": [c.get("name") if isinstance(c, dict) else str(c) for c in t.get("columns", [])]
                }
                for t in available_tables[:3]
            ],
            "records": [],
            "row_count": 0,
            "execution_time_seconds": 0.0,
            "compliance_status": "CLARIFICATION_REQUIRED",
        }


# --- 4. PLATFORM OWNER SUPER-ADMIN ACTIONS ---

@regulatory_router.delete("/use-cases/{use_case_id}")
def owner_delete_use_case(use_case_id: str):
    """Platform owner deletes/decommissions a use case."""
    try:
        delete_regulatory_use_case(use_case_id)
        return {"status": "deleted", "use_case_id": use_case_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete use case: {e}")


@regulatory_router.delete("/data-products/{product_id}")
def owner_delete_data_product(product_id: str):
    """Platform owner deletes/decommissions an existing data product."""
    try:
        delete_governed_data_product(product_id)
        return {"status": "deleted", "product_id": product_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete data product: {e}")
