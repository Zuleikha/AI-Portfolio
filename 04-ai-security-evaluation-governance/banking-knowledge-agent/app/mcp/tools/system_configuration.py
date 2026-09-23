"""``get_system_configuration``: the effective value of one configuration key.

This tool mirrors the documented ConfigurationStore endpoint
``GET /config/v1/config/{component}/{key}``, which the configuration reference
describes as *"the authoritative answer when a component appears not to be
honouring a change"*. It exists in this project for one reason, and the reason
is the whole argument of Stage 6:

    ``data/knowledge`` says ``limits.atm.per_transaction_amount`` defaults to
    ``500.00``. This tool says the effective value is ``250.00``, because an
    account override supplied it. Both statements are true. The gap between
    them is the answer to "why was my customer refused at 300?".

Documentation describes the platform as *designed*; a tool reports it as
*configured*. A support engineer who reads only the first gives a confidently
wrong answer, which is the failure mode this whole architecture exists to
prevent. So the payload carries not just the value but ``documented_default``
and ``differs_from_documented_default`` — the disagreement is promoted to a
field rather than left for a reader to notice.

**Why the payload carries ``precedence``.** The limits document defines a
three-level ladder — account override, then card product, then platform
default — and the *level* that supplied a value is often more actionable than
the value itself. ``limits.atm.daily_withdrawal_amount`` here resolves to the
same number as the documented default but arrives from ``card_product``:
changing the platform default would not move it. A payload of value-only would
have made that invisible.

**Why values are strings.** ``500.00`` is a decimal in the domain and would
become ``500.0`` the moment it were typed as a JSON number, and
``digital.minimum_client_version`` (``5.8.0``) is not a number at all. The
value is served exactly as ConfigurationStore holds it and ``value_type``
carries the reading instruction, which is the same reasoning
:meth:`app.mcp.models.ToolSpec.input_schema` uses for typing every argument as
a string. Parsing belongs to whoever knows what the key means.

**Why secrets are refused before anything else is checked.** ConfigurationStore
holds operational values only; credentials reach components through their
runtime environment and never appear in a configuration version or audit
record. That is a documented property of the platform, so the tool enforces it
rather than merely failing to hold such a key. The refusal is emitted *before*
the component is validated, so the response cannot be used to probe which
components exist by asking each one for a credential. The match is a
deliberately broad substring test: a legitimate key that happens to contain
``key`` is refused, which costs one confusing answer, whereas a narrower test
that let one credential-shaped key through would cost a secret. Refusing is the
cheap side of that trade.

**Rejected alternatives.**

* *Reading the values back out of ``data/knowledge`` at call time.* Tempting —
  the numbers are already written down there — and fatal, because it would
  guarantee the tool and the documentation could never disagree, which is the
  one behaviour worth demonstrating. It would also put filesystem I/O behind a
  seam the :class:`~app.mcp.base.Tool` protocol promises is pure.
* *Raising for an unknown component or key.* "There is no such key" is a true,
  useful answer to a reasonable question, so it returns ``ok=False``. Only a
  malformed *call* raises. See :mod:`app.mcp.base` for the full argument.
* *One flat ``{"component.key": value}`` dictionary.* Cheaper to write, but it
  makes "that component exists, that key does not" impossible to say, and that
  distinction is exactly what turns a dead end into a next step for the caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from app.core.tracing import traced
from app.mcp.base import reject_unknown_arguments, require_argument
from app.mcp.models import ToolName, ToolParameter, ToolResult, ToolSpec

_TOOL_NAME: ToolName = "get_system_configuration"

ValueType = Literal["decimal", "integer", "enum", "string", "boolean"]
"""How to read a configuration value that is always served as text."""

Precedence = Literal["platform_default", "card_product", "account_override"]
"""Which level of the configuration ladder supplied the effective value.

Named in the order the limits document resolves them, most specific first:
an account override beats a card product limit, which beats the platform
default. Levels merge per key, not wholesale.
"""

_BASELINE_VERSION = "v4.2.0"
"""The configuration version the documented 4.2 defaults were published in."""

_PLATFORM_OWNER = "platform.engineering@bank.example"
"""Synthetic author recorded against the untouched platform baseline."""

_BASELINE_REASON = "Platform baseline for the 4.2 configuration set."
"""Synthetic audit reason recorded against the untouched platform baseline."""

_SECRET_MARKERS: tuple[str, ...] = (
    "password",
    "secret",
    "key",
    "token",
    "credential",
)
"""Substrings that make a requested key credential-shaped.

Matched case-insensitively against the whole key. No key this module serves
contains any of them, so the test costs nothing on the happy path and refuses
early on the path that matters.
"""


@dataclass(frozen=True)
class _ConfigEntry:
    """One effective configuration value and the audit record behind it.

    Attributes:
        value: The value in effect, served as text. See the module docstring
            for why this is never a JSON number.
        value_type: How to read :attr:`value`.
        precedence: The ladder level that supplied :attr:`value`.
        configuration_version: The immutable version the value came from.
        last_changed_by: Synthetic author of that version.
        last_changed_reason: Synthetic audit reason for that version.
        documented_default: What ``data/knowledge`` publishes as the platform
            default for this key. Held alongside the effective value precisely
            so the two can be compared rather than confused.
        controls: One line on what the key governs, lifted from the
            documentation so a caller need not fetch it separately.
    """

    value: str
    value_type: ValueType
    precedence: Precedence
    configuration_version: str
    last_changed_by: str
    last_changed_reason: str
    documented_default: str
    controls: str

    @property
    def differs_from_documented_default(self) -> bool:
        """Whether the effective value disagrees with the published default."""
        return self.value != self.documented_default


def _baseline(value: str, value_type: ValueType, controls: str) -> _ConfigEntry:
    """Build an entry that is simply the documented platform default.

    Most keys are untouched, and writing their audit metadata out eight times
    would have been eight chances for it to drift.

    Args:
        value: The documented default, which is also the effective value.
        value_type: How to read it.
        controls: One line on what the key governs.

    Returns:
        An entry supplied by ``platform_default`` at the baseline version.
    """
    return _ConfigEntry(
        value=value,
        value_type=value_type,
        precedence="platform_default",
        configuration_version=_BASELINE_VERSION,
        last_changed_by=_PLATFORM_OWNER,
        last_changed_reason=_BASELINE_REASON,
        documented_default=value,
        controls=controls,
    )


_CONFIGURATION: Mapping[str, Mapping[str, _ConfigEntry]] = {
    "TransactionSwitch": {
        # Diverges from documentation: the published default is 8000. Still
        # above core.request_timeout_ms (5000), as the reference requires.
        "switch.downstream_timeout_ms": _ConfigEntry(
            value="6000",
            value_type="integer",
            precedence="platform_default",
            configuration_version="v4.2.11",
            last_changed_by=_PLATFORM_OWNER,
            last_changed_reason=(
                "INC-4417: fail ahead of the core banking timeout rather than "
                "after it, to stop reversals piling up on a slow core."
            ),
            documented_default="8000",
            controls="End-to-end budget for one transaction.",
        ),
        "switch.reversal_retry_count": _baseline(
            "3", "integer", "Reversal attempts before the exception queue."
        ),
    },
    "CoreBankingAdapter": {
        "core.request_timeout_ms": _baseline(
            "5000", "integer", "Core banking call timeout."
        ),
        "core.connection_pool_size": _baseline(
            "40", "integer", "Concurrent core banking connections."
        ),
    },
    "CardSecurityModule": {
        "csm.hsm_pool_size": _baseline("8", "integer", "HSM connections held."),
        "csm.hsm_request_timeout_ms": _baseline(
            "2000", "integer", "Per-HSM-request timeout."
        ),
    },
    "PaymentEngine": {
        "payments.idempotency_ttl_hours": _baseline(
            "24", "integer", "How long an idempotency reference is remembered."
        ),
        "payments.authorisation_validity_hours": _baseline(
            "168", "integer", "Before an authorisation expires."
        ),
        "payments.clearing_retry_count": _baseline(
            "3", "integer", "Batch submission attempts."
        ),
    },
    "AuthorizationService": {
        "cards.pin_retry_limit": _baseline(
            "3", "integer", "PIN attempts before the card blocks."
        ),
        "cards.allow_stripe_fallback": _baseline(
            "false", "boolean", "Magnetic-stripe fallback."
        ),
    },
    "DigitalGateway": {
        "digital.session_ttl_minutes": _baseline("30", "integer", "Session lifetime."),
        "digital.session_idle_timeout_minutes": _baseline(
            "10", "integer", "Inactivity cutoff."
        ),
        "digital.step_up_amount_threshold": _baseline(
            "1000.00", "decimal", "Amount requiring step-up authentication."
        ),
        "digital.rate_limit_per_session": _baseline(
            "60", "integer", "Requests per minute per session."
        ),
        "digital.rate_limit_per_account": _baseline(
            "120", "integer", "Requests per minute per account."
        ),
        "digital.minimum_client_version": _baseline(
            "5.8.0", "string", "Oldest supported mobile client."
        ),
    },
    "DeviceManager": {
        "device.heartbeat_interval_seconds": _baseline(
            "30", "integer", "Terminal heartbeat frequency."
        ),
        "device.heartbeat_timeout_seconds": _baseline(
            "120", "integer", "Before a terminal is marked UNREACHABLE."
        ),
        "device.cassette_low_threshold": _baseline(
            "150", "integer", "Note count that marks a terminal DEGRADED."
        ),
    },
    "LimitService": {
        # The headline disagreement. Documentation says 500.00; an account
        # override says 250.00, and the override is what the customer felt.
        "limits.atm.per_transaction_amount": _ConfigEntry(
            value="250.00",
            value_type="decimal",
            precedence="account_override",
            configuration_version="v4.2.11",
            last_changed_by="risk.operations@bank.example",
            last_changed_reason=(
                "Fraud pattern FP-2291: temporary account-level ATM cap "
                "pending review."
            ),
            documented_default="500.00",
            controls="Largest single ATM withdrawal.",
        ),
        # Same number as the documented default, supplied by a different
        # level. Editing the platform default would not move this value, and
        # only the precedence field says so.
        "limits.atm.daily_withdrawal_amount": _ConfigEntry(
            value="1000.00",
            value_type="decimal",
            precedence="card_product",
            configuration_version="v4.2.3",
            last_changed_by="card.product.owner@bank.example",
            last_changed_reason=(
                "Standard debit product restates the daily allowance at "
                "product level so product changes do not depend on the "
                "platform default."
            ),
            documented_default="1000.00",
            controls="Total ATM withdrawal per day, per account.",
        ),
        "limits.atm.daily_withdrawal_count": _baseline(
            "5", "integer", "Number of ATM withdrawals per day."
        ),
        "limits.atm.velocity_window_minutes": _baseline(
            "60", "integer", "Sliding window for velocity checks."
        ),
        "limits.atm.velocity_max_transactions": _baseline(
            "3", "integer", "Transactions allowed inside the velocity window."
        ),
        "limits.digital.per_payment_amount": _baseline(
            "2500.00", "decimal", "Largest single digital payment."
        ),
        "limits.digital.daily_payment_amount": _baseline(
            "5000.00", "decimal", "Total digital payments per day."
        ),
        "limits.enforcement_mode": _baseline(
            "strict", "enum", "strict rejects a breach; advisory logs only."
        ),
        "limits.currency": _baseline(
            "EUR", "string", "Currency all limit amounts are expressed in."
        ),
    },
}
"""The synthetic ConfigurationStore contents, keyed by canonical component.

Owned by this module and nothing else. The keys and documented defaults track
``data/knowledge/configuration/`` so that a reader can hold the document and
the tool output side by side; where the two disagree, the disagreement is
deliberate and recorded in ``documented_default``.
"""

_CANONICAL_COMPONENTS: Mapping[str, str] = {
    component.casefold(): component for component in _CONFIGURATION
}
"""Case-folded component name to its canonical spelling.

Callers type ``limitservice``, ``LimitService`` and ``LIMITSERVICE`` for the
same thing, and in Stage 7 a language model will produce whichever spelling the
question used. Matching is forgiving; the echoed value never is.
"""

_CANONICAL_KEYS: Mapping[str, Mapping[str, str]] = {
    component: {key.casefold(): key for key in entries}
    for component, entries in _CONFIGURATION.items()
}
"""Per component, case-folded configuration key to its canonical spelling."""

_SPEC = ToolSpec(
    name=_TOOL_NAME,
    summary=(
        "Report the effective value of one configuration key for one "
        "component, and the level that supplied it."
    ),
    description=(
        "Mirrors ConfigurationStore's GET /config/v1/config/{component}/{key}. "
        "Returns the value actually in effect, the immutable configuration "
        "version it came from, the precedence level that supplied it "
        "(platform_default, card_product or account_override), the audit "
        "record for the change, and the documented platform default so the "
        "two can be compared. Where the effective value disagrees with the "
        "documentation, the disagreement is usually the answer. It does NOT "
        "change configuration - there is no runtime write path - does NOT "
        "explain a specific transaction (use check_transaction_status), and "
        "never serves credentials, API keys or cryptographic material: those "
        "are not configuration and a request for one is refused."
    ),
    parameters=(
        ToolParameter(
            name="component",
            description=(
                "The component that owns the key. Matched case-insensitively."
            ),
            required=True,
            example="LimitService",
        ),
        ToolParameter(
            name="key",
            description="The dotted configuration key to read.",
            required=True,
            example="limits.atm.per_transaction_amount",
        ),
    ),
)


def _looks_like_a_secret(key: str) -> bool:
    """Whether a requested key is credential-shaped and must not be served.

    Args:
        key: The key as the caller supplied it.

    Returns:
        ``True`` if the key contains any marker in :data:`_SECRET_MARKERS`.
    """
    folded = key.casefold()
    return any(marker in folded for marker in _SECRET_MARKERS)


class SystemConfigurationTool:
    """Reads one effective configuration value from synthetic data.

    Holds no state beyond the module-level dataset, so a single instance is
    safe to share and :meth:`invoke` is pure: the same component and key
    produce the same result in every process, on every run.
    """

    @property
    def spec(self) -> ToolSpec:
        """What this tool is and how to call it."""
        return _SPEC

    @traced
    def invoke(self, arguments: Mapping[str, str]) -> ToolResult:
        """Look up the effective value of one configuration key.

        Args:
            arguments: Must contain ``component`` and ``key``, both non-empty.
                Both are matched case-insensitively and echoed back in their
                canonical spelling.

        Returns:
            On a hit, ``ok=True`` with the value, its type, the configuration
            version, the precedence level, the audit record, the documented
            default and whether the two differ. On an unknown component, an
            unknown key, or a request for something credential-shaped,
            ``ok=False`` with a stable ``error_code`` - each of which is a
            true answer, not a malfunction.

        Raises:
            ToolInputError: If ``component`` or ``key`` is missing or blank,
                or if any other argument is supplied.
        """
        reject_unknown_arguments(arguments, _SPEC)
        component = require_argument(arguments, "component", _TOOL_NAME)
        key = require_argument(arguments, "key", _TOOL_NAME)

        # Checked first, and before the component is validated: see the module
        # docstring on why a refusal must not double as an existence oracle.
        if _looks_like_a_secret(key):
            return ToolResult.failure(
                tool=_TOOL_NAME,
                summary=(
                    f"Refused: '{key}' is credential-shaped and secrets are "
                    f"never served through configuration."
                ),
                error_code="SECRET_NOT_SERVED",
                error_message=(
                    "ConfigurationStore holds operational values only. "
                    "Credentials, API keys and cryptographic material reach "
                    "components through their runtime environment and secret "
                    "management, and never appear in a configuration version "
                    "or audit record. No value was read."
                ),
            )

        canonical_component = _CANONICAL_COMPONENTS.get(component.casefold())
        if canonical_component is None:
            known = ", ".join(sorted(_CONFIGURATION))
            return ToolResult.failure(
                tool=_TOOL_NAME,
                summary=f"No component named '{component}' holds configuration.",
                error_code="UNKNOWN_COMPONENT",
                error_message=(
                    f"ConfigurationStore holds no configuration for "
                    f"'{component}'. Components with configuration: {known}."
                ),
            )

        canonical_key = _CANONICAL_KEYS[canonical_component].get(key.casefold())
        if canonical_key is None:
            known = ", ".join(sorted(_CONFIGURATION[canonical_component]))
            return ToolResult.failure(
                tool=_TOOL_NAME,
                summary=(f"{canonical_component} has no configuration key '{key}'."),
                error_code="UNKNOWN_KEY",
                error_message=(
                    f"'{key}' is not a configuration key of "
                    f"{canonical_component}. Its keys are: {known}."
                ),
            )

        entry = _CONFIGURATION[canonical_component][canonical_key]
        return ToolResult.success(
            tool=_TOOL_NAME,
            summary=_summarise(canonical_component, canonical_key, entry),
            data={
                "component": canonical_component,
                "key": canonical_key,
                "value": entry.value,
                "value_type": entry.value_type,
                "configuration_version": entry.configuration_version,
                "precedence": entry.precedence,
                "last_changed_by": entry.last_changed_by,
                "last_changed_reason": entry.last_changed_reason,
                "documented_default": entry.documented_default,
                "differs_from_documented_default": (
                    entry.differs_from_documented_default
                ),
                "controls": entry.controls,
            },
        )


def _summarise(component: str, key: str, entry: _ConfigEntry) -> str:
    """Write the one human-readable line that accompanies a hit.

    The comparison with the documented default is stated in the summary and
    not only in the payload, because the summary is what a log line and a
    prompt header show, and a reader who sees only ``= 250.00`` has been given
    a number without the thing that makes it surprising.

    Args:
        component: Canonical component name.
        key: Canonical configuration key.
        entry: The resolved entry.

    Returns:
        One line, safe to log and to display.
    """
    comparison = (
        f"documented default is {entry.documented_default}"
        if entry.differs_from_documented_default
        else "matches the documented default"
    )
    return (
        f"{component} {key} = {entry.value} ({entry.value_type}, from "
        f"{entry.precedence}, configuration version "
        f"{entry.configuration_version}; {comparison})."
    )
