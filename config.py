"""
Central configuration for the RegMesh AI app.
Change project/dataset/model settings here — nothing else should hardcode these.
"""
from dotenv import load_dotenv
load_dotenv()

import os

# --- GCP project settings ---
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "data-mosaic-506420")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

# --- BigQuery datasets already built this week ---
ECOMMERCE_DATASET = "ecommerce_central1"
SUPPORT_DATASET = "public"          # holds support_tickets (CDC via Datastream)
RAW_BANKING_DATASET = "raw_banking" # holds raw master_entities, counterparty_exposures, daily_fx_rates
CURATED_DATASET = "curated"         # holds customer_360, order_facts, regulatory marts

# --- Financial Regulatory Governance Datasets & Tables ---
FEEDBACK_DATASET = "governance"
FEEDBACK_TABLE = "recommendation_feedback"
REQUESTS_TABLE = "data_product_requests"
USE_CASES_TABLE = "regulatory_use_cases"
QUERY_AUDIT_TABLE = "regulatory_query_audits"
DATA_PRODUCTS_TABLE = "governed_data_products"

# --- Financial Regulatory Reporting Frameworks ---
FINANCIAL_REGULATORY_FRAMEWORKS = [
    "BCBS 239 (Risk Data Aggregation & Reporting)",
    "CCAR / DFAST (Capital Adequacy & Stress Testing)",
    "MiFID II / MiFIR (Transaction Reporting & Trade Transparency)",
    "Dodd-Frank (Swap Data & Systemic Risk Reporting)",
    "AML / KYC (Anti-Money Laundering & Sanctions)",
    "DORA (Digital Operational Resilience Act)",
    "Solvency II / Basel III/IV (Liquidity & Capital Ratios)",
]

# --- Models ---
GEMINI_MODEL = "gemini-2.5-flash"
EMBEDDING_MODEL = "text-embedding-005"

# --- Platform Owner Authentication ---
# Password required for administrative and approval actions by the Platform Owner.
PLATFORM_OWNER_PASSWORD = os.getenv("PLATFORM_OWNER_PASSWORD", "admin123")

# --- Matching thresholds ---
MATCH_CONFIDENCE_THRESHOLD = 0.75

# --- Financial Governance Domains ---
KNOWN_DOMAINS = [
    "Credit Risk",
    "Market Risk",
    "Liquidity & Treasury",
    "Customer Master & KYC",
    "Regulatory Reporting",
    "Trade & Transaction Surveillance",
    "Counterparty & Exposure"
]
