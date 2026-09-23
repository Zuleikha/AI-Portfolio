"""The six synthetic support tools, and the consistency between them.

Two kinds of test live here.

**Per-tool** tests assert the properties the contract demands of everything —
purity, case-insensitivity, canonical echo, not-found-is-data — plus the handful
of domain facts each tool exists to get right.

**Cross-tool** tests are the ones worth reading. The six tools were built in
parallel by six sub-agents that could not see each other's work, each owning its
own synthetic dataset. That is what made the parallel build possible and it is
also the one thing that can make two tools contradict each other. These tests are
the guard that replaces the shared constants module we deliberately did not
write; the version test below encodes a contradiction that actually occurred and
was fixed at integration (``docs/HANDOVER.md`` §6.C).
"""

from __future__ import annotations

import pytest

from app.mcp.base import ToolInputError
from app.mcp.models import ToolResult
from app.mcp.registry import ToolRegistry

COMPONENTS: tuple[str, ...] = (
    "TransactionSwitch",
    "AuthorizationService",
    "CardSecurityModule",
    "LimitService",
    "CoreBankingAdapter",
    "PaymentEngine",
    "DigitalGateway",
    "DeviceManager",
    "ConfigurationStore",
)

COMPONENT_TOOLS: tuple[str, ...] = (
    "get_component_status",
    "retrieve_system_version",
    "check_service_health",
)
"""The three tools that take a component name and must agree about the set."""


# --- Contract properties, asserted against every tool ---------------------


class TestEveryToolObeysTheContract:
    def test_every_tool_is_pure(self, tool_registry: ToolRegistry):
        """Same arguments, same result -- the basis of the whole offline suite."""
        calls = (
            (
                "get_system_configuration",
                {"component": "LimitService", "key": "limits.currency"},
            ),
            (
                "check_transaction_status",
                {"transaction_reference": "TXN-20260911-004182"},
            ),
            ("get_component_status", {"component": "LimitService"}),
            ("look_up_error_code", {"error_code": "LIM-4001"}),
            ("retrieve_system_version", {}),
            ("check_service_health", {}),
        )
        for name, arguments in calls:
            first = tool_registry.call(name, arguments)
            second = tool_registry.call(name, arguments)
            assert first == second, name

    def test_every_tool_rejects_an_undeclared_argument(
        self, tool_registry: ToolRegistry
    ):
        for spec in tool_registry.specs():
            with pytest.raises(ToolInputError, match="does not accept"):
                tool_registry.call(spec.name, {"definitely_not_a_parameter": "x"})

    def test_a_required_argument_is_enforced(self, tool_registry: ToolRegistry):
        for spec in tool_registry.specs():
            if not spec.required_parameters:
                continue
            with pytest.raises(ToolInputError):
                tool_registry.call(spec.name, {})

    def test_a_blank_required_argument_is_rejected(self, tool_registry: ToolRegistry):
        for spec in tool_registry.specs():
            if not spec.required_parameters:
                continue
            blank = {name: "   " for name in spec.required_parameters}
            with pytest.raises(ToolInputError):
                tool_registry.call(spec.name, blank)

    def test_an_optional_argument_may_be_omitted(self, tool_registry: ToolRegistry):
        """Two tools take an optional component and must answer without it."""
        optional = [
            spec.name
            for spec in tool_registry.specs()
            if spec.parameters and not spec.required_parameters
        ]
        assert set(optional) == {"retrieve_system_version", "check_service_health"}
        for name in optional:
            assert tool_registry.call(name, {}).ok

    def test_a_blank_optional_argument_means_omitted(self, tool_registry: ToolRegistry):
        for name in ("retrieve_system_version", "check_service_health"):
            assert tool_registry.call(name, {"component": "   "}).ok

    def test_no_tool_result_carries_a_secret(self, tool_registry: ToolRegistry):
        """Nothing in this layer may emit anything credential-shaped."""
        forbidden = ("password", "secret", "api_key", "token", "credential")
        for spec in tool_registry.specs():
            arguments = {
                name: _example(tool_registry, spec.name, name)
                for name in spec.required_parameters
            }
            body = tool_registry.call(spec.name, arguments).model_dump_json().lower()
            for word in forbidden:
                assert f'"{word}"' not in body, (spec.name, word)


def _example(registry: ToolRegistry, tool: str, parameter: str) -> str:
    """The spec's own documented example for one parameter."""
    for candidate in registry.get(tool).spec.parameters:
        if candidate.name == parameter:
            return candidate.example
    raise AssertionError(f"{tool} has no parameter {parameter}")


class TestEverySpecExampleActuallyWorks:
    """A documented example that does not resolve is worse than no example.

    The examples are published in every spec an MCP client lists, as the format
    to imitate.
    """

    def test_calling_each_tool_with_its_own_examples_succeeds(
        self, tool_registry: ToolRegistry
    ):
        for spec in tool_registry.specs():
            arguments = {p.name: p.example for p in spec.parameters}
            result = tool_registry.call(spec.name, arguments)
            assert result.ok, (spec.name, arguments, result.summary)


# --- Cross-tool consistency ------------------------------------------------


class TestToolsAgreeWithEachOther:
    def test_the_component_tools_accept_the_same_nine_components(
        self, tool_registry: ToolRegistry
    ):
        for tool in COMPONENT_TOOLS:
            for component in COMPONENTS:
                result = tool_registry.call(tool, {"component": component})
                assert result.ok, (tool, component)

    def test_the_component_tools_echo_the_same_canonical_spelling(
        self, tool_registry: ToolRegistry
    ):
        for component in COMPONENTS:
            echoed = {
                tool_registry.call(tool, {"component": component}).data["component"]
                for tool in COMPONENT_TOOLS
            }
            assert echoed == {component}, (component, echoed)

    def test_the_component_tools_all_match_case_insensitively(
        self, tool_registry: ToolRegistry
    ):
        for tool in COMPONENT_TOOLS:
            lowered = tool_registry.call(tool, {"component": "limitservice"})
            assert lowered.ok, tool
            assert lowered.data["component"] == "LimitService"

    def test_health_and_version_agree_about_every_running_version(
        self, tool_registry: ToolRegistry
    ):
        """The contradiction that actually happened, now impossible to reintroduce.

        ``check_service_health`` originally reported the documented platform
        line ``4.2`` for all nine services, while ``retrieve_system_version``
        knew two of them had not reached the current build. Two tools
        contradicting each other about the same fact is worse than either being
        absent.
        """
        fleet = tool_registry.call("retrieve_system_version", {}).data["components"]
        assert isinstance(fleet, list)
        for entry in fleet:
            assert isinstance(entry, dict)
            component = entry["component"]
            expected = entry["running_version"]
            health = tool_registry.call(
                "check_service_health", {"component": component}
            )
            assert health.data["reported_version"] == expected, component
            # The summary is prose a human reads and the model quotes, so it
            # must not contradict the payload beside it. It did, once: the
            # payload was fixed at integration and the summary was not.
            assert str(expected) in health.summary, component

    def test_the_error_codes_a_transaction_reports_are_all_in_the_catalogue(
        self, tool_registry: ToolRegistry
    ):
        """A transaction must not report a code the lookup tool cannot explain."""
        references = (
            "TXN-20260911-004317",
            "TXN-20260911-004320",
            "TXN-20260911-004401",
            "TXN-20260911-004455",
            "TXN-20260911-004473",
            "TXN-20260911-004488",
        )
        for reference in references:
            data = tool_registry.call(
                "check_transaction_status", {"transaction_reference": reference}
            ).data
            for field in ("error_code", "decline_reason"):
                code = data.get(field)
                if not code:
                    continue
                looked_up = tool_registry.call(
                    "look_up_error_code", {"error_code": str(code)}
                )
                assert looked_up.ok, (reference, field, code)

    def test_component_status_and_error_codes_agree_about_ownership(
        self, tool_registry: ToolRegistry
    ):
        """A component's recent error codes must carry that component's prefix."""
        for component in COMPONENTS:
            data = tool_registry.call(
                "get_component_status", {"component": component}
            ).data
            codes = data.get("recent_error_codes") or []
            assert isinstance(codes, list)
            for code in codes:
                looked_up = tool_registry.call(
                    "look_up_error_code", {"error_code": str(code)}
                )
                assert looked_up.ok, code
                assert looked_up.data["component"] == component, (component, code)


# --- What each tool must get right ----------------------------------------


class TestErrorCodeLookup:
    def test_a_limit_code_maps_to_the_documented_configuration_key(
        self, tool_registry: ToolRegistry
    ):
        data = tool_registry.call("look_up_error_code", {"error_code": "LIM-4001"}).data
        assert data["component"] == "LimitService"
        assert data["breached_configuration_key"] == (
            "limits.atm.daily_withdrawal_amount"
        )

    def test_the_payment_wrapper_code_is_flagged_as_a_wrapper(
        self, tool_registry: ToolRegistry
    ):
        """The documented "most common diagnostic mistake in payments"."""
        result = tool_registry.call("look_up_error_code", {"error_code": "PAY-8003"})
        assert result.data["is_wrapper"] is True
        assert "decline_reason" in str(result.data["wrapper_guidance"])

    def test_the_reversal_code_is_not_described_as_triggering_one(
        self, tool_registry: ToolRegistry
    ):
        data = tool_registry.call("look_up_error_code", {"error_code": "SWX-7004"}).data
        assert data["triggers_reversal"] is False
        assert data["reversal_role"] == "is_reversal"

    def test_a_known_prefix_with_an_unknown_number_says_so_specifically(
        self, tool_registry: ToolRegistry
    ):
        result = tool_registry.call("look_up_error_code", {"error_code": "LIM-4004"})
        assert not result.ok
        assert result.error_code == "UNKNOWN_CODE_FOR_COMPONENT"
        assert "LimitService" in result.summary

    def test_case_is_normalised(self, tool_registry: ToolRegistry):
        lower = tool_registry.call("look_up_error_code", {"error_code": "lim-4001"})
        upper = tool_registry.call("look_up_error_code", {"error_code": "LIM-4001"})
        assert lower == upper


class TestTransactionStatus:
    def test_a_completed_withdrawal_reaches_the_last_stage(
        self, tool_registry: ToolRegistry
    ):
        data = tool_registry.call(
            "check_transaction_status",
            {"transaction_reference": "TXN-20260911-004182"},
        ).data
        assert data["outcome"] == "COMPLETED"
        assert data["stage_reached"] == 8

    def test_a_limit_rejection_stops_at_the_limit_stage(
        self, tool_registry: ToolRegistry
    ):
        data = tool_registry.call(
            "check_transaction_status",
            {"transaction_reference": "TXN-20260911-004317"},
        ).data
        assert data["error_code"] == "LIM-4001"
        assert data["stage_reached"] == 4
        assert data["stage_component"] == "LimitService"

    def test_a_failure_after_card_authentication_records_that_it_passed(
        self, tool_registry: ToolRegistry
    ):
        """Stages 2-3 are card authentication; stage 4 onward is after it."""
        data = tool_registry.call(
            "check_transaction_status",
            {"transaction_reference": "TXN-20260911-004317"},
        ).data
        assert data["card_authentication"] == "PASSED"

    def test_an_unacknowledged_reversal_is_visible(self, tool_registry: ToolRegistry):
        data = tool_registry.call(
            "check_transaction_status",
            {"transaction_reference": "TXN-20260911-004473"},
        ).data
        reversal = data["reversal"]
        assert isinstance(reversal, dict)
        assert reversal["state"] == "UNACKNOWLEDGED"

    def test_the_wrapper_decline_carries_its_underlying_code(
        self, tool_registry: ToolRegistry
    ):
        data = tool_registry.call(
            "check_transaction_status",
            {"transaction_reference": "TXN-20260911-004488"},
        ).data
        assert data["error_code"] == "PAY-8003"
        assert data["decline_reason"]

    def test_an_unknown_reference_is_a_finding_not_an_error(
        self, tool_registry: ToolRegistry
    ):
        result = tool_registry.call(
            "check_transaction_status",
            {"transaction_reference": "TXN-19990101-000001"},
        )
        assert isinstance(result, ToolResult)
        assert not result.ok
        assert result.error_code == "NOT_FOUND"


class TestSystemConfiguration:
    def test_the_effective_value_can_differ_from_the_documented_default(
        self, tool_registry: ToolRegistry
    ):
        """The reason a config tool exists alongside the configuration reference."""
        data = tool_registry.call(
            "get_system_configuration",
            {"component": "LimitService", "key": "limits.atm.per_transaction_amount"},
        ).data
        assert data["documented_default"] == "500.00"
        assert data["value"] != data["documented_default"]
        assert data["differs_from_documented_default"] is True

    def test_the_precedence_level_is_reported(self, tool_registry: ToolRegistry):
        data = tool_registry.call(
            "get_system_configuration",
            {"component": "LimitService", "key": "limits.atm.per_transaction_amount"},
        ).data
        assert data["precedence"] == "account_override"

    def test_a_credential_shaped_key_is_refused(self, tool_registry: ToolRegistry):
        """ConfigurationStore holds operational values only, per the corpus."""
        result = tool_registry.call(
            "get_system_configuration",
            {"component": "CoreBankingAdapter", "key": "core.db_password"},
        )
        assert not result.ok
        assert result.error_code == "SECRET_NOT_SERVED"
        assert result.data == {}

    def test_the_secret_refusal_is_not_a_component_oracle(
        self, tool_registry: ToolRegistry
    ):
        """A secret-looking key must refuse before revealing whether X exists."""
        result = tool_registry.call(
            "get_system_configuration",
            {"component": "NotAComponent", "key": "some.secret"},
        )
        assert result.error_code == "SECRET_NOT_SERVED"

    def test_an_unknown_key_is_distinguished_from_an_unknown_component(
        self, tool_registry: ToolRegistry
    ):
        unknown_key = tool_registry.call(
            "get_system_configuration",
            {"component": "LimitService", "key": "limits.nope"},
        )
        unknown_component = tool_registry.call(
            "get_system_configuration",
            {"component": "Nope", "key": "limits.currency"},
        )
        assert unknown_key.error_code == "UNKNOWN_KEY"
        assert unknown_component.error_code == "UNKNOWN_COMPONENT"


class TestComponentStatus:
    def test_a_degraded_component_reports_why(self, tool_registry: ToolRegistry):
        data = tool_registry.call(
            "get_component_status", {"component": "CoreBankingAdapter"}
        ).data
        assert data["state"] == "DEGRADED"
        assert data["degradation_reason"]

    def test_the_three_letter_code_resolves(self, tool_registry: ToolRegistry):
        assert (
            tool_registry.call("get_component_status", {"component": "COR"}).data
            == tool_registry.call(
                "get_component_status", {"component": "CoreBankingAdapter"}
            ).data
        )

    def test_an_incident_links_cause_to_effect(self, tool_registry: ToolRegistry):
        """The origin and the impacted component share one incident id."""
        origin = tool_registry.call(
            "get_component_status", {"component": "CoreBankingAdapter"}
        ).data["active_incident"]
        impacted = tool_registry.call(
            "get_component_status", {"component": "TransactionSwitch"}
        ).data["active_incident"]
        assert isinstance(origin, dict)
        assert isinstance(impacted, dict)
        assert origin["id"] == impacted["id"]
        assert origin["role"] != impacted["role"]


class TestServiceHealth:
    def test_an_unhealthy_service_is_still_a_successful_call(
        self, tool_registry: ToolRegistry
    ):
        """ok describes the lookup, not the thing looked at."""
        result = tool_registry.call(
            "check_service_health", {"component": "CoreBankingAdapter"}
        )
        assert result.ok is True
        assert result.data["status"] == "DEGRADED"

    def test_a_failing_dependency_check_is_named(self, tool_registry: ToolRegistry):
        data = tool_registry.call(
            "check_service_health", {"component": "CoreBankingAdapter"}
        ).data
        failing = data["failing_checks"]
        assert isinstance(failing, list)
        assert failing

    def test_the_rollup_reports_the_worst_status(self, tool_registry: ToolRegistry):
        data = tool_registry.call("check_service_health", {}).data
        assert data["overall_status"] == "DEGRADED"

    def test_the_endpoint_matches_the_documented_pattern(
        self, tool_registry: ToolRegistry
    ):
        data = tool_registry.call(
            "check_service_health", {"component": "CoreBankingAdapter"}
        ).data
        assert str(data["endpoint"]).endswith("/v1/health")

    def test_health_is_liveness_not_throughput(self, tool_registry: ToolRegistry):
        """The division of labour with get_component_status, asserted."""
        data = tool_registry.call(
            "check_service_health", {"component": "CoreBankingAdapter"}
        ).data
        assert "checks" in data
        assert "requests_per_minute" not in data
        assert "queue_depth" not in data

    def test_component_status_is_throughput_not_liveness(
        self, tool_registry: ToolRegistry
    ):
        data = tool_registry.call(
            "get_component_status", {"component": "CoreBankingAdapter"}
        ).data
        assert "requests_per_minute" in data
        assert "probe_latency_ms" not in data


class TestSystemVersion:
    def test_the_fleet_view_needs_no_arguments(self, tool_registry: ToolRegistry):
        data = tool_registry.call("retrieve_system_version", {}).data
        assert data["platform_version"] == "4.2"
        components = data["components"]
        assert isinstance(components, list)
        assert len(components) == 9

    def test_version_drift_is_surfaced(self, tool_registry: ToolRegistry):
        """A component behind the platform build is the point of the tool."""
        data = tool_registry.call(
            "retrieve_system_version", {"component": "CardSecurityModule"}
        ).data
        assert data["running_version"] == "4.1.9"
        assert data["up_to_date"] is False
        assert data["drift"] is not None

    def test_an_aligned_component_reports_no_drift_object(
        self, tool_registry: ToolRegistry
    ):
        data = tool_registry.call(
            "retrieve_system_version", {"component": "PaymentEngine"}
        ).data
        assert data["up_to_date"] is True
        assert data["drift"] is None

    def test_the_fleet_view_flags_that_drift_exists(self, tool_registry: ToolRegistry):
        data = tool_registry.call("retrieve_system_version", {}).data
        assert data["drift_detected"] is True
