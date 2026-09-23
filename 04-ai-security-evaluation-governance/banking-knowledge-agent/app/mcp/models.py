"""Data contracts for the MCP tool layer.

These types are the vocabulary the application uses to talk about *tools*, in the
same way :mod:`app.llm.models` is the vocabulary it uses to talk about models. A
tool implementation's job is to translate between this vocabulary and whatever
synthetic backing data it owns::

    question   --policy-->    ToolInvocation      which tool, with which arguments
    invocation --registry-->  ToolResult          what the tool reported
    results    --prompts-->   a fenced block in the user turn

**Why a tool result is not just a string.** A tool that returned prose would be
indistinguishable, by the time it reached the prompt, from a retrieved document.
The whole point of Stage 6 is that a reader — and the model — can tell *live
information* from *documentation*, so a result carries its own provenance:
which tool produced it, whether the call succeeded, when it was observed, and a
structured payload separate from the one-line human summary.

**Documentation vs. live information.** This is the distinction ``prompt.md`` §14
asks for, and it is a real one, not a label. ``data/knowledge`` says what the
platform is *designed* to do — the documented default of
``limits.atm.per_transaction_amount`` is ``500.00``. A tool says what it is
*reportedly doing now* — this account's
effective limit is ``250.00`` because of an override. Both can be true, and when
they disagree the disagreement is usually the answer to the question. Collapsing
them into one undifferentiated block of context would destroy exactly the
information a support engineer needs.

**Everything here is synthetic.** No tool in this package reaches a real system,
opens a socket, or reads anything outside its own module. That is a property of
the architecture, not a promise about behaviour: there is no code path that
could, which is the same argument Stage 4 made for shipping no vendor adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

ToolName = Literal[
    "get_system_configuration",
    "check_transaction_status",
    "get_component_status",
    "look_up_error_code",
    "retrieve_system_version",
    "check_service_health",
]
"""The six tools ``prompt.md`` §14 asks for, named once.

A closed literal rather than a free string. The registry, the policy, the CLI and
the MCP server all refer to tools by name, and a typo in any of them should be a
type error found by ``mypy`` rather than a ``ToolNotFoundError`` found by a user.

This list was fixed *before* the six tool implementations were written, precisely
so that six independently-built modules could not disagree about what they were
called.
"""

TOOL_NAMES: tuple[ToolName, ...] = (
    "get_system_configuration",
    "check_transaction_status",
    "get_component_status",
    "look_up_error_code",
    "retrieve_system_version",
    "check_service_health",
)
"""Iterable form of :data:`ToolName`, in the order §14 lists them."""

TOOL_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "NOT_FOUND",
        "UNKNOWN_COMPONENT",
        "UNKNOWN_KEY",
        "UNKNOWN_CODE_FOR_COMPONENT",
        "MALFORMED_CODE",
        "SECRET_NOT_SERVED",
    }
)
"""Every value :attr:`ToolResult.error_code` is allowed to take.

**Written at integration, not up front, and that is the honest history.** The
contract handed to the six tool authors said only "a stable UPPER_SNAKE code, for
example ``NOT_FOUND``". Four tools used ``NOT_FOUND`` alone; two did not.
``get_system_configuration`` distinguishes ``UNKNOWN_COMPONENT`` from
``UNKNOWN_KEY``, and ``look_up_error_code`` adds ``UNKNOWN_CODE_FOR_COMPONENT``
and ``MALFORMED_CODE``.

The divergence was resolved *upward* rather than flattened to ``NOT_FOUND``,
because the specific codes are genuinely better answers: "that component exists,
that key does not" tells a caller what to try next, and a bare ``NOT_FOUND`` is a
dead end. What was actually wrong was not the vocabulary but that it was
unbounded — nothing stopped a seventh tool inventing ``NO_SUCH_THING``. Closing
the set here, and asserting it in ``tests/test_mcp_tools.py``, keeps the
expressiveness and removes the drift.

Note that ``SECRET_NOT_SERVED`` is not a "not found" at all: it is
``get_system_configuration`` refusing to return a value for a key that looks like
a credential, which the corpus states ConfigurationStore never holds.
"""

SYNTHETIC_OBSERVED_AT = "2026-09-11T09:00:00Z"
"""The single fixed instant every synthetic tool result claims to be observed at.

A real ``datetime.now()`` here would buy nothing and cost determinism: every
assertion about a tool result would have to exclude the timestamp, and the demo
output would differ between two runs a second apart for no reason a reader could
learn anything from. The data is synthetic, so the clock is synthetic too, and it
says so. When a tool one day reaches a real system, this constant is the thing
that gets replaced by an injected clock — it is deliberately a single named
symbol rather than a literal scattered through six modules.
"""


MAX_ARGUMENT_CHARS = 256
"""Longest value, and longest name, any tool argument may have (Stage 13).

Every argument in this domain is an identifier, a code, a component name or a
dotted configuration key; the longest real one is well under 64 characters. The
bound exists because a not-found result echoes the caller's value back, and that
echo ends up inside the model's prompt: an unbounded argument would be an
unbounded, caller-written block of prompt text. Advertised to MCP clients as
``maxLength`` in :meth:`ToolSpec.input_schema` (the SDK enforces it) and checked
again at run time by :func:`app.mcp.base.check_argument_bounds`, because the
in-process path has no schema validator in front of it.
"""


class ToolParameter(BaseModel):
    """One argument a tool accepts.

    Every parameter is a string (see :meth:`ToolSpec.input_schema` for why), so
    this carries no type field. What it does carry is an ``example``, because the
    spec is what an MCP client is shown, and a worked example is worth more than a
    type name for getting the format of a transaction reference right.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, description="Argument name, as passed.")
    description: str = Field(
        min_length=1, description="What it means, in one line, for a model or a human."
    )
    required: bool = Field(default=True, description="Whether the tool needs it.")
    example: str = Field(
        min_length=1, description="A valid value, showing the expected format."
    )


class ToolSpec(BaseModel):
    """What a tool is and how to call it: the tool's half of the contract.

    This is the object the MCP protocol layer converts into an MCP tool
    definition -- what a remote MCP client (and any model behind it) sees before
    choosing a tool -- and the object the agent's rule-based selector
    (:class:`app.agent.tool_policy.RuleToolSelector`) is built from: it reads the
    declared parameters to decide which tools a question can supply. No model
    chooses tools inside this application (``docs/HANDOVER.md`` §7.B). It
    deliberately contains no callable and no implementation detail — a spec
    can be listed, logged and rendered without the tool it
    describes being able to run.
    """

    model_config = ConfigDict(frozen=True)

    name: ToolName = Field(description="Stable identifier; the registry key.")
    summary: str = Field(
        min_length=1,
        description="One line. What this tool answers, in the caller's language.",
    )
    description: str = Field(
        min_length=1,
        description="Fuller description, including what it does NOT cover.",
    )
    parameters: tuple[ToolParameter, ...] = Field(
        default=(), description="Arguments, in the order a human would supply them."
    )

    @property
    def required_parameters(self) -> tuple[str, ...]:
        """Names of the arguments that must be present."""
        return tuple(p.name for p in self.parameters if p.required)

    def input_schema(self) -> dict[str, JsonValue]:
        """Render the parameters as the JSON Schema the MCP protocol expects.

        Every property is typed ``string``. That is not laziness: every argument
        in this domain is an identifier, a code or a configuration key. Inside
        the application the values come from the agent's regular-expression
        extractors, which produce strings; an external MCP client may have a
        model producing them, and declaring a number here would mean a model
        emitting ``"500"`` fails schema validation for being right in the wrong
        type. Parsing, where any is needed, belongs inside the tool that knows
        what the argument means.

        Every property carries ``maxLength`` (:data:`MAX_ARGUMENT_CHARS`), which
        the MCP SDK enforces before a call reaches the registry.

        ``additionalProperties`` is ``False`` so that a caller passing an
        argument the tool does not understand is told so, rather than having it
        silently ignored — the tool-layer equivalent of the LLM factory refusing
        an unknown provider instead of falling back to the mock.
        """
        properties: dict[str, JsonValue] = {
            parameter.name: {
                "type": "string",
                "maxLength": MAX_ARGUMENT_CHARS,
                "description": f"{parameter.description} Example: {parameter.example}",
            }
            for parameter in self.parameters
        }
        return {
            "type": "object",
            "properties": properties,
            "required": list(self.required_parameters),
            "additionalProperties": False,
        }


class ToolResult(BaseModel):
    """What one tool call reported.

    Three fields carry the answer and they are deliberately separate:

    * :attr:`summary` — one line, already readable, written by the tool itself.
      This is what a log line, a UI badge and a prompt header show.
    * :attr:`data` — the structured payload. Machine-readable, renderable, and
      the thing a Stage 9 interface will actually format.
    * :attr:`error_code` / :attr:`error_message` — populated only when
      :attr:`ok` is ``False``.

    **A failed call is still a result, not an exception.** ``ok=False`` means the
    tool ran correctly and has something true to report: *there is no transaction
    with that reference*. That is a legitimate answer to a legitimate question,
    and turning it into a raised exception would make "the thing you asked about
    does not exist" indistinguishable from "the tool is broken". Exceptions are
    reserved for the caller getting the call itself wrong
    (:class:`~app.mcp.base.ToolInputError`) or the tool failing
    (:class:`~app.mcp.base.ToolExecutionError`).
    """

    model_config = ConfigDict(frozen=True)

    tool: ToolName = Field(description="Which tool produced this.")
    ok: bool = Field(description="Whether the tool found what was asked for.")
    summary: str = Field(
        min_length=1,
        description="One human-readable line. Safe to log and to display.",
    )
    data: Mapping[str, JsonValue] = Field(
        default_factory=dict,
        description="Structured payload. Empty on failure.",
    )
    error_code: str | None = Field(
        default=None, description="Stable code when ok is False, e.g. NOT_FOUND."
    )
    error_message: str | None = Field(
        default=None, description="Human-readable reason when ok is False."
    )
    observed_at: str = Field(
        default=SYNTHETIC_OBSERVED_AT,
        description="When the tool claims to have observed this. Synthetic.",
    )
    source: Literal["synthetic_tool"] = Field(
        default="synthetic_tool",
        description="Provenance marker. Rendered into the prompt so the model "
        "cannot mistake a tool reading for documentation.",
    )

    @classmethod
    def success(
        cls,
        tool: ToolName,
        summary: str,
        data: Mapping[str, JsonValue],
    ) -> ToolResult:
        """Build a successful result."""
        return cls(tool=tool, ok=True, summary=summary, data=data)

    @classmethod
    def failure(
        cls,
        tool: ToolName,
        summary: str,
        error_code: str,
        error_message: str,
    ) -> ToolResult:
        """Build a result reporting that the thing asked about was not found.

        Not an error path — see the class docstring. ``data`` is left empty so a
        caller cannot half-read a payload that describes nothing.
        """
        return cls(
            tool=tool,
            ok=False,
            summary=summary,
            data={},
            error_code=error_code,
            error_message=error_message,
        )


class ToolInvocation(BaseModel):
    """A tool call the agent decided to make, before it is made.

    Produced by the agent's rule-based selector
    (:class:`app.agent.tool_policy.RuleToolSelector`) from the question alone
    (after the conversation layer has resolved a follow-up from earlier
    *questions*) -- never from model output, a retrieved passage or a tool
    result.
    Separate from :class:`ToolResult` because the decision and its outcome are
    recorded at different moments and are useful separately: the Stage 7 tests
    assert that a question routed to the right tool with the right arguments
    without caring what the tool then said.
    """

    model_config = ConfigDict(frozen=True)

    tool: ToolName = Field(description="The tool to call.")
    arguments: Mapping[str, str] = Field(
        default_factory=dict, description="Arguments, all string-valued."
    )
    reason: str = Field(
        min_length=1,
        description="Why the agent chose this tool. Safe to show in a UI.",
    )
