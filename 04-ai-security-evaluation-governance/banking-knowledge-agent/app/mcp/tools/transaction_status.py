"""``check_transaction_status`` — how far one transaction got, and why it stopped.

This is the first tool a support engineer reaches for, because the documented
runbook says so: *Troubleshooting a Failed Cash Withdrawal* opens with "Step 1 —
Get the transaction reference", and observes that without it "logs from nine
components cannot be correlated". Everything the other five tools report is
context around the answer this one gives.

**Why the eight documented stages are the vocabulary.** The obvious design is a
flat status enum — ``DECLINED``, ``FAILED``, ``OK``. It was rejected because it
throws away the one fact that decides what happens next. *ATM Transaction
Lifecycle* §"Why a transaction can fail after card authentication" is explicit:
a failure at stage 4 means no debit occurred and nothing is owed, while a
failure at stage 7 means the account was debited and the customer is out of
pocket until a reversal settles. Both are "failed". Only ``stage_reached``
separates them, so it is a first-class field, named with the exact stage names
from the reference table rather than paraphrased — a tool that invented its own
stage names would silently stop agreeing with the documentation the agent
retrieves alongside it, which is the specific failure this project exists to
avoid.

**Why outcome, stage and reversal are three fields rather than one.** They vary
independently. ``TXN-20260911-004455`` and ``TXN-20260911-004473`` are both
``FAILED`` after authorisation, both carry a reversal, and they need opposite
responses: one is already settled, the other is sitting in the reversal
exception queue and will not resolve on its own. Collapsing them into a single
string would force every caller to parse prose back into the distinction.

**Why ``decline_reason`` exists at all.** *Error Code Reference* §"Wrapper
codes" calls treating ``PAY-8003`` as the cause "the most common diagnostic
mistake in the payments domain": it reports that *something* declined the
payment, not what. A tool that returned only ``error_code: PAY-8003`` would
reproduce that mistake at machine speed and with a provenance marker attached.
So the wrapper and the underlying code are separate fields, and the digital
record in this module is deliberately shaped to make the difference visible.

**Why ``card_authentication`` is derived, not stored.** Stages 2 and 3 together
are what the platform calls card authentication, and "a successful PIN entry
does not mean the transaction should have completed" is listed under *what not
to conclude*. Deriving the field from ``stage_reached`` means it cannot drift
out of agreement with the stage it summarises; storing it per record would
create two facts that can disagree.

**Why amounts are strings.** ``"180.00"`` round-trips; ``180.0`` invites a
binary float into money and a renderer into printing ``180.0`` at a customer.
Nothing here does arithmetic, so the exact decimal text is strictly better than
a number.

**Why the dataset lives in this module.** The :class:`~app.mcp.base.Tool`
protocol requires ``invoke`` to be pure — no clock, no randomness, no I/O — so a
JSON file on disk was rejected: it would add a filesystem read, a parse failure
mode and an untyped payload to a tool whose whole value is that it cannot fail
in any of those ways. The records are module-level, frozen, and annotated, so
``mypy`` checks the dataset itself rather than only the code that reads it.

**Everything here is synthetic.** Invented references, invented account and
terminal identifiers, no card numbers, no customer data, no network. Same
arguments in, same result out, in every session.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from pydantic import JsonValue

from app.core.tracing import traced
from app.mcp.base import reject_unknown_arguments, require_argument
from app.mcp.models import ToolName, ToolParameter, ToolResult, ToolSpec

_TOOL: ToolName = "check_transaction_status"
"""This tool's registry key, named once so the spec and the errors agree."""

_ARGUMENT = "transaction_reference"
"""The single argument. Named once for the same reason as :data:`_TOOL`."""

ERROR_NOT_FOUND = "NOT_FOUND"
"""The only ``error_code`` this tool emits, for a reference it does not hold.

There is deliberately no ``MALFORMED_REFERENCE`` companion. Validating the
shape of a reference would mean this module asserting a format that
TransactionSwitch owns and could change, and it would turn "I do not have that
one" into two different answers for no diagnostic gain: an unrecognised
reference is not found, whatever it looks like.
"""

_STAGE_COUNT = 8
"""Stages in the documented ATM lifecycle. Reported so ``4`` reads as ``4/8``."""

_ECHO_LIMIT = 64
"""Longest caller-supplied reference echoed back into a human-readable line.

The ``summary`` of a failure is logged, displayed, and in Stage 7 rendered into
a prompt. Echoing an unbounded caller string into all three is how a hostile
reference smuggles newlines past a fence, so the echo is collapsed to a single
line and truncated. The tool is happy to say what it was asked for; it is not
obliged to repeat a paragraph of it.
"""

_StageNumber = Literal[1, 2, 3, 4, 5, 6, 7, 8]
_Channel = Literal["ATM", "DIGITAL"]
_Outcome = Literal["COMPLETED", "REJECTED", "FAILED", "IN_PROGRESS"]
_ReversalState = Literal["ACKNOWLEDGED", "UNACKNOWLEDGED", "NOT_REQUIRED"]
_Authentication = Literal["PASSED", "FAILED", "NOT_REACHED", "NOT_APPLICABLE"]


@dataclass(frozen=True, slots=True)
class _Stage:
    """One stage of the documented lifecycle: its name and its owner."""

    name: str
    component: str


_STAGES: Mapping[_StageNumber, _Stage] = MappingProxyType(
    {
        1: _Stage("Card read", "Terminal"),
        2: _Stage("Card identification", "AuthorizationService"),
        3: _Stage("PIN verification", "CardSecurityModule"),
        4: _Stage("Limit evaluation", "LimitService"),
        5: _Stage("Funds authorisation", "CoreBankingAdapter"),
        6: _Stage("Dispense preparation", "DeviceManager"),
        7: _Stage("Dispense and confirm", "DeviceManager"),
        8: _Stage("Completion or reversal", "TransactionSwitch"),
    }
)
"""The eight stages of *ATM Transaction Lifecycle*, verbatim.

Digital payments do not have eight stages — there is no card read and no
dispense. Their authorisation fans out to AuthorizationService, LimitService and
CoreBankingAdapter in that order (*Payment Authorisation API* §"Downstream
calls"), which is stages 2, 4 and 5 of this same table. So a digital record
reports the stage its fan-out reached and nothing else is invented for it.
"""


@dataclass(frozen=True, slots=True)
class _Transaction:
    """One synthetic transaction, as the switch would report it.

    Attributes:
        reference: Canonical ``transaction_reference``, as echoed back.
        channel: Which entry point the transaction arrived through.
        transaction_type: ``WITHDRAWAL`` or ``PAYMENT``.
        amount: Exact decimal text. A string on purpose; see the module
            docstring.
        currency: ISO code. ``EUR`` throughout, matching ``limits.currency``.
        terminal_id: The ATM, or ``None`` for a channel that has no terminal.
        account_id: The account. Always present, because every ATM limit is
            evaluated against the account and not the card.
        stage_reached: The last stage the transaction reached, 1 to 8.
        outcome: What the transaction did once it got there.
        error_code: The terminating code, or ``None`` if nothing terminated it.
        decline_reason: The underlying code behind a wrapper such as
            ``PAY-8003``. ``None`` when ``error_code`` is already the cause.
        reversal_required: Whether a reversal was raised for this transaction.
        reversal_state: Where that reversal got to.
        reversal_code: ``SWX-7004`` for a reversal, ``SWX-7006`` once it has
            exhausted its retries unacknowledged, ``None`` for neither.
        diagnostic_note: One line saying *why*, in the documentation's terms.
        next_step: One line saying *what to do*, which is a different question.
    """

    reference: str
    channel: _Channel
    transaction_type: str
    amount: str
    currency: str
    terminal_id: str | None
    account_id: str
    stage_reached: _StageNumber
    outcome: _Outcome
    error_code: str | None
    decline_reason: str | None
    reversal_required: bool
    reversal_state: _ReversalState
    reversal_code: str | None
    diagnostic_note: str
    next_step: str


_TRANSACTIONS: tuple[_Transaction, ...] = (
    _Transaction(
        reference="TXN-20260911-004182",
        channel="ATM",
        transaction_type="WITHDRAWAL",
        amount="180.00",
        currency="EUR",
        terminal_id="ATM-04417",
        account_id="ACC-8842190",
        stage_reached=8,
        outcome="COMPLETED",
        error_code=None,
        decline_reason=None,
        reversal_required=False,
        reversal_state="NOT_REQUIRED",
        reversal_code=None,
        diagnostic_note=(
            "Dispensed and confirmed at stage 7 and completed at stage 8. "
            "No terminating code and no reversal."
        ),
        next_step=(
            "Nothing to do. If the customer disputes this one, the dispute is "
            "about the debit, not about the transaction's outcome."
        ),
    ),
    _Transaction(
        reference="TXN-20260911-004317",
        channel="ATM",
        transaction_type="WITHDRAWAL",
        amount="300.00",
        currency="EUR",
        terminal_id="ATM-04417",
        account_id="ACC-8842190",
        stage_reached=4,
        outcome="REJECTED",
        error_code="LIM-4001",
        decline_reason=None,
        reversal_required=False,
        reversal_state="NOT_REQUIRED",
        reversal_code=None,
        diagnostic_note=(
            "limits.atm.daily_withdrawal_amount is 1000.00 EUR and the account "
            "had already consumed 940.00 EUR today. Limits are evaluated "
            "against the account, not the card, so another card or another "
            "channel on ACC-8842190 can have used the allowance."
        ),
        next_step=(
            "Check the account's consumed daily allowance rather than this "
            "card's history. Card and PIN were both accepted, and no debit "
            "occurred, so no reversal is due."
        ),
    ),
    _Transaction(
        reference="TXN-20260911-004320",
        channel="ATM",
        transaction_type="WITHDRAWAL",
        amount="60.00",
        currency="EUR",
        terminal_id="ATM-04502",
        account_id="ACC-7719034",
        stage_reached=4,
        outcome="REJECTED",
        error_code="LIM-4005",
        decline_reason=None,
        reversal_required=False,
        reversal_state="NOT_REQUIRED",
        reversal_code=None,
        diagnostic_note=(
            "Fourth withdrawal inside the sliding "
            "limits.atm.velocity_window_minutes of 60, against a "
            "limits.atm.velocity_max_transactions of 3. The daily allowance "
            "was nowhere near breached — velocity is a window, not a counter."
        ),
        next_step=(
            "Explain the velocity window, not the daily limit: the same "
            "withdrawal succeeds once the window has moved on. No debit, so "
            "no reversal."
        ),
    ),
    _Transaction(
        reference="TXN-20260911-004401",
        channel="ATM",
        transaction_type="WITHDRAWAL",
        amount="250.00",
        currency="EUR",
        terminal_id="ATM-04503",
        account_id="ACC-5560223",
        stage_reached=5,
        outcome="REJECTED",
        error_code="COR-5003",
        decline_reason=None,
        reversal_required=False,
        reversal_state="NOT_REQUIRED",
        reversal_code=None,
        diagnostic_note=(
            "CoreBankingAdapter reported insufficient available balance. This "
            "is COR-5003 and not the core timeout COR-5008: the two are "
            "indistinguishable to the customer but only COR-5008 is a "
            "platform incident."
        ),
        next_step=(
            "Handle as a balance question with the customer. Do not raise an "
            "incident, and do not look for a reversal: nothing was authorised."
        ),
    ),
    _Transaction(
        reference="TXN-20260911-004455",
        channel="ATM",
        transaction_type="WITHDRAWAL",
        amount="120.00",
        currency="EUR",
        terminal_id="ATM-04417",
        account_id="ACC-6612884",
        stage_reached=7,
        outcome="FAILED",
        error_code="DEV-6004",
        decline_reason=None,
        reversal_required=True,
        reversal_state="ACKNOWLEDGED",
        reversal_code="SWX-7004",
        diagnostic_note=(
            "Authorised at stage 5, then the dispenser jammed at stage 7: the "
            "money was debited and the cash was not delivered. "
            "TransactionSwitch raised SWX-7004 and CoreBankingAdapter "
            "acknowledged it."
        ),
        next_step=(
            "The customer is already made whole by the acknowledged reversal. "
            "Check ATM-04417 for other faults in the same period — a DEV-6004 "
            "jam usually affects several consecutive transactions, not one."
        ),
    ),
    _Transaction(
        reference="TXN-20260911-004473",
        channel="ATM",
        transaction_type="WITHDRAWAL",
        amount="200.00",
        currency="EUR",
        terminal_id="ATM-04502",
        account_id="ACC-3390871",
        stage_reached=8,
        outcome="FAILED",
        error_code="SWX-7001",
        decline_reason=None,
        reversal_required=True,
        reversal_state="UNACKNOWLEDGED",
        reversal_code="SWX-7006",
        diagnostic_note=(
            "A downstream call exceeded switch.downstream_timeout_ms and the "
            "switch abandoned the transaction. SWX-7001 names "
            "TransactionSwitch, not the component that was slow. The reversal "
            "was retried to switch.reversal_retry_count without "
            "acknowledgement and is now in the reversal exception queue as "
            "SWX-7006."
        ),
        next_step=(
            "Needs a human. Raise to operations for manual settlement — an "
            "unacknowledged reversal will not resolve on its own and is at "
            "least SEV2 — then correlate this reference in the switch log to "
            "find which downstream call ran out of budget."
        ),
    ),
    _Transaction(
        reference="TXN-20260911-004488",
        channel="DIGITAL",
        transaction_type="PAYMENT",
        amount="3200.00",
        currency="EUR",
        terminal_id=None,
        account_id="ACC-9004512",
        stage_reached=4,
        outcome="REJECTED",
        error_code="PAY-8003",
        decline_reason="LIM-4008",
        reversal_required=False,
        reversal_state="NOT_REQUIRED",
        reversal_code=None,
        diagnostic_note=(
            "PAY-8003 is a wrapper and is not the cause. The authorisation "
            "fan-out reached LimitService, which declined against "
            "limits.digital.per_payment_amount of 2500.00 EUR: the cause is "
            "the decline_reason LIM-4008."
        ),
        next_step=(
            "Diagnose LIM-4008 against the account's digital per-payment "
            "limit, not PaymentEngine. Nothing was reserved, so there is no "
            "authorisation to release and no reversal."
        ),
    ),
    _Transaction(
        reference="TXN-20260911-004501",
        channel="ATM",
        transaction_type="WITHDRAWAL",
        amount="80.00",
        currency="EUR",
        terminal_id="ATM-04601",
        account_id="ACC-7719034",
        stage_reached=6,
        outcome="IN_PROGRESS",
        error_code=None,
        decline_reason=None,
        reversal_required=False,
        reversal_state="NOT_REQUIRED",
        reversal_code=None,
        diagnostic_note=(
            "Still at dispense preparation with no terminating code recorded. "
            "No reversal has been raised; whether one becomes necessary "
            "depends on how stage 7 ends."
        ),
        next_step=(
            "Re-query the reference before concluding anything. An in-flight "
            "transaction is not a failed one, and treating it as one is how a "
            "duplicate withdrawal gets authorised."
        ),
    ),
)
"""Eight synthetic transactions, chosen to cover the decisions the runbook makes.

Between them they cover: a clean completion, a limit rejection and a velocity
rejection (different keys, identical-looking to the customer), a funds
rejection that must *not* be mistaken for a core timeout, an authorised
transaction the hardware failed to deliver with its reversal settled, the same
shape with the reversal stuck and needing a human, a wrapper code whose real
cause is in ``decline_reason``, and one still in flight.

``TXN-20260911-004182`` and ``TXN-20260911-004317`` share account
``ACC-8842190`` on purpose: the daily allowance is consumed per account, so the
dataset itself demonstrates the confusion the limits reference warns about
rather than only asserting it in prose.
"""

_BY_REFERENCE: Mapping[str, _Transaction] = MappingProxyType(
    {transaction.reference.upper(): transaction for transaction in _TRANSACTIONS}
)
"""Case-folded lookup index, built once at import.

Keyed on the upper-cased reference so that a reference pasted out of a terminal
journal in lower case still finds its transaction. The canonical casing is
always taken from the record, never from the caller.
"""

_SPEC = ToolSpec(
    name=_TOOL,
    summary="Report how far one transaction got and why it stopped.",
    description=(
        "Looks up a single transaction by its transaction_reference and "
        "reports the lifecycle stage it reached (1-8 of the documented ATM "
        "lifecycle), its outcome, the terminating error code, the underlying "
        "decline_reason where the code is a wrapper such as PAY-8003, the "
        "state of any reversal, and a one-line next step. Covers ATM "
        "withdrawals and digital payments; a digital payment reports only the "
        "stages its authorisation fan-out reaches, since it has no card read "
        "and no dispense. Does NOT search: it needs an exact reference and "
        "cannot find transactions by card, account, terminal or time window. "
        "Does NOT return customer or card data, does not explain what an "
        "error code means in general (use look_up_error_code), and does not "
        "report the health of the components involved (use "
        "check_service_health)."
    ),
    parameters=(
        ToolParameter(
            name=_ARGUMENT,
            description=(
                "The reference generated by TransactionSwitch at stage 1, as "
                "printed on the receipt or recorded in the terminal journal. "
                "Case-insensitive."
            ),
            required=True,
            example="TXN-20260911-004182",
        ),
    ),
)
"""Built once at import: the spec is constant for the tool's lifetime."""


def _authentication_state(transaction: _Transaction) -> _Authentication:
    """Say whether card authentication (stages 2 and 3) was passed.

    Derived rather than stored, so it cannot contradict ``stage_reached``.
    Everything from stage 4 onward happens after authentication has already
    succeeded, which is precisely the fact that surprises people when a
    transaction fails after a correct PIN.

    Args:
        transaction: The record to describe.

    Returns:
        ``NOT_APPLICABLE`` for a channel with no card, ``PASSED`` once the
        transaction is past stage 3, ``FAILED`` if it stopped at stage 2 or 3,
        and ``NOT_REACHED`` if it never got that far.
    """
    if transaction.channel != "ATM":
        return "NOT_APPLICABLE"
    if transaction.stage_reached >= 4:
        return "PASSED"
    if transaction.stage_reached >= 2 and transaction.outcome in {
        "REJECTED",
        "FAILED",
    }:
        return "FAILED"
    return "NOT_REACHED"


def _summarise(transaction: _Transaction) -> str:
    """Write the one human-readable line for a found transaction.

    Ordered the way the runbook reads it: what the transaction was, how far it
    got, what stopped it, and whether money is owed.

    Args:
        transaction: The record to describe.

    Returns:
        A single line, safe to log and to display.
    """
    stage = _STAGES[transaction.stage_reached]
    line = (
        f"{transaction.reference} "
        f"({transaction.channel} {transaction.transaction_type} "
        f"{transaction.amount} {transaction.currency}) "
        f"{transaction.outcome} at stage {transaction.stage_reached} of "
        f"{_STAGE_COUNT} ({stage.name}, {stage.component})"
    )
    if transaction.error_code is not None:
        line += f", terminating code {transaction.error_code}"
        if transaction.decline_reason is not None:
            line += f" with decline_reason {transaction.decline_reason}"
    if transaction.reversal_required:
        line += f"; reversal {transaction.reversal_state}"
        if transaction.reversal_code is not None:
            line += f" ({transaction.reversal_code})"
    return f"{line}."


def _payload(transaction: _Transaction) -> dict[str, JsonValue]:
    """Render a record as the structured payload of a successful result.

    Every key is always present, ``None`` where it does not apply, so that a
    renderer never has to distinguish "absent" from "not applicable" — the
    tool-layer equivalent of the closed tool-name literal.

    Args:
        transaction: The record to render.

    Returns:
        A JSON-safe mapping for :attr:`app.mcp.models.ToolResult.data`.
    """
    stage = _STAGES[transaction.stage_reached]
    return {
        "transaction_reference": transaction.reference,
        "channel": transaction.channel,
        "transaction_type": transaction.transaction_type,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "terminal_id": transaction.terminal_id,
        "account_id": transaction.account_id,
        "stage_reached": transaction.stage_reached,
        "stage_name": stage.name,
        "stage_component": stage.component,
        "stage_count": _STAGE_COUNT,
        "card_authentication": _authentication_state(transaction),
        "outcome": transaction.outcome,
        "error_code": transaction.error_code,
        "decline_reason": transaction.decline_reason,
        "reversal": {
            "required": transaction.reversal_required,
            "state": transaction.reversal_state,
            "code": transaction.reversal_code,
        },
        "diagnostic_note": transaction.diagnostic_note,
        "next_step": transaction.next_step,
    }


def _echo(reference: str) -> str:
    """Make a caller-supplied reference safe to put in a human-readable line.

    Collapses all whitespace to single spaces and truncates. See
    :data:`_ECHO_LIMIT` for why a tool does not repeat caller input verbatim
    into something that will be logged and later prompted with.

    Args:
        reference: The value as supplied, already stripped.

    Returns:
        A single-line, length-bounded rendering of it.
    """
    collapsed = " ".join(reference.split())
    if len(collapsed) <= _ECHO_LIMIT:
        return collapsed
    return f"{collapsed[:_ECHO_LIMIT]}..."


class TransactionStatusTool:
    """Reports the lifecycle status of one synthetic transaction.

    Implements :class:`app.mcp.base.Tool` structurally: it inherits nothing and
    imports nothing from the registry, so it can be constructed and invoked on
    its own in a test with no tool layer around it.

    Holds no state. An instance exists only to satisfy the protocol's shape;
    two instances are interchangeable, and neither remembers a call.
    """

    @property
    def spec(self) -> ToolSpec:
        """What this tool is and how to call it."""
        return _SPEC

    @traced
    def invoke(self, arguments: Mapping[str, str]) -> ToolResult:
        """Look up one transaction by reference.

        Unknown arguments are rejected before the required one is read. A
        caller who wrote ``transaction_ref`` has both passed something unknown
        and omitted something required, and "you passed an argument I do not
        accept" points at the typo, where "you forgot an argument" points at
        the argument they thought they had supplied.

        Args:
            arguments: Must contain ``transaction_reference`` and nothing else.
                Surrounding whitespace is stripped and matching is
                case-insensitive; the canonical reference is echoed back in
                ``data``.

        Returns:
            A result carrying the transaction's stage, outcome, error code,
            reversal state and next step. A reference this tool does not hold
            returns ``ok=False`` with ``error_code`` :data:`ERROR_NOT_FOUND` —
            "there is no such transaction" is a true and useful answer, not a
            malfunction.

        Raises:
            ToolInputError: If ``transaction_reference`` is missing or blank,
                or if any other argument is supplied.
        """
        reject_unknown_arguments(arguments, _SPEC)
        requested = require_argument(arguments, _ARGUMENT, _TOOL)

        transaction = _BY_REFERENCE.get(requested.upper())
        if transaction is None:
            echoed = _echo(requested)
            return ToolResult.failure(
                tool=_TOOL,
                summary=f"No transaction found with reference '{echoed}'.",
                error_code=ERROR_NOT_FOUND,
                error_message=(
                    f"No transaction with reference '{echoed}' is known to "
                    f"TransactionSwitch. Confirm the reference from the "
                    f"receipt or the terminal journal; references are "
                    f"generated at stage 1 and are not reused."
                ),
            )

        return ToolResult.success(
            tool=_TOOL,
            summary=_summarise(transaction),
            data=_payload(transaction),
        )


__all__ = ["ERROR_NOT_FOUND", "TransactionStatusTool"]
