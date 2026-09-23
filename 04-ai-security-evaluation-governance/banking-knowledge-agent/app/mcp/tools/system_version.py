"""``retrieve_system_version``: what is *actually* running, not what shipped.

The knowledge base states the design rule plainly — "components are released
together as a platform version (currently ``4.2``)" — and that sentence is, as
documentation, correct. It is also the single most misleading fact in the corpus
for anyone debugging a live incident, because a fleet is only ever "released
together" for as long as nothing blocks a deploy. This tool exists to report the
other half: the version each component is *observed* to be running now.

**Why this tool earns its place next to RAG.** Retrieval can only ever return
the documented answer, confidently and with a citation. An engineer who reads
"the platform is on 4.2" and then chases a bug that 4.2 fixed will conclude the
fix does not work, when in fact the box in front of them is still on 4.1.9 and
the fix was never deployed to it. Documentation and live state disagreeing is
not a defect in either source — it is the answer to the question, and it is
retrievable only through a tool. The synthetic dataset below therefore models
drift deliberately rather than reporting a tidy fleet all on one version:

* ``CardSecurityModule`` is a full minor version behind (``4.1.9``), its 4.2
  deploy deferred pending an HSM firmware certification window. It also still
  exposes the previous API contract, which is what an integrator needs to know.
* ``LimitService`` is one patch behind (``4.2.2``) mid-rollout.

A dataset in which every component matched ``4.2.3`` would make this tool a
slower, less citable duplicate of the overview document.

**Why the argument is optional rather than two separate tools.** The obvious
alternative was ``retrieve_platform_version`` (no arguments) plus
``retrieve_component_version`` (one required argument), which would have let
every tool in the set use :func:`~app.mcp.base.require_argument` uniformly. It
was rejected on three grounds. First, the tool name is fixed by
:data:`~app.mcp.models.ToolName`, so a split would have to be argued at the
contract level for the convenience of one helper. Second, the two questions have
one answer: the component picture *is* the platform picture, and splitting it
means a caller asking "what version are we on?" gets a number that is true of
nothing running. Third — and this is the operative reason — Stage 7 puts these
specs in front of a model, and two near-identically-described tools is the
classic way to make a model choose wrongly. One tool with an optional narrowing
argument is the same shape as ``GET /versions`` and ``GET /versions/{id}``, which
is a shape both models and humans already read correctly.

The cost of that choice is paid here: ``require_argument`` raises when an
argument is absent, which for this tool is a *valid call*, so the argument is
read directly from the mapping and blank-or-whitespace is treated as "omitted".
:func:`~app.mcp.base.reject_unknown_arguments` still runs, because an optional
argument is not a licence to ignore a misspelled one — a caller who typed
``components`` and silently received the whole fleet has been misinformed.

**Everything here is synthetic and pure.** No clock, no randomness, no network,
no filesystem, and pointedly no reading of the application's own version: this
tool reports the *platform's* state, and wiring it to ``app.__version__`` would
make a demo of drift impossible the moment the two happened to agree.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import JsonValue

from app.core.tracing import traced
from app.mcp.base import reject_unknown_arguments
from app.mcp.models import ToolName, ToolParameter, ToolResult, ToolSpec

_TOOL_NAME: ToolName = "retrieve_system_version"

PLATFORM_VERSION = "4.2"
"""The documented platform release line — the number the corpus quotes."""

PLATFORM_BUILD = "4.2.3"
"""The current patch build of that line: the target every component should be
on. Kept separate from :data:`PLATFORM_VERSION` because "we are on 4.2" and "we
are on 4.2.3" are different claims, and drift lives in the difference."""

PLATFORM_RELEASED_ON = "2026-08-19"
"""Release date of :data:`PLATFORM_BUILD`. Synthetic, fixed, never computed."""

PLATFORM_API_VERSION = "v5"
"""The externally-published API/schema contract version of :data:`PLATFORM_BUILD`.

Reported per component as well, because a component lagging behind the platform
build may still be serving the previous contract — which is the fact an
integrator debugging a rejected field actually needs.
"""


@dataclass(frozen=True)
class _ComponentVersion:
    """One component's observed version reading.

    Attributes:
        name: Canonical spelling, as the component overview document writes it.
        code: The three-letter component code, e.g. ``SWX``.
        running_version: Semantic version actually serving traffic.
        build: Immutable build identifier for ``running_version``.
        released_on: ISO date that build was promoted to production.
        api_version: The API/schema contract this build exposes.
        note: One sentence explaining the component's deploy state. For a
            drifted component this is the *reason*, which is the part a reader
            needs in order to know whether to wait or to escalate.
    """

    name: str
    code: str
    running_version: str
    build: str
    released_on: str
    api_version: str
    note: str


_COMPONENTS: tuple[_ComponentVersion, ...] = (
    _ComponentVersion(
        name="TransactionSwitch",
        code="SWX",
        running_version="4.2.3",
        build="4.2.3+b1874",
        released_on="2026-08-19",
        api_version="v5",
        note="Promoted with the 4.2.3 platform release.",
    ),
    _ComponentVersion(
        name="AuthorizationService",
        code="AUT",
        running_version="4.2.3",
        build="4.2.3+b1871",
        released_on="2026-08-19",
        api_version="v5",
        note="Promoted with the 4.2.3 platform release.",
    ),
    _ComponentVersion(
        name="CardSecurityModule",
        code="CSM",
        running_version="4.1.9",
        build="4.1.9+b1802",
        released_on="2026-05-27",
        api_version="v4",
        note=(
            "Deferred deploy: the 4.2 upgrade is held pending the HSM firmware "
            "certification window, so production still serves 4.1.9 on the v4 "
            "API contract. Fixes shipped in 4.2 are not present here."
        ),
    ),
    _ComponentVersion(
        name="LimitService",
        code="LIM",
        running_version="4.2.2",
        build="4.2.2+b1859",
        released_on="2026-07-30",
        api_version="v5",
        note=(
            "Mid-rollout: 4.2.3 is staged but not yet promoted, so production "
            "is still serving the 4.2.2 build."
        ),
    ),
    _ComponentVersion(
        name="CoreBankingAdapter",
        code="COR",
        running_version="4.2.3",
        build="4.2.3+b1875",
        released_on="2026-08-19",
        api_version="v5",
        note="Promoted with the 4.2.3 platform release.",
    ),
    _ComponentVersion(
        name="PaymentEngine",
        code="PAY",
        running_version="4.2.3",
        build="4.2.3+b1872",
        released_on="2026-08-19",
        api_version="v5",
        note="Promoted with the 4.2.3 platform release.",
    ),
    _ComponentVersion(
        name="DigitalGateway",
        code="DGW",
        running_version="4.2.3",
        build="4.2.3+b1869",
        released_on="2026-08-19",
        api_version="v5",
        note="Promoted with the 4.2.3 platform release.",
    ),
    _ComponentVersion(
        name="DeviceManager",
        code="DEV",
        running_version="4.2.3",
        build="4.2.3+b1877",
        released_on="2026-08-19",
        api_version="v5",
        note="Promoted with the 4.2.3 platform release.",
    ),
    _ComponentVersion(
        name="ConfigurationStore",
        code="CFG",
        running_version="4.2.3",
        build="4.2.3+b1866",
        released_on="2026-08-19",
        api_version="v5",
        note="Promoted with the 4.2.3 platform release.",
    ),
)
"""The nine runtime components of the component overview, with live readings.

Order matches the document's table so that a reader comparing the two is never
reconciling two different orderings of the same nine names.
"""


def _normalise(value: str) -> str:
    """Reduce a component reference to its comparison key.

    Case, spaces, hyphens and underscores are discarded, so ``"card security
    module"``, ``"Card-Security-Module"`` and ``"CSM"`` all resolve. A caller
    typing a component name from memory should not be told it does not exist
    because they wrote it the way a human writes it.

    Args:
        value: A component name or code, as supplied.

    Returns:
        Lower-cased alphanumerics only.
    """
    return "".join(char for char in value.lower() if char.isalnum())


_INDEX: dict[str, _ComponentVersion] = {
    key: component
    for component in _COMPONENTS
    for key in (_normalise(component.name), _normalise(component.code))
}
"""Lookup by normalised name *and* by normalised three-letter code.

Both are accepted because both are how the corpus refers to a component: prose
says ``LimitService``, an error code says ``LIM-4001``, and an engineer reading a
log line has the code in front of them, not the name. No name normalises onto
another's code, so the two key spaces cannot collide.
"""


def _version_tuple(version: str) -> tuple[int, ...]:
    """Split a dotted numeric version into comparable integer parts.

    Args:
        version: A version such as ``"4.2.3"``. Every value in this module's
            own dataset is dotted and numeric, so no tolerant parsing is
            warranted — a malformed literal here is a bug to be found loudly.

    Returns:
        The parts as integers, e.g. ``(4, 2, 3)``.
    """
    return tuple(int(part) for part in version.split("."))


def _drift_of(component: _ComponentVersion) -> dict[str, JsonValue] | None:
    """Describe how a component diverges from the platform build, if it does.

    Args:
        component: The component's observed reading.

    Returns:
        A structured drift record, or ``None`` when the component is running
        exactly :data:`PLATFORM_BUILD`. ``None`` rather than a record with an
        ``in_drift: false`` flag, so that a caller cannot mistake the presence
        of the key for the presence of a problem.
    """
    running = _version_tuple(component.running_version)
    expected = _version_tuple(PLATFORM_BUILD)
    if running == expected:
        return None
    if running > expected:
        severity = "ahead"
    elif running[:2] != expected[:2]:
        severity = "minor"
    else:
        severity = "patch"
    return {
        "component": component.name,
        "component_code": component.code,
        "running_version": component.running_version,
        "expected_version": PLATFORM_BUILD,
        "severity": severity,
        "api_version": component.api_version,
        "expected_api_version": PLATFORM_API_VERSION,
        "reason": component.note,
    }


def _component_entry(component: _ComponentVersion) -> dict[str, JsonValue]:
    """Render one component as the payload shape used in the fleet listing.

    Args:
        component: The component's observed reading.

    Returns:
        A JSON-safe mapping of that component's version facts.
    """
    return {
        "component": component.name,
        "component_code": component.code,
        "running_version": component.running_version,
        "build": component.build,
        "released_on": component.released_on,
        "api_version": component.api_version,
        "up_to_date": _drift_of(component) is None,
    }


class SystemVersionTool:
    """Reports the running version of the platform, or of one component.

    Satisfies :class:`~app.mcp.base.Tool` structurally: no base class, no
    registration side effect at import time. The registry names it explicitly.

    Two answers, one tool (see the module docstring for why):

    * no ``component`` argument — the platform version and every component's
      running version, with drift called out;
    * a ``component`` argument — that one component's version detail.
    """

    @property
    def spec(self) -> ToolSpec:
        """The tool's contract: name, purpose and its single optional argument."""
        return ToolSpec(
            name=_TOOL_NAME,
            summary=(
                "Report the running platform version, or one component's "
                "version, as observed now."
            ),
            description=(
                "Returns live version readings rather than documented release "
                "notes. Omit 'component' for the platform version plus every "
                "component's running version and any drift from the current "
                "platform build; supply 'component' (name or three-letter "
                "code, case-insensitive) for that component's version, build, "
                "release date and API contract version. Components are "
                "documented as being released together, so a component "
                "reported here on a different version is genuine drift and is "
                "flagged as such. This tool does not report component health, "
                "configuration values or deployment history."
            ),
            parameters=(
                ToolParameter(
                    name="component",
                    description=(
                        "Optional. Component name or three-letter code; omit "
                        "for the whole platform."
                    ),
                    required=False,
                    example="LimitService",
                ),
            ),
        )

    @traced
    def invoke(self, arguments: Mapping[str, str]) -> ToolResult:
        """Report platform-wide versions, or one component's version.

        Args:
            arguments: May contain ``component``. Absent, empty or
                whitespace-only all mean "the whole platform"; an argument
                supplied as a blank string is a caller who has nothing to
                narrow by, not a caller asking about a component called "".

        Returns:
            A successful result carrying the version picture, or ``ok=False``
            with ``error_code="NOT_FOUND"`` when the named component is not one
            of the nine runtime components.

        Raises:
            ToolInputError: If an argument this tool does not declare was
                supplied.
        """
        reject_unknown_arguments(arguments, self.spec)

        requested = (arguments.get("component") or "").strip()
        if not requested:
            return self._platform_result()

        component = _INDEX.get(_normalise(requested))
        if component is None:
            return self._not_found(requested)
        return self._component_result(component)

    def _platform_result(self) -> ToolResult:
        """Build the fleet-wide answer: platform build plus all nine components."""
        entries = [_component_entry(component) for component in _COMPONENTS]
        drifted = [
            drift
            for drift in (_drift_of(component) for component in _COMPONENTS)
            if drift is not None
        ]
        aligned = len(_COMPONENTS) - len(drifted)

        data: dict[str, JsonValue] = {
            "platform_version": PLATFORM_VERSION,
            "platform_build": PLATFORM_BUILD,
            "platform_released_on": PLATFORM_RELEASED_ON,
            "platform_api_version": PLATFORM_API_VERSION,
            "component_count": len(_COMPONENTS),
            "components_on_platform_build": aligned,
            "drift_detected": bool(drifted),
            "components": list(entries),
            "drift": list(drifted),
        }

        if drifted:
            behind = ", ".join(
                f"{component.name} {component.running_version}"
                for component in _COMPONENTS
                if _drift_of(component) is not None
            )
            summary = (
                f"Platform {PLATFORM_VERSION} (build {PLATFORM_BUILD}): "
                f"{aligned} of {len(_COMPONENTS)} components on the current "
                f"build; {behind} not on {PLATFORM_BUILD}."
            )
        else:
            summary = (
                f"Platform {PLATFORM_VERSION} (build {PLATFORM_BUILD}): "
                f"all {len(_COMPONENTS)} components on the current build."
            )

        return ToolResult.success(tool=_TOOL_NAME, summary=summary, data=data)

    def _component_result(self, component: _ComponentVersion) -> ToolResult:
        """Build the answer for one component.

        Args:
            component: The matched component, already resolved to its canonical
                record so that ``data`` echoes the documented spelling rather
                than whatever the caller typed.
        """
        drift = _drift_of(component)
        data: dict[str, JsonValue] = {
            "platform_version": PLATFORM_VERSION,
            "platform_build": PLATFORM_BUILD,
            "component": component.name,
            "component_code": component.code,
            "running_version": component.running_version,
            "build": component.build,
            "released_on": component.released_on,
            "api_version": component.api_version,
            "up_to_date": drift is None,
            "drift": drift,
            "note": component.note,
        }

        if drift is None:
            summary = (
                f"{component.name} ({component.code}) is running "
                f"{component.running_version}, build {component.build}, "
                f"matching platform build {PLATFORM_BUILD}."
            )
        else:
            summary = (
                f"{component.name} ({component.code}) is running "
                f"{component.running_version} — {drift['severity']} version "
                f"drift behind platform build {PLATFORM_BUILD}. "
                f"{component.note}"
            )

        return ToolResult.success(tool=_TOOL_NAME, summary=summary, data=data)

    def _not_found(self, requested: str) -> ToolResult:
        """Report that no such component exists — data, not an error.

        Args:
            requested: What the caller asked for, echoed back so they can see
                the string that failed to match.
        """
        known = ", ".join(f"{c.name} ({c.code})" for c in _COMPONENTS)
        return ToolResult.failure(
            tool=_TOOL_NAME,
            summary=(
                f"No runtime component matches '{requested}'; no version can "
                "be reported for it."
            ),
            error_code="NOT_FOUND",
            error_message=(
                f"'{requested}' is not one of the {len(_COMPONENTS)} runtime "
                f"components. Known components: {known}."
            ),
        )
