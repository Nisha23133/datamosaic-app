"""
AI Agents for Financial Regulatory Reporting Governance.
Includes:
1. UseCaseIntakeAgent: Interactive guided chatbot extracting & standardizing the 6 core regulatory fields
   (description, business objective, expected outcome, data requirements, compliance, audit trail).
2. SemanticLayerAgent: Generates automated Dataform/dbt-compatible semantic layer models & contracts.
3. FinancialSQLAgent: Converts natural language into compliant BigQuery SQL ensuring Master ID joins and aggregations.
"""

import json
import vertexai
from vertexai.generative_models import GenerativeModel
import config

_model = None


def _get_model():
    global _model
    if _model is None:
        vertexai.init(project=config.PROJECT_ID, location=config.LOCATION)
        _model = GenerativeModel(config.GEMINI_MODEL)
    return _model


# --- Chatbot Use Case Intake Agent ---

def generate_use_case_from_chat(chat_history: list[dict], current_message: str) -> dict:
    """
    Takes interactive conversation with the Data Consumer and either:
    1. Asks clarification questions if core regulatory fields are missing.
    2. Or extracts the completed standard Regulatory Use Case specification.
    """
    history_formatted = "\n".join(
        f"{m.get('sender', 'user').upper()}: {m.get('text', '')}"
        for m in chat_history
    )

    frameworks_str = ", ".join(config.FINANCIAL_REGULATORY_FRAMEWORKS)

    prompt = f"""You are the Financial Regulatory Governance Architect at an enterprise investment bank.
Your job is to assist Data Consumers (Compliance Officers, Risk Modelers, Regulatory Reporting Leads)
in formally specifying a Regulatory Data Reporting Use Case to prevent regulatory audit penalties and fines
(e.g., BCBS 239, CCAR, MiFID II, Dodd-Frank, DORA, AML/KYC).

Conversation History so far:
{history_formatted}

Latest User Input:
{current_message}

Available Frameworks:
{frameworks_str}

Evaluate if the user has provided enough information to construct a formal regulatory use case covering:
1. Title & Regulatory Framework
2. Description
3. Business Objective (avoiding fines/penalties, meeting supervisory mandates)
4. Expected Outcome (e.g. daily counterparty exposure report, trade surveillance mart, CCAR capital projection)
5. Data Requirements (retention period, quality rules, required data components/fields like Master ID, Trade Date, LEI)
6. Compliance Notes & Audit Trail

CRITICAL INSTRUCTION:
Whenever the user describes a regulatory reporting goal, compliance requirement, or asks to create a use case (even in their first prompt), ALWAYS generate a complete, high-quality, audit-compliant regulatory use case draft with is_complete: true so they can review and submit it immediately. Do not make the user loop through unnecessary questions. If minor details are omitted, infer enterprise banking standards (e.g., 7 Years SEC 17a-4 retention, 0% null on master_id, ISO 4217 currency checks).

Respond with ONLY JSON in this format:
{{
  "is_complete": true,
  "reply": "I have drafted the regulatory use case according to financial supervisory standards. Please review the structured summary below and confirm to register it for Data Producer review.",
  "use_case": {{
    "title": "Clear concise regulatory title",
    "regulatory_framework": "One of the frameworks above (e.g. BCBS 239, CCAR, MiFID II)",
    "description": "Comprehensive summary of reporting scope",
    "business_objective": "Specific justification (e.g. Mitigate BCBS 239 Principle 3 & 4 non-compliance fines)",
    "expected_outcome": "Delivery of governed data product with sub-second audit queries",
    "retention_policy": "7 Years (WORM compliant / SEC 17a-4)",
    "quality_rules": "0% null on master_id, 100% currency ISO 4217 validation, reconciliation tolerance < 0.01%",
    "data_components": ["master_id", "legal_entity_name", "risk_weighted_assets", "trade_date", "exposure_usd"],
    "compliance_notes": "Meets supervisory stress-testing standards with full automated lineage.",
    "assigned_producer": "Core Risk & Banking Data Producer Team"
  }}
}}
"""
    model = _get_model()
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception as e:
        return {
            "is_complete": False,
            "reply": f"Understood. Let's make sure we specify the regulatory framework, required data components (such as Master ID), and retention guidelines. Could you elaborate further? (Error: {e})",
            "use_case": None,
        }


# --- Automated Semantic Layer Generator Agent ---

def generate_semantic_layer_tool(use_case: dict, existing_catalog_fields: list = None) -> dict:
    """
    When a Data Producer approves a use case, this agent automatically synthesizes
    the semantic layer contract (Dataform/dbt SQLX specification, dimension/metric definitions,
    and mandatory Master ID join logic).
    """
    prompt = f"""You are a Financial Data Mesh & Semantic Engineer.
Generate an automated, audit-ready semantic layer model for this regulatory use case.

Use Case Title: {use_case.get('title')}
Framework: {use_case.get('regulatory_framework')}
Business Objective: {use_case.get('business_objective')}
Data Components: {use_case.get('data_components', [])}
Quality Rules: {use_case.get('quality_rules')}

Requirements for the Semantic Layer:
1. Every customer or counterparty entity MUST carry and resolve to a canonical 'master_id'.
2. Must specify dimensions, measures/metrics (e.g. Total Exposure USD, Risk Weighted Asset sum), and time grains.
3. Must provide an executable BigQuery SQL view definition with built-in audit columns (_inserted_at, _audit_hash).

Respond ONLY with valid JSON:
{{
  "model_name": "semantic_model_snake_case",
  "dimensions": [
    {{"name": "master_id", "type": "STRING", "description": "Global enterprise master entity identifier", "is_primary_key": true}},
    {{"name": "legal_entity_name", "type": "STRING", "description": "Verified legal corporate title"}},
    {{"name": "country_code", "type": "STRING", "description": "ISO 3166-1 alpha-2 jurisdiction"}}
  ],
  "metrics": [
    {{"name": "total_exposure_usd", "aggregation": "SUM(exposure_usd)", "description": "Aggregate gross exposure across all accounts"}},
    {{"name": "breach_count", "aggregation": "COUNTIF(limit_breached = TRUE)", "description": "Number of regulatory threshold violations"}}
  ],
  "dataform_sqlx": "SELECT master_id, legal_entity_name, ... FROM ...",
  "regulatory_certification": "CERTIFIED_BCBS239_READY",
  "recommended_table_name": "curated_regulatory_mart"
}}
"""
    model = _get_model()
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception as e:
        return {
            "model_name": "regulatory_semantic_mart",
            "dimensions": [{"name": "master_id", "type": "STRING", "description": "Master identifier"}],
            "metrics": [{"name": "total_exposure", "aggregation": "SUM(exposure)"}],
            "dataform_sqlx": f"-- Automated SQLX for {use_case.get('title')}\nSELECT master_id FROM curated.customer_360",
            "regulatory_certification": "MANUAL_REVIEW_NEEDED",
            "recommended_table_name": "regulatory_reporting_mart"
        }


# --- Natural Language Financial SQL Query Agent ---

def generate_financial_sql_tool(natural_query: str, available_tables: list[dict]) -> dict:
    """
    Translates user questions into compliant, performant BigQuery SQL.
    If the requested table or data point does not match existing tables/attributes,
    it identifies the closest matching candidates and returns suggestions asking
    the user for clarification.
    """
    schema_context_lines = []
    all_table_names = []
    table_column_map = {}

    for t in available_tables:
        tname = t.get("table_name", "")
        all_table_names.append(tname)
        cols = [c.get("name") if isinstance(c, dict) else str(c) for c in t.get("columns", [])]
        table_column_map[tname] = cols
        schema_context_lines.append(
            f"Table: `{config.PROJECT_ID}.{t.get('dataset', config.CURATED_DATASET)}.{tname}`\n"
            f"Attributes / Columns: {', '.join(cols[:25])}"
        )

    schema_context = "\n\n".join(schema_context_lines)

    prompt = f"""You are a Financial Data Mesh & BigQuery Query Assistant for regulatory compliance.
The user wants to query data using natural language.

User Request: "{natural_query}"

Currently Available Enterprise Tables & Attributes in BigQuery:
{schema_context}

RULES:
1. Examine if the user's requested data concept or table name maps confidently to one of the available tables above.
   Note: User might type approximate names (e.g. "counterparty exposure", "BCBS239", "customer 360", "orders", "credit limit").
2. If the user mentions a table or data attributes that DO NOT clearly match any available table or columns, or if it is ambiguous, DO NOT invent fake table/column names. Instead set "needs_clarification": true, provide "suggestions", and explain the exact available tables and columns.
3. If it DOES match:
   - Generate a valid, compliant, read-only SELECT query.
   - Enforce 'master_id' (or customer_id fallback).
   - Use fully-qualified BigQuery table names: `{config.PROJECT_ID}.<dataset>.<table>`.
   - Add LIMIT 100.
   - Set "needs_clarification": false.

Respond ONLY with valid JSON in this exact shape:
{{
  "needs_clarification": false,
  "sql": "SELECT master_id, ... FROM `{config.PROJECT_ID}.curated.table_name` LIMIT 100;",
  "target_table": "table_name",
  "matched_columns": ["master_id", "total_exposure_usd"],
  "explanation": "Clear explanation of how the query resolves the user's intent.",
  "suggestions": []
}}

OR if ambiguous or table/attribute is not found:
{{
  "needs_clarification": true,
  "sql": "",
  "target_table": "",
  "matched_columns": [],
  "explanation": "I could not find an exact match for the requested data point or table. Did you mean one of the following?",
  "suggestions": [
    {{
      "suggested_table": "table_name",
      "suggested_query": "Retrieve all records from table_name with master_id",
      "available_columns": ["master_id", "total_exposure_usd"]
    }}
  ]
}}
"""
    model = _get_model()
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        parsed = json.loads(text)
        return parsed
    except Exception as e:
        # Fallback to first available table or guidance
        fallback_table = all_table_names[0] if all_table_names else "customer_360"
        return {
            "needs_clarification": True,
            "sql": "",
            "target_table": fallback_table,
            "matched_columns": [],
            "explanation": f"Could not match table/attribute names accurately. Available tables include: {', '.join(all_table_names)}.",
            "suggestions": [
                {
                    "suggested_table": fallback_table,
                    "suggested_query": f"Retrieve records carrying master_id from {fallback_table}",
                    "available_columns": table_column_map.get(fallback_table, ["master_id"])
                }
            ]
        }

