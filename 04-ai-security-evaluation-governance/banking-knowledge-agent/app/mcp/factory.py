"""Composition for the MCP tool layer: configuration in, a live registry out.

The same pattern as :mod:`app.llm.factory` and :mod:`app.agent.factory`, and the
same reason for existing: the modules that *use* a registry should not also be
the modules that decide what is in it.

**Registration is an explicit list, not discovery.** All six tools are named
here, in the order ``prompt.md`` §14 lists them. There is no package scan, no
entry-point lookup and no import-time side effect. The cost is one line per tool;
the benefit is that the set of tools an agent has is a fact you can read, in one
place, rather than a consequence of which modules happened to be imported. A
registry assembled by discovery differs between a test run and a production run
in ways nothing declares.

**No settings, deliberately.** Unlike the LLM factory, nothing here reads
configuration. There is no ``BKA_MCP_*`` variable, no way to disable a tool by
environment, and no endpoint to point at. Every tool is synthetic and
in-process, so there is nothing to configure that would not be inventing a knob
for a system that does not exist yet. When a tool one day talks to something
real, its endpoint and credentials arrive as settings then — and that change will
be visible in this file's signature rather than hidden inside a tool.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.tracing import traced
from app.mcp.registry import ToolRegistry
from app.mcp.tools import (
    ComponentStatusTool,
    ErrorCodeLookupTool,
    ServiceHealthTool,
    SystemConfigurationTool,
    SystemVersionTool,
    TransactionStatusTool,
)


@traced
def build_tool_registry() -> ToolRegistry:
    """Build a fresh registry holding all six synthetic support tools.

    Returns:
        A registry with the six tools registered, in ``prompt.md`` §14's order.
    """
    return ToolRegistry(
        (
            SystemConfigurationTool(),
            TransactionStatusTool(),
            ComponentStatusTool(),
            ErrorCodeLookupTool(),
            SystemVersionTool(),
            ServiceHealthTool(),
        )
    )


@lru_cache(maxsize=1)
def get_tool_registry() -> ToolRegistry:
    """Return the cached registry singleton.

    Cached because the tools are stateless and their datasets are module-level
    constants: building a second registry would allocate six identical objects
    to no purpose. Tests that want isolation call :func:`build_tool_registry`
    instead, which is why both exist.
    """
    return build_tool_registry()
