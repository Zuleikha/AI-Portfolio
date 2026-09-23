"""Checking an answer's inline citations against the evidence it was given.

The prompt numbers passages ``[1]``, ``[2]`` and tool results ``[T1]``,
``[T2]``. A marker outside those ranges points at nothing the model was shown:
the mechanical sign of hallucination.

Stage 11 used this offline, in the evaluation. **Stage 14.B (guide §20.59)**
also applies it to every live answer: :class:`~app.llm.service.LLMService`
withholds an answer that cites evidence never sent, exactly as it withholds a
truncated one. One function, so the two checks cannot drift apart.
"""

from __future__ import annotations

import re

from app.core.tracing import traced
from app.llm.prompts import TOOL_CITATION_PREFIX

CITATION_PATTERN = re.compile(r"\[(" + re.escape(TOOL_CITATION_PREFIX) + r")?(\d+)\]")
"""A passage citation ``[n]`` or a tool-result citation ``[Tn]``."""


@traced
def invalid_citations(text: str, chunks_used: int, tools_used: int) -> tuple[str, ...]:
    """Citations in ``text`` that point at no supplied passage or tool result.

    Args:
        text: The answer text.
        chunks_used: How many passages were numbered in the prompt.
        tools_used: How many tool results were numbered in the prompt.

    Returns:
        Each invalid marker once, in order of first appearance. Empty when every
        marker is valid, including when there are none.
    """
    invalid: dict[str, None] = {}
    for match in CITATION_PATTERN.finditer(text):
        number = int(match.group(2))
        limit = tools_used if match.group(1) else chunks_used
        if not 1 <= number <= limit:
            invalid.setdefault(match.group(0), None)
    return tuple(invalid)
