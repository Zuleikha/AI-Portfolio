"""The MCP protocol server: a small number of smoke tests, on the real protocol.

Deliberately a *small* file. The registry is what the agent uses and what the
rest of the suite covers exhaustively; this server is a thin wrapper, and testing
it exhaustively would mostly re-test the SDK.

What these tests do establish is the claim the wrapper exists to support: that
the protocol path works, and that it reports exactly what the in-process path
reports. They run a genuine client session against a genuine server over the
SDK's in-memory transport — a real ``initialize``, real ``tools/list`` and real
``tools/call``, with real JSON-RPC framing — rather than calling the handler
functions directly. Calling the handlers would prove the functions work and
nothing about whether the protocol does.

No subprocess and no stdio: the transport is in-memory, so these stay as fast,
deterministic and offline as everything else.
"""

from __future__ import annotations

import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

from app.mcp.factory import build_tool_registry
from app.mcp.models import TOOL_NAMES
from app.mcp.registry import ToolRegistry
from app.mcp.server import SERVER_NAME, build_server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    """Run the async tests on asyncio only; trio is not a dependency here."""
    return "asyncio"


def _payload(content: list[object]) -> dict[str, object]:
    """Extract the single JSON text block a tool call returns."""
    assert len(content) == 1, content
    block = content[0]
    assert isinstance(block, TextContent)
    parsed = json.loads(block.text)
    assert isinstance(parsed, dict)
    return parsed


class TestTheProtocolWorks:
    async def test_a_client_can_initialise_against_the_server(
        self, tool_registry: ToolRegistry
    ):
        async with create_connected_server_and_client_session(
            build_server(tool_registry)
        ) as client:
            result = await client.initialize()
            assert result.serverInfo.name == SERVER_NAME

    async def test_tools_list_returns_all_six(self, tool_registry: ToolRegistry):
        async with create_connected_server_and_client_session(
            build_server(tool_registry)
        ) as client:
            await client.initialize()
            listed = await client.list_tools()
            assert tuple(tool.name for tool in listed.tools) == TOOL_NAMES

    async def test_every_listed_tool_carries_a_usable_input_schema(
        self, tool_registry: ToolRegistry
    ):
        async with create_connected_server_and_client_session(
            build_server(tool_registry)
        ) as client:
            await client.initialize()
            listed = await client.list_tools()
            for tool in listed.tools:
                assert tool.description
                schema = tool.inputSchema
                assert schema["type"] == "object"
                assert schema["additionalProperties"] is False
                for definition in schema["properties"].values():
                    assert definition["type"] == "string"

    async def test_a_tool_can_be_called_over_the_protocol(
        self, tool_registry: ToolRegistry
    ):
        async with create_connected_server_and_client_session(
            build_server(tool_registry)
        ) as client:
            await client.initialize()
            called = await client.call_tool(
                "look_up_error_code", {"error_code": "LIM-4001"}
            )
            assert called.isError is False
            data = _payload(list(called.content))["data"]
            assert isinstance(data, dict)
            assert data["component"] == "LimitService"

    async def test_a_tool_taking_no_arguments_can_be_called(
        self, tool_registry: ToolRegistry
    ):
        async with create_connected_server_and_client_session(
            build_server(tool_registry)
        ) as client:
            await client.initialize()
            called = await client.call_tool("check_service_health", {})
            assert called.isError is False


class TestBothPathsAgree:
    """The claim the wrapper exists to support: one implementation, two doors."""

    CALLS = (
        ("look_up_error_code", {"error_code": "PAY-8003"}),
        ("check_transaction_status", {"transaction_reference": "TXN-20260911-004473"}),
        ("get_component_status", {"component": "CoreBankingAdapter"}),
        ("retrieve_system_version", {}),
        ("check_service_health", {"component": "CardSecurityModule"}),
        (
            "get_system_configuration",
            {"component": "LimitService", "key": "limits.currency"},
        ),
    )

    async def test_the_protocol_returns_what_the_registry_returns(
        self, tool_registry: ToolRegistry
    ):
        async with create_connected_server_and_client_session(
            build_server(tool_registry)
        ) as client:
            await client.initialize()
            for name, arguments in self.CALLS:
                over_the_wire = _payload(
                    list((await client.call_tool(name, arguments)).content)
                )
                in_process = tool_registry.call(name, arguments).model_dump(mode="json")
                assert over_the_wire == in_process, name

    async def test_a_not_found_crosses_the_wire_as_a_result_not_an_error(
        self, tool_registry: ToolRegistry
    ):
        """ok=False is a finding. Marking it isError would misreport it."""
        async with create_connected_server_and_client_session(
            build_server(tool_registry)
        ) as client:
            await client.initialize()
            called = await client.call_tool(
                "check_transaction_status",
                {"transaction_reference": "TXN-19990101-000001"},
            )
            assert called.isError is False
            payload = _payload(list(called.content))
            assert payload["ok"] is False
            assert payload["error_code"] == "NOT_FOUND"

    async def test_a_malformed_call_is_reported_as_an_error(
        self, tool_registry: ToolRegistry
    ):
        """A missing required argument is the call being wrong, not the answer."""
        async with create_connected_server_and_client_session(
            build_server(tool_registry)
        ) as client:
            await client.initialize()
            called = await client.call_tool("look_up_error_code", {})
            assert called.isError is True

    async def test_an_unknown_tool_is_reported_as_an_error(
        self, tool_registry: ToolRegistry
    ):
        async with create_connected_server_and_client_session(
            build_server(tool_registry)
        ) as client:
            await client.initialize()
            called = await client.call_tool("no_such_tool", {})
            assert called.isError is True


class TestTheServerIsAWrapperNotAnImplementation:
    def test_the_server_module_contains_no_synthetic_data(self):
        """A second copy of the data would be a second source of truth."""
        from pathlib import Path

        source = Path("app/mcp/server.py").read_text(encoding="utf-8")
        for marker in ("LIM-4001", "TransactionSwitch", "TXN-2026", "4.2.3"):
            assert marker not in source, marker

    def test_the_server_imports_no_tool_module_directly(self):
        import ast
        from pathlib import Path

        tree = ast.parse(Path("app/mcp/server.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("app.mcp.tools")

    async def test_the_server_exposes_whatever_registry_it_is_given(self):
        """Proof of delegation: a smaller registry yields a smaller tool list."""
        registry = ToolRegistry()
        full = build_tool_registry()
        registry.register(full.get("look_up_error_code"))
        async with create_connected_server_and_client_session(
            build_server(registry)
        ) as client:
            await client.initialize()
            listed = await client.list_tools()
            assert [tool.name for tool in listed.tools] == ["look_up_error_code"]
