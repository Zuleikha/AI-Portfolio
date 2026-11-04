"""The ``@traced`` decorator (docs/PRD.md, Stage 3 "Supporting piece").

Writes one line on entry, exit (with duration) and error for every wrapped call
to a trace log on disk. The default is ``runs/trace.log``; set
``RESEARCH_AGENT_TRACE_LOG`` to override it. The log's folder is created if it
is missing.

Only the function's module and name are written: never arguments, return
values or exception messages, so no secrets or queries can reach the log.

The private helpers below are not decorated: tracing the tracer would recurse.
"""

import functools
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

TRACE_LOG_ENV = "RESEARCH_AGENT_TRACE_LOG"
DEFAULT_TRACE_LOG = Path("runs") / "trace.log"


def _trace_log_path() -> Path:
    """Resolved on every write, so the env setting can change between calls."""
    return Path(os.environ.get(TRACE_LOG_ENV, str(DEFAULT_TRACE_LOG)))


def _write(event: str, name: str, detail: str = "") -> None:
    path = _trace_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="milliseconds")
    line = f"{stamp} {event:<5} {name}" + (f" {detail}" if detail else "")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def traced[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Trace entry, exit and errors of ``func`` to the trace log."""
    name = f"{func.__module__}.{func.__qualname__}"

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        _write("ENTER", name)
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        except BaseException as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            _write("ERROR", name, f"{type(exc).__name__} {elapsed_ms:.2f} ms")
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        _write("EXIT", name, f"{elapsed_ms:.2f} ms")
        return result

    return wrapper
