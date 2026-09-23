"""FastAPI application surface: POST /extract and GET /items.

The composition root — the only module that knows about both extraction and
persistence, and the only one that turns exceptions into HTTP status codes.
Holds no logic of its own beyond upload validation, the schema-to-model mapping,
and that error translation.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from sqlalchemy import select

from menuforge.config.settings import get_settings, reset_settings
from menuforge.llm.client import ExtractionFailedError, extract_menu
from menuforge.observability.logging import configure_logging, log_event, operation
from menuforge.schemas import ExtractedMenu
from menuforge.tools.database import MenuItem, get_session, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Load configuration, configure logging, and create tables before serving.

    `.env` is loaded here rather than at import time so that importing this
    module has no side effect on the process environment — importing the app in
    a test must not pull a developer's real `DATABASE_URL` off disk.
    `load_dotenv` does not override variables that are already set, so a real
    environment always wins over the file.

    `usecwd=True` searches upward from the working directory. Without it,
    python-dotenv searches from *this file's* location instead, which silently
    finds nothing when the package is installed into site-packages.
    """
    load_dotenv(find_dotenv(usecwd=True))

    # Settings are read *after* `.env`, and the cache is dropped first so a
    # reload picks up a changed environment rather than serving a stale object.
    reset_settings()
    settings = get_settings()

    configure_logging(settings.logging.level)
    init_db()
    log_event(
        logger,
        logging.INFO,
        "startup.complete",
        environment=settings.environment,
        model=settings.llm.model,
    )
    yield


app = FastAPI(title="menuforge", lifespan=lifespan)


def _reject(status_code: int, reason: str, **fields: Any) -> HTTPException:
    """Log a rejected upload and build the exception to raise.

    Rejections are logged here rather than in the endpoint so that every refusal
    is recorded exactly once, with its reason.
    """
    log_event(logger, logging.WARNING, "extract.rejected", reason=reason, **fields)
    return HTTPException(status_code=status_code, detail=reason)


def _validate_media_type(media_type: str) -> None:
    allowed = get_settings().upload.allowed_media_types
    if media_type not in allowed:
        raise _reject(
            415,
            "unsupported media type: expected one of " + ", ".join(sorted(allowed)),
            media_type=media_type or "<none>",
        )


def _too_large(size: int) -> HTTPException:
    max_bytes = get_settings().upload.max_bytes
    return _reject(413, f"image exceeds the {max_bytes} byte limit", size_bytes=size)


def _validate_size(size: int) -> None:
    if size == 0:
        raise _reject(400, "empty upload", size_bytes=0)
    if size > get_settings().upload.max_bytes:
        raise _too_large(size)


def _persist(result: ExtractedMenu) -> None:
    """Write every extracted item. All items commit together, or none do."""
    session = get_session()
    try:
        for item in result.items:
            session.add(
                MenuItem(
                    name=item.name,
                    price=item.price,
                    description=item.description,
                    modifiers=item.modifiers,
                )
            )
        session.commit()
    finally:
        session.close()


@app.post("/extract")
async def extract(file: UploadFile) -> dict[str, Any]:
    """Extract a menu from an uploaded image, store it, and return it.

    Upload validation runs before any LLM call, so a bad upload costs no API
    spend. A failed extraction writes nothing: the caller either gets a whole
    valid menu or a 422.
    """
    media_type = file.content_type or ""
    _validate_media_type(media_type)

    # Check the declared size first so an oversized upload is refused without
    # reading it into memory.
    if file.size is not None and file.size > get_settings().upload.max_bytes:
        raise _too_large(file.size)

    image_bytes = await file.read()
    _validate_size(len(image_bytes))

    # Only the size is logged. The bytes themselves never reach a log call.
    with operation(logger, "extract", media_type=media_type, size_bytes=len(image_bytes)):
        try:
            result = extract_menu(image_bytes, media_type)
        except ExtractionFailedError as exc:
            raise HTTPException(status_code=422, detail=f"extraction failed: {exc}") from exc
        _persist(result)
        log_event(logger, logging.INFO, "extract.persisted", item_count=len(result.items))

    return result.model_dump()


@app.get("/items")
def list_items() -> list[dict[str, Any]]:
    """Return every stored menu item. No pagination at prototype scale."""
    session = get_session()
    try:
        items = session.scalars(select(MenuItem)).all()
        return [
            {
                "id": item.id,
                "name": item.name,
                "price": item.price,
                "description": item.description,
                "modifiers": item.modifiers,
            }
            for item in items
        ]
    finally:
        session.close()
