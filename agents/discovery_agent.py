"""
Discovery Agent: takes a natural-language question and searches
Knowledge Catalog for matching data products.
"""

from google.adk.agents import Agent
import config
from tools.catalog_client import search_catalog


def search_catalog_tool(query: str) -> dict:
    """
    Search Knowledge Catalog entries matching the given query.

    Args:
        query: natural language description of the data being sought,
               e.g. "customer support ticket data" or "order revenue"

    Returns:
        A dict with a list of matching data products (name, description).
    """
    results = search_catalog(query)
    if results and "error" in results[0]:
        return {"status": "error", "message": results[0]["error"]}
    return {"status": "success", "matches": results}


discovery_agent = Agent(
    name="discovery_agent",
    model=config.GEMINI_MODEL,
    description="Helps users find relevant data products by searching the Knowledge Catalog.",
    instruction=(
        "You help business and technical users find data products. "
        "When asked a question about available data, use the search_catalog_tool "
        "to look up matching entries, then summarize the results in plain, "
        "business-friendly language — avoid technical jargon like 'entry' or "
        "'aspect'. If nothing matches, say so clearly and suggest the user "
        "try different wording or offer to create a new data product."
    ),
    tools=[search_catalog_tool],
)
