"""
API endpoints tying the frontend to the agent tools directly.
For the demo, routes call the tool functions directly rather than going
through the full ADK agent conversation loop — simpler to wire up and
debug, while still using the same underlying logic the agents use.
"""

import tempfile
import shutil
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from tools.file_parser import parse_uploaded_file
from tools.catalog_client import search_data_products, register_data_product, list_data_products_with_governance
from tools.catalog_cache import get_catalog_embeddings
from tools.bigquery_client import create_physical_table
from agents.semantic_agent import match_attribute_tool, register_alias_tool, unregister_alias_tool, list_aliases_tool
from agents.recommendation_agent import recommend_metadata_tool, record_feedback_tool, suggest_product_metadata_tool
from tools.feedback_store import log_feedback

from fastapi import Depends
from api.auth import verify_platform_owner_password
from tools.product_request_store import (
    submit_product_request,
    list_product_requests,
    get_product_request,
    update_product_request_status,
)

# Open router for general access: discovery, uploads, AI recommendations, request submission
router = APIRouter()

# Protected router for Platform Owner actions only
admin_router = APIRouter(prefix="/admin", dependencies=[Depends(verify_platform_owner_password)])

_executor = ThreadPoolExecutor(max_workers=6)


def _match_one(attr: dict) -> dict:
    start = time.time()
    match_result = match_attribute_tool(
        attribute_name=attr["name"],
        sample_values=attr["sample_values"],
        description="",
    )
    print(f"  [timing] matched '{attr['name']}' in {time.time() - start:.2f}s")
    return {"attribute": attr, "match_result": match_result}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Accepts a CSV/JSON/XLSX file, parses it, and runs each attribute
    through the semantic matching pipeline IN PARALLEL. Timing is
    printed to the terminal at each stage to make slow points visible.
    """
    t0 = time.time()

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    attributes = parse_uploaded_file(tmp_path)
    print(f"[timing] file parsed: {len(attributes)} attributes in {time.time() - t0:.2f}s")

    # Warm the catalog cache BEFORE the parallel matching starts, so the
    # one-time build cost happens once and isn't accidentally repeated
    # by multiple threads racing to build it simultaneously.
    t1 = time.time()
    get_catalog_embeddings()
    print(f"[timing] catalog cache ready in {time.time() - t1:.2f}s")

    t2 = time.time()
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(_executor, _match_one, attr) for attr in attributes]
    results = await asyncio.gather(*tasks)
    print(f"[timing] all attributes matched in {time.time() - t2:.2f}s")
    print(f"[timing] TOTAL upload time: {time.time() - t0:.2f}s")

    return {"file_name": file.filename, "attribute_count": len(attributes), "results": results}


class SearchRequest(BaseModel):
    query: str


@router.get("/aliases")
def list_aliases():
    """Every learned alias — the guardrail for reviewing/catching a bad approval later."""
    return {"aliases": list_aliases_tool()}


@router.delete("/aliases/{raw_name}")
def revoke_alias(raw_name: str):
    """Revoke a learned alias — the fix if a wrong match was approved."""
    return unregister_alias_tool(raw_name)


@router.get("/data-products")
def data_products():
    """All data products with domain + owner, grouped client-side for the sidebar."""
    return {"results": list_data_products_with_governance()}


@router.post("/search")
def search(request: SearchRequest):
    """Natural-language search over Knowledge Catalog (Discovery agent) — data products only, with real fields."""
    return {"results": search_data_products(request.query)}


class MatchFeedbackRequest(BaseModel):
    attribute_name: str
    sample_values: list
    matched_column_name: str
    confidence: float
    user_action: str  # "approved" | "rejected"


@router.post("/match-feedback")
def match_feedback(request: MatchFeedbackRequest):
    """
    Record approve/reject on a CATALOG MATCH (not an AI recommendation).
    Approving is what actually trains the alias cache — the next upload
    with this exact raw attribute name gets an instant alias_match
    instead of re-running the embedding pipeline. Rejecting logs it so
    the attribute can fall back to /recommend instead.
    """
    log_feedback(
        attribute_name=request.attribute_name,
        sample_values=request.sample_values,
        suggested_glossary_term=request.matched_column_name,
        suggested_domain="",
        suggested_subdomain="",
        suggested_source_application="",
        confidence_score=request.confidence,
        user_action=request.user_action,
    )

    if request.user_action == "approved":
        register_alias_tool(request.attribute_name, request.matched_column_name)
    else:
        unregister_alias_tool(request.attribute_name)

    return {"status": "logged", "action": request.user_action}


class RecommendRequest(BaseModel):
    attribute_name: str
    sample_values: list
    description: str = ""


@router.post("/recommend")
def recommend(request: RecommendRequest):
    """Get AI-suggested metadata for an unmatched attribute."""
    result = recommend_metadata_tool(
        attribute_name=request.attribute_name,
        sample_values=request.sample_values,
        description=request.description,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))
    return result


class FeedbackRequest(BaseModel):
    attribute_name: str
    sample_values: list
    suggested_glossary_term: str
    suggested_domain: str
    suggested_subdomain: str
    suggested_source_application: str
    confidence: float
    user_action: str  # "approved" | "rejected" | "corrected"
    corrected_value: str = ""


@router.post("/feedback")
def feedback(request: FeedbackRequest):
    """Record approve/reject/correct on a recommendation, and register
    the alias if approved with a different raw name than the term."""
    result = record_feedback_tool(**request.dict())

    if request.user_action in ("approved", "corrected"):
        final_term = request.corrected_value or request.suggested_glossary_term
        register_alias_tool(request.attribute_name, final_term)

    return result


class SuggestProductMetaRequest(BaseModel):
    attributes: list  # [{name, description}, ...]


@router.post("/suggest-product-meta")
def suggest_product_meta(request: SuggestProductMetaRequest):
    """AI-suggested product name and domain — the user can override both manually."""
    result = suggest_product_metadata_tool(request.attributes)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))
    return result


# --- Public Data Product Request Submission ---

class SubmitProductRequest(BaseModel):
    product_name: str
    domain: str
    requested_by: str
    business_justification: str
    attributes: list  # [{name, inferred_type, description}, ...]


@router.post("/requests/submit")
def submit_request(request: SubmitProductRequest):
    """
    Submits a data product creation request from any user.
    Does NOT write directly to BigQuery yet.
    Logged for Platform Owner review and approval.
    """
    if not request.product_name.strip() or not request.domain.strip():
        raise HTTPException(status_code=400, detail="Product name and domain are required.")
    if not request.requested_by.strip():
        raise HTTPException(status_code=400, detail="'Requested by' information is required.")
    if not request.business_justification.strip():
        raise HTTPException(status_code=400, detail="Business justification/requirement is required.")
    if not request.attributes:
        raise HTTPException(status_code=400, detail="At least one attribute is required.")

    try:
        created = submit_product_request(
            product_name=request.product_name,
            domain=request.domain,
            requested_by=request.requested_by,
            business_justification=request.business_justification,
            attributes=request.attributes,
        )
        return created
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit request: {str(e)}")


@router.get("/requests")
def get_public_requests():
    """Returns a list of recent product requests and their statuses."""
    return {"requests": list_product_requests()}


# --- Platform Owner Admin Endpoints (Require Platform Owner Key) ---

@admin_router.get("/requests")
def admin_list_requests():
    """Platform owner view: all product requests with full details."""
    return {"requests": list_product_requests()}


class ReviewActionRequest(BaseModel):
    reviewer_notes: str = ""


@admin_router.post("/requests/{request_id}/approve")
def admin_approve_request(request_id: str, action: ReviewActionRequest = ReviewActionRequest()):
    """
    Platform Owner approves the request:
    1. Creates the physical BigQuery table in the curated dataset.
    2. Registers the table as a governed Data Product.
    3. Updates request status to APPROVED with execution metadata.
    """
    req = get_product_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found.")

    if req["status"] == "APPROVED":
        raise HTTPException(status_code=400, detail=f"Request {request_id} has already been approved.")

    attributes = req.get("attributes", [])
    product_name = req["product_name"]
    domain = req["domain"]
    requested_by = req.get("requested_by", "")
    justification = req.get("business_justification", "")

    # 1. Create physical BigQuery table
    table_result = create_physical_table(
        product_name=product_name,
        attributes=attributes,
    )
    if table_result.get("status") == "error":
        raise HTTPException(
            status_code=500,
            detail=f"BigQuery table creation failed: {table_result.get('message')}"
        )

    # 2. Register data product
    registration = register_data_product(
        table_full_name=table_result["table_full_name"],
        domain=domain,
        owner_email=requested_by,
        description=justification,
    )

    # 3. Update request status
    update_product_request_status(
        request_id=request_id,
        status="APPROVED",
        reviewer_notes=action.reviewer_notes or "Approved and provisioned by Platform Owner.",
        table_full_name=table_result["table_full_name"],
    )

    return {
        "status": "APPROVED",
        "request_id": request_id,
        "table_creation": table_result,
        "data_product_registration": registration,
    }


@admin_router.post("/requests/{request_id}/reject")
def admin_reject_request(request_id: str, action: ReviewActionRequest = ReviewActionRequest()):
    """Platform Owner rejects the request."""
    req = get_product_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found.")

    update_product_request_status(
        request_id=request_id,
        status="REJECTED",
        reviewer_notes=action.reviewer_notes or "Rejected by Platform Owner.",
    )

    return {
        "status": "REJECTED",
        "request_id": request_id,
        "reviewer_notes": action.reviewer_notes,
    }


# Include admin router in root router
router.include_router(admin_router)

