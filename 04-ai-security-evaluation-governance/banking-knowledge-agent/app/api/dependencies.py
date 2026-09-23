"""Shared FastAPI dependencies.

Settings are resolved from ``request.app.state`` rather than the cached
``get_settings()`` singleton, so the application factory stays the single
source of truth and tests can build an app with overridden configuration.

The conversation service lives on ``app.state`` too: one per application, so a
session started by one request exists for the next (guide §20.28). It is built
on first use, not at startup, so the health check never loads the embedding
model or the index.

Dependencies are not wrapped in ``@traced`` for the same reason route handlers
are not: FastAPI resolves their annotations against the function's module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.conversation.factory import get_conversation_service
from app.conversation.service import ConversationService
from app.core.config import Settings


def get_app_settings(request: Request) -> Settings:
    """Return the settings the running application was built with."""
    settings: Settings = request.app.state.settings
    return settings


def get_conversation(request: Request) -> ConversationService:
    """Return the application's conversation service, building it once."""
    state = request.app.state
    with state.conversation_lock:
        if state.conversation is None:
            state.conversation = get_conversation_service(state.settings)
        service: ConversationService = state.conversation
    return service


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
ConversationDep = Annotated[ConversationService, Depends(get_conversation)]
