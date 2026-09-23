"""Configuration management tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    LLM_MAX_RETRIES_MAX,
    LLM_TIMEOUT_MAX_SECONDS,
    Settings,
    get_settings,
)


def test_defaults_are_local_and_safe():
    settings = Settings(_env_file=None)
    assert settings.environment == "local"
    assert settings.is_production is False
    assert settings.port == 8000
    assert settings.log_level == "INFO"


def test_environment_variables_override_defaults(monkeypatch):
    monkeypatch.setenv("BKA_ENVIRONMENT", "production")
    # Production refuses to start without an API key (guide §20.50).
    monkeypatch.setenv("BKA_API_KEY", "test-only-not-a-secret")
    monkeypatch.setenv("BKA_PORT", "9100")
    monkeypatch.setenv("BKA_LOG_FORMAT", "json")

    settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.is_production is True
    assert settings.port == 9100
    assert settings.log_format == "json"


def test_invalid_port_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, port=70000)


def test_invalid_environment_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="staging")


def test_security_defaults_are_open_locally_and_bounded():
    settings = Settings(_env_file=None)
    assert settings.api_key is None
    assert settings.rate_limit_per_minute == 60
    assert settings.question_max_chars == 2000


def test_production_without_api_key_refuses_to_start(monkeypatch):
    monkeypatch.delenv("BKA_API_KEY", raising=False)
    with pytest.raises(ValidationError, match="BKA_API_KEY"):
        Settings(_env_file=None, environment="production")


def test_production_with_blank_api_key_refuses_to_start():
    with pytest.raises(ValidationError, match="BKA_API_KEY"):
        Settings(_env_file=None, environment="production", api_key="   ")


def test_api_key_is_never_rendered():
    settings = Settings(_env_file=None, api_key="test-only-not-a-secret")
    assert "test-only-not-a-secret" not in repr(settings)
    assert "test-only-not-a-secret" not in str(settings.model_dump())


def test_rate_limit_zero_disables_and_negative_is_rejected():
    assert Settings(_env_file=None, rate_limit_per_minute=0).rate_limit_per_minute == 0
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rate_limit_per_minute=-1)


def test_question_max_chars_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, question_max_chars=0)


@pytest.mark.parametrize(
    ("field", "at_cap", "over_cap"),
    [
        ("llm_timeout_seconds", LLM_TIMEOUT_MAX_SECONDS, LLM_TIMEOUT_MAX_SECONDS + 1),
        ("llm_max_retries", LLM_MAX_RETRIES_MAX, LLM_MAX_RETRIES_MAX + 1),
    ],
)
def test_llm_timeout_and_retries_have_an_upper_bound(field, at_cap, over_cap):
    # Stage 14 (carried from 13): an unbounded value could hold a worker and
    # the session lock for minutes.
    assert getattr(Settings(_env_file=None, **{field: at_cap}), field) == at_cap
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: over_cap})


def test_worst_case_llm_wait_is_bounded():
    worst = LLM_TIMEOUT_MAX_SECONDS * (LLM_MAX_RETRIES_MAX + 1)
    assert worst <= 480


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_settings_are_immutable():
    settings = Settings(_env_file=None)
    with pytest.raises(ValidationError):
        settings.port = 1234
