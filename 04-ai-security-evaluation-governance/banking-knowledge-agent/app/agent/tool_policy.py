"""Choosing which MCP tools a question calls for, and with which arguments.

**Stage 7 replaced Stage 6's rule rather than patching it.** Stage 6 had a single
function that knew all six tools by name and hard-wired which identifier fed
which tool. Stage 7 inverts that: the selector is *built from the registry's
specs*, and reads each tool's declared parameters to decide whether the question
supplies them::

    registry.specs() ──▶ RuleToolSelector        validated at construction, loudly
                              │
    question ────────────────▶ select()
                              │  for each spec, in registry order:
                              │    extract every parameter the spec declares
                              │    all REQUIRED parameters found?
                              │    at least one argument found?
                              │    only a shared scope argument found? then its cue
                              ▼
                         ToolInvocation x 0..4

**Arguments are extracted by parameter name, not by tool.** An extractor knows
what an ``error_code``, a ``transaction_reference``, a configuration ``key`` or a
``component`` looks like, and nothing about which tool wants one. A seventh tool
taking an ``error_code`` is selectable the moment it is registered; a tool
declaring a parameter no extractor understands is refused when the selector is
built, because a registered tool that can never be chosen is a silent gap.

**Rules, not a model — by the user's decision** (``docs/HANDOVER.md`` §7.B). An
LLM selector was offered and declined: it would add a paid model call to every
question, make routing non-deterministic, and could only ever have been proven
against the mock — proven to parse, not to choose well.

**Why identifiers select on their own and a component does not.** Stage 6's
argument still holds: an identifier is a fact about *form* — ``LIM-4001`` matches
the documented ``PREFIX-NNNN`` shape — not a guess about meaning, and a tool is
callable exactly when the question supplies what it needs. A component name is
different. Three tools take one, so a component alone cannot say *which* reading
is wanted; those tools additionally need a cue in the question
(:data:`SELECTION_CUES`). A component-only tool with no cue is refused at
construction, because it would otherwise be called for every mention of every
component.

**False positives are still cheap; false negatives are not.** Calling a tool that
finds nothing costs a dictionary lookup and gives the model a true statement.
Missing a tool produces a documentation-only answer that reads as authoritative
and may be stale.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import product
from typing import Protocol

from app.core.tracing import traced
from app.mcp.models import ToolInvocation, ToolSpec

ERROR_CODE_PATTERN = re.compile(r"\b([A-Z]{3})-(\d{4})\b")
"""The documented platform error-code form, ``PREFIX-NNNN``.

Uppercase only, and that is intentional. A question mentioning ``lim-4001`` in
lower case is rare, whereas matching case-insensitively would fire on ordinary
prose that happens to contain three letters, a hyphen and four digits. The tool
itself accepts either case; this pattern decides only whether to call it.
"""

TRANSACTION_REFERENCE_PATTERN = re.compile(r"\bTXN-\d{8}-\d{6}\b", re.IGNORECASE)
"""The documented transaction reference form, ``TXN-YYYYMMDD-NNNNNN``."""

CONFIGURATION_KEY_PATTERN = re.compile(r"\b([a-z][a-z_]*(?:\.[a-z][a-z_]*){1,3})\b")
"""A dotted lower-case configuration key, e.g. ``limits.atm.per_transaction_amount``.

Requires at least one dot and allows at most three, which is the shape every key
in the configuration reference takes. The bound matters: without an upper limit
this pattern would happily match a sentence written without spaces after its full
stops.
"""

COMPONENT_NAMES: tuple[str, ...] = (
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
"""The nine documented runtime components — the default component vocabulary.

Injectable into :class:`RuleToolSelector` rather than read from a tool, because
the selector decides *whether* to call a tool and must not depend on any tool's
internals. ``tests/test_mcp_agent.py`` asserts the list agrees with what the
tools actually accept. :mod:`app.agent.policy` also uses it to vet the component
names allowed into a refined search query.
"""

MAX_TOOL_CALLS = 4
"""Ceiling on tool calls for a single question.

A question naming four components and three error codes would otherwise fan out
into a dozen calls, and the prompt would arrive at the model as a wall of tool
output with the actual question buried at the bottom. The calls are cheap; the
model's attention is not.
"""

SCOPE_PARAMETERS: frozenset[str] = frozenset({"component"})
"""Parameters that say *where* to look rather than *what* to look up.

Several tools share them, so finding one does not by itself say which tool is
wanted. Every other parameter an extractor understands is an identifier.
"""

PARAMETER_LABELS: Mapping[str, str] = {
    "error_code": "error code",
    "transaction_reference": "transaction reference",
    "key": "configuration key",
    "component": "component",
}
"""How each parameter is named in a displayable selection reason."""

_HEALTH_CUE = re.compile(
    r"\b(health|healthy|unhealthy|up|down|degraded|outage|responding|alive|"
    r"probe|liveness|readiness)\b",
    re.IGNORECASE,
)

_STATUS_CUE = re.compile(
    r"\b(status|state|healthy|unhealthy|up|down|degraded|outage|incident|"
    r"operational|backlog|queue|instances|error\s+rate)\b",
    re.IGNORECASE,
)

_VERSION_CUE = re.compile(
    r"\b(version|versions|release|build|patch|upgraded|running)\b", re.IGNORECASE
)

SELECTION_CUES: Mapping[str, re.Pattern[str]] = {
    "check_service_health": _HEALTH_CUE,
    "get_component_status": _STATUS_CUE,
    "retrieve_system_version": _VERSION_CUE,
}
"""Question-form cues for the tools a shared scope argument cannot tell apart.

These are cues about *what kind of reading* is asked for — health, state,
version — not banking topic keywords. "Is CoreBankingAdapter healthy?" matches
both the health and the status cue, deliberately: a probe result and the
operational state are the two halves of that answer.
"""

ArgumentExtractor = Callable[[str], tuple[str, ...]]
"""Finds every value of one parameter kind in a question, in order, unique."""


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    """Distinct values, first occurrence first."""
    return tuple(dict.fromkeys(values))


@traced
def extract_error_codes(question: str) -> tuple[str, ...]:
    """Every documented-form error code in ``question``."""
    return _unique(match.group(0) for match in ERROR_CODE_PATTERN.finditer(question))


@traced
def extract_transaction_references(question: str) -> tuple[str, ...]:
    """Every transaction reference in ``question``, normalised to upper case."""
    return _unique(
        match.group(0).upper()
        for match in TRANSACTION_REFERENCE_PATTERN.finditer(question)
    )


@traced
def extract_configuration_keys(question: str) -> tuple[str, ...]:
    """Every dotted configuration key in ``question``."""
    return _unique(
        match.group(1) for match in CONFIGURATION_KEY_PATTERN.finditer(question)
    )


@traced
def component_extractor(components: Sequence[str]) -> ArgumentExtractor:
    """Build an extractor for ``components``, matched as whole words, any case.

    Raises:
        ValueError: If ``components`` is empty — a vocabulary with nothing in it
            would silently disable every component tool.
    """
    if not components:
        raise ValueError("The component vocabulary must name at least one component.")
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(name) for name in components) + r")\b",
        re.IGNORECASE,
    )
    canonical = {name.casefold(): name for name in components}

    def extract(question: str) -> tuple[str, ...]:
        return _unique(
            canonical[match.group(1).casefold()] for match in pattern.finditer(question)
        )

    return extract


class ToolSelector(Protocol):
    """Anything that turns a question into the tool calls it warrants.

    A protocol, like ``Embedder``, ``LLMProvider`` and ``Tool``: an implementation
    qualifies structurally, and a test double needs no inheritance. There is one
    implementation, :class:`RuleToolSelector`, by decision (``HANDOVER.md`` §7.B).
    """

    def select(self, question: str) -> tuple[ToolInvocation, ...]:
        """Return the tool calls ``question`` warrants, possibly none."""
        ...


class RuleToolSelector:
    """Selects tools from the specs it was built with, by deterministic rules.

    Free, offline, deterministic and testable without a provider. Built by
    :class:`~app.agent.agent.KnowledgeAgent` from its registry, so it can only
    ever select a tool the agent can actually call.
    """

    def __init__(
        self,
        specs: Iterable[ToolSpec],
        components: Sequence[str] = COMPONENT_NAMES,
        cues: Mapping[str, re.Pattern[str]] = SELECTION_CUES,
        max_calls: int = MAX_TOOL_CALLS,
    ) -> None:
        """Build and validate a selector.

        Args:
            specs: The tools that may be selected, in the order to call them.
                Normally ``registry.specs()``.
            components: The component vocabulary to recognise.
            cues: Question-form cues keyed by tool name.
            max_calls: Ceiling on calls for one question.

        Raises:
            ValueError: If a spec declares no parameters, declares a parameter
                no extractor understands, or can only be selected by a shared
                scope argument and has no cue. Each is a tool the selector
                could never choose correctly, and that is refused here rather
                than discovered as a question that silently went unanswered.
        """
        if max_calls < 1:
            raise ValueError("max_calls must be at least 1.")
        self._extractors: dict[str, ArgumentExtractor] = {
            "error_code": extract_error_codes,
            "transaction_reference": extract_transaction_references,
            "key": extract_configuration_keys,
            "component": component_extractor(components),
        }
        self._specs = tuple(specs)
        self._cues = dict(cues)
        self._max_calls = max_calls
        for spec in self._specs:
            self._validate(spec)

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        """The tools this selector can choose between, in call order."""
        return self._specs

    @traced
    def select(self, question: str) -> tuple[ToolInvocation, ...]:
        """Choose the tool calls ``question`` warrants, with their arguments.

        Args:
            question: The user's question, in natural language.

        Returns:
            Invocations in registry order, one per identifier value, capped at
            ``max_calls``. Empty when the question supplies nothing a tool can
            act on — the common case, and not a failure.
        """
        found = {
            name: extractor(question) for name, extractor in self._extractors.items()
        }
        invocations = [
            ToolInvocation(
                tool=spec.name,
                arguments=arguments,
                reason=self._reason(spec, arguments),
            )
            for spec in self._specs
            for arguments in self._argument_sets(spec, found, question)
        ]
        return tuple(invocations[: self._max_calls])

    def _validate(self, spec: ToolSpec) -> None:
        """Refuse a spec this selector could never choose correctly."""
        if not spec.parameters:
            raise ValueError(
                f"Tool '{spec.name}' declares no parameters, so there is nothing "
                "in a question a rule could select it on."
            )
        unknown = sorted(
            parameter.name
            for parameter in spec.parameters
            if parameter.name not in self._extractors
        )
        if unknown:
            raise ValueError(
                f"Tool '{spec.name}' declares parameter(s) {unknown} that no "
                "argument extractor understands, so it could never be selected. "
                "Add an extractor to RuleToolSelector before registering it."
            )
        scope_only = all(
            parameter.name in SCOPE_PARAMETERS for parameter in spec.parameters
        )
        if scope_only and spec.name not in self._cues:
            raise ValueError(
                f"Tool '{spec.name}' takes only a component, which several tools "
                "share, so it needs a question-form cue; without one it would be "
                "called for every mention of every component."
            )

    def _argument_sets(
        self,
        spec: ToolSpec,
        found: Mapping[str, tuple[str, ...]],
        question: str,
    ) -> list[dict[str, str]]:
        """Every argument combination the question supplies for ``spec``.

        Identifier parameters fan out — two error codes are two calls. A scope
        parameter takes the first component named, as in Stage 6.
        """
        choices: list[tuple[str, tuple[str, ...]]] = []
        for parameter in spec.parameters:
            values = found[parameter.name]
            if not values:
                if parameter.required:
                    return []
                continue
            if parameter.name in SCOPE_PARAMETERS:
                values = values[:1]
            choices.append((parameter.name, values))
        if not choices:
            return []

        cue = self._cues.get(spec.name)
        has_identifier = any(name not in SCOPE_PARAMETERS for name, _ in choices)
        if cue is None and not has_identifier:
            return []
        if cue is not None and not cue.search(question):
            return []

        names = [name for name, _ in choices]
        return [
            dict(zip(names, combination, strict=True))
            for combination in product(*(values for _, values in choices))
        ]

    @staticmethod
    def _reason(spec: ToolSpec, arguments: Mapping[str, str]) -> str:
        """A displayable sentence naming what the call acts on.

        Displayed, never logged: it names argument values, which is exactly why
        :class:`~app.agent.models.ToolCallSummary` does not carry it.
        """
        named = " and ".join(
            f"the {PARAMETER_LABELS.get(name, name)} {value}"
            for name, value in arguments.items()
        )
        return f"The question names {named}, which {spec.name} takes as input."
