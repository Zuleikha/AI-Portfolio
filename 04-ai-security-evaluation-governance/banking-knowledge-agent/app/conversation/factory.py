"""The single place the application constructs a conversation service.

Composes :func:`app.agent.factory.get_agent` with a store built from the
``BKA_CONVERSATION_*`` settings, and decides nothing else. Each call builds a new
store: how long one store lives across HTTP requests is Stage 9's decision.
"""

from __future__ import annotations

from app.agent.factory import get_agent
from app.conversation.service import ConversationService
from app.conversation.store import InMemorySessionStore
from app.core.config import Settings, get_settings
from app.core.tracing import traced


@traced
def get_conversation_service(settings: Settings | None = None) -> ConversationService:
    """Build the configured agent wrapped in a conversation service.

    Args:
        settings: Application settings. Defaults to the cached singleton.

    Returns:
        A service with a fresh in-memory session store.
    """
    resolved = settings or get_settings()
    return ConversationService(
        agent=get_agent(resolved),
        store=InMemorySessionStore.from_settings(resolved),
        settings=resolved,
    )
