"""MCP tool layer: synthetic banking support tools, and the protocol server.

``prompt.md`` §14 asks for MCP and for six synthetic support tools. This package
delivers both, as two layers over **one** set of tool implementations::

    KnowledgeAgent ──▶ ToolRegistry ──▶ Tool ──▶ ToolResult      in-process
                            ▲
    MCP client ──stdio──▶ server.py ─┘                           the protocol

The registry is the source of truth. :mod:`app.mcp.server` is a thin adapter that
speaks the real MCP protocol and calls the same registry — not a second
implementation of the tools. Everything the full test suite covers goes through
the registry, offline and deterministically, in the manner of Stages 3 to 5; the
protocol server gets a small number of smoke tests that prove the wire path
works and that both paths agree.

**Live information is not documentation.** This package answers *what the system
is reportedly doing now*; :mod:`app.rag` answers *what the documentation says it
is designed to do*. The two are kept visibly apart all the way into the prompt,
where they occupy separate fences, and out again into
:class:`~app.agent.models.AgentAnswer`, which records them separately so a
Stage 9 interface can show a reader which half of an answer came from where.

**Every tool here is synthetic and offline by construction.** No socket, no
clock, no filesystem: each tool reads a dictionary defined in its own module. It
is not that the tools are configured not to reach a real system — there is no
code path that could.
"""

from app.mcp.base import (
    Tool,
    ToolError,
    ToolExecutionError,
    ToolInputError,
    ToolNotFoundError,
    ToolUnavailableError,
)
from app.mcp.factory import build_tool_registry, get_tool_registry
from app.mcp.models import (
    SYNTHETIC_OBSERVED_AT,
    TOOL_FAILURE_CODES,
    TOOL_NAMES,
    ToolInvocation,
    ToolName,
    ToolParameter,
    ToolResult,
    ToolSpec,
)
from app.mcp.registry import ToolRegistry

__all__ = [
    "SYNTHETIC_OBSERVED_AT",
    "TOOL_FAILURE_CODES",
    "TOOL_NAMES",
    "Tool",
    "ToolError",
    "ToolExecutionError",
    "ToolInputError",
    "ToolInvocation",
    "ToolName",
    "ToolNotFoundError",
    "ToolParameter",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "ToolUnavailableError",
    "build_tool_registry",
    "get_tool_registry",
]
