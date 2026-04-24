"""Travel Assistant Agent - Agent definition with discovery tools."""

import json
import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

from dotenv import load_dotenv
from strands.models.litellm import LiteLLMModel
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolChoice, ToolSpec

load_dotenv()


class MockModel(LiteLLMModel):
    """Mock model that returns fixed responses without API calls."""

    def __init__(self, mock_text: str, **kwargs: Any) -> None:
        super().__init__(model_id="anthropic/claude-sonnet-4-5-20250929")
        self._mock_text = mock_text

    async def stream(
        self,
        messages: Any,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        system_prompt_content: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {}}}
        yield {"contentBlockDelta": {"delta": {"text": self._mock_text}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}

    # Override to avoid any real API call
    async def __aiter__(self):  # type: ignore
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}


TRAVEL_MOCK_RESPONSE = (
    "I found several flight options for your trip. "
    "Searching flights from New York to Los Angeles, "
    "SF to NY, and other routes. "
    "Available flights include UA101 (United Airlines, $250), "
    "AA202 (American Airlines, $275), DL303 (Delta, $260). "
    "I can discover and invoke other agents to book, reserve, "
    "and confirm your booking. Agent discovery is available."
)

from dependencies import (
    get_db_manager,
    get_registry_client,
    get_remote_agent_cache,
)
from strands import (
    Agent,
    tool,
)
from strands.models.litellm import LiteLLMModel
from tools import (
    TRAVEL_ASSISTANT_TOOLS,
    check_prices,
    create_trip_plan,
    get_recommendations,
    search_flights,
)

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# LiteLLM model identifier for Anthropic Claude
MODEL_ID = "anthropic/claude-sonnet-4-5-20250929"
if os.getenv("MOCK_LLM"):
    litellm_model = MockModel(mock_text=TRAVEL_MOCK_RESPONSE)
else:
    litellm_model = LiteLLMModel(model_id=MODEL_ID)


@tool
async def discover_remote_agents(
    query: str,
    max_results: int = 5,
) -> str:
    """Discover remote agents from the registry with natural language query.

    Cache them for visibility and invocation for later tool calls from LLM.
    """
    logger.info(
        f"Tool called: discover_remote_agents("
        f"query='{query}', max_results={max_results})"
    )

    try:
        registry_client = get_registry_client()

        # Search registry
        discovered = await registry_client.discover_by_semantic_search(
            query=query,
            max_results=max_results,
        )

        if not discovered:
            return json.dumps(
                {
                    "query": query,
                    "agents_found": 0,
                    "message": "No agents found matching your query",
                }
            )

        # Cache the agents (no auth token needed for stub registry)
        cache = get_remote_agent_cache()
        newly_cached = cache.cache_discovered_agents(discovered)

        result = {
            "query": query,
            "agents_found": len(discovered),
            "newly_cached": len(newly_cached),
            "total_cached": len(cache),
            "agents": [
                {
                    "id": agent.path,
                    "name": agent.name,
                    "description": agent.description,
                    "url": agent.url,
                    "skills": agent.skill_names,
                    "tags": agent.tags,
                    "relevance_score": agent.relevance_score,
                    "trust_level": agent.trust_level,
                }
                for agent in discovered
            ],
            "next_steps": [
                "Use view_cached_remote_agents() to see all cached agents",
                "Use invoke_remote_agent(agent_id, message) to call a specific agent",
            ],
        }

        logger.info(
            f"Discovery successful: found {len(discovered)} agents, "
            f"cached {len(newly_cached)} new"
        )
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(
            f"Discovery error in discover_remote_agents: {e}",
            exc_info=True,
        )
        return json.dumps(
            {
                "error": "Discovery failed",
                "message": str(e),
            }
        )


@tool
async def view_cached_remote_agents() -> str:
    """View all cached remote agents available for invocation."""
    logger.info("Tool called: view_cached_remote_agents()")

    try:
        cache = get_remote_agent_cache()

        if len(cache) == 0:
            return json.dumps(
                {
                    "total": 0,
                    "message": (
                        "No agents cached. Use discover_remote_agents() "
                        "to find and cache agents."
                    ),
                }
            )

        all_agents = cache.get_all()
        result = {
            "total": len(cache),
            "agents": [
                {
                    "id": agent_id,
                    "name": agent_client.agent_name,
                    "url": agent_client.agent_url,
                    "skills": agent_client.skills,
                }
                for agent_id, agent_client in all_agents.items()
            ],
            "usage": (
                "Use invoke_remote_agent(agent_id, message) "
                "to call any of these agents"
            ),
        }

        logger.info(f"Returning {len(cache)} cached agents")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(
            f"Error in view_cached_remote_agents: {e}", exc_info=True
        )
        return json.dumps(
            {
                "error": "Failed to view cached agents",
                "message": str(e),
            }
        )


@tool
async def invoke_remote_agent(
    agent_id: str,
    message: str,
) -> str:
    """Invoke a cached remote agent by ID with a natural language message."""
    logger.info(
        f"Tool called: invoke_remote_agent("
        f"agent_id='{agent_id}', message='{message[:100]}...')"
    )

    try:
        cache = get_remote_agent_cache()

        if agent_id not in cache:
            all_agents = cache.get_all()
            available_ids = list(all_agents.keys())
            return json.dumps(
                {
                    "error": f"Agent '{agent_id}' not found in cache",
                    "available_agents": available_ids,
                    "hint": (
                        "Use discover_remote_agents() to find and cache "
                        "agents, or view_cached_remote_agents() to see "
                        "what's available"
                    ),
                }
            )

        # Get the cached agent client and invoke it
        agent_client = cache.get(agent_id)
        logger.info(f"Invoking agent: {agent_client.agent_name}")

        response = await agent_client.send_message(message)

        logger.info(f"Successfully invoked {agent_client.agent_name}")
        return response

    except Exception as e:
        logger.error(
            f"Error in invoke_remote_agent: {e}", exc_info=True
        )
        return json.dumps(
            {
                "error": "Failed to invoke remote agent",
                "agent_id": agent_id,
                "message": str(e),
            }
        )


ALL_TOOLS = TRAVEL_ASSISTANT_TOOLS + [
    discover_remote_agents,
    view_cached_remote_agents,
    invoke_remote_agent,
]

strands_agent = Agent(
    name="Travel Assistant Agent",
    description="Flight search and trip planning agent with dynamic agent discovery",
    tools=ALL_TOOLS,
    callback_handler=None,
    model=litellm_model,
)


def get_agent_instance():
    """Return the agent singleton."""
    return strands_agent
