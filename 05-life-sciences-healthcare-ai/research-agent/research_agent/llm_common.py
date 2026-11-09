"""Shared Claude helpers for the nodes that call the model (docs/PRD.md, C-Q1).

Used by ``nodes/summarise.py`` (Stage 4) and ``nodes/citation_check.py`` (Stage 5),
so neither node imports the other's internals.

Settings come from environment variables only. ``.env`` is loaded by the entry
point, not here. ``ANTHROPIC_API_KEY`` is read by ``langchain-anthropic``.
"""

import os
import re

from langchain_anthropic import ChatAnthropic

from research_agent.observability import traced

API_KEY_ENV = "ANTHROPIC_API_KEY"

MAX_RETRIES = 2  # library default is 6 (S7, C3)
TIMEOUT_SECONDS = 60.0


@traced
def require_env(name: str, error: type[Exception]) -> str:
    """The setting's value, or ``error`` if it is missing or blank (fail loud)."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise error(f"{name} is not set")
    return value


@traced
def build_chat_model(model_env: str, max_tokens: int, error: type[Exception]) -> ChatAnthropic:
    """The Claude chat model. No temperature/top_p/top_k (S8), no tools (S4, C3)."""
    require_env(API_KEY_ENV, error)  # fail loud here, not deep inside the SDK
    return ChatAnthropic(
        model=require_env(model_env, error),
        max_retries=MAX_RETRIES,
        timeout=TIMEOUT_SECONDS,
        max_tokens=max_tokens,
    )


@traced
def neutralise(text: str, tags: tuple[str, ...]) -> str:
    """Turns "<tag" / "</tag" (any case) into harmless "&lt;tag", so source text
    cannot open or close one of the prompt's own tags (S12, C12)."""
    pattern = re.compile(r"<(/?)(" + "|".join(re.escape(t) for t in tags) + ")", re.IGNORECASE)
    return pattern.sub(r"&lt;\1\2", text)
