"""
Orchestrator Agent: the single entry point the API talks to. Routes
user requests to discovery, semantic matching, or recommendation as
appropriate, using ADK's sub-agent delegation.
"""

from google.adk.agents import Agent
import config
from agents.discovery_agent import discovery_agent
from agents.semantic_agent import semantic_agent
from agents.recommendation_agent import recommendation_agent

root_agent = Agent(
    name="datamosaic_orchestrator",
    model=config.GEMINI_MODEL,
    description="Routes data-mesh requests to the right specialist agent.",
    instruction=(
        "You are the front door for the RegMesh AI platform. Route requests "
        "as follows:\n"
        "- Questions about finding/discovering existing data ('where can I find...', "
        "'do we have data on...') -> delegate to discovery_agent.\n"
        "- Requests to check whether an uploaded attribute matches something "
        "existing -> delegate to semantic_agent.\n"
        "- Requests to get metadata suggestions for a new/unmatched attribute, "
        "or to record approve/reject/correct feedback -> delegate to "
        "recommendation_agent.\n"
        "Keep responses in plain, business-friendly language throughout."
    ),
    sub_agents=[discovery_agent, semantic_agent, recommendation_agent],
)
