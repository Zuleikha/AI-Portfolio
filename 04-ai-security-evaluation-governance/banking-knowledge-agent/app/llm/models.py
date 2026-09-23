"""Data contracts for the LLM layer.

These types are the vocabulary the application uses to talk to *any* language
model, so none of them names a vendor. A provider adapter's job is to translate
between this vocabulary and whatever shape its own API happens to use::

    question + RetrievalResult  --prompts--> CompletionRequest
    CompletionRequest           --provider-> LLMResponse
    LLMResponse                 --service--> GroundedAnswer

The split matters. ``LLMResponse`` is what the model returned. ``GroundedAnswer``
is what the application is willing to stand behind: the same text plus the
sources it was built from, the number of passages that were actually injected,
and whether a model was consulted at all. An answer without that provenance is
indistinguishable from a guess, and this project's whole point is that the
difference is visible.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["user", "assistant"]
"""Conversation roles. System instructions are a separate field, not a role.

Providers disagree about whether the system prompt is a message or a top-level
parameter. Modelling it as a field of :class:`CompletionRequest` rather than a
role keeps that disagreement inside the adapters.
"""

StopReason = Literal["end_turn", "max_tokens", "refusal", "error", "other"]
"""Why generation stopped, normalised across providers.

``max_tokens`` and ``refusal`` are the two that must never be mistaken for a
complete answer: the first is a sentence cut in half, the second is the model
declining. Both are treated as failures by :mod:`app.llm.service`.
"""


class LLMMessage(BaseModel):
    """One turn of a conversation.

    Stage 4 only ever sends a single user turn. The tuple-of-messages shape is
    here because Stage 8 adds conversation context, and retrofitting a list onto
    a single-string interface later would change every call site.
    """

    model_config = ConfigDict(frozen=True)

    role: Role = Field(description="Who produced this turn.")
    content: str = Field(min_length=1, description="The turn's text.")


class CompletionRequest(BaseModel):
    """Everything a provider needs to generate one response.

    Deliberately minimal. It carries no sampling parameters (``temperature``,
    ``top_p``, ``top_k``) for two reasons: this application wants the most
    faithful reading of the retrieved passages rather than a varied one, and
    several current frontier models reject those parameters outright. A provider
    that needs them can read them from its own settings; putting them in the
    shared contract would push a vendor's quirks into every caller.
    """

    model_config = ConfigDict(frozen=True)

    system: str = Field(
        min_length=1,
        description="System instructions. Stable across requests; see prompts.py.",
    )
    messages: tuple[LLMMessage, ...] = Field(
        min_length=1, description="Conversation turns, oldest first."
    )
    max_tokens: int = Field(
        ge=1,
        description="Ceiling on generated tokens. A safety limit, not a target.",
    )

    @property
    def user_text(self) -> str:
        """Concatenated text of the user turns. Used by tests and by the mock."""
        return "\n\n".join(m.content for m in self.messages if m.role == "user")


class TokenUsage(BaseModel):
    """Tokens consumed by one request.

    Recorded from Stage 4 onward because cost and latency are properties of a
    production system, not an afterthought — Stage 10 turns these into metrics.
    A provider that does not report usage leaves the counts at zero rather than
    inventing them.
    """

    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0, description="Tokens sent.")
    output_tokens: int = Field(default=0, ge=0, description="Tokens generated.")
    cached_input_tokens: int = Field(
        default=0,
        ge=0,
        description="Input tokens served from a provider-side cache, if reported.",
    )

    @property
    def total_tokens(self) -> int:
        """Input plus output. Cached input is a subset of input, not an addition."""
        return self.input_tokens + self.output_tokens


class LLMResponse(BaseModel):
    """A single generation, normalised across providers.

    ``text`` may legitimately be empty when ``stop_reason`` is ``refusal``; it is
    the service, not this model, that decides such a response is unusable.
    """

    model_config = ConfigDict(frozen=True)

    text: str = Field(description="The generated text, with no provider framing.")
    provider_id: str = Field(
        min_length=1, description="Which provider implementation produced this."
    )
    model_id: str = Field(min_length=1, description="Which model produced this.")
    stop_reason: StopReason = Field(
        default="end_turn", description="Why generation stopped."
    )
    usage: TokenUsage = Field(
        default_factory=TokenUsage, description="Token accounting for this call."
    )

    @property
    def is_complete(self) -> bool:
        """Whether this response ended naturally rather than being cut off."""
        return self.stop_reason == "end_turn"


class GroundedAnswer(BaseModel):
    """An answer together with the evidence it was built from.

    The provenance fields exist so a caller can tell these three apart without
    reading the prose, which is exactly the distinction a support engineer needs:

    * a **grounded answer** — ``llm_called`` and at least one piece of evidence,
      whether a retrieved passage or a live tool result;
    * an **honest refusal** — ``refused``, because there was no evidence at all,
      so no model was consulted and nothing could be invented;
    * a **model-side decline** — never returned; the service raises instead.

    ``chunks_used`` and ``tools_used`` are counted separately rather than summed
    into one "evidence" number, for the reason the whole of Stage 6 exists: an
    answer built from three documents is a different kind of claim from one built
    from a live reading of the running system, and a caller deciding how much to
    trust it needs to be able to tell.
    """

    model_config = ConfigDict(frozen=True)

    question: str = Field(min_length=1, description="The question that was asked.")
    text: str = Field(min_length=1, description="The answer shown to the user.")
    sources: tuple[str, ...] = Field(
        default=(), description="Citations for the passages that were injected."
    )
    chunks_used: int = Field(
        default=0, ge=0, description="Passages actually placed in the prompt."
    )
    chunks_available: int = Field(
        default=0,
        ge=0,
        description="Passages retrieval offered, before the context budget applied.",
    )
    tools_used: int = Field(
        default=0,
        ge=0,
        description="Live tool results placed in the prompt (Stage 6).",
    )
    refused: bool = Field(
        default=False,
        description="True when there was no evidence and the answer says so.",
    )
    llm_called: bool = Field(
        default=True, description="Whether a model was actually consulted."
    )
    response: LLMResponse | None = Field(
        default=None, description="The raw generation, absent on a refusal."
    )
    prompt_version: str = Field(
        min_length=1, description="Version of the system instructions used."
    )

    @property
    def is_grounded(self) -> bool:
        """Whether this answer was generated from at least one retrieved passage."""
        return self.llm_called and self.chunks_used > 0
