"""Typed application settings, assembled from three layers.

Precedence, strongest first:

1. **Environment variable** — see ``ENV_OVERRIDES``. How a deployment changes one
   value without shipping a file.
2. **``config/<environment>.yaml``** — the checked-in per-environment defaults.
   The environment is chosen by ``MENUFORGE_ENV`` (default ``development``).
3. **Code default** — the field defaults below, which are what the app runs on
   when there is no config directory at all.

**Secrets are never part of this.** ``ANTHROPIC_API_KEY`` and ``DATABASE_URL`` are
read straight from the environment at their point of use, and the models here
reject unknown keys, so a credential written into a YAML file fails the load
rather than being quietly accepted. See SECURITY.md.

Loading is lazy and cached — nothing reads configuration at import time, because
`menuforge.main` loads `.env` during startup and settings must observe that.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CONFIG_DIR = "config"
DEFAULT_ENVIRONMENT = "development"

# Environment variable -> (section, field). Flat and explicit: the set of
# settings a deployment may override is a deliberate list, not everything.
ENV_OVERRIDES: dict[str, tuple[str, str]] = {
    "MENUFORGE_LOG_LEVEL": ("logging", "level"),
    "MENUFORGE_MODEL": ("llm", "model"),
    "MENUFORGE_MAX_RETRIES": ("llm", "max_retries"),
    "MENUFORGE_MAX_TOKENS": ("llm", "max_tokens"),
    "MENUFORGE_EFFORT": ("llm", "effort"),
    "MENUFORGE_MAX_UPLOAD_BYTES": ("upload", "max_bytes"),
}


class _Section(BaseModel):
    """Base for every settings section.

    ``extra="forbid"`` is the load-bearing part: a typo'd or unrecognised key is
    an error, not a silently ignored line. It is also what stops a credential
    written into a YAML file from being accepted.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class LoggingSettings(_Section):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Only one renderer exists. Declared so the key is legal in YAML and so
    # adding a second format later is a schema change, not a free-text field.
    format: Literal["json"] = "json"


class LLMSettings(_Section):
    model: str = "claude-sonnet-5"

    # 2 retries => 3 total attempts. Matches the reference prototype.
    max_retries: int = Field(default=2, ge=0, le=10)

    # Caps thinking *and* response text together on this model, so it sits well
    # above what the tool arguments alone need.
    max_tokens: int = Field(default=8000, gt=0)

    # Extraction is transcription, not reasoning — the cheapest, fastest setting.
    effort: Literal["low", "medium", "high"] = "low"


class UploadSettings(_Section):
    max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    allowed_media_types: tuple[str, ...] = (
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
    )


class Settings(_Section):
    app_name: str = "menuforge"
    environment: str = DEFAULT_ENVIRONMENT
    logging: LoggingSettings = LoggingSettings()
    llm: LLMSettings = LLMSettings()
    upload: UploadSettings = UploadSettings()


# The layer-3 baseline, exposed so tests and callers can name it.
DEFAULTS = Settings()

_settings: Settings | None = None


def config_dir() -> Path:
    """Directory holding the per-environment YAML files.

    Relative to the working directory, matching how `menuforge.main` finds `.env`.
    ``MENUFORGE_CONFIG_DIR`` overrides it, which is how tests point at a temp dir
    and how a container can mount config somewhere else.
    """
    return Path(os.environ.get("MENUFORGE_CONFIG_DIR", DEFAULT_CONFIG_DIR))


def environment() -> str:
    """The active environment, naming the YAML file to load."""
    return os.environ.get("MENUFORGE_ENV", DEFAULT_ENVIRONMENT)


def _read_yaml(path: Path) -> dict[str, Any]:
    """Parse one config file. Absent is fine; unparseable is not."""
    if not path.is_file():
        return {}

    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"config file {path} is not valid YAML: {exc}") from exc

    # An empty file is a legitimate "no overrides".
    if loaded is None:
        return {}
    if isinstance(loaded, dict):
        return loaded
    raise ValueError(f"config file {path} must contain a mapping, got {type(loaded).__name__}")


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Layer environment variables on top of the YAML mapping.

    Values stay strings here — Pydantic does the coercion, so an unparseable
    override fails validation loudly instead of being silently dropped.
    """
    for variable, (section, field) in ENV_OVERRIDES.items():
        value = os.environ.get(variable)
        if value is None:
            continue
        current = raw.get(section)
        raw[section] = {**current, field: value} if isinstance(current, dict) else {field: value}
    return raw


def load_settings() -> Settings:
    """Build settings from YAML plus environment overrides, ignoring any cache.

    Raises ``ValueError`` on unreadable config and ``pydantic.ValidationError`` on
    config that parses but does not validate.
    """
    raw = _read_yaml(config_dir() / f"{environment()}.yaml")
    raw.setdefault("environment", environment())
    return Settings.model_validate(_apply_env_overrides(raw))


def get_settings() -> Settings:
    """Return the process-wide settings, loading them on first use.

    Cached because these are read on every request; call `reset_settings` after
    changing the environment.
    """
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings() -> None:
    """Drop the cached settings so the next read reloads them."""
    global _settings
    _settings = None
