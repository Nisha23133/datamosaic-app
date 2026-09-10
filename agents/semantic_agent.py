"""
Semantic Agent: given an uploaded attribute (name + sample values),
determines whether it matches an existing catalog column — using a
layered pipeline (alias lookup -> value overlap -> embeddings -> Gemini)
rather than relying on the LLM alone. See conversation notes for why.

Alias mappings are persisted in BigQuery (tools/alias_store.py), NOT
an in-memory dict — a plain dict reset on every server restart and
wasn't shared across multiple deployed instances, so an approval made
in one session was invisible everywhere else. Querying BigQuery for
this exact-match lookup is still the cheapest step in the pipeline
(faster than the embedding-based fallback), so nothing is lost by
moving it off memory.
"""

from google.adk.agents import Agent
import config
from tools.embeddings import get_embedding, cosine_similarity, build_attribute_text
from tools.catalog_cache import get_catalog_embeddings
from tools.alias_store import get_alias, register_alias, unregister_alias, list_aliases


def match_attribute_tool(attribute_name: str, sample_values: list, description: str = "") -> dict:
    """
    Attempt to match an uploaded attribute to an existing catalog column.

    Args:
        attribute_name: raw column name as uploaded, e.g. "Customer Account No."
        sample_values: a few example values from the uploaded data
        description: optional free-text description if the user provided one

    Returns:
        dict with match status: "alias_match", "candidate_match", or "no_match",
        plus the best candidate(s) and a confidence score.
    """
    # Step 1: exact alias lookup — cheapest, most reliable when it hits.
    # Backed by BigQuery, so this is consistent across restarts and
    # across every instance of the app, not just this one process.
    canonical_term = get_alias(attribute_name)
    if canonical_term:
        return {
            "status": "alias_match",
            "canonical_term": canonical_term,
            "confidence": 1.0,
        }

    # Step 2 + 3: embedding similarity against the catalog, using a
    # cache built once per server run instead of a fresh search +
    # embedding call for every candidate on every single upload.
    catalog_entries = get_catalog_embeddings()

    if catalog_entries:
        query_text = build_attribute_text(attribute_name, sample_values, description)
        query_embedding = get_embedding(query_text)  # only ONE embedding call now

        scored = []
        for c in catalog_entries:
            score = cosine_similarity(query_embedding, c["embedding"])
            scored.append({
                "table_name": c["table_name"],
                "column_name": c["column_name"],
                "dataset": c.get("dataset", ""),
                "table_description": c.get("table_description", ""),
                "confidence": round(score, 3),
            })

        scored.sort(key=lambda x: x["confidence"], reverse=True)
        top = scored[0] if scored else None

        if top and top["confidence"] >= config.MATCH_CONFIDENCE_THRESHOLD:
            return {"status": "candidate_match", "match": top, "all_candidates": scored[:3]}

        return {"status": "weak_match", "all_candidates": scored[:3]}

    return {"status": "no_match", "all_candidates": []}


def register_alias_tool(raw_attribute_name: str, canonical_term: str) -> dict:
    """
    Record that a raw attribute name maps to a canonical business term,
    so future uploads with this exact name match instantly, from ANY
    instance of the app. Call this after a user approves a match where
    the raw name differs from the term.
    """
    register_alias(raw_attribute_name, canonical_term)
    return {"status": "alias_registered", "raw_name": raw_attribute_name, "canonical_term": canonical_term}


def list_aliases_tool() -> list[dict]:
    """
    Returns every currently learned alias mapping, read fresh from
    BigQuery — the guardrail for reviewing/catching a bad approval
    later, from any session, not just the one where it happened.
    """
    return list_aliases()


def unregister_alias_tool(raw_attribute_name: str) -> dict:
    """
    Remove a previously-registered alias — used when a user reverses an
    approval, so the alias cache doesn't keep a stale mapping around.
    """
    unregister_alias(raw_attribute_name)
    return {"status": "alias_removed", "raw_name": raw_attribute_name}


semantic_agent = Agent(
    name="semantic_agent",
    model=config.GEMINI_MODEL,
    description="Matches uploaded data attributes to existing catalog columns and business terms.",
    instruction=(
        "You resolve uploaded attribute names to existing business terms in "
        "the catalog, even when names differ (e.g. 'Account No.' vs 'Customer "
        "Account No.'). Use match_attribute_tool first. If it returns "
        "'candidate_match' with confidence above 0.85, state the match "
        "confidently. If 'weak_match', present the top candidates and ask "
        "the user to confirm. If 'no_match', say clearly that this looks "
        "like a new attribute with no existing catalog match."
    ),
    tools=[match_attribute_tool, register_alias_tool],
)
