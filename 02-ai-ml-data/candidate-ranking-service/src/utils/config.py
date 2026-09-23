"""Runtime configuration, read from environment variables or a local ``.env``."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RankingMethod = Literal["lexical", "embedding"]


class Settings(BaseSettings):
    """Every tunable value in the service.

    Nothing here is hardcoded elsewhere: modules take a ``Settings`` instance
    rather than reaching for module-level constants.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    # --- Ranking -----------------------------------------------------------
    ranking_method: RankingMethod = Field(
        default="lexical",
        description="Which text-similarity backend to use. 'embedding' requires the "
        "optional sentence-transformers extra.",
    )
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Sentence-transformers checkpoint used when ranking_method='embedding'.",
    )

    skill_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    experience_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    similarity_weight: float = Field(default=0.2, ge=0.0, le=1.0)
    required_skill_share: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Share of the skill component attributed to required (versus "
        "preferred) skills.",
    )

    # --- Candidate store ---------------------------------------------------
    max_candidates: int = Field(
        default=1000,
        ge=1,
        description="Hard cap on in-memory candidates. Uploads beyond this are "
        "rejected rather than silently evicted.",
    )
    max_resume_chars: int = Field(default=20_000, ge=100)

    # --- API ---------------------------------------------------------------
    api_key: str | None = Field(
        default=None,
        description="When set, write endpoints require a matching X-API-Key header. "
        "When unset the API is open — see docs/SECURITY.md.",
    )
    cors_origins: str = Field(default="*", description="Comma-separated origin list.")
    log_level: str = Field(default="INFO")

    @property
    def cors_origin_list(self) -> list[str]:
        """``cors_origins`` split into the list CORSMiddleware expects."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _weights_must_sum_to_one(self) -> Settings:
        total = self.skill_weight + self.experience_weight + self.similarity_weight
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                "skill_weight + experience_weight + similarity_weight must sum to 1.0, "
                f"got {total:.4f}"
            )
        return self


def get_settings() -> Settings:
    """Build a ``Settings`` instance from the current environment.

    Not cached: tests override the environment and expect a fresh read.
    """
    return Settings()
