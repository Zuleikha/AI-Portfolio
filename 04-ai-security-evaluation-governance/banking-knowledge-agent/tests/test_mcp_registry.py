"""The tool contract and the in-process registry.

These tests target the seam, not the six datasets behind it: what a tool must
promise, what the registry does with a name, and where the line falls between a
result that reports nothing and a call that was wrong. ``test_mcp_tools.py``
covers what the individual tools actually know.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from app.mcp.base import (
    Tool,
    ToolError,
    ToolExecutionError,
    ToolInputError,
    ToolNotFoundError,
    ToolUnavailableError,
    reject_unknown_arguments,
    require_argument,
)
from app.mcp.factory import build_tool_registry, get_tool_registry
from app.mcp.models import (
    SYNTHETIC_OBSERVED_AT,
    TOOL_FAILURE_CODES,
    TOOL_NAMES,
    ToolInvocation,
    ToolParameter,
    ToolResult,
    ToolSpec,
)
from app.mcp.registry import ToolRegistry

SPEC = ToolSpec(
    name="look_up_error_code",
    summary="A stub.",
    description="A stub tool used to test the seam.",
    parameters=(
        ToolParameter(name="error_code", description="A code.", example="LIM-4001"),
    ),
)


class StubTool:
    """A tool that inherits nothing, to prove the protocol is structural."""

    def __init__(self, result: ToolResult | None = None) -> None:
        self._result = result
        self.calls: list[Mapping[str, str]] = []

    @property
    def spec(self) -> ToolSpec:
        return SPEC

    def invoke(self, arguments: Mapping[str, str]) -> ToolResult:
        self.calls.append(dict(arguments))
        if self._result is not None:
            return self._result
        return ToolResult.success(SPEC.name, "stub ok", {"echo": "1"})


class ExplodingTool(StubTool):
    """A tool with a bug in it."""

    def invoke(self, arguments: Mapping[str, str]) -> ToolResult:
        raise KeyError("a bug nobody anticipated")


class RaisingTool(StubTool):
    """A tool that raises a typed tool error."""

    def invoke(self, arguments: Mapping[str, str]) -> ToolResult:
        raise ToolInputError("bad argument")


# --- The protocol ---------------------------------------------------------


class TestTheProtocol:
    def test_a_tool_qualifies_structurally(self):
        assert isinstance(StubTool(), Tool)

    def test_every_registered_tool_satisfies_the_protocol(self):
        for tool in build_tool_registry()._tools.values():
            assert isinstance(tool, Tool)

    def test_a_spec_is_constant_for_the_lifetime_of_the_tool(self):
        registry = build_tool_registry()
        for name in registry.names:
            tool = registry.get(name)
            assert tool.spec == tool.spec

    def test_a_spec_name_matches_its_registry_key(self):
        registry = build_tool_registry()
        for name in registry.names:
            assert registry.get(name).spec.name == name

    def test_all_six_prompt_md_tools_are_registered(self):
        assert build_tool_registry().names == TOOL_NAMES


# --- The error taxonomy ---------------------------------------------------


class TestTheErrorTaxonomy:
    @pytest.mark.parametrize(
        ("error", "retryable"),
        [
            (ToolNotFoundError, False),
            (ToolInputError, False),
            (ToolExecutionError, False),
            (ToolUnavailableError, True),
        ],
    )
    def test_retryable_flags(self, error: type[ToolError], retryable: bool):
        assert error("x").retryable is retryable

    def test_every_tool_error_is_a_tool_error(self):
        for error in (
            ToolNotFoundError,
            ToolInputError,
            ToolExecutionError,
            ToolUnavailableError,
        ):
            assert issubclass(error, ToolError)

    def test_callers_can_branch_on_the_base_class(self):
        """The contract callers rely on: one except clause catches the layer."""
        with pytest.raises(ToolError):
            raise ToolNotFoundError("x")


class TestArgumentHelpers:
    def test_require_argument_strips_whitespace(self):
        assert require_argument({"a": "  x  "}, "a", "t") == "x"

    def test_require_argument_rejects_a_missing_argument(self):
        with pytest.raises(ToolInputError, match="not supplied"):
            require_argument({}, "a", "t")

    def test_require_argument_rejects_a_blank_argument(self):
        with pytest.raises(ToolInputError, match="non-empty"):
            require_argument({"a": "   "}, "a", "t")

    def test_the_error_names_the_tool_and_the_argument(self):
        with pytest.raises(ToolInputError) as caught:
            require_argument({}, "error_code", "look_up_error_code")
        assert "error_code" in str(caught.value)
        assert "look_up_error_code" in str(caught.value)

    def test_unknown_arguments_are_rejected_not_ignored(self):
        with pytest.raises(ToolInputError, match="does not accept"):
            reject_unknown_arguments({"nope": "1"}, SPEC)

    def test_declared_arguments_are_accepted(self):
        reject_unknown_arguments({"error_code": "LIM-4001"}, SPEC)


# --- The registry ---------------------------------------------------------


class TestTheRegistry:
    def test_an_empty_registry_has_no_tools(self):
        assert len(ToolRegistry()) == 0

    def test_registration_is_by_spec_name(self):
        registry = ToolRegistry((StubTool(),))
        assert "look_up_error_code" in registry

    def test_a_duplicate_name_is_refused(self):
        registry = ToolRegistry((StubTool(),))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(StubTool())

    def test_an_unknown_name_raises_and_lists_what_exists(self):
        registry = ToolRegistry((StubTool(),))
        with pytest.raises(ToolNotFoundError) as caught:
            registry.call("no_such_tool")
        assert "look_up_error_code" in str(caught.value)

    def test_arguments_reach_the_tool_verbatim(self):
        tool = StubTool()
        ToolRegistry((tool,)).call("look_up_error_code", {"error_code": "LIM-4001"})
        assert tool.calls == [{"error_code": "LIM-4001"}]

    def test_no_arguments_means_an_empty_mapping_not_none(self):
        tool = StubTool()
        ToolRegistry((tool,)).call("look_up_error_code")
        assert tool.calls == [{}]

    def test_an_untyped_exception_is_wrapped(self):
        registry = ToolRegistry((ExplodingTool(),))
        with pytest.raises(ToolExecutionError, match="KeyError"):
            registry.call("look_up_error_code")

    def test_the_wrapper_preserves_the_cause(self):
        registry = ToolRegistry((ExplodingTool(),))
        with pytest.raises(ToolExecutionError) as caught:
            registry.call("look_up_error_code")
        assert isinstance(caught.value.__cause__, KeyError)

    def test_a_typed_tool_error_passes_through_unwrapped(self):
        registry = ToolRegistry((RaisingTool(),))
        with pytest.raises(ToolInputError):
            registry.call("look_up_error_code")

    def test_specs_are_returned_in_registration_order(self):
        assert [s.name for s in build_tool_registry().specs()] == list(TOOL_NAMES)

    def test_invoke_runs_a_decided_invocation(self):
        tool = StubTool()
        registry = ToolRegistry((tool,))
        registry.invoke(
            ToolInvocation(
                tool="look_up_error_code",
                arguments={"error_code": "LIM-4001"},
                reason="test",
            )
        )
        assert tool.calls == [{"error_code": "LIM-4001"}]

    def test_invoke_all_preserves_order(self):
        registry = build_tool_registry()
        results = registry.invoke_all(
            (
                ToolInvocation(
                    tool="look_up_error_code",
                    arguments={"error_code": "LIM-4001"},
                    reason="r",
                ),
                ToolInvocation(
                    tool="retrieve_system_version", arguments={}, reason="r"
                ),
            )
        )
        assert [r.tool for r in results] == [
            "look_up_error_code",
            "retrieve_system_version",
        ]


class TestTheFactory:
    def test_the_singleton_is_cached(self):
        assert get_tool_registry() is get_tool_registry()

    def test_build_returns_a_fresh_registry(self):
        assert build_tool_registry() is not build_tool_registry()

    def test_registration_is_explicit_not_discovered(self):
        """No import-time side effects: importing a tool must register nothing."""
        import app.mcp.tools.error_code  # noqa: F401

        assert len(ToolRegistry()) == 0


# --- Results --------------------------------------------------------------


class TestToolResults:
    def test_success_is_ok_with_no_error_code(self):
        result = ToolResult.success("look_up_error_code", "found", {"a": 1})
        assert result.ok
        assert result.error_code is None

    def test_failure_is_not_ok_and_carries_no_payload(self):
        result = ToolResult.failure("look_up_error_code", "nope", "NOT_FOUND", "no")
        assert not result.ok
        assert result.data == {}

    def test_every_result_is_marked_as_a_tool_reading(self):
        assert ToolResult.success("look_up_error_code", "x", {}).source == (
            "synthetic_tool"
        )

    def test_the_clock_is_synthetic_and_fixed(self):
        assert ToolResult.success("look_up_error_code", "x", {}).observed_at == (
            SYNTHETIC_OBSERVED_AT
        )

    def test_a_result_is_immutable(self):
        result = ToolResult.success("look_up_error_code", "x", {})
        with pytest.raises(ValueError):
            result.ok = False  # type: ignore[misc]


class TestSpecs:
    def test_the_input_schema_types_every_argument_as_a_string(self):
        schema = SPEC.input_schema()
        properties = schema["properties"]
        assert isinstance(properties, dict)
        for value in properties.values():
            assert isinstance(value, dict)
            assert value["type"] == "string"

    def test_the_input_schema_forbids_undeclared_arguments(self):
        assert SPEC.input_schema()["additionalProperties"] is False

    def test_optional_parameters_are_not_required(self):
        spec = ToolSpec(
            name="check_service_health",
            summary="s",
            description="d",
            parameters=(
                ToolParameter(
                    name="component",
                    description="c",
                    example="LimitService",
                    required=False,
                ),
            ),
        )
        assert spec.input_schema()["required"] == []

    def test_the_example_reaches_the_schema_description(self):
        properties = SPEC.input_schema()["properties"]
        assert isinstance(properties, dict)
        error_code = properties["error_code"]
        assert isinstance(error_code, dict)
        assert "LIM-4001" in str(error_code["description"])

    def test_every_real_spec_documents_every_parameter(self):
        for spec in build_tool_registry().specs():
            for parameter in spec.parameters:
                assert parameter.description.strip()
                assert parameter.example.strip()


class TestTheFailureVocabularyIsClosed:
    """Six tools were written independently; their error codes must be bounded.

    The integration finding recorded in ``docs/HANDOVER.md`` §6.C. Four tools
    used ``NOT_FOUND``; two invented richer codes, which turned out to be better
    answers. The vocabulary was widened rather than flattened -- and then closed,
    so that a seventh tool cannot quietly add a seventh spelling.
    """

    def test_every_tool_failure_code_is_in_the_closed_set(self):
        registry = build_tool_registry()
        misses = (
            ("get_system_configuration", {"component": "Nope", "key": "a.b"}),
            ("get_system_configuration", {"component": "LimitService", "key": "a.b"}),
            (
                "check_transaction_status",
                {"transaction_reference": "TXN-19990101-000001"},
            ),
            ("get_component_status", {"component": "Nope"}),
            ("look_up_error_code", {"error_code": "ZZZ-9999"}),
            ("look_up_error_code", {"error_code": "LIM-4004"}),
            ("look_up_error_code", {"error_code": "not a code"}),
            ("retrieve_system_version", {"component": "Nope"}),
            ("check_service_health", {"component": "Nope"}),
        )
        seen = set()
        for name, arguments in misses:
            result = registry.call(name, arguments)
            assert not result.ok, (name, arguments)
            assert result.error_code in TOOL_FAILURE_CODES, result.error_code
            seen.add(result.error_code)
        assert len(seen) >= 4, "expected the richer vocabulary to be exercised"

    def test_every_declared_code_is_upper_snake_case(self):
        for code in TOOL_FAILURE_CODES:
            assert code.isupper()
            assert " " not in code
