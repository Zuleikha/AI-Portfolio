"""Stage 14 (carried from 13): repository hygiene that git itself enforces.

Files written for Linux containers must keep LF endings on a Windows checkout,
whatever each machine's ``core.autocrlf`` is. ``.gitattributes`` is what makes
that true; this test pins which files it covers.
"""

from __future__ import annotations

import sys
import tomllib

import pytest

from app.core.config import PROJECT_ROOT

GITATTRIBUTES = PROJECT_ROOT / ".gitattributes"

# 15.C: `.dockerignore` deliberately keeps git metadata out of every image, so
# inside the container these assert something that is correctly absent. Skip
# rather than fail -- the same pattern as the Docker smoke tests, which skip
# unless BKA_SMOKE_BASE_URL names a running container.
needs_a_git_checkout = pytest.mark.skipif(
    not GITATTRIBUTES.exists(),
    reason="no .gitattributes: not a git checkout (e.g. inside the image)",
)


def lf_patterns() -> set[str]:
    patterns: set[str] = set()
    for raw in GITATTRIBUTES.read_text("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pattern, *attributes = line.split()
        if {"text", "eol=lf"} <= set(attributes):
            patterns.add(pattern)
    return patterns


@pytest.mark.parametrize(
    "pattern",
    [
        "*.py",
        "*.md",
        "*.html",
        "*.yaml",
        "*.txt",
        "Dockerfile",
        "*.js",
        "*.css",
        ".dockerignore",
        ".env.example",
        "*.toml",
        ".gitignore",
    ],
)
@needs_a_git_checkout
def test_file_type_is_forced_to_lf(pattern):
    assert pattern in lf_patterns()


# --- 15.B: the declared interpreter is the one that is actually tested -----

PYPROJECT = PROJECT_ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text("utf-8"))


def test_requires_python_matches_the_tested_interpreter(pyproject):
    """A version range is a promise something verifies; 3.11 is never built."""
    assert pyproject["project"]["requires-python"] == ">=3.12"


def test_ruff_and_mypy_target_the_same_version(pyproject):
    assert pyproject["tool"]["ruff"]["target-version"] == "py312"
    assert pyproject["tool"]["mypy"]["python_version"] == "3.12"


def test_the_running_interpreter_satisfies_the_declared_floor():
    assert sys.version_info >= (3, 12)
