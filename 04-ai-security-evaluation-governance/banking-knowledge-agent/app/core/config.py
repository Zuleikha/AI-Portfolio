"""Environment-based application configuration.

All configuration is read from environment variables (optionally seeded from a
local ``.env`` file). Nothing is hardcoded and no secret ever has a real
default value -- see ``.env.example`` for the documented settings.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

Environment = Literal["local", "test", "production"]
LogFormat = Literal["json", "console"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Stage 14 (guide §20.60): a request holds a worker and its session's lock for
# the whole provider wait, so the wait is capped -- at most 120 s x 4 attempts.
LLM_TIMEOUT_MAX_SECONDS = 120.0
LLM_MAX_RETRIES_MAX = 3


class Settings(BaseSettings):
    """Typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BKA_",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "Banking Knowledge Agent"
    app_version: str = "0.1.0"
    environment: Environment = "local"
    debug: bool = False

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    knowledge_dir: Path = PROJECT_ROOT / "data" / "knowledge"

    # --- RAG pipeline (Stage 3) ------------------------------------------
    # The index is a build artefact of knowledge_dir, so it is git-ignored and
    # rebuilt rather than committed.
    vectorstore_dir: Path = PROJECT_ROOT / "data" / "vectorstore"

    # Runs locally: no API key, no per-query cost, no network after the first
    # download. Set to "hashing" to run the pipeline with no model at all.
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # None lets sentence-transformers choose (CUDA when present, else CPU).
    embedding_device: str | None = None
    embedding_batch_size: int = Field(default=32, ge=1)

    # None means "use the embedding model's own limit", which is the safe
    # default -- a hardcoded number would silently truncate if the model changed.
    chunk_max_tokens: int | None = Field(default=None, ge=16)
    chunk_overlap_tokens: int = Field(default=32, ge=0)

    retrieval_top_k: int = Field(default=5, ge=1)
    # Empirically calibrated against this corpus and this model; re-measure with
    # `python -m app.rag calibrate` if either changes.
    retrieval_min_score: float = Field(default=0.25, ge=-1.0, le=1.0)

    # --- Agent decision (Stage 7) ----------------------------------------
    # A completed search whose top score is below this is "weak", and the agent
    # may run ONE refined second search. Measured, not guessed: documentation
    # questions top out at 0.71-0.82 with the real model, identifier-heavy ones
    # at 0.34-0.49 (docs/HANDOVER.md 7.C/7.D). A weak search is only repeated
    # when a documented component is available to refine it with, so this never
    # causes an identical re-search, and it never lowers the floor above.
    agent_confident_score: float = Field(default=0.50, ge=-1.0, le=1.0)

    # --- Conversation context (Stage 8) ----------------------------------
    # How much of a conversation a follow-up question may use. The window is
    # the number of EARLIER QUESTIONS consulted and sent to the model; earlier
    # answers are never sent (docs/HANDOVER.md 8.B). 0 turns disables
    # conversation context entirely. The character budget drops the oldest
    # questions whole, never mid-sentence -- the same rule as passages.
    conversation_max_history_turns: int = Field(default=3, ge=0)
    conversation_max_history_chars: int = Field(default=1000, ge=0)
    # Store limits, so an in-memory session store cannot grow without bound:
    # turns kept per session, sessions kept at once (least recently used is
    # evicted), and how long an idle session lives.
    conversation_max_turns: int = Field(default=50, ge=1)
    conversation_max_sessions: int = Field(default=1000, ge=1)
    conversation_ttl_seconds: float = Field(default=1800.0, gt=0.0)

    # --- Evaluation (Stage 11) -------------------------------------------
    # The question set `python -m app.eval` and the evaluation tests score
    # against. Its score floors live in the file, beside the questions they
    # apply to, so changing one never means editing code.
    eval_dataset_path: Path = PROJECT_ROOT / "data" / "eval" / "questions.yaml"

    # --- LLM abstraction (Stages 4 and 5) --------------------------------
    # mock | anthropic | openai. The default stays "mock" -- deterministic,
    # in-process and free -- so nothing calls a paid API unless someone
    # deliberately changes this AND supplies a key. An unrecognised value
    # fails loudly in app.llm.factory rather than silently falling back to
    # the mock: an application that answers questions with a stub while
    # looking healthy is worse than one that refuses to start.
    llm_provider: str = "mock"

    # None means "whatever the configured provider's own default is". A
    # hardcoded model name here would be one vendor's string sitting in
    # vendor-neutral configuration, so each adapter owns its own default.
    llm_model: str | None = None

    # A ceiling, not a target: it exists to bound a runaway generation. It must
    # leave room for any reasoning tokens a provider bills as output, so it is
    # set well above the length of a support answer. Answer *brevity* is the
    # system prompt's job, not this number's.
    llm_max_tokens: int = Field(default=4096, ge=256)

    # Transport behaviour, passed to whichever vendor SDK client is built.
    llm_timeout_seconds: float = Field(default=60.0, gt=0.0, le=LLM_TIMEOUT_MAX_SECONDS)
    llm_max_retries: int = Field(default=2, ge=0, le=LLM_MAX_RETRIES_MAX)

    # Context budget. The LLM receives retrieved passages, never the knowledge
    # base; these two numbers are what "never" is enforced with. Passages are
    # dropped whole when a budget is reached -- never truncated mid-passage.
    llm_context_max_chunks: int = Field(default=5, ge=1)
    llm_context_max_chars: int = Field(default=12000, ge=500)

    # Environment only. Unset by default, held as a SecretStr so it cannot be
    # printed by accident: repr() and str() render it as '**********', and
    # pydantic excludes it from model_dump() unless explicitly unmasked.
    # Read only by the anthropic/openai adapters, which refuse to construct
    # without it -- so switching provider without setting this fails loudly
    # rather than reaching a vendor's ambient environment variable.
    llm_api_key: SecretStr | None = None

    # --- Security (Stage 13) ---------------------------------------------
    # One shared key for /api/* and /metrics (guide §20.50). Unset means the
    # API is open, which is only allowed outside production -- see
    # _require_api_key_in_production. SecretStr for the same reason as
    # llm_api_key: it must never render in a repr, a dump or a log line.
    api_key: SecretStr | None = None
    # Requests per client per one-minute fixed window on /api/* (guide
    # §20.51). 0 disables the limiter. Per process, not shared.
    rate_limit_per_minute: int = Field(default=60, ge=0)
    # Upper bound on a question's length, checked before the agent runs. It
    # bounds embedding work and prompt size; a support question is far shorter.
    question_max_chars: int = Field(default=2000, ge=1)

    log_level: LogLevel = "INFO"
    log_format: LogFormat = "console"
    log_dir: Path = PROJECT_ROOT / "logs"
    log_to_file: bool = True

    @model_validator(mode="after")
    def _require_api_key_in_production(self) -> Settings:
        """Refuse a production configuration that would leave the API open."""
        if self.is_production and (
            self.api_key is None or not self.api_key.get_secret_value().strip()
        ):
            raise ValueError("BKA_API_KEY must be set when BKA_ENVIRONMENT=production.")
        return self

    @property
    def is_production(self) -> bool:
        """Whether the app is running with production settings."""
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
