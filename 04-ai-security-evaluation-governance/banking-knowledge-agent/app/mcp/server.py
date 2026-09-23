"""The real MCP protocol server: the same six tools, over stdio.

This module is the *protocol* half of Stage 6. It uses the official ``mcp`` SDK
to expose :mod:`app.mcp.registry`'s tools to any MCP client — Claude Desktop, an
IDE, another agent — over a JSON-RPC stdio transport::

    MCP client
       │  initialize
       │  tools/list   ──▶  ToolRegistry.specs()      ──▶  six tool definitions
       │  tools/call   ──▶  ToolRegistry.call(...)    ──▶  one ToolResult
       ▼
    stdio (JSON-RPC)

**It is a wrapper, not a second implementation.** Every handler below delegates
to the registry. There is no tool logic here, no synthetic data, and no branch
that could make the protocol path answer differently from the in-process one.
That property is the whole reason the module is this thin, and
``tests/test_mcp_server.py`` asserts it by running both paths over the same
questions and comparing the results.

**Why build this at all, when the agent does not use it.** The agent takes the
in-process path deliberately (see :mod:`app.mcp.registry`): a subprocess and a
JSON-RPC round trip between a question and its answer would cost determinism and
speed in a 600-test suite and buy nothing. So this server is not on the critical
path — and it is still worth having, for two reasons. First, "we implemented an
interface shaped like MCP" and "we ran MCP" are different claims, and only the
second is verifiable. Second, the protocol is where the assumptions get tested:
writing it is what forced the tool specs to carry real JSON Schema, forced every
payload to be JSON-serialisable, and forced a decision about how a ``ok=False``
result crosses the wire.

**How a failed lookup crosses the wire.** MCP distinguishes a *tool error*
(``isError=True``) from a successful call. This server maps that boundary the way
:mod:`app.mcp.base` defines it, and not the way the field names tempt you to:

* ``ok=False`` — *no transaction has that reference* — is **not** an error. It is
  a successful call returning a true finding, so ``isError`` stays false and the
  finding is in the content. Marking it an error would tell every client that the
  tool had malfunctioned when in fact it had answered.
* :class:`~app.mcp.base.ToolInputError` and the rest of the taxonomy **are**
  errors, and are reported as such.

**What a client is told when a call fails (Stage 13).** A caller mistake —
:class:`~app.mcp.base.ToolInputError` or :class:`~app.mcp.base.ToolNotFoundError`
— is returned with its message, because that message is written for the caller
and names only the tool and the argument. Every other tool error is replaced by
a fixed sentence naming the tool: an unexpected exception's text can carry a
path, a key or a row of backing data, and the SDK would otherwise send
``str(exc)`` straight to the client. The detail stays server-side (the error
*type* is logged; the message is not).

**Who can reach it.** The transport is stdio, so the only client is the process
that launched the server — there is no listening socket, no authentication and
no rate limit, and none is needed while that stays true. Exposing these tools
over a network transport is a Stage 14 concern and would need the same API-key
and rate-limit protections as the HTTP API.

**Running it.** ``python -m app.mcp serve``. The transport is stdio, so the
server speaks JSON-RPC on stdin/stdout and must never print anything else there
— which is why logging in this project goes to a file sink and to stderr, never
to stdout.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.lowlevel import Server
from mcp.types import TextContent
from mcp.types import Tool as MCPToolDefinition

from app.core.logging import get_logger
from app.core.tracing import traced
from app.mcp.base import (
    ToolError,
    ToolExecutionError,
    ToolInputError,
    ToolNotFoundError,
    ToolUnavailableError,
)
from app.mcp.factory import get_tool_registry
from app.mcp.models import ToolResult
from app.mcp.registry import ToolRegistry

logger = get_logger(__name__)

SERVER_NAME = "banking-knowledge-agent"
"""The name this server reports to a client during ``initialize``."""

CALLER_ERRORS: tuple[type[ToolError], ...] = (ToolInputError, ToolNotFoundError)
"""Tool errors whose message is safe to return to a client verbatim."""


@traced
def client_safe_error(name: str, exc: ToolError) -> ToolError:
    """The error to hand the SDK for a failed ``tools/call``.

    Args:
        name: The tool that was called (already known to be registered unless
            ``exc`` is a :class:`~app.mcp.base.ToolNotFoundError`).
        exc: What the registry raised.

    Returns:
        ``exc`` itself for a caller mistake; otherwise a new error of a public
        type with a fixed message, so no internal detail crosses the wire.
    """
    if isinstance(exc, CALLER_ERRORS):
        return exc
    if isinstance(exc, ToolUnavailableError):
        return ToolUnavailableError(
            f"Tool '{name}' is temporarily unavailable. Retry later."
        )
    return ToolExecutionError(f"Tool '{name}' failed unexpectedly.")


def _as_definition(registry: ToolRegistry, name: str) -> MCPToolDefinition:
    """Translate one :class:`~app.mcp.models.ToolSpec` into an MCP definition.

    The translation is deliberately total: every field the protocol offers that
    this project has an honest value for is populated. ``description`` carries
    the tool's full description rather than its one-line summary, because the
    description is the only thing a remote model sees before choosing.
    """
    spec = registry.get(name).spec
    return MCPToolDefinition(
        name=spec.name,
        title=spec.summary,
        description=spec.description,
        inputSchema=spec.input_schema(),
    )


def _as_content(result: ToolResult) -> list[TextContent]:
    """Render a :class:`~app.mcp.models.ToolResult` as MCP content.

    One text block containing the whole result as JSON — summary, payload,
    provenance and all. A client receives exactly what the in-process caller
    receives, with nothing dropped and nothing reformatted into prose, so the two
    paths cannot diverge in what they report.
    """
    payload = result.model_dump(mode="json")
    body = json.dumps(payload, indent=2, sort_keys=True)
    return [TextContent(type="text", text=body)]


def build_server(registry: ToolRegistry | None = None) -> Server[Any, Any]:
    """Build the MCP server, bound to a tool registry.

    Args:
        registry: The tools to expose. Defaults to the configured registry.

    Returns:
        A configured server, not yet running. Kept separate from
        :func:`serve` so that tests can drive the handlers directly without a
        subprocess or an event loop of their own.
    """
    tools = registry or get_tool_registry()
    server: Server[Any, Any] = Server(SERVER_NAME)

    @server.list_tools()  # type: ignore[no-untyped-call, misc]
    async def list_tools() -> list[MCPToolDefinition]:
        """Answer ``tools/list`` from the registry."""
        logger.info("mcp.server.list_tools", tools=len(tools))
        return [_as_definition(tools, name) for name in tools.names]

    @server.call_tool()  # type: ignore[misc]
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Answer ``tools/call`` from the registry.

        Arguments arrive as JSON and are coerced to strings, because the tool
        contract is string-valued throughout (see
        :meth:`app.mcp.models.ToolSpec.input_schema`). A client that sends the
        number ``4001`` where a code was wanted gets the same treatment as one
        that sends ``"4001"``, rather than a type error from deep inside a tool.

        A :class:`~app.mcp.base.ToolError` propagates, passed through
        :func:`client_safe_error` first: the SDK converts it into an MCP error
        response, which is the correct outcome for a malformed call.
        A ``ok=False`` result is *not* an error and returns
        normally — see the module docstring.
        """
        supplied = {key: str(value) for key, value in (arguments or {}).items()}
        try:
            result = tools.call(name, supplied)
        except ToolError as exc:
            logger.info(
                "mcp.server.tool_error",
                tool=name,
                error=type(exc).__name__,
                retryable=exc.retryable,
            )
            safe = client_safe_error(name, exc)
            if safe is exc:
                raise
            raise safe from exc
        return _as_content(result)

    return server


async def serve(registry: ToolRegistry | None = None) -> None:
    """Run the MCP server over stdio until the client disconnects.

    Args:
        registry: The tools to expose. Defaults to the configured registry.
    """
    from mcp.server.stdio import stdio_server

    server = build_server(registry)
    options = server.create_initialization_options()
    logger.info("mcp.server.starting", server=SERVER_NAME, transport="stdio")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)
