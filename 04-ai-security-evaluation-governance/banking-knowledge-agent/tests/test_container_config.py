"""Stage 12: the container files pin the recorded decisions.

``docs/HANDOVER.md`` §12.A-§12.F (guide §20.43-§20.48). These tests read the
Dockerfile, ``compose.yaml`` and ``.dockerignore`` as text, so they run offline
and without Docker. What they cannot prove -- that the image builds and the
container answers -- is ``test_docker_smoke.py``.
"""

from __future__ import annotations

import re

import pytest
import yaml

from app.core.config import PROJECT_ROOT

DOCKERFILE = PROJECT_ROOT / "Dockerfile"
COMPOSE_FILE = PROJECT_ROOT / "compose.yaml"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"


def stage_lines(target: str) -> list[str]:
    """Return the instruction lines of one named build stage, continuations joined."""
    text = DOCKERFILE.read_text("utf-8").replace("\\\n", " ")
    lines: list[str] = []
    inside = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("FROM "):
            inside = line.lower().endswith(f" as {target}")
        if inside:
            lines.append(line)
    if not lines:
        raise AssertionError(f"Dockerfile has no stage named '{target}'")
    return lines


@pytest.fixture(scope="module")
def compose() -> dict[str, object]:
    loaded = yaml.safe_load(COMPOSE_FILE.read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


# --- 12.B: base image and CPU-only PyTorch ---------------------------------


def test_runtime_stage_starts_from_python_312_slim():
    assert stage_lines("runtime")[0].startswith("FROM python:3.12-slim")


def test_torch_is_installed_from_the_cpu_index_at_the_pinned_version():
    joined = " ".join(stage_lines("runtime"))
    assert "https://download.pytorch.org/whl/cpu" in joined
    # The version comes from requirements.txt, never a second copy of the pin.
    assert not re.search(r"torch==\d", joined)
    assert "requirements.txt" in joined


# --- 12.A: model and index baked in, offline at runtime --------------------


def test_the_index_is_built_during_the_image_build():
    runs = [line for line in stage_lines("runtime") if line.startswith("RUN ")]
    assert any("app.rag build" in line for line in runs)


def test_the_runtime_never_reaches_hugging_face():
    joined = " ".join(stage_lines("runtime"))
    assert "HF_HUB_OFFLINE=1" in joined
    assert "HF_HOME=" in joined


# --- 12.D: health check -----------------------------------------------------


def test_healthcheck_calls_the_liveness_endpoint_without_curl():
    checks = [
        line for line in stage_lines("runtime") if line.startswith("HEALTHCHECK ")
    ]
    assert len(checks) == 1
    assert "/health" in checks[0]
    assert "curl" not in checks[0]


# --- 12.F: non-root ---------------------------------------------------------


def test_runtime_stage_runs_as_a_non_root_user():
    users = [
        line.split()[1] for line in stage_lines("runtime") if line.startswith("USER ")
    ]
    assert users, "runtime stage never switches user"
    assert users[-1] not in {"root", "0"}


def test_the_server_binds_all_interfaces_from_settings():
    joined = " ".join(stage_lines("runtime"))
    assert "BKA_HOST=0.0.0.0" in joined
    # 14.A: the app reads BKA_HOST / BKA_PORT itself, through validated
    # settings -- no shell, no uvicorn flags built from raw environment values.
    cmd = next(line for line in stage_lines("runtime") if line.startswith("CMD "))
    assert cmd.startswith('CMD ["python", "-m", "app"')
    assert "sh" not in cmd.split("[", 1)[1].split(",")[0]
    assert "--host" not in cmd and "--port" not in cmd


def test_the_runtime_image_logs_json():
    """15.A: a container writes one JSON object per line, not console format."""
    assert "BKA_LOG_FORMAT=json" in " ".join(stage_lines("runtime"))


def test_compose_defaults_the_log_format_to_json(compose):
    """15.A: overridable from the shell, but JSON unless you say otherwise."""
    environment = compose["services"]["app"]["environment"]
    assert environment["BKA_LOG_FORMAT"] == "${BKA_LOG_FORMAT:-json}"


def test_the_server_disables_uvicorn_access_log():
    # 13.H: uvicorn's access log prints client IP and path and bypasses log
    # redaction; the request middleware already logs every request.
    cmd = next(line for line in stage_lines("runtime") if line.startswith("CMD "))
    assert "--no-access-log" in cmd


# --- 12.E: a separate test target -------------------------------------------


def test_test_stage_builds_on_runtime_and_adds_dev_requirements():
    lines = stage_lines("test")
    assert lines[0].split()[1] == "runtime"
    assert "requirements-dev.txt" in " ".join(lines)


def test_runtime_stage_installs_no_dev_requirements():
    assert "requirements-dev.txt" not in " ".join(stage_lines("runtime"))


# --- 12.C: compose ----------------------------------------------------------


def test_compose_defines_exactly_one_app_service(compose):
    assert set(compose["services"]) == {"app"}


def test_compose_builds_the_runtime_target(compose):
    assert compose["services"]["app"]["build"]["target"] == "runtime"


def test_compose_defaults_the_llm_provider_to_mock(compose):
    environment = compose["services"]["app"]["environment"]
    assert environment["BKA_LLM_PROVIDER"] == "${BKA_LLM_PROVIDER:-mock}"


def test_compose_carries_no_secret_values(compose):
    environment = compose["services"]["app"]["environment"]
    for key, value in environment.items():
        if "KEY" in key or "SECRET" in key or "TOKEN" in key:
            assert value.startswith("${") and ":-" not in value, key
    assert "env_file" not in compose["services"]["app"]


def test_compose_mounts_the_host_logs_folder(compose):
    volumes = compose["services"]["app"]["volumes"]
    assert any(str(volume).startswith("./logs:") for volume in volumes)


# --- .dockerignore ------------------------------------------------------------


@pytest.mark.parametrize(
    "pattern",
    [
        ".env",
        ".venv",
        ".git",
        "logs",
        "data/vectorstore",
        "docs",
        ".claude",
        "__pycache__",
    ],
)
def test_dockerignore_keeps_local_and_secret_files_out_of_the_build(pattern):
    entries = {
        line.strip().rstrip("/").removeprefix("**/")
        for line in DOCKERIGNORE.read_text("utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert pattern in entries
