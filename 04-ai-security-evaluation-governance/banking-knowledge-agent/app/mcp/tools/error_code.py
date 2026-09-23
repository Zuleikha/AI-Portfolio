"""The ``look_up_error_code`` tool: a platform error code in, a diagnosis out.

A support engineer almost never arrives with a question. They arrive with a
code — ``LIM-4001`` in a log line, ``PAY-8003`` in a screenshot, something
``COR-`` shaped half-remembered from a call. This tool turns that string into
the four things they actually need: which component raised it, whether it is a
normal business outcome or a fault, whether money moved, and what to do next.

**Why this is a tool and not retrieval.** ``data/knowledge`` already contains the
error-code reference, and the RAG layer can find it. But a lookup by exact key is
the one question retrieval is worst at: forty codes in one document all score
alike against "what is LIM-4001", and the chunk that comes back may well be the
CoreBankingAdapter table. An exact-match dictionary is not an optimisation here,
it is a correctness fix. What retrieval keeps is the *prose* — the runbooks and
lifecycle documents this tool deliberately does not try to reproduce.

**Wrapper codes are the reason this tool earns its place.** ``PAY-8003`` says a
payment was declined; it does not say by what. The reference calls treating it as
the cause "the most common diagnostic mistake in the payments domain", and
``SWX-7001`` — a timeout that names TransactionSwitch while the fault sits in
whichever downstream component was slow — misleads the same way. Both are flagged
with an explicit ``is_wrapper`` boolean *and* remediation text that refuses to
answer the question as asked. A tool that returned "Authorisation declined" and
stopped would be accurate, useless, and actively harmful, because it would end
the investigation one hop short of the cause.

**What was rejected.**

* *Parsing the markdown reference at call time.* It would make the tool's answer
  depend on the filesystem, break :class:`~app.mcp.base.Tool`'s purity guarantee,
  and couple a tool to a document's table formatting. The catalogue is inlined
  and owned here. The documents remain the source of truth for a human; this
  module is a faithful transcription of them and nothing more.
* *Raising on an unknown code.* An invented-looking code is a finding, not a
  breakage — see :class:`~app.mcp.models.ToolResult`. If someone reports
  ``LIM-4004``, the useful answer is "LimitService is real, that code is not",
  which usually means a typo or a fabricated log line. So a miss whose prefix is
  a known component is reported *differently* from a miss whose prefix is not,
  and the failure carries the codes that component does document.
* *Treating a malformed string as a caller error.* ``ToolInputError`` is reserved
  for the call being wrong. A garbled paste is a wrong *value*, answered with the
  expected shape rather than an exception — the same reasoning as an unknown
  code, one step further out.

**Two different things are both called an error code here**, and conflating them
would be a real bug: :attr:`~app.mcp.models.ToolResult.error_code` is the
*tool-failure* code (``NOT_FOUND``), while the banking code the caller asked
about always travels in ``data`` under ``error_code``. On a miss there is no
``data`` at all, so the two can never appear in the same field.

Everything here is synthetic and frozen: no clock, no I/O, no randomness.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import JsonValue

from app.core.tracing import traced
from app.mcp.base import reject_unknown_arguments, require_argument
from app.mcp.models import ToolName, ToolParameter, ToolResult, ToolSpec

TOOL_NAME: Final[ToolName] = "look_up_error_code"
"""This tool's key in :data:`app.mcp.models.ToolName`, named once."""

ARGUMENT_ERROR_CODE: Final[str] = "error_code"
"""The single argument. Named as a constant so the spec and the reader agree."""

ERROR_NOT_FOUND: Final[str] = "NOT_FOUND"
"""Miss: the prefix belongs to no known component (or the code is unknown)."""

ERROR_UNKNOWN_CODE_FOR_COMPONENT: Final[str] = "UNKNOWN_CODE_FOR_COMPONENT"
"""Miss: the component is real, this number is not documented against it."""

ERROR_MALFORMED_CODE: Final[str] = "MALFORMED_CODE"
"""Miss: the value is not shaped like ``PREFIX-NNNN`` at all."""

_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^([A-Z]{3})-(\d{4})$")
"""Canonical code shape, applied after upper-casing and stripping."""

ReversalRole = Literal["none", "triggers", "is_reversal", "reversal_failed"]
"""A code's relationship to reversals.

Four states rather than one boolean, because the interesting cases are not
symmetrical. ``DEV-6004`` *causes* a reversal; ``SWX-7004`` *is* one;
``SWX-7006`` is one that never completed and is now sitting in the exception
queue. Collapsing those into ``triggers_reversal: true`` would tell a reader that
money is being returned in a case where it demonstrably is not.
"""


@dataclass(frozen=True)
class ErrorCodeEntry:
    """One row of the platform error code catalogue.

    Attributes:
        component: The component that raises the code, e.g. ``LimitService``.
        meaning: The reference's one-line meaning, transcribed verbatim.
        error_class: The reference's class column — ``Business``, ``Fault``,
            ``Configuration``, ``Client``, ``Operational``, ``Informational``,
            ``Wrapper`` or ``Business or fraud``. Only the fault classes warrant
            an incident, which is why the column is carried through unchanged
            rather than being reduced to a severity.
        remediation: What to do about it, in the caller's language.
        is_wrapper: Whether the code hides the real cause behind it. Not derived
            from ``error_class``: ``SWX-7001`` is classed ``Fault`` in the
            reference and still misdirects exactly like a wrapper, so the two
            facts are recorded separately.
        wrapper_guidance: Where the real cause is to be found. Present only when
            ``is_wrapper`` is true.
        reversal_role: See :data:`ReversalRole`.
        breached_configuration_key: The limit key this code reports a breach of,
            for ``LIM-`` codes. ``None`` everywhere else.
    """

    component: str
    meaning: str
    error_class: str
    remediation: str
    is_wrapper: bool = False
    wrapper_guidance: str | None = None
    reversal_role: ReversalRole = "none"
    breached_configuration_key: str | None = None


COMPONENT_BY_PREFIX: Final[Mapping[str, str]] = {
    "SWX": "TransactionSwitch",
    "AUT": "AuthorizationService",
    "CSM": "CardSecurityModule",
    "LIM": "LimitService",
    "COR": "CoreBankingAdapter",
    "PAY": "PaymentEngine",
    "DGW": "DigitalGateway",
    "DEV": "DeviceManager",
    "CFG": "ConfigurationStore",
}
"""Prefix to component, from the reference's own table.

``CFG`` is listed with no codes beneath it, and that gap is kept rather than
quietly dropped: ``CFG-1000`` should be answered with "ConfigurationStore is
real, that code is not", which is a far more useful reply than a bare miss.
"""

_WRAPPER_PAY_8003: Final[str] = (
    "PAY-8003 is a WRAPPER. It reports that something declined the payment, not "
    "what. Read `decline_reason` in the response body and look that code up "
    "instead — it will name the component that actually declined "
    "(AuthorizationService, LimitService, CoreBankingAdapter). Treating PAY-8003 "
    "itself as the cause is the most common diagnostic mistake in the payments "
    "domain."
)

_WRAPPER_SWX_7001: Final[str] = (
    "SWX-7001 behaves as a WRAPPER. It names TransactionSwitch, but the fault is "
    "nearly always in whichever downstream component was slow. Identify the "
    "downstream call that timed out and diagnose that component; the switch is "
    "the reporter, not the cause."
)

CATALOGUE: Final[Mapping[str, ErrorCodeEntry]] = {
    # --- AuthorizationService -------------------------------------------------
    "AUT-2001": ErrorCodeEntry(
        component="AuthorizationService",
        meaning="Card not found",
        error_class="Business",
        remediation=(
            "Confirm the card number or token was passed correctly. A card that "
            "was never issued and one whose token has been rotated look "
            "identical here, so check the card record before escalating."
        ),
    ),
    "AUT-2004": ErrorCodeEntry(
        component="AuthorizationService",
        meaning="Card blocked",
        error_class="Business",
        remediation=(
            "Expected behaviour, not a fault. Find the block reason and who set "
            "it (fraud, customer request, arrears). The block is lifted in card "
            "management; retrying the transaction will fail identically."
        ),
    ),
    "AUT-2007": ErrorCodeEntry(
        component="AuthorizationService",
        meaning="Card expired",
        error_class="Business",
        remediation=(
            "Check the expiry date on the card record against the transaction "
            "date. Reissue is a card-management action; no platform "
            "configuration change will authorise an expired card."
        ),
    ),
    "AUT-2012": ErrorCodeEntry(
        component="AuthorizationService",
        meaning="Card product not enabled for channel",
        error_class="Configuration",
        remediation=(
            "A configuration gap, not a customer problem — every card on this "
            "product will fail on this channel. Enable the product for the "
            "channel and re-test before replying to the customer."
        ),
    ),
    "AUT-2015": ErrorCodeEntry(
        component="AuthorizationService",
        meaning="Geographic restriction",
        error_class="Business",
        remediation=(
            "Compare the card's geographic restriction list with the acquirer "
            "country of the transaction. Lift the restriction only on the "
            "customer's instruction."
        ),
    ),
    # --- CardSecurityModule ---------------------------------------------------
    "CSM-3002": ErrorCodeEntry(
        component="CardSecurityModule",
        meaning="PIN verification failed",
        error_class="Business",
        remediation=(
            "The normal outcome of a wrong PIN. Check the PIN retry counter "
            "before assuming a platform issue — repeated failures block the "
            "card, and the block is then reported as AUT-2004, not as this."
        ),
    ),
    "CSM-3005": ErrorCodeEntry(
        component="CardSecurityModule",
        meaning="Invalid PIN block format",
        error_class="Configuration",
        remediation=(
            "The terminal or channel sent a PIN block in a format "
            "CardSecurityModule does not expect. A terminal build or "
            "configuration problem; it is never caused by what the customer "
            "typed, and it will affect every transaction from that estate."
        ),
    ),
    "CSM-3007": ErrorCodeEntry(
        component="CardSecurityModule",
        meaning="Cryptogram validation failed",
        error_class="Business or fraud",
        remediation=(
            "Either a genuine cryptogram mismatch or a fraud signal. Correlate "
            "with the card's recent activity and the terminal before treating "
            "it as a platform fault; a cluster on one terminal is a different "
            "investigation from a single occurrence."
        ),
    ),
    "CSM-3010": ErrorCodeEntry(
        component="CardSecurityModule",
        meaning="HSM unavailable",
        error_class="Fault",
        remediation=(
            "A fault warranting an incident. Every PIN and cryptogram operation "
            "fails platform-wide while it lasts. Check HSM health and the "
            "CardSecurityModule connection pool; retrying individual "
            "transactions achieves nothing."
        ),
    ),
    "CSM-3014": ErrorCodeEntry(
        component="CardSecurityModule",
        meaning="Key check value mismatch",
        error_class="Configuration",
        remediation=(
            "The loaded key is not the key expected. A key-ceremony or "
            "configuration error — correct the key material rather than "
            "retrying, which will fail identically every time."
        ),
    ),
    # --- LimitService ---------------------------------------------------------
    "LIM-4001": ErrorCodeEntry(
        component="LimitService",
        meaning="Daily withdrawal amount exceeded",
        error_class="Business",
        remediation=(
            "Cumulative ATM withdrawals for the day exceeded the effective "
            "value of `limits.atm.daily_withdrawal_amount`. Read the effective "
            "value for this account before quoting the documented default — an "
            "account or product override may apply, and the difference is "
            "usually the whole answer."
        ),
        breached_configuration_key="limits.atm.daily_withdrawal_amount",
    ),
    "LIM-4002": ErrorCodeEntry(
        component="LimitService",
        meaning="Per-transaction amount exceeded",
        error_class="Business",
        remediation=(
            "The single withdrawal was larger than the effective "
            "`limits.atm.per_transaction_amount`. A lower per-transaction "
            "override does not discard the daily amount limit; both still "
            "apply, so clearing this one may simply reveal LIM-4001."
        ),
        breached_configuration_key="limits.atm.per_transaction_amount",
    ),
    "LIM-4003": ErrorCodeEntry(
        component="LimitService",
        meaning="Daily withdrawal count exceeded",
        error_class="Business",
        remediation=(
            "The account has used all of `limits.atm.daily_withdrawal_count` "
            "withdrawals today. A count limit, not an amount limit — the "
            "customer can be well inside their daily allowance and still be "
            "stopped by this."
        ),
        breached_configuration_key="limits.atm.daily_withdrawal_count",
    ),
    "LIM-4005": ErrorCodeEntry(
        component="LimitService",
        meaning="Velocity limit exceeded",
        error_class="Business",
        remediation=(
            "More than `limits.atm.velocity_max_transactions` withdrawals inside "
            "the `limits.atm.velocity_window_minutes` sliding window. Distinct "
            "from the daily count limit and it clears by itself as the window "
            "moves, so a customer retrying later may well succeed."
        ),
        breached_configuration_key="limits.atm.velocity_max_transactions",
    ),
    "LIM-4008": ErrorCodeEntry(
        component="LimitService",
        meaning="Digital per-payment amount exceeded",
        error_class="Business",
        remediation=(
            "The single digital payment exceeded the effective "
            "`limits.digital.per_payment_amount`. Digital limits are separate "
            "from ATM limits — do not diagnose this against the ATM values."
        ),
        breached_configuration_key="limits.digital.per_payment_amount",
    ),
    "LIM-4009": ErrorCodeEntry(
        component="LimitService",
        meaning="Digital daily payment amount exceeded",
        error_class="Business",
        remediation=(
            "Cumulative digital payments for the day exceeded the effective "
            "`limits.digital.daily_payment_amount`. Check the effective value "
            "for the account, and note that this is reported to PaymentEngine "
            "callers as PAY-8003 with LIM-4009 as the decline reason."
        ),
        breached_configuration_key="limits.digital.daily_payment_amount",
    ),
    # --- CoreBankingAdapter ---------------------------------------------------
    "COR-5003": ErrorCodeEntry(
        component="CoreBankingAdapter",
        meaning="Insufficient funds",
        error_class="Business",
        remediation=(
            "A normal decline from the core banking system, not a platform "
            "fault. Confirm the available balance rather than the ledger "
            "balance; pending authorisations reduce one and not the other."
        ),
    ),
    "COR-5006": ErrorCodeEntry(
        component="CoreBankingAdapter",
        meaning="Account blocked or dormant",
        error_class="Business",
        remediation=(
            "The account, not the card, is the problem — AUT-2004 is the card "
            "equivalent and they are frequently confused. Resolution is an "
            "account-servicing action in the core banking system."
        ),
    ),
    "COR-5008": ErrorCodeEntry(
        component="CoreBankingAdapter",
        meaning="Core banking timeout",
        error_class="Fault",
        remediation=(
            "A fault. The posting may or may not have been applied at the core, "
            "so absence of a reversal record is not proof that no debit "
            "occurred. Verify the posting by transaction reference before "
            "telling a customer their money was not taken."
        ),
    ),
    "COR-5011": ErrorCodeEntry(
        component="CoreBankingAdapter",
        meaning="Core banking rejected the posting",
        error_class="Fault",
        remediation=(
            "The core banking system refused the posting outright. Retrying is "
            "safe — postings are idempotent on the transaction reference — but "
            "it will not help until the rejection reason at the core is fixed."
        ),
    ),
    "COR-5015": ErrorCodeEntry(
        component="CoreBankingAdapter",
        meaning="Connection pool exhausted",
        error_class="Fault",
        remediation=(
            "A capacity fault, not a per-transaction one: it affects every "
            "channel at once and typically appears alongside SWX-7001 upstream. "
            "Check core banking latency and the adapter's pool sizing."
        ),
    ),
    # --- TransactionSwitch ----------------------------------------------------
    "SWX-7001": ErrorCodeEntry(
        component="TransactionSwitch",
        meaning="Downstream timeout",
        error_class="Fault",
        remediation=_WRAPPER_SWX_7001,
        is_wrapper=True,
        wrapper_guidance=(
            "The real cause is the downstream component that failed to respond "
            "in time — commonly CoreBankingAdapter (COR-5008, COR-5015) or "
            "CardSecurityModule (CSM-3010). Do not diagnose TransactionSwitch."
        ),
    ),
    "SWX-7004": ErrorCodeEntry(
        component="TransactionSwitch",
        meaning="Reversal generated",
        error_class="Informational",
        remediation=(
            "Informational and expected. This code IS the reversal: "
            "TransactionSwitch has sent it to CoreBankingAdapter to release or "
            "refund an amount already authorised. Its presence is the good "
            "outcome after a failed dispense; confirm it was acknowledged, "
            "because an unacknowledged one becomes SWX-7006."
        ),
        reversal_role="is_reversal",
    ),
    "SWX-7006": ErrorCodeEntry(
        component="TransactionSwitch",
        meaning="Reversal unacknowledged after retries",
        error_class="Fault",
        remediation=(
            "A fault with direct customer money impact. The reversal was "
            "retried `switch.reversal_retry_count` times without acknowledgement "
            "and is now in the reversal exception queue; it will NOT resolve on "
            "its own. The customer is still out of pocket until it is worked."
        ),
        reversal_role="reversal_failed",
    ),
    "SWX-7009": ErrorCodeEntry(
        component="TransactionSwitch",
        meaning="Unroutable transaction type",
        error_class="Configuration",
        remediation=(
            "TransactionSwitch has no route for this transaction type. A "
            "routing configuration gap, so it fails deterministically for every "
            "transaction of that type rather than intermittently."
        ),
    ),
    # --- DeviceManager --------------------------------------------------------
    "DEV-6002": ErrorCodeEntry(
        component="DeviceManager",
        meaning="Cassette empty",
        error_class="Operational",
        remediation=(
            "The denomination was unavailable at the terminal. An operational "
            "matter for replenishment, but the account was already debited at "
            "authorisation, so confirm the reversal (SWX-7004) landed."
        ),
        reversal_role="triggers",
    ),
    "DEV-6004": ErrorCodeEntry(
        component="DeviceManager",
        meaning="Dispenser jam",
        error_class="Fault",
        remediation=(
            "A mechanical failure mid-dispense. Take the terminal out of "
            "service for engineering, and confirm the reversal (SWX-7004) was "
            "generated and acknowledged — the customer has been debited."
        ),
        reversal_role="triggers",
    ),
    "DEV-6009": ErrorCodeEntry(
        component="DeviceManager",
        meaning="Note count mismatch",
        error_class="Fault",
        remediation=(
            "The counter and the dispenser disagree. The only dispense outcome "
            "that cannot be resolved from the platform alone: the discrepancy "
            "must be settled against the physical cash count at the next "
            "replenishment. A reversal is raised and reconciliation follows; at "
            "volume this is an incident."
        ),
        reversal_role="triggers",
    ),
    "DEV-6011": ErrorCodeEntry(
        component="DeviceManager",
        meaning="Notes presented but not taken",
        error_class="Operational",
        remediation=(
            "The notes were presented and retracted after a timeout. "
            "Operational, and it triggers a reversal — but the retracted cash "
            "must still be reconciled, so this is not automatically a "
            "no-impact outcome for the customer."
        ),
        reversal_role="triggers",
    ),
    # --- PaymentEngine --------------------------------------------------------
    "PAY-8001": ErrorCodeEntry(
        component="PaymentEngine",
        meaning="Request validation failed",
        error_class="Client",
        remediation=(
            "The caller's request was malformed or incomplete. Fix the request; "
            "nothing on the platform side will change the outcome, and no "
            "payment was attempted."
        ),
    ),
    "PAY-8003": ErrorCodeEntry(
        component="PaymentEngine",
        meaning="Authorisation declined",
        error_class="Wrapper",
        remediation=_WRAPPER_PAY_8003,
        is_wrapper=True,
        wrapper_guidance=(
            "The underlying code is in the `decline_reason` field of the "
            "response body. Look THAT code up — PAY-8003 itself identifies no "
            "cause and no component."
        ),
    ),
    "PAY-8007": ErrorCodeEntry(
        component="PaymentEngine",
        meaning="Idempotency key conflict",
        error_class="Client",
        remediation=(
            "The same idempotency key was reused for a different payload. This "
            "is the protection working: it prevents a double payment. Resolve "
            "by reconciling the original payment rather than by reissuing with "
            "a fresh key."
        ),
    ),
    "PAY-8011": ErrorCodeEntry(
        component="PaymentEngine",
        meaning="Currency not supported",
        error_class="Configuration",
        remediation=(
            "The requested currency is not configured for the payment product. "
            "A configuration answer; it fails identically for every caller "
            "using that currency."
        ),
    ),
    "PAY-8020": ErrorCodeEntry(
        component="PaymentEngine",
        meaning="Downstream unavailable",
        error_class="Fault",
        remediation=(
            "A downstream dependency of PaymentEngine could not be reached. "
            "Retryable once the dependency recovers; identify which downstream "
            "is down before retrying, and check for a matching COR- or SWX- "
            "fault at the same moment."
        ),
    ),
    # --- DigitalGateway -------------------------------------------------------
    "DGW-9002": ErrorCodeEntry(
        component="DigitalGateway",
        meaning="Session expired",
        error_class="Business",
        remediation=(
            "The session outlived its lifetime. Expected; the customer signs in "
            "again. Distinct from DGW-9004, which means the token was never "
            "valid — an expired session is routine, an invalid token is not."
        ),
    ),
    "DGW-9004": ErrorCodeEntry(
        component="DigitalGateway",
        meaning="Session token invalid",
        error_class="Business",
        remediation=(
            "The token presented did not validate. Treat a cluster of these as "
            "a possible security signal rather than a usability problem; a "
            "single occurrence after a client update is usually benign."
        ),
    ),
    "DGW-9006": ErrorCodeEntry(
        component="DigitalGateway",
        meaning="Step-up authentication required",
        error_class="Informational",
        remediation=(
            "Not a failure. The channel is asking for stronger authentication "
            "before proceeding; the client is expected to run the step-up flow "
            "and retry. A client that surfaces this to the customer as an error "
            "is a client bug."
        ),
    ),
    "DGW-9009": ErrorCodeEntry(
        component="DigitalGateway",
        meaning="Rate limit exceeded",
        error_class="Client",
        remediation=(
            "The caller exceeded its permitted request rate. Back off and "
            "retry; if it is sustained, the client is looping rather than the "
            "limit being wrong."
        ),
    ),
    "DGW-9012": ErrorCodeEntry(
        component="DigitalGateway",
        meaning="Channel disabled",
        error_class="Configuration",
        remediation=(
            "The channel is switched off in configuration — deliberately, for "
            "maintenance, or by mistake. Affects every customer on that "
            "channel, so check this before investigating any single case."
        ),
    ),
    "DGW-9014": ErrorCodeEntry(
        component="DigitalGateway",
        meaning="Client version unsupported",
        error_class="Client",
        remediation=(
            "The client application version is below the supported minimum. "
            "The customer must update the app; no server-side change resolves "
            "it for them."
        ),
    ),
}
"""The complete platform error code catalogue, keyed by canonical code.

Transcribed from ``data/knowledge/operations/error-code-reference.md``, with the
``LIM-`` breached keys from
``data/knowledge/configuration/transaction-limits-configuration.md`` and the
dispense reversal outcomes from ``data/knowledge/atm/atm-device-states.md``. The
meanings and classes are verbatim; the remediation text is this tool's own
contribution and is the part a caller cannot get from a table.
"""


def _codes_for_prefix(prefix: str) -> tuple[str, ...]:
    """List the documented codes for one component prefix, in order.

    Args:
        prefix: An upper-case three-letter prefix, e.g. ``"LIM"``.

    Returns:
        Every catalogue code carrying that prefix, sorted. Empty for a prefix
        that is a real component with no documented codes, such as ``CFG``.
    """
    return tuple(sorted(code for code in CATALOGUE if code.startswith(f"{prefix}-")))


class ErrorCodeLookupTool:
    """Resolves a platform error code to its meaning, owner and remediation.

    Implements :class:`app.mcp.base.Tool` structurally — it inherits from
    nothing and imports the protocol only for the shared argument helpers, so
    that the seam stays a shape rather than a base class.

    :meth:`invoke` is pure: it reads a frozen module-level dictionary and
    consults no clock, file or network. The same code produces the same result
    in every session, which is what lets the demo output and the test suite
    assert on it directly.
    """

    _SPEC: Final[ToolSpec] = ToolSpec(
        name=TOOL_NAME,
        summary="Explain a platform error code: component, class and what to do.",
        description=(
            "Looks up a code of the form PREFIX-NNNN in the platform error code "
            "reference and returns the component that raised it, its class "
            "(Business, Fault, Configuration, Client, Operational, "
            "Informational or Wrapper), whether it is a wrapper hiding another "
            "code, whether it involves a reversal, the limit configuration key "
            "it reports a breach of where there is one, and what to do next. "
            "Matching is case-insensitive. It does NOT look up a specific "
            "transaction, read a live component's health, or tell you whether "
            "this code is occurring now — use check_transaction_status, "
            "get_component_status or check_service_health for those. A code "
            "that is not in the catalogue is reported as a normal result with "
            "ok=false, not as an error."
        ),
        parameters=(
            ToolParameter(
                name=ARGUMENT_ERROR_CODE,
                description=(
                    "The platform error code to explain, PREFIX-NNNN. "
                    "Case-insensitive."
                ),
                required=True,
                example="LIM-4001",
            ),
        ),
    )

    @property
    def spec(self) -> ToolSpec:
        """What this tool is and how to call it."""
        return self._SPEC

    @traced
    def invoke(self, arguments: Mapping[str, str]) -> ToolResult:
        """Explain one platform error code.

        Args:
            arguments: Must contain ``error_code``. Surrounding whitespace and
                letter case are tolerated; the canonical upper-case form is
                echoed back in ``data``.

        Returns:
            On a hit, ``ok=True`` with the catalogue entry in ``data``. On a
            miss, ``ok=False`` with :data:`ERROR_UNKNOWN_CODE_FOR_COMPONENT`
            when the prefix names a real component, :data:`ERROR_MALFORMED_CODE`
            when the value is not shaped like a code at all, and
            :data:`ERROR_NOT_FOUND` otherwise. ``data`` is empty on a miss, so
            the banking code and the tool-failure code can never be confused.

        Raises:
            ToolInputError: If ``error_code`` is missing or blank, or if any
                argument this tool does not declare was supplied.
        """
        reject_unknown_arguments(arguments, self._SPEC)
        raw = require_argument(arguments, ARGUMENT_ERROR_CODE, TOOL_NAME)
        code = raw.upper()

        match = _CODE_PATTERN.match(code)
        if match is None:
            return self._malformed(raw)

        entry = CATALOGUE.get(code)
        if entry is None:
            return self._miss(code, prefix=match.group(1))

        return ToolResult.success(
            tool=TOOL_NAME,
            summary=self._summarise(code, entry),
            data=self._payload(code, match.group(1), entry),
        )

    @staticmethod
    def _payload(
        code: str,
        prefix: str,
        entry: ErrorCodeEntry,
    ) -> dict[str, JsonValue]:
        """Render one catalogue entry as the structured payload.

        Args:
            code: The canonical upper-case code.
            prefix: Its three-letter component prefix.
            entry: The catalogue row.

        Returns:
            The ``data`` mapping for a successful result.
        """
        return {
            "error_code": code,
            "component": entry.component,
            "component_code": prefix,
            "meaning": entry.meaning,
            "error_class": entry.error_class,
            "is_wrapper": entry.is_wrapper,
            "wrapper_guidance": entry.wrapper_guidance,
            "triggers_reversal": entry.reversal_role == "triggers",
            "reversal_role": entry.reversal_role,
            "breached_configuration_key": entry.breached_configuration_key,
            "remediation": entry.remediation,
            "warrants_incident": entry.error_class == "Fault",
        }

    @staticmethod
    def _summarise(code: str, entry: ErrorCodeEntry) -> str:
        """Write the one human-readable line for a hit.

        The wrapper warning goes first, before the meaning, because a reader who
        stops at the end of the first clause must not walk away believing
        ``PAY-8003`` identified the cause.

        Args:
            code: The canonical upper-case code.
            entry: The catalogue row.

        Returns:
            A single line, safe to log and to display.
        """
        parts: list[str] = []
        if entry.is_wrapper:
            parts.append("WRAPPER CODE.")
        parts.append(f"{code} ({entry.component}, {entry.error_class}):")
        parts.append(f"{entry.meaning}.")
        if entry.is_wrapper:
            parts.append("This is not the cause; the real code is behind it.")
        if entry.breached_configuration_key is not None:
            parts.append(f"Breaches {entry.breached_configuration_key}.")
        if entry.reversal_role == "triggers":
            parts.append("Triggers a reversal (SWX-7004).")
        elif entry.reversal_role == "is_reversal":
            parts.append("This code is itself the reversal.")
        elif entry.reversal_role == "reversal_failed":
            parts.append("A reversal that was never acknowledged.")
        return " ".join(parts)

    @staticmethod
    def _miss(code: str, prefix: str) -> ToolResult:
        """Report a well-formed code that is not in the catalogue.

        A miss whose prefix names a real component is a materially better answer
        than a bare "not found": it separates "you mistyped a LimitService code"
        from "no component on this platform uses that prefix", and the second is
        strong evidence the code was invented or came from another system. The
        codes the component *does* document are listed, because that is what the
        reader will ask for next.

        Args:
            code: The canonical upper-case code.
            prefix: Its three-letter component prefix.

        Returns:
            A ``ok=False`` result. Never raises — an unknown code is data.
        """
        component = COMPONENT_BY_PREFIX.get(prefix)
        if component is None:
            return ToolResult.failure(
                tool=TOOL_NAME,
                summary=(
                    f"{code} is not in the platform error code catalogue, and "
                    f"'{prefix}' is not a known component prefix."
                ),
                error_code=ERROR_NOT_FOUND,
                error_message=(
                    f"No component uses the prefix '{prefix}'. Known prefixes: "
                    f"{', '.join(sorted(COMPONENT_BY_PREFIX))}. A code with an "
                    "unrecognised prefix usually did not come from this "
                    "platform, or was transcribed incorrectly."
                ),
            )

        known = _codes_for_prefix(prefix)
        documented = ", ".join(known) if known else "none"
        return ToolResult.failure(
            tool=TOOL_NAME,
            summary=(
                f"{code} is not in the catalogue, but '{prefix}' is "
                f"{component}: the component is real, this code is not."
            ),
            error_code=ERROR_UNKNOWN_CODE_FOR_COMPONENT,
            error_message=(
                f"{component} raises codes with the prefix '{prefix}', but "
                f"{code} is not documented against it. Documented "
                f"{prefix} codes: {documented}. Check for a transcription error "
                "before treating this code as real."
            ),
        )

    @staticmethod
    def _malformed(raw: str) -> ToolResult:
        """Report a value that is not shaped like a platform error code.

        Answered as data rather than raised, for the same reason an unknown code
        is: the caller asked a sensible question about a string they were given,
        and the useful reply states the expected shape.

        Args:
            raw: The argument as supplied, stripped but not upper-cased.

        Returns:
            A ``ok=False`` result carrying the expected format.
        """
        return ToolResult.failure(
            tool=TOOL_NAME,
            summary=(
                f"'{raw}' is not a platform error code. Codes have the form "
                "PREFIX-NNNN, for example LIM-4001."
            ),
            error_code=ERROR_MALFORMED_CODE,
            error_message=(
                f"Could not read '{raw}' as an error code. Expected three "
                "letters, a hyphen and four digits, e.g. 'PAY-8003'. Known "
                f"prefixes: {', '.join(sorted(COMPONENT_BY_PREFIX))}."
            ),
        )
