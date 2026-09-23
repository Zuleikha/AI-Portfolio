"""FastAPI application entry point.

Stage 1 wired the foundation: configuration, structured logging, tracing and a
health endpoint. Stage 9 adds the conversation API (``/api/sessions``) and the
static web page at ``/``. Stage 10 adds request middleware (a request id, a
timing record and metrics per request) and ``GET /metrics``. Stage 13 adds an
optional API key and a per-client rate limit on the API (guide §20.50-§20.51).

Run locally with (Stage 14: host and port from ``BKA_HOST`` / ``BKA_PORT``)::

    python -m app --reload
"""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app.conversation.service import ConversationService
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.tracing import traced

logger = get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"
"""The no-build web page (guide §20.31), served at ``/``."""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Log application startup and shutdown."""
    settings: Settings = app.state.settings
    logger.info(
        "application.startup",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
    yield
    logger.info("application.shutdown", service=settings.app_name)


@traced
def create_app(
    settings: Settings | None = None,
    conversation_service: ConversationService | None = None,
) -> FastAPI:
    """Build and configure the FastAPI application.

    Using a factory (rather than a module-level singleton only) keeps the app
    testable: tests can construct an instance with overridden settings.

    Args:
        settings: Application settings. Defaults to the cached singleton.
        conversation_service: The service every conversation request shares.
            When omitted it is built on first use (guide §20.28), so creating
            the app never loads the embedding model or the index.
    """
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Source-backed knowledge and support agent for a banking "
            "technology platform. All domain content is synthetic."
        ),
        lifespan=lifespan,
        debug=settings.debug,
    )
    app.state.settings = settings
    app.state.conversation = conversation_service
    app.state.conversation_lock = threading.Lock()

    from fastapi.exceptions import RequestValidationError

    from app.api.errors import validation_error_handler
    from app.api.middleware import RequestContextMiddleware
    from app.api.rate_limit import FixedWindowRateLimiter, enforce_rate_limit
    from app.api.routes import conversation, health, metrics
    from app.api.security import require_api_key

    # One limiter per application, so tests and processes never share counts.
    app.state.rate_limiter = (
        FixedWindowRateLimiter(settings.rate_limit_per_minute)
        if settings.rate_limit_per_minute > 0
        else None
    )

    # 422 bodies name the field, never the value sent (guide §20.61).
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_middleware(RequestContextMiddleware)
    # /health and /ready stay open: probes hold no key (guide §20.50).
    app.include_router(health.router)
    app.include_router(metrics.router, dependencies=[Depends(require_api_key)])
    # Rate limit BEFORE the key check, so wrong-key guessing is capped too.
    app.include_router(
        conversation.router,
        dependencies=[Depends(enforce_rate_limit), Depends(require_api_key)],
    )
    # Mounted last: API routes and /docs always win over a same-named file.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
    return app


app = create_app()
