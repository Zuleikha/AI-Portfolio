"""The single place the application constructs a ready-to-use agent.

Mirrors :func:`app.rag.embeddings.get_embedder` and
:func:`app.llm.factory.get_provider`: composition happens in one function driven
by configuration, so the API layer in Stage 9 asks for an agent and never learns
which embedder, which store or which provider is behind it.

Nothing here chooses a provider itself — that is
:func:`app.llm.factory.get_llm_service`'s job, and duplicating the decision would
create a second place where ``BKA_LLM_PROVIDER`` is interpreted. The same applies
to the tool registry: :func:`app.mcp.factory.get_tool_registry` decides what is
in it, and this function only asks for it.

**Stage 6 gave the agent a third collaborator and changed nothing else here.**
The agent is composed from a retriever, an LLM service and a tool registry, all
injected. That the addition of an entire MCP layer cost this file two lines is
the point of the seam: Stage 9 will still ask for an agent and still learn
nothing about what is behind it.
"""

from __future__ import annotations

from app.agent.agent import KnowledgeAgent
from app.core.config import Settings, get_settings
from app.core.tracing import traced
from app.llm.factory import get_llm_service
from app.mcp.factory import get_tool_registry
from app.rag.pipeline import get_retriever


@traced
def get_agent(settings: Settings | None = None) -> KnowledgeAgent:
    """Build the configured agent, indexing the corpus first if it is stale.

    Args:
        settings: Application settings. Defaults to the cached singleton.

    Returns:
        An agent wired to the configured retriever and provider, and to all six
        synthetic MCP support tools.

    Raises:
        LLMConfigurationError: If ``BKA_LLM_PROVIDER`` names a provider this
            build cannot construct.
        EmbeddingError: If the embedding model cannot be loaded.
    """
    resolved = settings or get_settings()
    return KnowledgeAgent(
        retriever=get_retriever(resolved),
        llm_service=get_llm_service(resolved),
        settings=resolved,
        tools=get_tool_registry(),
    )
