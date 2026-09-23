"""Per-client rate limiting for the conversation API (Stage 13, guide §20.51).

**What it does.** Every ``/api/sessions`` request is counted against its client
(the connecting IP address). A client gets ``limit`` requests per *fixed
window*: the window opens at the client's first request and lasts
``window_seconds``. Once the count is used up, further requests are refused with
``429 Too Many Requests`` and a ``Retry-After`` header saying how many whole
seconds remain until the window ends and the count starts again.

**Why it exists.** Each question can run a search and a paid model call, so one
client sending requests in a loop could run up cost and crowd out everyone
else. The limit runs *before* the API key check, so it also caps how fast
anyone can guess keys.

**Limits of this design** (a Stage 14 production concern):

- Counts live in this process's memory. Several worker processes or replicas
  each keep their own counts, and a restart forgets them all. A shared store
  such as Redis would be the production fix.
- The client is ``request.client.host`` only. ``X-Forwarded-For`` is **not**
  trusted, because any client can forge it. Behind a reverse proxy every
  request would share the proxy's address -- the proxy must then be configured
  to pass the real address (for example uvicorn's ``--forwarded-allow-ips``).
- Clients behind one NAT gateway share one address and therefore one count.

Memory stays bounded: clients whose window has ended are pruned.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.logging import get_logger
from app.core.observability import RATE_LIMITED_TOTAL, fingerprint, get_metrics
from app.core.tracing import traced

logger = get_logger(__name__)

RATE_LIMITED = "Too many requests. Try again later."
"""The only text a 429 response carries."""

WINDOW_SECONDS = 60.0
"""Length of one fixed window."""

UNKNOWN_CLIENT = "unknown"
"""The shared key for requests whose client address is not known."""


@dataclass
class _Window:
    """One client's current window: when it opened and how many requests used."""

    started: float
    count: int


class FixedWindowRateLimiter:
    """Counts requests per client key in fixed windows; thread-safe.

    FastAPI runs the dependency on worker threads, so every read and update of
    the counts happens under one lock. The work under it is a dictionary
    update, plus an occasional pass that drops expired windows.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Allow ``limit`` requests per client per window (``limit`` >= 1).

        Args:
            limit: Requests allowed per client per window.
            window_seconds: Length of one window.
            clock: Monotonic seconds. Injectable so tests control time.

        Raises:
            ValueError: If ``limit`` is below 1 or ``window_seconds`` is not
                positive.
        """
        if limit < 1:
            raise ValueError(f"Rate limit must be at least 1: limit={limit}.")
        if window_seconds <= 0:
            raise ValueError(
                f"Rate limit window must be positive: window_seconds={window_seconds}."
            )
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()
        self._next_prune = clock() + window_seconds

    @property
    def tracked_clients(self) -> int:
        """Clients currently held in memory (expired ones may linger until pruned)."""
        with self._lock:
            return len(self._windows)

    # Traced: it runs once per API request, like the session store's methods --
    # not several times inside a measurement, so the 10.F exemption does not
    # apply. The trace records no arguments, so the client key never reaches it.
    @traced
    def check(self, client: str) -> float | None:
        """Record one request; return ``None`` if allowed, else seconds to wait."""
        with self._lock:
            now = self._clock()
            if now >= self._next_prune:
                self._prune(now)
            window = self._windows.get(client)
            if window is None or now - window.started >= self.window_seconds:
                self._windows[client] = _Window(started=now, count=1)
                return None
            if window.count < self.limit:
                window.count += 1
                return None
            return window.started + self.window_seconds - now

    def _prune(self, now: float) -> None:
        """Drop every expired window. Called under the lock.

        Runs at most once per window length, so its cost is spread thinly over
        many requests while no expired entry outlives two window lengths.
        """
        expired = [
            key
            for key, window in self._windows.items()
            if now - window.started >= self.window_seconds
        ]
        for key in expired:
            del self._windows[key]
        self._next_prune = now + self.window_seconds


def enforce_rate_limit(request: Request) -> None:
    """Reject the request with 429 + ``Retry-After`` when its client is over.

    Uses ``request.app.state.rate_limiter``; a no-op when that is ``None``.
    A FastAPI dependency, so not ``@traced`` (see ``app/api/dependencies.py``).
    """
    limiter: FixedWindowRateLimiter | None = request.app.state.rate_limiter
    if limiter is None:
        return
    client = request.client.host if request.client else UNKNOWN_CLIENT
    wait = limiter.check(client)
    if wait is None:
        return
    get_metrics().increment(RATE_LIMITED_TOTAL)
    # Only a fingerprint: a client address is personal data (contract §2).
    logger.warning("api.rate_limited", client=fingerprint(client))
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=RATE_LIMITED,
        headers={"Retry-After": str(max(1, math.ceil(wait)))},
    )
