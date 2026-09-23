"""Tests for the configuration loader.

These pin the precedence rule the rest of the app depends on:
environment variable > YAML for the active environment > code default.

The last test in this file is the one that matters most: it loads the *shipped*
`config/*.yaml` files, so they cannot silently drift back into decoration.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from menuforge.config.settings import (
    DEFAULTS,
    Settings,
    get_settings,
    load_settings,
    reset_settings,
)

REPO_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _write(config_dir: Path, name: str, body: str) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / f"{name}.yaml").write_text(body, encoding="utf-8")


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------


def test_missing_config_dir_falls_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deployment configured purely by environment variables must still boot."""
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path / "nope"))

    settings = load_settings()

    assert settings.llm.model == DEFAULTS.llm.model
    assert settings.upload.max_bytes == DEFAULTS.upload.max_bytes


def test_missing_file_for_environment_falls_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MENUFORGE_ENV", "staging")
    _write(tmp_path, "development", "llm:\n  model: from-yaml\n")

    assert load_settings().llm.model == DEFAULTS.llm.model


# --------------------------------------------------------------------------
# YAML
# --------------------------------------------------------------------------


def test_yaml_overrides_the_code_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "llm:\n  model: claude-from-yaml\n  max_retries: 5\n")

    settings = load_settings()

    assert settings.llm.model == "claude-from-yaml"
    assert settings.llm.max_retries == 5


def test_partial_yaml_keeps_defaults_for_absent_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "llm:\n  model: only-this-key\n")

    settings = load_settings()

    assert settings.llm.model == "only-this-key"
    assert settings.llm.max_tokens == DEFAULTS.llm.max_tokens


def test_environment_selects_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "llm:\n  model: dev-model\n")
    _write(tmp_path, "production", "llm:\n  model: prod-model\n")

    monkeypatch.setenv("MENUFORGE_ENV", "production")

    assert load_settings().llm.model == "prod-model"


def test_environment_defaults_to_development(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("MENUFORGE_ENV", raising=False)
    _write(tmp_path, "development", "llm:\n  model: dev-model\n")

    assert load_settings().llm.model == "dev-model"


# --------------------------------------------------------------------------
# Environment variables win
# --------------------------------------------------------------------------


def test_env_var_beats_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "llm:\n  model: from-yaml\n")
    monkeypatch.setenv("MENUFORGE_MODEL", "from-env")

    assert load_settings().llm.model == "from-env"


def test_env_var_is_coerced_to_the_declared_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment variables are strings; the schema decides the real type."""
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MENUFORGE_MAX_UPLOAD_BYTES", "2048")

    max_bytes = load_settings().upload.max_bytes

    assert max_bytes == 2048
    assert isinstance(max_bytes, int)


def test_unparseable_env_var_fails_loud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MENUFORGE_MAX_RETRIES", "lots")

    with pytest.raises(ValidationError):
        load_settings()


# --------------------------------------------------------------------------
# Fail loud on bad config
# --------------------------------------------------------------------------


def test_malformed_yaml_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "llm:\n  model: [unclosed\n")

    with pytest.raises(ValueError, match="config"):
        load_settings()


def test_non_mapping_yaml_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "- just\n- a list\n")

    with pytest.raises(ValueError, match="must contain a mapping"):
        load_settings()


def test_empty_yaml_is_treated_as_no_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "")

    assert load_settings().llm.model == DEFAULTS.llm.model


def test_invalid_value_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "llm:\n  max_retries: -1\n")

    with pytest.raises(ValidationError):
        load_settings()


def test_unknown_key_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo'd key must not be silently ignored — that is how config rots."""
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "llm:\n  modle: typo\n")

    with pytest.raises(ValidationError):
        load_settings()


# --------------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------------


def test_a_secret_in_yaml_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SECURITY.md: credentials come from the environment, never from a file."""
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "anthropic_api_key: sk-ant-not-a-real-key\n")

    with pytest.raises(ValidationError):
        load_settings()


def test_settings_expose_no_credential_fields() -> None:
    """Nothing on the settings object should ever hold a secret."""
    leaf_names = {
        name
        for section in Settings.model_fields.values()
        if hasattr(section.annotation, "model_fields")
        for name in section.annotation.model_fields  # type: ignore[union-attr]
    } | set(Settings.model_fields)

    for forbidden in ("api_key", "anthropic_api_key", "database_url", "password", "secret"):
        assert forbidden not in leaf_names


# --------------------------------------------------------------------------
# Caching
# --------------------------------------------------------------------------


def test_get_settings_is_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "llm:\n  model: first\n")

    assert get_settings().llm.model == "first"

    _write(tmp_path, "development", "llm:\n  model: second\n")

    assert get_settings().llm.model == "first", "must not re-read the file on every call"


def test_reset_settings_forces_a_reload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    _write(tmp_path, "development", "llm:\n  model: first\n")
    assert get_settings().llm.model == "first"

    _write(tmp_path, "development", "llm:\n  model: second\n")
    reset_settings()

    assert get_settings().llm.model == "second"


# --------------------------------------------------------------------------
# The shipped files must stay real
# --------------------------------------------------------------------------


@pytest.mark.parametrize("environment", ["development", "production"])
def test_shipped_config_files_load(environment: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The repo's own config must parse and validate — no decorative keys."""
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(REPO_CONFIG_DIR))
    monkeypatch.setenv("MENUFORGE_ENV", environment)
    for name in ("MENUFORGE_MODEL", "MENUFORGE_LOG_LEVEL", "MENUFORGE_MAX_UPLOAD_BYTES"):
        monkeypatch.delenv(name, raising=False)

    settings = load_settings()

    assert settings.environment == environment
    assert settings.llm.max_retries == 2
    assert "image/png" in settings.upload.allowed_media_types


def test_development_and_production_differ_in_log_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two files exist to differ; if they are identical, one is pointless."""
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(REPO_CONFIG_DIR))
    monkeypatch.delenv("MENUFORGE_LOG_LEVEL", raising=False)

    monkeypatch.setenv("MENUFORGE_ENV", "development")
    development = load_settings()
    monkeypatch.setenv("MENUFORGE_ENV", "production")
    production = load_settings()

    assert development.logging.level == "DEBUG"
    assert production.logging.level == "INFO"
