"""Run the web application with the host and port from the settings.

::

    python -m app                   # BKA_HOST / BKA_PORT, default 127.0.0.1:8000
    python -m app --reload          # restart on code changes (development)
    python -m app --no-access-log   # what the container runs (13.H)

**Stage 14.A (guide §20.58).** ``BKA_HOST`` and ``BKA_PORT`` are validated in
:class:`~app.core.config.Settings` -- the port must be 1 to 65535. Before this
entry point no code read them: the container passed the raw environment values
straight to uvicorn's flags, so the check never ran on the values in use. This
is now the one place they are applied. A bad value fails here, loudly, before
uvicorn starts.

``uvicorn app.main:app`` still works; it simply ignores the two settings.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from typing import Any

from app.core.config import Settings, get_settings
from app.core.tracing import traced

APP_IMPORT_PATH = "app.main:app"
"""Passed as a string, not an object: uvicorn's ``--reload`` needs to re-import it."""


@traced
def _run_uvicorn(app: str, **kwargs: Any) -> None:
    """Start uvicorn. Imported late so tests never load the server."""
    import uvicorn

    uvicorn.run(app, **kwargs)


@traced
def main(
    argv: Sequence[str] | None = None,
    run: Callable[..., None] = _run_uvicorn,
    settings_factory: Callable[[], Settings] = get_settings,
) -> int:
    """Start the server.

    Args:
        argv: Argument list. Defaults to ``sys.argv[1:]``.
        run: The server runner; replaced in tests so no port is bound.
        settings_factory: Where the settings come from; replaced in tests.

    Returns:
        A process exit code, once the server stops.

    Raises:
        pydantic.ValidationError: If the settings are invalid, before the
            server starts.
    """
    parser = argparse.ArgumentParser(
        prog="python -m app",
        description="Run the Banking Knowledge Agent web application.",
    )
    parser.add_argument(
        "--reload", action="store_true", help="Restart when code changes."
    )
    parser.add_argument(
        "--no-access-log",
        action="store_true",
        help="Turn off uvicorn's per-request log line (it records client IPs).",
    )
    args = parser.parse_args(argv)

    settings = settings_factory()
    run(
        APP_IMPORT_PATH,
        host=settings.host,
        port=settings.port,
        access_log=not args.no_access_log,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
