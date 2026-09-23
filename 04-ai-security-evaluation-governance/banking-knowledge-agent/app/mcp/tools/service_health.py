"""The liveness/readiness probe tool: ``GET /{component}/v1/health``.

This tool answers one question and refuses to answer any other: *does the
service answer its health endpoint, how fast, which version does it report, and
are the dependencies it declares in that response passing?* The corpus documents
the endpoint in ``api/api-integration-guide.md`` as ``GET /{component}/v1/health``
returning "Liveness and version", and this module is the synthetic reading of
exactly that endpoint for the nine runtime components in
``platform/platform-component-overview.md``.

**Why this is not ``get_component_status``.** The two tools were deliberately
split rather than merged, and the split is the interesting design decision here:

===================  =====================================================
``check_service_health``   the *probe*. Kubernetes readiness, not Grafana.
                           Does the endpoint answer, in how many milliseconds,
                           at which version, with which declared dependency
                           checks passing (database, HSM pool, downstream
                           service, message broker, configuration refresh).
``get_component_status``   the *operational picture* during an incident.
                           Instance counts, error rate, throughput, queue
                           depth, active incident, degradation reason.
===================  =====================================================

Merging them was considered and rejected. **A service can pass its liveness
probe and still be operationally degraded** — a process that answers ``200`` in
4 ms while rejecting 30% of real traffic is *live* and *broken*, and those are
different facts that a support engineer reaches for at different moments. One
tool returning both would force every caller to receive the whole incident
dashboard in order to ask "is the endpoint answering at all?", and — worse —
would let a healthy probe result be read as an all-clear on throughput. The gap
between the two answers *is* the diagnostic signal; collapsing it destroys the
signal.

**``ok`` is about the tool, not about the service.** This is the rule that is
easiest to get backwards and does the most damage when it is:

* ``ok=True`` — the probe was performed and its outcome is reported. A service
  that is ``DEGRADED`` or ``DOWN`` is still ``ok=True``: the tool successfully
  determined the health, and "this service is failing" is a true, useful,
  *successful* answer.
* ``ok=False`` — the tool could not answer the question at all. In this module
  that has exactly one cause: a component name nobody has heard of, reported as
  ``NOT_FOUND``.

Were a ``DOWN`` service returned as ``ok=False``, "TransactionSwitch is down"
and "there is no such service as TransactionSwtich" would arrive at the agent as
the same shape, and a typo in a component name would be escalated as an outage.
That is the same argument :mod:`app.mcp.base` makes about failures versus
errors, applied one level in.

**Why the ``component`` argument is optional.** The question a support engineer
actually opens with is "is anything unhealthy?", not "is CoreBankingAdapter
unhealthy?" — the second question only exists once the first has been answered.
So omitting the argument returns the roll-up across all nine services plus an
overall status, and supplying it returns one service's probe detail. This is why
:func:`app.mcp.base.require_argument` is *not* used for it: that helper raises
:class:`~app.mcp.base.ToolInputError` on absence, which is right for a mandatory
identifier and wrong here, where absence is a legitimate and common call. A
blank or whitespace-only value is treated as absence rather than as a component
named ``""``, so that a caller doing ``{"component": ""}`` gets the roll-up
instead of a spurious ``NOT_FOUND``.
:func:`app.mcp.base.reject_unknown_arguments` still runs, because "optional"
applies to ``component`` and not to arguments the tool has never heard of.

**The synthetic reading, and why it hangs together.** The dataset below is a
single frozen instant, chosen to be diagnostically instructive rather than
uniformly green. CoreBankingAdapter's ``core_banking_connection_pool`` check is
``FAIL`` (all 40 of ``core.connection_pool_size`` in use, callers rejected with
``COR-5015``, calls over ``core.request_timeout_ms`` abandoning with
``COR-5008``), and TransactionSwitch's ``core_banking_adapter`` downstream check
is ``FAIL`` for that reason, producing ``SWX-7001`` at the switch. Cause and
effect are therefore traceable across two services and both are consistent with
``api/core-banking-integration.md`` and ``operations/incident-response-runbook.md``.
PaymentEngine carries the same root cause as a ``WARN`` and stays ``UP``, which
is the blast radius made visible. No service is fabricated as fully ``DOWN``: a
degraded service with a named failing dependency teaches how to read a health
response, whereas a dead process teaches only that a process is dead.

**Nothing here is probed.** No socket, no HTTP client, no filesystem, no clock,
no randomness — :meth:`ServiceHealthTool.invoke` reads a module-level tuple of
frozen dataclasses and returns. Same arguments, same result, every call, in
every session, which is the purity contract :class:`app.mcp.base.Tool` requires
and what makes the demo output stable. Every service reports platform version
``4.2`` because the corpus states components are released together as one
platform version; inventing per-component patch drift here would have
contradicted :data:`app.mcp.models.ToolName`'s ``retrieve_system_version`` tool
for the sake of decoration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import JsonValue

from app.core.tracing import traced
from app.mcp.base import reject_unknown_arguments
from app.mcp.models import ToolName, ToolParameter, ToolResult, ToolSpec

ServiceStatus = Literal["UP", "DEGRADED", "DOWN"]
"""The three-value health vocabulary this tool reports.

``UP`` — the probe answered and every declared dependency check is passing (a
``WARN`` check still passes). ``DEGRADED`` — the probe answered, so the service
is live, but at least one declared dependency check is failing. ``DOWN`` — the
probe did not answer. Deliberately not a boolean: the whole reason a readiness
probe reports dependency checks is that "answering" and "fit to serve" are
different states, and a boolean would erase the one in the middle that most
incidents actually live in.
"""

CheckStatus = Literal["PASS", "WARN", "FAIL"]
"""The outcome of one dependency check inside a health response.

``WARN`` is a *passing* state — the dependency answered inside its budget but
with a measurement worth reading, such as latency climbing towards a timeout.
It exists because ``csm.hsm_request_timeout_ms`` breaches show up as elevated
latency long before they show up as ``CSM-3010``, and a two-valued check would
have to call that either fine or broken when it is neither. Each rendered check
therefore carries both ``status`` and a plain ``passed`` boolean, so a caller
that only wants pass/fail never has to learn what ``WARN`` means.
"""

CheckKind = Literal["database", "hsm_pool", "downstream", "broker", "configuration"]
"""What sort of dependency a check covers, for grouping and filtering."""

_TOOL: Final[ToolName] = "check_service_health"
"""This tool's registry name, taken from the closed literal in the models."""

_COMPONENT_ARGUMENT: Final[str] = "component"
"""The single, optional argument name."""

_PLATFORM_VERSION: Final[str] = "4.2"
"""The documented platform release line, as stated in the component overview."""

_PLATFORM_BUILD: Final[str] = "4.2.3"
"""The build every service is expected to be running.

**Set at integration, not by this module's author.** The health endpoint is
documented to return liveness *and version*, and this module originally reported
the platform line ``4.2`` for all nine services -- which flatly contradicted
``retrieve_system_version``, built in parallel, which knows that two components
have not reached the current build. Two tools disagreeing about the same fact is
worse than either tool being absent. The per-service overrides below now match
that tool exactly, and ``tests/test_mcp_tools.py`` asserts the agreement so the
two datasets cannot drift apart again.
"""
"""The platform version every component reports, per the component overview."""

_ENDPOINT_PATTERN: Final[str] = "/{component}/v1/health"
"""The documented health endpoint, echoed so a reader can verify the source."""

_ERROR_NOT_FOUND: Final[str] = "NOT_FOUND"
"""The only ``ok=False`` code this tool can produce: no such component."""

_STATUS_SEVERITY: Final[Mapping[ServiceStatus, int]] = {
    "UP": 0,
    "DEGRADED": 1,
    "DOWN": 2,
}
"""Ordering used to roll nine service statuses up into one overall status.

The roll-up is the worst status present, not an average or a majority. Eight
healthy services do not dilute one failing one, and a caller asking "is anything
unhealthy?" is asking precisely for the maximum.
"""


def _format_uptime(seconds: int) -> str:
    """Render an uptime in seconds as ``Nd HHh MMm``.

    Derived from the seconds rather than stored alongside them, so the two can
    never drift apart in the dataset below.

    Args:
        seconds: Whole seconds of uptime.

    Returns:
        The human-readable form, e.g. ``18d 06h 12m``.
    """
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    return f"{days}d {hours:02d}h {minutes:02d}m"


@dataclass(frozen=True, slots=True)
class _Check:
    """One dependency check a service declares in its health response."""

    name: str
    kind: CheckKind
    status: CheckStatus
    detail: str

    @property
    def passed(self) -> bool:
        """Whether this check is not failing. ``WARN`` counts as passing."""
        return self.status != "FAIL"

    def payload(self) -> dict[str, JsonValue]:
        """Render the check as the JSON-safe mapping a result carries."""
        return {
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class _ServiceHealth:
    """One service's synthetic reading of ``GET /{component}/v1/health``."""

    component: str
    code: str
    path_segment: str
    status: ServiceStatus
    probe_latency_ms: float
    uptime_seconds: int
    note: str
    related_error_codes: tuple[str, ...]
    checks: tuple[_Check, ...]
    reported_version: str = _PLATFORM_BUILD

    @property
    def endpoint(self) -> str:
        """The documented path this reading came from."""
        return f"/{self.path_segment}/v1/health"

    @property
    def failing_checks(self) -> tuple[str, ...]:
        """Names of the dependency checks reporting ``FAIL``."""
        return tuple(check.name for check in self.checks if not check.passed)

    @property
    def warning_checks(self) -> tuple[str, ...]:
        """Names of the dependency checks reporting ``WARN``."""
        return tuple(check.name for check in self.checks if check.status == "WARN")

    def brief(self) -> dict[str, JsonValue]:
        """Render the one-line form used inside the all-services roll-up."""
        failing: list[JsonValue] = list(self.failing_checks)
        return {
            "component": self.component,
            "component_code": self.code,
            "status": self.status,
            "endpoint": self.endpoint,
            "probe_latency_ms": self.probe_latency_ms,
            "failing_checks": failing,
            "note": self.note,
        }

    def payload(self) -> dict[str, JsonValue]:
        """Render the full single-service form, checks included."""
        checks: list[JsonValue] = [check.payload() for check in self.checks]
        failing: list[JsonValue] = list(self.failing_checks)
        warning: list[JsonValue] = list(self.warning_checks)
        codes: list[JsonValue] = list(self.related_error_codes)
        return {
            "scope": "single_service",
            "component": self.component,
            "component_code": self.code,
            "status": self.status,
            "probe_latency_ms": self.probe_latency_ms,
            "endpoint": self.endpoint,
            "health_endpoint_pattern": _ENDPOINT_PATTERN,
            "reported_version": self.reported_version,
            "platform_version": _PLATFORM_VERSION,
            "uptime": _format_uptime(self.uptime_seconds),
            "uptime_seconds": self.uptime_seconds,
            "checks": checks,
            "checks_total": len(self.checks),
            "checks_passing": sum(1 for check in self.checks if check.passed),
            "failing_checks": failing,
            "warning_checks": warning,
            "related_error_codes": codes,
            "note": self.note,
        }

    def summary(self) -> str:
        """Write the one human-readable line for this service's probe."""
        passing = sum(1 for check in self.checks if check.passed)
        detail = ""
        if self.failing_checks:
            detail = f", failing: {', '.join(self.failing_checks)}"
        return (
            f"{self.component} ({self.code}) is {self.status}: "
            f"{self.endpoint} answered in {self.probe_latency_ms:.1f} ms at version "
            f"{self.reported_version}, {passing}/{len(self.checks)} dependency checks "
            f"passing{detail}."
        )


_SERVICES: Final[tuple[_ServiceHealth, ...]] = (
    _ServiceHealth(
        component="TransactionSwitch",
        code="SWX",
        path_segment="switch",
        status="DEGRADED",
        probe_latency_ms=148.4,
        uptime_seconds=1_577_520,
        note=(
            "Live and routing, but the CoreBankingAdapter leg is over budget, so "
            "a share of transactions is abandoned with SWX-7001. The switch names "
            "the timeout; the fault is downstream of it."
        ),
        related_error_codes=("SWX-7001",),
        checks=(
            _Check(
                name="authorization_service",
                kind="downstream",
                status="PASS",
                detail="AuthorizationService health probe answered in 11 ms.",
            ),
            _Check(
                name="core_banking_adapter",
                kind="downstream",
                status="FAIL",
                detail=(
                    "CoreBankingAdapter answered but reports DEGRADED; its call leg "
                    "is exceeding switch.downstream_timeout_ms (8000 ms) and those "
                    "transactions abandon with SWX-7001."
                ),
            ),
            _Check(
                name="limit_service",
                kind="downstream",
                status="PASS",
                detail="LimitService health probe answered in 8 ms.",
            ),
            _Check(
                name="device_manager",
                kind="downstream",
                status="PASS",
                detail="DeviceManager health probe answered in 10 ms.",
            ),
            _Check(
                name="reversal_queue",
                kind="broker",
                status="WARN",
                detail=(
                    "Broker reachable; reversal queue depth 214 and rising, drained "
                    "through the same saturated core banking path "
                    "(switch.reversal_retry_count=3)."
                ),
            ),
            _Check(
                name="configuration_refresh",
                kind="configuration",
                status="PASS",
                detail="Config version cfg-4.2-0198 applied; no refresh pending.",
            ),
        ),
    ),
    _ServiceHealth(
        component="AuthorizationService",
        code="AUT",
        path_segment="cards",
        status="UP",
        probe_latency_ms=9.4,
        uptime_seconds=2_768_700,
        note="Probe healthy; every declared dependency answering inside budget.",
        related_error_codes=(),
        checks=(
            _Check(
                name="card_registry_database",
                kind="database",
                status="PASS",
                detail="Read and write probes both under 4 ms.",
            ),
            _Check(
                name="card_security_module",
                kind="downstream",
                status="PASS",
                detail="CardSecurityModule health probe answered in 13 ms.",
            ),
            _Check(
                name="limit_service",
                kind="downstream",
                status="PASS",
                detail="LimitService health probe answered in 8 ms.",
            ),
            _Check(
                name="configuration_refresh",
                kind="configuration",
                status="PASS",
                detail="Config version cfg-4.2-0198 applied; no refresh pending.",
            ),
        ),
    ),
    _ServiceHealth(
        component="CardSecurityModule",
        code="CSM",
        reported_version="4.1.9",
        path_segment="csm",
        status="UP",
        probe_latency_ms=12.7,
        uptime_seconds=1_032_060,
        note=(
            "HSM pool fully established. Rising HSM latency is the early warning "
            "for CSM-3010, so this check is worth reading even when it passes."
        ),
        related_error_codes=(),
        checks=(
            _Check(
                name="hsm_pool",
                kind="hsm_pool",
                status="PASS",
                detail=(
                    "8 of 8 HSM connections established (csm.hsm_pool_size=8); "
                    "slowest member answered in 41 ms against a 2000 ms "
                    "csm.hsm_request_timeout_ms. No CSM-3010 in the probe window."
                ),
            ),
            _Check(
                name="key_store_database",
                kind="database",
                status="PASS",
                detail="Key metadata store answered in 3 ms.",
            ),
            _Check(
                name="configuration_refresh",
                kind="configuration",
                status="PASS",
                detail="Config version cfg-4.2-0198 applied; no refresh pending.",
            ),
        ),
    ),
    _ServiceHealth(
        component="LimitService",
        code="LIM",
        reported_version="4.2.2",
        path_segment="limits",
        status="UP",
        probe_latency_ms=7.8,
        uptime_seconds=2_768_640,
        note="Probe healthy; limit counters and velocity cache both responsive.",
        related_error_codes=(),
        checks=(
            _Check(
                name="limit_counter_database",
                kind="database",
                status="PASS",
                detail="Counter store answered in 3 ms; no replication lag.",
            ),
            _Check(
                name="velocity_cache",
                kind="database",
                status="PASS",
                detail="Velocity window cache answered in 1 ms.",
            ),
            _Check(
                name="configuration_refresh",
                kind="configuration",
                status="PASS",
                detail="Config version cfg-4.2-0198 applied; no refresh pending.",
            ),
        ),
    ),
    _ServiceHealth(
        component="CoreBankingAdapter",
        code="COR",
        path_segment="core",
        status="DEGRADED",
        probe_latency_ms=312.5,
        uptime_seconds=15_960,
        note=(
            "Root cause of the current picture. The process is live and answers "
            "its probe, but the core banking connection pool is exhausted, so it "
            "is rejecting callers with COR-5015 and timing out with COR-5008. "
            "Restarted 04h26m ago as a mitigation; the pool re-saturated."
        ),
        related_error_codes=("COR-5015", "COR-5008"),
        checks=(
            _Check(
                name="core_banking_connection_pool",
                kind="downstream",
                status="FAIL",
                detail=(
                    "40 of 40 connections in use (core.connection_pool_size=40) "
                    "with 27 requests queued; new callers are rejected with "
                    "COR-5015."
                ),
            ),
            _Check(
                name="core_banking_session",
                kind="downstream",
                status="WARN",
                detail=(
                    "Core ledger reachable, but mean response 4180 ms against "
                    "core.request_timeout_ms=5000; anything over budget abandons "
                    "with COR-5008."
                ),
            ),
            _Check(
                name="posting_journal_database",
                kind="database",
                status="PASS",
                detail="Local posting journal answered in 5 ms.",
            ),
            _Check(
                name="configuration_refresh",
                kind="configuration",
                status="PASS",
                detail="Config version cfg-4.2-0198 applied; no refresh pending.",
            ),
        ),
    ),
    _ServiceHealth(
        component="PaymentEngine",
        code="PAY",
        path_segment="payments",
        status="UP",
        probe_latency_ms=11.2,
        uptime_seconds=2_193_480,
        note=(
            "Live and inside budget, but carrying the CoreBankingAdapter problem "
            "as a warning: the blast radius of the same root cause, one hop away."
        ),
        related_error_codes=(),
        checks=(
            _Check(
                name="authorisation_store_database",
                kind="database",
                status="PASS",
                detail="Authorisation store answered in 4 ms.",
            ),
            _Check(
                name="clearing_batch_broker",
                kind="broker",
                status="PASS",
                detail=(
                    "Clearing batch topic reachable; queue depth 12 "
                    "(payments.clearing_retry_count=3)."
                ),
            ),
            _Check(
                name="core_banking_adapter",
                kind="downstream",
                status="WARN",
                detail=(
                    "CoreBankingAdapter reports DEGRADED; settlement posting "
                    "latency elevated but still inside the payment retry budget."
                ),
            ),
            _Check(
                name="configuration_refresh",
                kind="configuration",
                status="PASS",
                detail="Config version cfg-4.2-0198 applied; no refresh pending.",
            ),
        ),
    ),
    _ServiceHealth(
        component="DigitalGateway",
        code="DGW",
        path_segment="digital",
        status="UP",
        probe_latency_ms=6.9,
        uptime_seconds=791_520,
        note="Probe healthy; session store and PaymentEngine leg both responsive.",
        related_error_codes=(),
        checks=(
            _Check(
                name="session_store",
                kind="database",
                status="PASS",
                detail=(
                    "Session store answered in 2 ms "
                    "(digital.session_ttl_minutes=30)."
                ),
            ),
            _Check(
                name="payment_engine",
                kind="downstream",
                status="PASS",
                detail="PaymentEngine health probe answered in 12 ms.",
            ),
            _Check(
                name="configuration_refresh",
                kind="configuration",
                status="PASS",
                detail="Config version cfg-4.2-0198 applied; no refresh pending.",
            ),
        ),
    ),
    _ServiceHealth(
        component="DeviceManager",
        code="DEV",
        path_segment="devices",
        status="UP",
        probe_latency_ms=10.3,
        uptime_seconds=2_193_420,
        note="Probe healthy; device state store and telemetry broker responsive.",
        related_error_codes=(),
        checks=(
            _Check(
                name="device_state_database",
                kind="database",
                status="PASS",
                detail="Device state store answered in 4 ms.",
            ),
            _Check(
                name="terminal_telemetry_broker",
                kind="broker",
                status="PASS",
                detail="Telemetry topic reachable; no consumer lag.",
            ),
            _Check(
                name="configuration_refresh",
                kind="configuration",
                status="PASS",
                detail="Config version cfg-4.2-0198 applied; no refresh pending.",
            ),
        ),
    ),
    _ServiceHealth(
        component="ConfigurationStore",
        code="CFG",
        path_segment="config",
        status="UP",
        probe_latency_ms=5.1,
        uptime_seconds=4_017_780,
        note=(
            "Probe healthy. Distributing cfg-4.2-0198, which every other "
            "component reports as applied."
        ),
        related_error_codes=(),
        checks=(
            _Check(
                name="configuration_database",
                kind="database",
                status="PASS",
                detail="Versioned configuration store answered in 2 ms.",
            ),
            _Check(
                name="distribution_broker",
                kind="broker",
                status="PASS",
                detail=(
                    "Change-notification topic reachable; all 9 components "
                    "acknowledged cfg-4.2-0198."
                ),
            ),
        ),
    ),
)
"""The frozen synthetic reading of all nine documented runtime components."""


def _build_index(
    services: tuple[_ServiceHealth, ...],
) -> Mapping[str, _ServiceHealth]:
    """Index services by every accepted spelling, case-folded.

    A caller may name a service by its canonical name (``CoreBankingAdapter``),
    its documented three-letter code (``COR``) or the path segment its endpoint
    uses (``core``) — all case-insensitively. Support engineers type all three,
    and a tool that only recognised one of them would return ``NOT_FOUND`` for a
    question that was perfectly clear.

    Args:
        services: The dataset to index.

    Returns:
        A mapping from case-folded alias to service.

    Raises:
        ValueError: If two different services claim the same alias. Fails at
            import rather than silently letting one shadow the other, which
            would make the answer depend on dataset ordering.
    """
    index: dict[str, _ServiceHealth] = {}
    for service in services:
        for alias in (service.component, service.code, service.path_segment):
            key = alias.casefold()
            existing = index.get(key)
            if existing is not None and existing is not service:
                raise ValueError(
                    f"Alias '{alias}' is claimed by both "
                    f"'{existing.component}' and '{service.component}'."
                )
            index[key] = service
    return index


_INDEX: Final[Mapping[str, _ServiceHealth]] = _build_index(_SERVICES)
"""Case-folded alias -> service lookup, built once at import."""

_KNOWN: Final[str] = ", ".join(
    f"{service.component} ({service.code})" for service in _SERVICES
)
"""The components this tool knows, for the ``NOT_FOUND`` message."""

_SPEC: Final[ToolSpec] = ToolSpec(
    name=_TOOL,
    summary="Report the health probe result for one service, or for every service.",
    description=(
        "Reads the documented liveness/readiness endpoint "
        "GET /{component}/v1/health for the nine Meridian runtime components: "
        "whether the endpoint answers, how long the probe took, the platform "
        "version it reports, its uptime, and the pass/fail state of each "
        "dependency check it declares (database, HSM pool, downstream service, "
        "message broker, configuration refresh). Omit 'component' for a roll-up "
        "across all services with an overall status; supply it for one "
        "service's probe detail. This is the probe, NOT the operational "
        "picture: it does not report instance counts, error rates, throughput, "
        "queue depth or active incidents - use get_component_status for those. "
        "A service can pass its liveness probe and still be operationally "
        "degraded. A DEGRADED or DOWN service is a successful result (ok=True); "
        "ok=False means only that no such component exists."
    ),
    parameters=(
        ToolParameter(
            name=_COMPONENT_ARGUMENT,
            description=(
                "Optional. The service to probe, by name, three-letter code or "
                "endpoint path segment, case-insensitive. Omit or leave blank "
                "for every service plus an overall roll-up status."
            ),
            required=False,
            example="CoreBankingAdapter",
        ),
    ),
)
"""This tool's half of the contract, built once and shared by every instance."""


def _roll_up() -> ToolResult:
    """Build the all-services result: overall status plus a per-service map.

    Returns:
        A successful result. The overall status is the worst status present.
    """
    tally: dict[str, int] = {"UP": 0, "DEGRADED": 0, "DOWN": 0}
    for service in _SERVICES:
        tally[service.status] += 1

    overall: ServiceStatus = max(
        _SERVICES, key=lambda service: _STATUS_SEVERITY[service.status]
    ).status
    not_up = tuple(service for service in _SERVICES if service.status != "UP")

    status_counts: dict[str, JsonValue] = {
        status: count for status, count in tally.items()
    }
    service_status: dict[str, JsonValue] = {
        service.component: service.status for service in _SERVICES
    }
    attention: list[JsonValue] = [service.brief() for service in not_up]

    data: dict[str, JsonValue] = {
        "scope": "all_services",
        "overall_status": overall,
        "platform_version": _PLATFORM_VERSION,
        "health_endpoint_pattern": _ENDPOINT_PATTERN,
        "services_total": len(_SERVICES),
        "services_up": tally["UP"],
        "services_not_up": len(not_up),
        "status_counts": status_counts,
        "service_status": service_status,
        "needs_attention": attention,
    }

    if not_up:
        named = ", ".join(f"{s.component} {s.status}" for s in not_up)
        tail = f"{len(not_up)} not UP ({named})"
    else:
        tail = "0 not UP"
    summary = (
        f"Platform health {overall}: {tally['UP']}/{len(_SERVICES)} services UP, "
        f"{tail}."
    )
    return ToolResult.success(tool=_TOOL, summary=summary, data=data)


class ServiceHealthTool:
    """Reports the ``GET /{component}/v1/health`` probe for Meridian services.

    Implements :class:`app.mcp.base.Tool` structurally — no inheritance, no
    registration side effect. The instance holds no state: the dataset, the
    index and the spec are all module-level and frozen, so two instances are
    interchangeable and neither can be mutated into disagreeing with the other.

    **What ``ok`` means here, restated because it is the easiest thing to get
    backwards.** ``ok=True`` says the probe was performed and its outcome is
    reported — including when that outcome is ``DEGRADED`` or ``DOWN``, which
    are true and useful answers, not failures of this tool. ``ok=False`` says
    the tool could not answer at all, which in this module happens only for an
    unknown component and is reported as ``NOT_FOUND``. Reporting an unhealthy
    service as ``ok=False`` would make "the service is down" and "there is no
    such service" indistinguishable to the agent above.

    **What this tool does not answer.** Instance counts, error rate, throughput,
    queue depth, active incident and degradation reason belong to
    ``get_component_status``. A green probe here is not an all-clear there.
    """

    @property
    def spec(self) -> ToolSpec:
        """What this tool is and how to call it."""
        return _SPEC

    @traced
    def invoke(self, arguments: Mapping[str, str]) -> ToolResult:
        """Report health for one service, or for all of them.

        Args:
            arguments: May contain ``component`` — a service name, three-letter
                code or endpoint path segment, case-insensitive. Absent, empty
                or whitespace-only means "every service", which is a normal
                call and not an input error.

        Returns:
            A result with ``ok=True`` carrying either the all-services roll-up
            (overall status, per-service status map, count of anything not UP)
            or one service's probe detail (status, probe latency, endpoint,
            reported version, uptime and its dependency checks). A result with
            ``ok=False`` and ``error_code="NOT_FOUND"`` when no component
            matches — the only failure this tool can report. An unhealthy
            service is never ``ok=False``.

        Raises:
            ToolInputError: If an argument the tool does not declare was passed.
        """
        reject_unknown_arguments(arguments, _SPEC)

        requested = (arguments.get(_COMPONENT_ARGUMENT) or "").strip()
        if not requested:
            return _roll_up()

        service = _INDEX.get(requested.casefold())
        if service is None:
            return ToolResult.failure(
                tool=_TOOL,
                summary=(
                    f"No runtime component matches '{requested}', so no health "
                    "probe could be read."
                ),
                error_code=_ERROR_NOT_FOUND,
                error_message=(
                    f"'{requested}' is not one of the nine Meridian runtime "
                    f"components. Accepted by name, three-letter code or "
                    f"endpoint path segment: {_KNOWN}."
                ),
            )

        return ToolResult.success(
            tool=_TOOL,
            summary=service.summary(),
            data=service.payload(),
        )
