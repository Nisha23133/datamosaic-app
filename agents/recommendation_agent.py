"""
Recommendation Agent: for an attribute with no existing catalog match,
generates suggested glossary term, domain, subdomain, and source
application using Gemini — grounded in past approved/corrected feedback
as few-shot examples where available.
"""

import json
from google.adk.agents import Agent
from vertexai.generative_models import GenerativeModel
import vertexai
import config
from tools.feedback_store import get_similar_past_feedback, log_feedback

_model = None


def _get_model():
    global _model
    if _model is None:
        vertexai.init(project=config.PROJECT_ID, location=config.LOCATION)
        _model = GenerativeModel(config.GEMINI_MODEL)
    return _model


def recommend_metadata_tool(attribute_name: str, sample_values: list, description: str = "") -> dict:
    """
    Generate a recommended glossary term, domain, subdomain, and source
    application for an attribute that has no existing catalog match.

    Args:
        attribute_name: raw column name as uploaded
        sample_values: a few example values from the uploaded data
        description: optional free-text description if provided

    Returns:
        dict with suggested_glossary_term, suggested_domain,
        suggested_subdomain, suggested_source_application, confidence,
        and reasoning.
    """
    past_examples = get_similar_past_feedback(attribute_name)
    examples_text = ""
    if past_examples:
        examples_text = "Here are similar attributes reviewed before, for reference:\n"
        for ex in past_examples:
            examples_text += (
                f"- '{ex['attribute_name']}' -> term: {ex['suggested_glossary_term']}, "
                f"domain: {ex['suggested_domain']}, subdomain: {ex['suggested_subdomain']}\n"
            )

    known_domains = ", ".join(config.KNOWN_DOMAINS)

    # Only two real source systems exist in this project so far — the
    # model must pick one of these if genuinely justified, or say "NA".
    # Giving it the ACTUAL known options prevents it from inventing a
    # plausible-sounding but fictional source app.
    known_source_applications = (
        "E-commerce Platform (BigQuery ecommerce_central1 dataset — "
        "users, orders, products, inventory), "
        "Support Ticketing System (Cloud SQL support_db, replicated as "
        "public.support_tickets)"
    )

    prompt = f"""You are a data governance assistant. Suggest metadata for ONE
specific uploaded attribute so it can be cataloged as part of a data product.

CRITICAL: base every answer strictly on the ACTUAL attribute name and
sample values given below — do not reuse a generic or previously-seen
answer. Two different attributes with different names/values must get
genuinely different suggestions unless they truly represent the same
real-world concept.

Attribute name: "{attribute_name}"
Sample values: {sample_values[:5]}
Description provided by user: {description or "(none provided)"}

Known existing domains in this organization: {known_domains}
(Prefer an existing domain if it genuinely fits based on the attribute's
actual meaning; otherwise propose a new, specific domain — never a vague
placeholder like "Application" or "Resource".)

Known source applications in this organization: {known_source_applications}
Only name one of these as suggested_source_application if the attribute
name or sample values genuinely indicate that origin (e.g. an order ID,
a product name, a customer email suggest the E-commerce Platform; a
ticket ID, ticket status, or support category suggest the Support
Ticketing System). If neither is clearly indicated, respond exactly
"NA" for suggested_source_application — do not guess or invent one.

{examples_text}

Respond ONLY with valid JSON in exactly this shape, no other text:
{{
  "suggested_glossary_term": "a specific business term for this exact attribute",
  "definition": "one clear sentence defining what this attribute represents, grounded in its name and sample values",
  "suggested_domain": "...",
  "suggested_subdomain": "...",
  "suggested_source_application": "one of the known applications above, or exactly 'NA'",
  "confidence": 0.0,
  "reasoning": "one sentence explaining why, referencing the actual attribute name or sample values"
}}
"""

    model = _get_model()

    try:
        response = model.generate_content(prompt)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Gemini call failed: {e}",
            "attribute_name": attribute_name,
        }

    try:
        text = response.text.strip()
        if text.startswith("```"):
            # Strip a leading ```json or ``` fence and trailing ```
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        result = json.loads(text)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Could not parse model response: {e}",
            "raw": getattr(response, "text", str(response)),
            "attribute_name": attribute_name,
        }

    result["status"] = "success"
    result["attribute_name"] = attribute_name
    result["sample_values"] = sample_values
    return result


def suggest_product_metadata_tool(attributes: list) -> dict:
    """
    Suggest a data product name and domain based on the full set of
    approved attributes going into it. User can override both manually
    in the UI — this is a starting suggestion, not a final answer.

    Args:
        attributes: list of {name, description} for the approved attributes

    Returns:
        dict with suggested_product_name, suggested_domain, reasoning.
    """
    known_domains = ", ".join(config.KNOWN_DOMAINS)
    attr_list = "\n".join(
        f"- {a.get('name', '')}: {a.get('description', '(no description)')}"
        for a in attributes
    )

    prompt = f"""You are a data governance assistant. Based on this set of
attributes that will become columns in a new data product, suggest a
short, clear product name (snake_case, suitable as a BigQuery table
name) and which domain it belongs to.

Attributes:
{attr_list}

Known existing domains in this organization: {known_domains}
(Prefer an existing domain if it genuinely fits; otherwise suggest a
new, specific one.)

Respond ONLY with valid JSON in exactly this shape, no other text:
{{
  "suggested_product_name": "snake_case_name",
  "suggested_domain": "...",
  "reasoning": "one sentence explaining the suggestion"
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
        result = json.loads(text)
        result["status"] = "success"
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


def record_feedback_tool(
    attribute_name: str,
    sample_values: list,
    suggested_glossary_term: str,
    suggested_domain: str,
    suggested_subdomain: str,
    suggested_source_application: str,
    confidence: float,
    user_action: str,
    corrected_value: str = "",
) -> dict:
    """
    Log the user's approve/reject/correct decision on a recommendation.
    user_action must be one of: "approved", "rejected", "corrected".
    """
    log_feedback(
        attribute_name=attribute_name,
        sample_values=sample_values,
        suggested_glossary_term=suggested_glossary_term,
        suggested_domain=suggested_domain,
        suggested_subdomain=suggested_subdomain,
        suggested_source_application=suggested_source_application,
        confidence_score=confidence,
        user_action=user_action,
        corrected_value=corrected_value,
    )
    return {"status": "logged", "action": user_action}


recommendation_agent = Agent(
    name="recommendation_agent",
    model=config.GEMINI_MODEL,
    description="Suggests glossary term, domain, subdomain, and source application for unmatched data attributes.",
    instruction=(
        "When an uploaded attribute has no existing catalog match, use "
        "recommend_metadata_tool to generate a suggestion. Present it clearly "
        "to the user with the confidence score, and ask them to approve, "
        "reject, or correct it. Once they respond, call record_feedback_tool "
        "with their decision — this is required every time, since it's how "
        "the system improves over time."
    ),
    tools=[recommend_metadata_tool, record_feedback_tool],
)