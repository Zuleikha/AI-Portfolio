"""``get_component_status`` — the operational picture for one platform component.

This tool answers the question an engineer actually asks first during an
incident: *what is this component doing right now?* Not "is the process
running", but how many of its instances are healthy, how much traffic it is
taking, what proportion of that traffic is failing, how deep its backlog has
grown, and whether any of that is already attached to an incident.

**Why this is not ``check_service_health``.** The two tools look adjacent and
are deliberately not merged. ``check_service_health`` is the *probe*: it calls
``GET /{component}/v1/health``, reports whether the endpoint answered, how long
it took, and whether the component's own dependency checks passed. It answers a
binary, mechanical question — is this thing alive and ready to be sent work.
This tool answers a graded, operational one — is this thing *working well*.

Those come apart constantly, and the gap between them is where real incidents
live. A component whose process is up, whose port is open and whose health
endpoint returns ``UP`` in 4 ms can simultaneously be failing 7% of its
requests with a backlog of nearly two thousand items, because a liveness probe
is a cheap synthetic request that touches none of the saturated resource. The
synthetic data below models exactly that case: :data:`CoreBankingAdapter` is
reachable and answering, and is also the worst-behaving component on the
platform. Collapsing the two tools into one would force a single answer to two
different questions, and the answer that wins is always the reassuring one.

**Rejected alternatives.**

* *One ``get_component`` tool with a ``view`` argument.* Cheaper to register,
  worse to call: Stage 7 chooses a tool from its summary, and "component
  information" gives a model nothing to choose on. Two tools with two sharp
  summaries are two decisions a model can get right.
* *Returning latency percentiles here.* Latency is the probe tool's currency
  and duplicating it would invite the two tools to disagree — the classic
  failure of a second source of truth for the same number. This tool reports
  volume, failure rate and backlog; those are its own.
* *Deriving ``state`` from the numbers at call time.* Tempting, and wrong: a
  threshold buried in a tool is an operational policy nobody agreed, and it
  would make the tool's opinion change whenever the numbers were edited. The
  state is part of the dataset, stated explicitly, exactly as it would arrive
  from a real monitoring system that owns those thresholds.

**Cause and effect is modelled, not just decorated.** ``CoreBankingAdapter``
(``COR-5015`` pool exhausted, then ``COR-5008`` timeouts) and
``TransactionSwitch`` (``SWX-7001``, downstream too slow) both carry incident
``INC-4417``, one as its origin and one as impacted. That is the story the
knowledge base tells in prose — the switch names itself in the error code but
is rarely the culprit — made visible as live readings, so an agent can join
documentation to observation instead of restating one of them.

**Everything here is synthetic and fixed.** No clock, no randomness, no I/O.
The nine components, their codes and what they own are copied from
``data/knowledge/platform/platform-component-overview.md`` so that a tool
reading and a document reading cannot contradict each other on the facts that
are not supposed to change. The observation time comes from
``SYNTHETIC_OBSERVED_AT`` via :class:`~app.mcp.models.ToolResult`'s default.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import JsonValue

from app.core.tracing import traced
from app.mcp.base import reject_unknown_arguments, require_argument
from app.mcp.models import ToolName, ToolParameter, ToolResult, ToolSpec

TOOL_NAME: Final[ToolName] = "get_component_status"
"""This tool's name, taken from the closed literal in :mod:`app.mcp.models`."""

ARGUMENT_COMPONENT: Final = "component"
"""The single required argument. Named once so the spec and the reader agree."""

ERROR_NOT_FOUND: Final = "NOT_FOUND"
"""``error_code`` for a component name that is not one of the documented nine.

Deliberately the same UPPER_SNAKE string the other tools use for "the thing you
asked about does not exist". A caller should be able to branch on ``NOT_FOUND``
without first working out which tool produced the result.
"""

ComponentState = Literal["HEALTHY", "DEGRADED", "DOWN"]
"""The three operational states, and no more.

Three is a deliberate ceiling. Every extra state ("WARNING", "RECOVERING",
"PARTIAL") sounds informative and costs a caller a decision it cannot make:
the only question downstream of this tool is whether the component is fine,
misbehaving while still serving, or not serving at all. Nuance belongs in
``degradation_reason``, which is prose and does not have to be enumerated.
"""

IncidentStatus = Literal["ACTIVE", "RESOLVED"]
"""Whether an incident is still open."""

IncidentRole = Literal["origin", "impacted"]
"""This component's part in an incident.

The field that makes a multi-component incident readable. ``origin`` is where
the fault is; ``impacted`` is a component that is failing *because* of it. A
support engineer chasing ``SWX-7001`` needs to know the switch is the second
kind before they start reading switch code.
"""


@dataclass(frozen=True, slots=True)
class _Incident:
    """One incident record as this tool reports it.

    Attributes:
        identifier: The incident reference, e.g. ``INC-4417``. Rendered as
            ``id`` in the payload; spelled out here to avoid shadowing the
            builtin.
        severity: Severity band, ``SEV1`` (worst) to ``SEV4``.
        title: One line describing the incident.
        status: Whether the incident is still open.
        role: Whether this component is the origin or is merely impacted.
        started_at: Synthetic ISO-8601 instant the incident was raised.
    """

    identifier: str
    severity: str
    title: str
    status: IncidentStatus
    role: IncidentRole
    started_at: str

    def to_payload(self) -> dict[str, JsonValue]:
        """Render the incident as a JSON-safe mapping."""
        return {
            "id": self.identifier,
            "severity": self.severity,
            "title": self.title,
            "status": self.status,
            "role": self.role,
            "started_at": self.started_at,
        }


@dataclass(frozen=True, slots=True)
class _ComponentStatus:
    """The full operational reading for one component.

    A dataclass rather than a nested dictionary literal so that ``mypy
    --strict`` checks the dataset itself: a missing field or a typo in a state
    name is a type error at import time, not a ``KeyError`` in front of a user
    half a stage later.

    Attributes:
        component: Canonical spelling, as the platform overview writes it.
        code: The three-letter prefix that owns this component's error codes.
        owns: What the component is responsible for, in one line.
        state: Operational state.
        instances_healthy: Instances currently serving.
        instances_total: Instances the deployment expects.
        error_rate_percent: Failed requests as a percentage of all requests.
        requests_per_minute: Current throughput.
        queue_depth: Items waiting to be processed. Zero for components that
            work synchronously and are not backed up.
        depends_on: Components this one calls, canonical spellings.
        recent_error_codes: Codes seen in the current window, most significant
            first. Empty when nothing notable is failing.
        degradation_reason: Why the state is not ``HEALTHY``, or ``None``.
        active_incident: The open incident, or ``None``.
        last_resolved_incident: The most recent closed incident, or ``None``.
            Kept alongside ``active_incident`` because "nothing is wrong now,
            and something was wrong an hour ago" is a materially different
            answer from "nothing has been wrong".
        last_state_change: Synthetic ISO-8601 instant the state last changed.
    """

    component: str
    code: str
    owns: str
    state: ComponentState
    instances_healthy: int
    instances_total: int
    error_rate_percent: float
    requests_per_minute: int
    queue_depth: int
    depends_on: tuple[str, ...]
    recent_error_codes: tuple[str, ...]
    degradation_reason: str | None
    active_incident: _Incident | None
    last_resolved_incident: _Incident | None
    last_state_change: str

    def to_payload(self) -> dict[str, JsonValue]:
        """Render the reading as the ``data`` mapping of a tool result."""
        active = self.active_incident
        resolved = self.last_resolved_incident
        return {
            "component": self.component,
            "code": self.code,
            "owns": self.owns,
            "state": self.state,
            "instances_healthy": self.instances_healthy,
            "instances_total": self.instances_total,
            "error_rate_percent": self.error_rate_percent,
            "requests_per_minute": self.requests_per_minute,
            "queue_depth": self.queue_depth,
            "depends_on": list(self.depends_on),
            "recent_error_codes": list(self.recent_error_codes),
            "degradation_reason": self.degradation_reason,
            "active_incident": active.to_payload() if active else None,
            "last_resolved_incident": resolved.to_payload() if resolved else None,
            "last_state_change": self.last_state_change,
        }

    def to_summary(self) -> str:
        """Write the one human-readable line that accompanies the payload.

        Composed from the same fields as the payload rather than stored beside
        them, so a summary can never drift from the numbers it describes.
        """
        line = (
            f"{self.component} ({self.code}) is {self.state}: "
            f"{self.instances_healthy}/{self.instances_total} instances healthy, "
            f"{self.error_rate_percent:.2f}% errors at "
            f"{self.requests_per_minute} req/min, queue depth {self.queue_depth}."
        )
        if self.degradation_reason:
            line += f" Reason: {self.degradation_reason}."
        if self.active_incident:
            incident = self.active_incident
            line += (
                f" Incident {incident.identifier} ({incident.severity}) active,"
                f" this component is {incident.role}."
            )
        return line


_INCIDENT_CORE_POOL_ORIGIN: Final = _Incident(
    identifier="INC-4417",
    severity="SEV2",
    title="CoreBankingAdapter connection pool exhaustion",
    status="ACTIVE",
    role="origin",
    started_at="2026-09-11T08:38:00Z",
)
"""The open incident, seen from the component that is actually at fault."""

_INCIDENT_CORE_POOL_IMPACT: Final = _Incident(
    identifier="INC-4417",
    severity="SEV2",
    title="CoreBankingAdapter connection pool exhaustion",
    status="ACTIVE",
    role="impacted",
    started_at="2026-09-11T08:38:00Z",
)
"""The same incident, seen from TransactionSwitch, which is only downstream."""

_COMPONENTS: Final[tuple[_ComponentStatus, ...]] = (
    _ComponentStatus(
        component="TransactionSwitch",
        code="SWX",
        owns="Routing and orchestration of ATM and POS transactions",
        state="DEGRADED",
        instances_healthy=6,
        instances_total=6,
        error_rate_percent=3.10,
        requests_per_minute=12480,
        queue_depth=214,
        depends_on=(
            "AuthorizationService",
            "LimitService",
            "CoreBankingAdapter",
            "DeviceManager",
        ),
        recent_error_codes=("SWX-7001", "SWX-7004"),
        degradation_reason=(
            "every instance is up and answering, but 3.1% of transactions are "
            "abandoned with SWX-7001 after CoreBankingAdapter exceeds its "
            "timeout; the switch is the reporter, not the fault"
        ),
        active_incident=_INCIDENT_CORE_POOL_IMPACT,
        last_resolved_incident=None,
        last_state_change="2026-09-11T08:47:00Z",
    ),
    _ComponentStatus(
        component="AuthorizationService",
        code="AUT",
        owns="Card identification, status checks, authorisation decision",
        state="HEALTHY",
        instances_healthy=4,
        instances_total=4,
        error_rate_percent=0.12,
        requests_per_minute=9340,
        queue_depth=3,
        depends_on=("CardSecurityModule", "ConfigurationStore"),
        recent_error_codes=(),
        degradation_reason=None,
        active_incident=None,
        last_resolved_incident=None,
        last_state_change="2026-09-09T22:15:00Z",
    ),
    _ComponentStatus(
        component="CardSecurityModule",
        code="CSM",
        owns="PIN block translation, EMV cryptogram validation, HSM access",
        state="HEALTHY",
        instances_healthy=3,
        instances_total=3,
        error_rate_percent=0.04,
        requests_per_minute=8120,
        queue_depth=0,
        depends_on=(),
        recent_error_codes=(),
        degradation_reason=None,
        active_incident=None,
        last_resolved_incident=None,
        last_state_change="2026-09-08T05:02:00Z",
    ),
    _ComponentStatus(
        component="LimitService",
        code="LIM",
        owns="Transaction, daily and velocity limit evaluation",
        state="HEALTHY",
        instances_healthy=4,
        instances_total=4,
        error_rate_percent=0.09,
        requests_per_minute=7650,
        queue_depth=1,
        depends_on=("ConfigurationStore",),
        recent_error_codes=(),
        degradation_reason=None,
        active_incident=None,
        last_resolved_incident=None,
        last_state_change="2026-09-09T22:15:00Z",
    ),
    _ComponentStatus(
        component="CoreBankingAdapter",
        code="COR",
        owns="Balance enquiry, debit and credit posting to the core ledger",
        state="DEGRADED",
        instances_healthy=3,
        instances_total=6,
        error_rate_percent=7.40,
        requests_per_minute=5210,
        queue_depth=1874,
        depends_on=(),
        recent_error_codes=("COR-5015", "COR-5008"),
        degradation_reason=(
            "core ledger latency rose from 120 ms to 2.4 s, so connections are "
            "held longer and the pool saturated (COR-5015); calls that cannot "
            "take a connection now time out (COR-5008) and the posting backlog "
            "is growing"
        ),
        active_incident=_INCIDENT_CORE_POOL_ORIGIN,
        last_resolved_incident=None,
        last_state_change="2026-09-11T08:41:00Z",
    ),
    _ComponentStatus(
        component="PaymentEngine",
        code="PAY",
        owns="Payment authorisation, capture, reversal and settlement",
        state="HEALTHY",
        instances_healthy=4,
        instances_total=4,
        error_rate_percent=0.31,
        requests_per_minute=3980,
        queue_depth=27,
        depends_on=(
            "AuthorizationService",
            "LimitService",
            "CoreBankingAdapter",
        ),
        recent_error_codes=("PAY-8011",),
        degradation_reason=None,
        active_incident=None,
        last_resolved_incident=None,
        last_state_change="2026-09-09T22:15:00Z",
    ),
    _ComponentStatus(
        component="DigitalGateway",
        code="DGW",
        owns="Mobile and web banking channel entry point",
        state="HEALTHY",
        instances_healthy=6,
        instances_total=6,
        error_rate_percent=0.22,
        requests_per_minute=11240,
        queue_depth=12,
        depends_on=("PaymentEngine",),
        recent_error_codes=("DGW-9012",),
        degradation_reason=None,
        active_incident=None,
        last_resolved_incident=_Incident(
            identifier="INC-4408",
            severity="SEV3",
            title="Elevated session rejections after channel config rollout",
            status="RESOLVED",
            role="origin",
            started_at="2026-09-10T14:05:00Z",
        ),
        last_state_change="2026-09-10T15:40:00Z",
    ),
    _ComponentStatus(
        component="DeviceManager",
        code="DEV",
        owns="ATM device state, cassette levels, hardware health",
        state="HEALTHY",
        instances_healthy=2,
        instances_total=2,
        error_rate_percent=0.47,
        requests_per_minute=1620,
        queue_depth=5,
        depends_on=("ConfigurationStore",),
        recent_error_codes=("DEV-6004", "DEV-6009"),
        degradation_reason=None,
        active_incident=None,
        last_resolved_incident=_Incident(
            identifier="INC-4402",
            severity="SEV3",
            title="Dispenser jams at branch cluster 14 pending engineer visit",
            status="RESOLVED",
            role="origin",
            started_at="2026-09-10T07:20:00Z",
        ),
        last_state_change="2026-09-10T11:55:00Z",
    ),
    _ComponentStatus(
        component="ConfigurationStore",
        code="CFG",
        owns="Versioned configuration distribution to every component",
        state="HEALTHY",
        instances_healthy=3,
        instances_total=3,
        error_rate_percent=0.01,
        requests_per_minute=640,
        queue_depth=0,
        depends_on=(),
        recent_error_codes=(),
        degradation_reason=None,
        active_incident=None,
        last_resolved_incident=None,
        last_state_change="2026-09-07T18:30:00Z",
    ),
)
"""The nine runtime components of the platform overview, and nothing else.

Nine, not "the interesting ones": a lookup that answers for six components and
reports the other three as unknown teaches a caller that ``NOT_FOUND`` means
"unmonitored" rather than "no such component", and that is the one thing this
result must not be ambiguous about.
"""


def _normalise(value: str) -> str:
    """Reduce a component reference to its comparison key.

    Case, spaces, hyphens and underscores are discarded, so
    ``CoreBankingAdapter``, ``corebankingadapter``, ``core banking adapter``
    and ``core-banking-adapter`` all reach the same entry. Callers write
    component names from memory, from a log line and from a ticket title, and
    none of those agree on punctuation; rejecting a name over a hyphen would be
    a lookup failure dressed as a fact about the platform.

    Args:
        value: A component name or three-letter code, as supplied.

    Returns:
        Lower-case alphanumeric characters only.
    """
    return "".join(character for character in value.lower() if character.isalnum())


_INDEX: Final[Mapping[str, _ComponentStatus]] = {
    key: status
    for status in _COMPONENTS
    for key in (_normalise(status.component), _normalise(status.code))
}
"""Lookup by normalised name *and* by normalised three-letter code.

The codes are accepted because they are what appears in the artefact a support
engineer is usually holding: an error code such as ``COR-5008`` names its
component only by prefix. Requiring the reader to expand ``COR`` into
``CoreBankingAdapter`` before they may ask about it adds a step and a chance to
get it wrong. No code collides with any component name, so one flat index is
enough and there is no precedence rule to remember.
"""


class ComponentStatusTool:
    """Reports the operational state of one platform component.

    Implements :class:`app.mcp.base.Tool` structurally: no base class, no
    registration side effect. The instance is stateless and its data is
    module-level and frozen, so one instance can be shared by the registry, the
    protocol server and any number of tests.
    """

    @property
    def spec(self) -> ToolSpec:
        """What this tool is and how to call it."""
        return ToolSpec(
            name=TOOL_NAME,
            summary=(
                "Report the operational state of one platform component: "
                "instances, error rate, throughput, backlog and any incident."
            ),
            description=(
                "Answers 'how is this component behaving right now'. Returns "
                "its operational state (HEALTHY, DEGRADED or DOWN), how many "
                "instances are healthy of how many are expected, the current "
                "error rate and throughput, the queue depth, the error codes "
                "seen recently, why it is degraded if it is, and the active or "
                "most recent incident. Does NOT probe the component: for "
                "whether its health endpoint answers, its probe latency and "
                "its dependency checks, use check_service_health. A component "
                "can be alive and still be degraded, which is why both tools "
                "exist. Covers only the nine documented runtime components; an "
                "unrecognised name is reported as NOT_FOUND, not as an error."
            ),
            parameters=(
                ToolParameter(
                    name=ARGUMENT_COMPONENT,
                    description=(
                        "Component name or its three-letter code. "
                        "Case and punctuation are ignored."
                    ),
                    required=True,
                    example="CoreBankingAdapter",
                ),
            ),
        )

    @traced
    def invoke(self, arguments: Mapping[str, str]) -> ToolResult:
        """Look up one component's operational reading.

        Args:
            arguments: Must contain ``component``: a component name such as
                ``CoreBankingAdapter`` or its code, ``COR``.

        Returns:
            The reading. ``ok=False`` with ``error_code`` ``NOT_FOUND`` when the
            name matches none of the nine documented components — a true answer
            about the platform, not a failure of the tool.

        Raises:
            ToolInputError: If ``component`` is missing or blank, or if an
                argument this tool does not declare was supplied.
        """
        spec = self.spec
        reject_unknown_arguments(arguments, spec)
        requested = require_argument(arguments, ARGUMENT_COMPONENT, TOOL_NAME)

        status = _INDEX.get(_normalise(requested))
        if status is None:
            return ToolResult.failure(
                tool=TOOL_NAME,
                summary=f"No platform component matches '{requested}'.",
                error_code=ERROR_NOT_FOUND,
                error_message=(
                    f"'{requested}' is not one of the platform's runtime "
                    f"components. Known components: "
                    f"{', '.join(entry.component for entry in _COMPONENTS)}."
                ),
            )

        return ToolResult.success(
            tool=TOOL_NAME,
            summary=status.to_summary(),
            data=status.to_payload(),
        )
