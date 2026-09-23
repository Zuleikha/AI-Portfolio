"""Request middleware: one request id and one timing record per HTTP request.

Route handlers cannot be ``@traced`` (see :mod:`app.core.tracing`), so request
tracing lives here, around the whole application (guide §20.34):

1. resolve the request id from ``X-Request-ID`` (guide §20.35);
2. bind it with ``structlog.contextvars`` for the duration of the request, so
   every log and trace line below -- including code running on FastAPI's worker
   threads, which copy the context -- carries it;
3. return it in the ``X-Request-ID`` response header;
4. log ``http.request`` with method, path, status and latency, and update the
   request metrics.

**Only the path is logged**, never the query string or a body: the session id
travels in the JSON body (guide §20.30) and a query string can hold anything.

**An unhandled exception** is logged as ``http.request_failed`` with its type
only -- its message may quote a provider or a tool. If no response has started,
this middleware sends the 500 itself -- a fixed JSON body,
:data:`SERVER_ERROR_BODY`, with the ``X-Request-ID`` header -- so a user
reporting the failure can quote the id that finds its log lines (Stage 13; until
then Starlette built the 500 outside this middleware, without the header). The
exception is then **re-raised**, never swallowed: Starlette's outer error
handler sees that a response has already started and sends nothing more, and
the server still logs the traceback. If a response had already started, the
exception is simply re-raised; a second response cannot be sent.

Written as plain ASGI middleware rather than Starlette's ``BaseHTTPMiddleware``,
which runs the application in a separate task and has a history of context and
streaming surprises.
"""

from __future__ import annotations

import time

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger
from app.core.observability import (
    HTTP_ERRORS_TOTAL,
    HTTP_REQUEST_DURATION_MS,
    HTTP_REQUESTS_TOTAL,
    REQUEST_ID_HEADER,
    elapsed_ms,
    get_metrics,
    resolve_request_id,
)
from app.core.tracing import traced_async

logger = get_logger(__name__)

SERVER_ERROR = 500
"""The status recorded when the application raised before responding."""

SERVER_ERROR_BODY = {"detail": "Internal Server Error"}
"""The only body a 500 from an unhandled exception carries."""


class RequestContextMiddleware:
    """Gives every HTTP request an id, a log record and metrics."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap ``app``."""
        self._app = app

    @traced_async
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI connection; only ``http`` scopes are instrumented."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        method: str = scope["method"]
        path: str = scope["path"]
        status = SERVER_ERROR
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        started = time.perf_counter()
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                await self._app(scope, receive, send_with_request_id)
            except Exception as exc:
                logger.error(
                    "http.request_failed",
                    method=method,
                    path=path,
                    error_type=type(exc).__name__,
                )
                if not response_started:
                    error = JSONResponse(SERVER_ERROR_BODY, status_code=SERVER_ERROR)
                    await error(scope, receive, send_with_request_id)
                raise
            finally:
                latency = elapsed_ms(started)
                metrics = get_metrics()
                metrics.increment(HTTP_REQUESTS_TOTAL)
                metrics.observe(HTTP_REQUEST_DURATION_MS, latency)
                if status >= SERVER_ERROR:
                    metrics.increment(HTTP_ERRORS_TOTAL)
                logger.info(
                    "http.request",
                    method=method,
                    path=path,
                    status=status,
                    latency_ms=latency,
                )
