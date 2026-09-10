"""
Central configuration for the Data Mosaic app.
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
CURATED_DATASET = "curated"         # holds customer_360, order_facts

# --- BigQuery table used to log AI recommendation feedback and product requests ---
FEEDBACK_DATASET = "governance"
FEEDBACK_TABLE = "recommendation_feedback"
REQUESTS_TABLE = "data_product_requests"

# --- Models ---
GEMINI_MODEL = "gemini-2.5-flash"
EMBEDDING_MODEL = "text-embedding-005"

# --- Platform Owner Authentication ---
# Password required for administrative and approval actions by the Platform Owner.
# General product discovery, matching, and request submission are open to everyone.
PLATFORM_OWNER_PASSWORD = os.getenv("PLATFORM_OWNER_PASSWORD")

# --- Matching thresholds ---
# Below this similarity score, treat as "no confident match" and trigger AI recommendation
MATCH_CONFIDENCE_THRESHOLD = 0.75

# --- Knowledge Catalog domains created manually this week ---
KNOWN_DOMAINS = ["Customer", "Sales"]
