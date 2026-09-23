"""API key authentication (Stage 13, guide §20.50).

**What it does.** When ``settings.api_key`` is set, every protected route
(``/api/sessions/*`` and ``/metrics``, wired in :mod:`app.main`) needs the
request header ``X-API-Key`` to hold that key. Anything else is 401. When no
key is set, nothing is checked -- local development stays zero-setup, and
production refuses to start without a key (:mod:`app.core.config`).

**Why.** Without it, anyone who can reach the server can run questions through
the agent (and, with a paid provider, spend money) and read the metrics.

**How it avoids leaking.**

- The key is compared with :func:`hmac.compare_digest`, which takes the same
  time wherever the first wrong character is, so response timing does not
  reveal how much of a guess was right.
- A missing key and a wrong key get the *same* 401 body and header, so a
  caller cannot tell which one happened.
- The log line ``api.auth_rejected`` records only the reason (``missing`` or
  ``invalid``) -- never the header value, which might be a real key sent to
  the wrong server.
- Each rejection adds one to the ``auth_failures_total`` metric, so repeated
  guessing is visible on ``/metrics``.

This is one shared key: it says "this caller may use the API", not *who* the
caller is. Per-user identity is a Stage 14 concern.

Not ``@traced``, for the reason no FastAPI dependency is (see
:mod:`app.api.dependencies`).
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.observability import AUTH_FAILURES_TOTAL, get_metrics

logger = get_logger(__name__)

API_KEY_HEADER = "X-API-Key"
"""The request header carrying the shared key."""

AUTH_REQUIRED = "A valid API key is required."
"""The only text a 401 response carries -- the same for a missing or wrong key."""


def require_api_key(request: Request) -> None:
    """Reject the request with 401 unless it carries the configured API key.

    A no-op when ``settings.api_key`` is unset.

    Raises:
        HTTPException: 401 with :data:`AUTH_REQUIRED` and
            ``WWW-Authenticate: ApiKey`` when the header is missing or wrong.
    """
    settings: Settings = request.app.state.settings
    if settings.api_key is None:
        return
    supplied = request.headers.get(API_KEY_HEADER)
    if supplied is None:
        reason = "missing"
    elif hmac.compare_digest(
        supplied.encode("utf-8"),
        settings.api_key.get_secret_value().encode("utf-8"),
    ):
        return
    else:
        reason = "invalid"
    logger.warning("api.auth_rejected", reason=reason)
    get_metrics().increment(AUTH_FAILURES_TOTAL)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=AUTH_REQUIRED,
        headers={"WWW-Authenticate": "ApiKey"},
    )
