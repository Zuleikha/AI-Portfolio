"""Turning a follow-up into a question that stands on its own -- by rules.

"Is it healthy?" names nothing a tool can act on and nothing a search can find.
Before the agent sees it, :func:`resolve_follow_up` rewrites it from the previous
turn, so tool selection and retrieval work exactly as they do for a first
question. First matching rule wins::

    no earlier turn in the window ─────────────────────────────▶ standalone
    "what about / how about / and (for) / same for" + ONE identifier,
        and the previous question had one of that kind ────────▶ substituted_identifier
    the question names its own identifier ─────────────────────▶ standalone
    no reference word (it, that, they, ...) ───────────────────▶ standalone
    reference word, previous question has identifiers ─────────▶ carried_identifiers
    reference word, previous question has none ────────────────▶ carried_topic

**No model does this -- by the same reasoning as Stage 7** (guide §20.17,
§20.24): a model rewrite would be a paid, variable call before every follow-up.
Identifiers are found by Stage 7's own extractors, so there is still one
definition of what an error code or a component looks like.

**Only earlier questions are read.** Never an earlier answer, never a tool
result: nothing the model wrote and nothing untrusted can be carried into a
search query.

**History limits.** The window (``conversation_max_history_turns``) bounds the
earlier questions sent to the model, and the character budget drops the oldest
whole. A standalone question sends none -- history it did not need would only
cost tokens and distract.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import NamedTuple

from app.agent.tool_policy import (
    COMPONENT_NAMES,
    component_extractor,
    extract_configuration_keys,
    extract_error_codes,
    extract_transaction_references,
)
from app.conversation.models import (
    ConversationContext,
    ConversationTurn,
    ResolutionKind,
)
from app.core.config import Settings, get_settings
from app.core.tracing import traced

MAX_CARRIED_IDENTIFIERS = 3
"""Most identifiers a follow-up may carry. Stage 7 caps tool calls at four."""

REFERENCE_CUE = re.compile(
    r"\b(it|its|that|this|these|those|they|them|their|same|above|previous|earlier)\b",
    re.IGNORECASE,
)
"""Words that point back at something said before. Whole words only."""

ELLIPSIS_CUE = re.compile(
    r"^\s*(?:(?:and\s+)?(?:what|how)\s+about|and(?:\s+for)?|same\s+for)\b",
    re.IGNORECASE,
)
"""An opening that asks the previous question again about something else."""


class Identifier(NamedTuple):
    """One identifier found in a question: its parameter kind and its value."""

    kind: str
    value: str


_EXTRACTORS: tuple[tuple[str, Callable[[str], tuple[str, ...]]], ...] = (
    ("error_code", extract_error_codes),
    ("transaction_reference", extract_transaction_references),
    ("key", extract_configuration_keys),
    ("component", component_extractor(COMPONENT_NAMES)),
)
"""Stage 7's extractors, keyed by the same parameter names the tools declare."""


@traced
def find_identifiers(question: str) -> tuple[Identifier, ...]:
    """Every identifier in ``question``, in the order it appears.

    Args:
        question: Any question text.

    Returns:
        The identifiers, by position; components in their canonical spelling.
    """
    folded = question.casefold()
    found = [
        (folded.find(value.casefold()), Identifier(kind, value))
        for kind, extract in _EXTRACTORS
        for value in extract(question)
    ]
    return tuple(identifier for _, identifier in sorted(found, key=lambda f: f[0]))


@traced
def resolve_follow_up(
    question: str,
    earlier: Sequence[ConversationTurn],
    settings: Settings | None = None,
) -> ConversationContext:
    """Resolve ``question`` against the earlier turns of its session.

    Args:
        question: The question as asked.
        earlier: The session's earlier turns, oldest first.
        settings: Application settings. Defaults to the cached singleton.

    Returns:
        The standalone question to answer, which rule produced it, and the
        earlier questions to send with it (none for a standalone question).

    Raises:
        ValueError: If the question is blank.
    """
    if not question.strip():
        raise ValueError("Cannot resolve an empty question.")

    resolved = settings or get_settings()
    size = resolved.conversation_max_history_turns
    window = tuple(earlier[-size:]) if size > 0 else ()
    if not window:
        return _standalone(question)

    previous = window[-1]
    own = find_identifiers(question)
    max_chars = resolved.conversation_max_history_chars

    substituted = _substitute(question, own, previous)
    if substituted is not None:
        return _follow_up(
            question,
            substituted,
            "substituted_identifier",
            carried=(),
            topic=substituted,
            window=window,
            max_chars=max_chars,
        )

    if own or not REFERENCE_CUE.search(question):
        return _standalone(question)

    carried = tuple(
        dict.fromkeys(
            identifier.value
            for identifier in find_identifiers(previous.resolved_question)
        )
    )[:MAX_CARRIED_IDENTIFIERS]
    if carried:
        rewritten = f"{question} (regarding {', '.join(carried)})"
        return _follow_up(
            question,
            rewritten,
            "carried_identifiers",
            carried=carried,
            topic=rewritten,
            window=window,
            max_chars=max_chars,
        )

    return _follow_up(
        question,
        f"{question} (following: {previous.topic})",
        "carried_topic",
        carried=(),
        topic=previous.topic,
        window=window,
        max_chars=max_chars,
    )


def _standalone(question: str) -> ConversationContext:
    """A question used exactly as asked, with no history."""
    return ConversationContext(
        question=question,
        resolved_question=question,
        resolution="standalone",
        topic=question,
    )


def _substitute(
    question: str, own: Sequence[Identifier], previous: ConversationTurn
) -> str | None:
    """The previous question with one identifier swapped, if the rule applies."""
    if len(own) != 1 or not ELLIPSIS_CUE.search(question):
        return None
    new = own[0]
    same_kind = [
        identifier
        for identifier in find_identifiers(previous.resolved_question)
        if identifier.kind == new.kind
    ]
    if len(same_kind) != 1 or same_kind[0].value.casefold() == new.value.casefold():
        return None
    pattern = re.compile(
        rf"(?<!\w){re.escape(same_kind[0].value)}(?!\w)", re.IGNORECASE
    )
    return pattern.sub(lambda _match: new.value, previous.resolved_question, count=1)


def _follow_up(
    question: str,
    rewritten: str,
    resolution: ResolutionKind,
    *,
    carried: tuple[str, ...],
    topic: str,
    window: Sequence[ConversationTurn],
    max_chars: int,
) -> ConversationContext:
    """A resolved follow-up, with the earlier questions that fit the budget."""
    history, dropped = _history(window, max_chars)
    return ConversationContext(
        question=question,
        resolved_question=rewritten,
        resolution=resolution,
        carried=carried,
        topic=topic,
        history=history,
        history_dropped=dropped,
    )


def _history(
    window: Sequence[ConversationTurn], max_chars: int
) -> tuple[tuple[str, ...], int]:
    """Newest-first, whole questions only, until the budget is reached.

    Returns:
        The kept questions oldest first, and how many in the window were dropped.
    """
    kept: list[str] = []
    used = 0
    for turn in reversed(window):
        cost = len(turn.question)
        if used + cost > max_chars:
            break
        kept.append(turn.question)
        used += cost
    kept.reverse()
    return tuple(kept), len(window) - len(kept)
