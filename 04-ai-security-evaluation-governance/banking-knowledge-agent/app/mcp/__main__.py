"""Command-line entry point for the MCP tool layer.

::

    python -m app.mcp list                        # the six tool specs
    python -m app.mcp call <tool> k=v [k=v ...]   # run one tool
    python -m app.mcp demo                        # a worked call of each tool
    python -m app.mcp serve                       # the real MCP server, stdio

**Every command here is free and offline.** No provider is constructed, no key
is read and no model is called: the tool layer has no LLM in it. That is why
this CLI carries none of the paid-provider guards that ``app.llm`` and
``app.agent`` do — there is nothing here that could cost money. The agent CLI is
where a tool call and a model call meet, and its existing guard covers that.

``demo`` is the command to read first. It shows the two things Stage 6 exists to
demonstrate: that six independent tools answer through one registry, and that a
tool reading can *disagree with the documentation* — which is the entire reason
for having tools alongside RAG.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from app.core.cli import RULE
from app.core.logging import configure_logging
from app.mcp.base import ToolError
from app.mcp.factory import get_tool_registry
from app.mcp.models import ToolResult
from app.mcp.registry import ToolRegistry

DEMO_CALLS: tuple[tuple[str, dict[str, str], str], ...] = (
    (
        "get_system_configuration",
        {"component": "LimitService", "key": "limits.atm.per_transaction_amount"},
        "Documented default is 500.00. The effective value is not.",
    ),
    (
        "check_transaction_status",
        {"transaction_reference": "TXN-20260911-004473"},
        "A timeout whose reversal was never acknowledged - needs a human.",
    ),
    (
        "get_component_status",
        {"component": "CoreBankingAdapter"},
        "The origin of the current incident.",
    ),
    (
        "look_up_error_code",
        {"error_code": "PAY-8003"},
        "A wrapper code: it reports that something declined, not what.",
    ),
    (
        "retrieve_system_version",
        {"component": "CardSecurityModule"},
        "Documentation says 4.2. This component has not got there.",
    ),
    (
        "check_service_health",
        {},
        "The whole fleet: liveness and dependency checks, not throughput.",
    ),
    (
        "check_transaction_status",
        {"transaction_reference": "TXN-19990101-000001"},
        "A miss. ok=False is a finding, not an error.",
    ),
)
"""One worked call per tool, plus a deliberate miss.

Chosen so that a reader who runs ``demo`` once sees every tool answer, sees the
documentation-versus-live disagreement twice, and sees what a not-found looks
like — which is the distinction the whole error contract turns on.
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument list. Defaults to ``sys.argv[1:]``.

    Returns:
        A process exit code.
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.mcp",
        description="Inspect and run the synthetic banking support tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List the registered tools and their arguments.")

    call = subparsers.add_parser("call", help="Run one tool.")
    call.add_argument("tool", help="Tool name, as shown by 'list'.")
    call.add_argument(
        "arguments",
        nargs="*",
        metavar="key=value",
        help="Arguments, e.g. component=LimitService",
    )

    subparsers.add_parser("demo", help="Run a worked call of each tool.")
    subparsers.add_parser("serve", help="Run the MCP protocol server over stdio.")

    args = parser.parse_args(argv)

    if args.command == "serve":
        # Deliberately before logging is configured and before stdout is
        # touched: stdio IS the protocol transport here, and anything this
        # process prints to stdout is a framing error the client sees as
        # corrupt JSON-RPC.
        return _serve()

    # Tool summaries carry em dashes; a cp1252 console would mangle them.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    configure_logging()
    registry = get_tool_registry()

    if args.command == "list":
        return _list(registry)
    if args.command == "call":
        return _call(registry, args.tool, args.arguments)
    return _demo(registry)


def _list(registry: ToolRegistry) -> int:
    """Print every tool's spec."""
    print(RULE)
    print(f"{len(registry)} tools registered - all synthetic, all offline")
    print(RULE)
    for spec in registry.specs():
        print()
        print(f"{spec.name}")
        print(f"  {spec.summary}")
        for parameter in spec.parameters:
            requirement = "required" if parameter.required else "optional"
            print(
                f"    {parameter.name:24} {requirement:8} " f"e.g. {parameter.example}"
            )
        if not spec.parameters:
            print("    (no arguments)")
    print()
    return 0


def _parse_arguments(pairs: Sequence[str]) -> dict[str, str]:
    """Parse ``key=value`` command-line pairs.

    Raises:
        ValueError: If a pair has no ``=``. Reported rather than guessed at:
            a positional argument would have to be matched to a parameter by
            position, and getting that wrong silently calls the tool with the
            right value in the wrong field.
    """
    parsed: dict[str, str] = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator:
            raise ValueError(f"Expected key=value, got {pair!r}.")
        parsed[key] = value
    return parsed


def _render(result: ToolResult) -> None:
    """Print one result: the summary line, then the payload."""
    status = "ok" if result.ok else f"not found ({result.error_code})"
    print(f"  status   {status}")
    print(f"  observed {result.observed_at}  source={result.source}")
    print(f"  summary  {result.summary}")
    if result.error_message:
        print(f"  detail   {result.error_message}")
    if result.data:
        body = json.dumps(dict(result.data), indent=2, sort_keys=True)
        for line in body.splitlines():
            print(f"  {line}")


def _call(registry: ToolRegistry, tool: str, pairs: Sequence[str]) -> int:
    """Run one tool and print its result."""
    try:
        arguments = _parse_arguments(pairs)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    try:
        result = registry.call(tool, arguments)
    except ToolError as exc:
        # Loud, and distinguishable from a not-found: this is the call being
        # wrong, not the answer being negative.
        print(f"{type(exc).__name__}: {exc}")
        return 2

    print(RULE)
    print(f"{tool}  {arguments}")
    print(RULE)
    _render(result)
    return 0


def _demo(registry: ToolRegistry) -> int:
    """Run one worked call of every tool."""
    print(RULE)
    print("MCP tool demo - Agent -> MCP -> Tool -> Result")
    print("All data is synthetic. No network, no model, no cost.")
    print(RULE)
    for tool, arguments, note in DEMO_CALLS:
        print()
        print(f"{tool}  {arguments}")
        print(f"  why      {note}")
        _render(registry.call(tool, arguments))
    print()
    print(RULE)
    print(
        f"{len(DEMO_CALLS)} calls across {len(registry)} tools. "
        "No call cost anything."
    )
    print(RULE)
    return 0


def _serve() -> int:
    """Run the MCP protocol server until the client disconnects."""
    from app.mcp.server import serve

    configure_logging()
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
