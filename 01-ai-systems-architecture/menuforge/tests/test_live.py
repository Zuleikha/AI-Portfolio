"""Live end-to-end test against the real Anthropic API. **This costs money.**

Deselected by default — `pyproject.toml` sets `addopts = -m "not live"`. Run it
deliberately:

    pytest -m live

Everything here derives from **one** API call, made once per module by the
`live_result` fixture. Adding an assertion costs nothing; adding a test that
calls the model again costs a request, so don't.

What this proves that no other test can: that the tool schema, `tool_choice`,
image encoding and `output_config` we send are accepted by the real API, and
that a real response validates against `ExtractedMenu`. Every other test asserts
against a `MagicMock` shaped the way we *assume* the API behaves.

The fixture image is synthetic — see `fixtures/generate_menu_image.py`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from dotenv import dotenv_values, find_dotenv
from fastapi.testclient import TestClient

pytestmark = pytest.mark.live

FIXTURE_IMAGE = Path(__file__).resolve().parent / "fixtures" / "sample_menu.png"
REPO_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# conftest sets this so the client can be constructed offline. It is not a key.
PLACEHOLDER_KEY = "test-key-not-a-real-credential"

# What fixtures/sample_menu.png actually says. Prices are exact; the model is
# transcribing printed text, not estimating.
EXPECTED_PRICES = {
    "tomato soup": 4.50,
    "garlic bread": 3.25,
    "margherita pizza": 12.50,
    "mushroom risotto": 11.00,
    "espresso": 2.80,
    "orange juice": 3.00,
}


class LiveResult(NamedTuple):
    status_code: int
    body: dict[str, Any]
    stored: list[dict[str, Any]]


def _real_api_key() -> str | None:
    """Return a usable key, or None if only the offline placeholder is available.

    Reads `.env` with `dotenv_values`, which returns a dict rather than mutating
    the environment — loading `.env` for real here would also import a developer's
    `DATABASE_URL` into every other test in the session.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or key == PLACEHOLDER_KEY:
        key = dotenv_values(find_dotenv(usecwd=True)).get("ANTHROPIC_API_KEY") or ""
    return key if key.startswith("sk-ant-") else None


@pytest.fixture(scope="module")
def live_result(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveResult]:
    """POST the fixture image to a real app with extraction **unpatched**.

    Exactly one Anthropic request per test run of this module.
    """
    key = _real_api_key()
    if key is None:
        pytest.skip("no real ANTHROPIC_API_KEY available; set one to run live tests")
    if not FIXTURE_IMAGE.is_file():
        pytest.skip(f"missing fixture image {FIXTURE_IMAGE}")

    tmp_path = tmp_path_factory.mktemp("live")
    previous = dict(os.environ)
    os.environ.update(
        {
            "ANTHROPIC_API_KEY": key,
            # A throwaway database: a live run must never touch a real one.
            "DATABASE_URL": f"sqlite:///{tmp_path / 'live.db'}",
            "MENUFORGE_CONFIG_DIR": str(REPO_CONFIG_DIR),
        }
    )

    from menuforge import main
    from menuforge.config.settings import reset_settings
    from menuforge.tools import database as db

    reset_settings()
    db.reset_engine()

    try:
        with TestClient(main.app) as client:
            response = client.post(
                "/extract",
                files={"file": (FIXTURE_IMAGE.name, FIXTURE_IMAGE.read_bytes(), "image/png")},
            )
            stored = client.get("/items").json() if response.status_code == 200 else []
            yield LiveResult(response.status_code, response.json(), stored)
    finally:
        os.environ.clear()
        os.environ.update(previous)
        db.reset_engine()
        reset_settings()


def _by_name(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["name"].strip().lower(): item for item in items}


# --------------------------------------------------------------------------
# The request was accepted and the response validated
# --------------------------------------------------------------------------


def test_live_extraction_succeeds(live_result: LiveResult) -> None:
    """A 422 here means the real response failed Pydantic validation."""
    assert live_result.status_code == 200, live_result.body


def test_live_extraction_returns_items(live_result: LiveResult) -> None:
    assert len(live_result.body["items"]) >= 5


def test_live_items_have_the_contract_shape(live_result: LiveResult) -> None:
    for item in live_result.body["items"]:
        assert isinstance(item["name"], str) and item["name"].strip()
        assert isinstance(item["price"], float)
        assert item["price"] > 0
        assert isinstance(item["description"], str)
        assert isinstance(item["modifiers"], list)


# --------------------------------------------------------------------------
# It read the actual menu, not something plausible
# --------------------------------------------------------------------------


def test_live_extraction_finds_the_expected_dishes(live_result: LiveResult) -> None:
    """Every dish printed on the fixture image should come back.

    Matched on a normalised name so casing or trailing whitespace does not fail
    the test; the *set* of dishes is what is being checked.
    """
    found = set(_by_name(live_result.body["items"]))

    assert set(EXPECTED_PRICES) <= found, f"missing: {set(EXPECTED_PRICES) - found}"


def test_live_extraction_reads_prices_exactly(live_result: LiveResult) -> None:
    """Prices are printed on the image, so transcription must be exact."""
    items = _by_name(live_result.body["items"])

    actual = {name: items[name]["price"] for name in EXPECTED_PRICES if name in items}

    assert actual == pytest.approx(EXPECTED_PRICES)


# --------------------------------------------------------------------------
# And it was persisted
# --------------------------------------------------------------------------


def test_live_result_is_persisted(live_result: LiveResult) -> None:
    assert len(live_result.stored) == len(live_result.body["items"])
    assert all(isinstance(item["id"], int) for item in live_result.stored)


def test_live_stored_names_match_the_response(live_result: LiveResult) -> None:
    assert _by_name(live_result.stored).keys() == _by_name(live_result.body["items"]).keys()
