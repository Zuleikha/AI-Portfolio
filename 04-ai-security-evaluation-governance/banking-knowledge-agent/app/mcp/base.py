"""The ``Tool`` seam, and the error taxonomy every tool maps onto.

This module is to tools what :mod:`app.llm.base` is to models, and the symmetry
is deliberate rather than decorative. Both layers face the same problem — an
application that must not learn the shape of whatever is behind the seam — and
solving it the same way twice means a reader who has understood one has already
understood the other.

**Why a protocol rather than an abstract base class.** A tool qualifies
structurally: anything with a ``spec`` and an ``invoke`` is a tool, with no
inheritance, no registration and no import of this module. That is what lets a
test write a three-line hostile tool to prove the injection defence holds,
without that tool being a subclass of anything.

**Why the errors live here and not in each tool.** Six tools were built
independently. If each had invented its own failure type, the registry would
have needed six ``except`` clauses and the agent would have needed to know which
tool it had called in order to interpret the failure. One taxonomy, translated at
the boundary, is the same argument Stage 4 made about vendor SDK exceptions.

**The line between a failure and an error.** This is the most important rule in
the module, and it is easy to get wrong:

* *The thing you asked about does not exist* — an unknown transaction reference,
  an error code that is not in the catalogue, a component nobody has heard of —
  is **data**. It comes back as :class:`~app.mcp.models.ToolResult` with
  ``ok=False``. It is a true, useful answer to a reasonable question.
* *The call itself was wrong or the tool broke* — a required argument missing, an
  argument that cannot be parsed, an unexpected exception inside a tool — is an
  **error**. It raises.

Collapsing the two in either direction does real damage. If "not found" raised,
then asking about a transaction that has been purged would look like an outage.
If a missing argument returned ``ok=False``, a genuine bug in the agent's
rule-based argument extraction (:mod:`app.agent.tool_policy`), or in an external
MCP client's call, would be silently reported to users as "no such transaction"
forever.

**No model chooses tools here.** Inside the application a tool call is decided by
the agent's deterministic selector from the question text (``docs/HANDOVER.md``
§7.B); model output is never parsed into a tool call. A model can only reach
these tools from outside, as an MCP client of :mod:`app.mcp.server`, which is why
every argument is also bounded (:func:`check_argument_bounds`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from app.core.tracing import traced
from app.mcp.models import MAX_ARGUMENT_CHARS, ToolResult, ToolSpec

__all__ = [
    "MAX_ARGUMENT_CHARS",
    "Tool",
    "ToolError",
    "ToolExecutionError",
    "ToolInputError",
    "ToolNotFoundError",
    "ToolUnavailableError",
    "check_argument_bounds",
    "reject_unknown_arguments",
    "require_argument",
]


class ToolError(RuntimeError):
    """Base class for every failure originating in the MCP tool layer.

    Attributes:
        retryable: Whether the same call could plausibly succeed if made again.
            Callers should branch on this rather than on the concrete type, so
            that a new error class does not silently become non-retryable at
            every existing call site. The same contract as
            :attr:`app.llm.base.LLMError.retryable`.
    """

    retryable: bool = False


class ToolNotFoundError(ToolError):
    """No tool is registered under the requested name.

    Never retryable: the registry's contents do not change between two calls
    within a process. Stage 7 chose a rule-based selector built from the
    registry's own specs, so the agent cannot request an unregistered tool. The
    error therefore catches a caller bug, or an MCP client naming a tool that
    does not exist — a failure that must be loud rather than quietly swallowed
    into a refusal.
    """


class ToolInputError(ToolError):
    """The arguments do not satisfy the tool's spec.

    A required argument is missing, is blank, is too long, or cannot be parsed
    into what the tool needs. Not retryable — the same arguments will fail
    identically. The message names the offending argument and the tool, because
    it is the feedback that tells the caller — the agent's rule-based selector
    in-process, or an external MCP client (possibly driven by its own model) —
    that it called the tool wrongly. It is the one tool error whose message an
    MCP client receives verbatim (:mod:`app.mcp.server`), so it must never carry
    internal detail, and it never echoes an over-long value.
    """


class ToolExecutionError(ToolError):
    """A tool raised something its implementation did not anticipate.

    The catch-all that stops an unmapped exception escaping the tool layer as
    whatever type it happened to be. Its presence in a log is a signal that a
    tool has a gap in its own error handling — the same role
    :class:`app.llm.base.LLMProviderError` plays one layer across.
    """


class ToolUnavailableError(ToolError):
    """The system behind a tool could not be reached.

    Retryable, because nothing about the request is wrong.

    **No tool in Stage 6 can raise this**, and that is worth stating plainly
    rather than leaving the class looking like dead code. Every tool here reads
    a synthetic dictionary in its own module; there is nothing to be unavailable.
    It is defined now because the taxonomy is the part that must be right before
    the first tool reaches a real system: the alternative is discovering on that
    day that callers have been treating every tool failure as permanent. Stage 4
    made precisely the opposite mistake by designing an error taxonomy with
    nothing to test it against, and Stage 5's first real adapter found the gap
    within an hour (see :class:`app.llm.base.LLMConnectionError`).
    """

    retryable = True


@runtime_checkable
class Tool(Protocol):
    """A single synthetic banking support tool.

    Implementations must guarantee:

    * ``spec`` is constant for the lifetime of the object, and its ``name``
      matches the key the tool is registered under.
    * ``invoke`` either returns a :class:`~app.mcp.models.ToolResult` — whose
      ``ok`` may be ``True`` or ``False`` — or raises a :class:`ToolError`. No
      other exception type escapes, and no sentinel result stands in for a
      failure.
    * ``invoke`` is pure with respect to the process: no I/O, no clock, no
      randomness. The same arguments produce the same result on every call, in
      every session. This is what makes the whole tool layer testable offline
      and the demo output stable.
    """

    @property
    def spec(self) -> ToolSpec:
        """What this tool is and how to call it."""

    def invoke(self, arguments: Mapping[str, str]) -> ToolResult:
        """Run the tool.

        Args:
            arguments: String-valued arguments matching :attr:`spec`.

        Returns:
            The result. ``ok=False`` is a valid, successful return describing
            something that was not found.

        Raises:
            ToolInputError: If a required argument is missing or unusable.
            ToolError: For any other failure in the tool layer.
        """


def require_argument(
    arguments: Mapping[str, str],
    name: str,
    tool: str,
) -> str:
    """Read one required argument, or raise :class:`ToolInputError`.

    Shared by all six tools so that a missing argument produces the identical
    error whichever tool was called. Six independently-written validation blocks
    would have drifted — one raising on a missing key, another on a blank
    string, a third treating whitespace as present — and the difference would
    only ever have surfaced as an inconsistent error message in front of a user.

    Args:
        arguments: The arguments as passed to :meth:`Tool.invoke`.
        name: The argument to read.
        tool: The calling tool's name, for the error message.

    Returns:
        The argument's value, stripped of surrounding whitespace.

    Raises:
        ToolInputError: If the argument is absent, empty, or only whitespace.
    """
    value = arguments.get(name)
    if value is None:
        raise ToolInputError(
            f"Tool '{tool}' requires the argument '{name}', which was not supplied."
        )
    stripped = value.strip()
    if not stripped:
        raise ToolInputError(
            f"Tool '{tool}' requires a non-empty value for the argument '{name}'."
        )
    return stripped


def reject_unknown_arguments(
    arguments: Mapping[str, str],
    spec: ToolSpec,
) -> None:
    """Raise if the caller passed an argument the tool does not declare.

    The runtime counterpart of ``additionalProperties: false`` in
    :meth:`app.mcp.models.ToolSpec.input_schema`. Ignoring an unknown argument
    would let a caller believe it had filtered, scoped or qualified a request
    that was in fact answered unfiltered — a wrong answer delivered with
    complete confidence, which is the failure mode this project exists to avoid.

    Args:
        arguments: The arguments as passed to :meth:`Tool.invoke`.
        spec: The tool's own spec.

    Raises:
        ToolInputError: If any argument is not declared in ``spec``.
    """
    declared = {parameter.name for parameter in spec.parameters}
    unknown = sorted(set(arguments) - declared)
    if unknown:
        raise ToolInputError(
            f"Tool '{spec.name}' does not accept the argument(s) "
            f"{', '.join(repr(name) for name in unknown)}. "
            f"Accepted: {', '.join(sorted(declared)) or 'none'}."
        )


@traced
def check_argument_bounds(arguments: Mapping[str, str], tool: str) -> None:
    """Raise if any argument name or value exceeds :data:`MAX_ARGUMENT_CHARS`.

    Run by :meth:`app.mcp.registry.ToolRegistry.call` before every tool, so it
    covers the two tools that read their optional ``component`` argument
    directly instead of through :func:`require_argument`. The over-long value is
    never echoed: repeating it would put the very text the bound exists to keep
    out into an error message, a log line or a prompt.

    Args:
        arguments: The arguments as passed to :meth:`Tool.invoke`.
        tool: The tool being called, for the error message.

    Raises:
        ToolInputError: If a name or a value is longer than the bound.
    """
    for name, value in arguments.items():
        if len(name) > MAX_ARGUMENT_CHARS:
            raise ToolInputError(
                f"Tool '{tool}' was passed an argument name longer than "
                f"{MAX_ARGUMENT_CHARS} characters."
            )
        if len(value) > MAX_ARGUMENT_CHARS:
            raise ToolInputError(
                f"Tool '{tool}' argument '{name}' is longer than "
                f"{MAX_ARGUMENT_CHARS} characters."
            )
