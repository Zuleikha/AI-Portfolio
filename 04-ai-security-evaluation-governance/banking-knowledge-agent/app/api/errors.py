"""Request validation errors that name the field, never the value sent.

FastAPI's default 422 body repeats each offending value (``input``) and extra
detail (``ctx``). A caller's question, session id or malformed JSON would come
straight back in the response -- and into anything that records responses.
Carried from the Stage 13 audit, fixed in Stage 14 (guide §20.61).

The handler keeps an **allow-list** of fields rather than removing two known
ones, so a field added by a later FastAPI or pydantic version stays out until
someone decides it is safe.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.tracing import traced, traced_async

SAFE_ERROR_FIELDS: tuple[str, ...] = ("type", "loc", "msg")
"""What each error keeps: the kind of failure, where it is, and the fixed wording."""


@traced
def safe_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """The validation errors with every field outside the allow-list removed."""
    return [
        {field: error[field] for field in SAFE_ERROR_FIELDS if field in error}
        for error in exc.errors()
    ]


@traced_async
async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Answer 422 with the safe error list. Registered in ``create_app``.

    Raises:
        TypeError: If registered for any other exception type.
    """
    if not isinstance(exc, RequestValidationError):
        raise TypeError(f"Expected RequestValidationError, got {type(exc).__name__}.")
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(safe_validation_errors(exc))},
    )
