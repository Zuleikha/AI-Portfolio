"""The in-process tool registry: the MCP layer the agent actually talks to.

``ToolRegistry`` is the ``MCP`` box in ``prompt.md`` §14's diagram::

    Agent
      │
      ▼  ToolRegistry.call(name, arguments)
      │
      ├── get_system_configuration      ── each tool owns its own synthetic data
      ├── check_transaction_status
      ├── get_component_status
      ├── look_up_error_code
      ├── retrieve_system_version
      └── check_service_health
      │
      ▼
    ToolResult

**Why the registry and not the protocol server is what the agent uses.** There
are two ways into these six tools: this registry, in-process, and
:mod:`app.mcp.server`, which speaks the real MCP protocol over stdio. They are
not two implementations — the server is a thin adapter that calls *this*
registry. The agent takes the in-process path because a subprocess, a JSON-RPC
round trip and an async event loop between a question and its answer would buy
nothing here and cost determinism, speed and offline testability in the 600-test
suite. The protocol path exists because "we built an interface shaped like MCP"
and "we ran MCP" are different claims, and only one of them is testable.

**Registration is explicit, never discovered.** There is no plugin scan, no
``importlib`` walk of the ``tools`` package, no decorator side effect at import
time. :func:`app.mcp.factory.get_tool_registry` names all six. Auto-discovery
would mean the set of tools an agent has depends on which modules happened to be
imported — a difference between a test run and a production run that nothing
declares and no test can see.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping

from app.core.logging import get_logger
from app.core.observability import (
    TOOL_CALL_DURATION_MS,
    TOOL_CALLS_TOTAL,
    TOOL_ERRORS_TOTAL,
    elapsed_ms,
    get_metrics,
)
from app.core.tracing import traced
from app.mcp.base import (
    Tool,
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    check_argument_bounds,
)
from app.mcp.models import MAX_ARGUMENT_CHARS, ToolInvocation, ToolResult, ToolSpec

logger = get_logger(__name__)


class ToolRegistry:
    """Holds the available tools and runs them by name.

    The registry is the only component that knows the mapping from a name to an
    implementation. Everything above it — the agent, the CLI, the protocol
    server — works in terms of names and :class:`~app.mcp.models.ToolSpec`, which
    is what allows the six tools to have been written independently and lets
    Stage 7 add a seventh without touching a caller.
    """

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        """Build a registry, optionally pre-populated.

        Args:
            tools: Tools to register, in listing order.

        Raises:
            ValueError: If two tools claim the same name.
        """
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        """Add a tool.

        Args:
            tool: The tool to add. Its ``spec.name`` becomes its key.

        Raises:
            ValueError: If a tool with that name is already registered. A
                duplicate is always a mistake — either the same tool twice, or
                two different tools that would silently shadow one another — and
                a registry that quietly kept the last one would make which
                implementation answered depend on registration order.
        """
        name = tool.spec.name
        if name in self._tools:
            raise ValueError(
                f"A tool named '{name}' is already registered. Tool names must "
                "be unique: registration order must never decide which "
                "implementation answers."
            )
        self._tools[name] = tool

    def __len__(self) -> int:
        """How many tools are registered."""
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        """Whether a tool is registered under ``name``."""
        return name in self._tools

    @property
    def names(self) -> tuple[str, ...]:
        """Registered tool names, in registration order."""
        return tuple(self._tools)

    def specs(self) -> tuple[ToolSpec, ...]:
        """List every tool's spec — the ``list_tools`` half of the MCP shape.

        Returned in registration order so that the CLI, the protocol server and
        Stage 7's prompt all present tools in the same, stable order.
        """
        return tuple(tool.spec for tool in self._tools.values())

    def get(self, name: str) -> Tool:
        """Look up one tool.

        Args:
            name: The tool's registered name.

        Returns:
            The tool.

        Raises:
            ToolNotFoundError: If nothing is registered under ``name``. The
                message lists what *is* registered, because the caller that got
                the name wrong is usually one typo away from the right one.
        """
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(
                f"No tool named '{name}' is registered. "
                f"Available: {', '.join(self.names) or 'none'}."
            ) from None

    @traced
    def call(
        self,
        name: str,
        arguments: Mapping[str, str] | None = None,
    ) -> ToolResult:
        """Run one tool by name — the ``call_tool`` half of the MCP shape.

        Args:
            name: The tool to run.
            arguments: String-valued arguments. ``None`` means no arguments.

        Returns:
            The tool's result. ``ok=False`` is a valid outcome describing
            something that was not found; it is not an error.

        Raises:
            ToolNotFoundError: If no such tool is registered.
            ToolInputError: If the arguments do not satisfy the tool's spec, or
                a name or value exceeds
                :data:`~app.mcp.models.MAX_ARGUMENT_CHARS` (Stage 13).
            ToolExecutionError: If the tool raised something untyped. Wrapped
                here rather than allowed to escape, for the same reason
                :meth:`app.llm.service.LLMService._complete` wraps an untyped
                provider exception: a raw ``KeyError`` from inside a tool
                reaching the API layer would be reported as a generic 500 with
                no indication of which tool produced it. The message names the
                exception *type* only; the original exception is kept as
                ``__cause__``. Its text can carry internal detail (a key, a
                path, a row of data) and this message is printed by the CLI
                and may reach an MCP client (Stage 13).
                Also raised when a tool returns something that is not a
                :class:`~app.mcp.models.ToolResult` -- a contract bug that would
                otherwise surface later as an ``AttributeError``.

        Every call is counted, including one naming an unregistered tool: an
        unknown name is a failed call, and leaving it out of
        ``tool_errors_total`` would hide a misbehaving client (Stage 13).
        """
        supplied = dict(arguments or {})
        metrics = get_metrics()
        metrics.increment(TOOL_CALLS_TOTAL)
        started = time.perf_counter()
        # The requested name is caller-supplied; only a registered one is logged.
        logged_name = name if name in self._tools else "unregistered"
        try:
            tool = self.get(name)
            check_argument_bounds(supplied, name)
            result = tool.invoke(supplied)
            if not isinstance(result, ToolResult):
                raise ToolExecutionError(
                    f"Tool '{name}' returned {type(result).__name__}, "
                    "not a ToolResult."
                )
        except Exception as exc:  # noqa: BLE001 - logged, re-raised as a typed error
            error = (
                exc
                if isinstance(exc, ToolError)
                else ToolExecutionError(
                    f"Tool '{name}' raised an unhandled {type(exc).__name__}."
                )
            )
            latency = elapsed_ms(started)
            metrics.increment(TOOL_ERRORS_TOTAL)
            metrics.observe(TOOL_CALL_DURATION_MS, latency)
            logger.warning(
                "mcp.tool_failed",
                # Type and argument names only, as for a successful call below.
                # Names are clipped: an over-long one is exactly what
                # check_argument_bounds refuses, and must not reach the log whole.
                tool=logged_name,
                arguments=sorted(key[:MAX_ARGUMENT_CHARS] for key in supplied),
                error_type=type(error).__name__,
                latency_ms=latency,
            )
            if error is exc:
                raise
            raise error from exc
        latency = elapsed_ms(started)
        metrics.observe(TOOL_CALL_DURATION_MS, latency)

        logger.info(
            "mcp.tool_called",
            # Argument *names* are logged; argument *values* are not. A
            # transaction reference or an account id is exactly the kind of
            # identifier Stage 13 will review, and the summary text is written
            # by the tool rather than by this layer. Shape only, as everywhere
            # else in this codebase.
            tool=name,
            ok=result.ok,
            latency_ms=latency,
            arguments=sorted(supplied),
            error_code=result.error_code,
            fields=len(result.data),
        )
        return result

    @traced
    def invoke(self, invocation: ToolInvocation) -> ToolResult:
        """Run a tool from a decided :class:`~app.mcp.models.ToolInvocation`.

        The form the agent uses: the policy produces invocations, and this runs
        them without the agent having to unpack a name and an argument mapping
        at the call site.
        """
        return self.call(invocation.tool, invocation.arguments)

    @traced
    def invoke_all(
        self, invocations: Iterable[ToolInvocation]
    ) -> tuple[ToolResult, ...]:
        """Run several invocations in order, returning every result.

        Sequential on purpose. These are in-process dictionary lookups, so
        concurrency would add an event loop and a failure mode to save
        microseconds; and a stable order means the fenced tool block in the
        prompt is stable too, which is what makes a prompt reproducible.
        """
        return tuple(self.invoke(invocation) for invocation in invocations)
