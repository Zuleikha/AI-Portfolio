"""Tests for the API surface.

The extraction function is patched, so these assert status codes, response shape
and persistence — not extraction behaviour, which is test_extraction.py's job.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from menuforge import main
from menuforge.config.settings import get_settings, reset_settings
from menuforge.llm.client import ExtractionFailedError
from menuforge.schemas import ExtractedMenu

MENU = ExtractedMenu.model_validate(
    {
        "items": [
            {
                "name": "Margherita Pizza",
                "price": 12.5,
                "description": "Classic",
                "modifiers": ["extra cheese"],
            },
            {"name": "Espresso", "price": 2.8},
        ]
    }
)

# The (filename, content, media_type) triple httpx expects for a file part.
Upload = tuple[str, bytes, str]

PNG: Upload = ("menu.png", b"fake image bytes", "image/png")


@pytest.fixture
def client(database: None) -> Iterator[TestClient]:
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def extraction() -> Iterator[MagicMock]:
    with patch.object(main, "extract_menu") as mock:
        mock.return_value = MENU
        yield mock


def _post(client: TestClient, upload: Upload = PNG) -> httpx.Response:
    # Annotated locally because TestClient.post is untyped, so mypy sees Any.
    response: httpx.Response = client.post("/extract", files={"file": upload})
    return response


# --------------------------------------------------------------------------
# GET /items
# --------------------------------------------------------------------------


def test_items_is_empty_before_any_extraction(client: TestClient) -> None:
    response = client.get("/items")

    assert response.status_code == 200
    assert response.json() == []


def test_items_returns_stored_items(client: TestClient, extraction: MagicMock) -> None:
    _post(client)

    response = client.get("/items")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2

    first = items[0]
    assert first["name"] == "Margherita Pizza"
    assert first["price"] == 12.5
    assert first["description"] == "Classic"
    assert first["modifiers"] == ["extra cheese"]
    assert isinstance(first["id"], int)


def test_items_preserves_schema_defaults(client: TestClient, extraction: MagicMock) -> None:
    _post(client)

    second = client.get("/items").json()[1]

    assert second["name"] == "Espresso"
    assert second["description"] == ""
    assert second["modifiers"] == []


def test_repeated_uploads_append(client: TestClient, extraction: MagicMock) -> None:
    """Documents accepted prototype behaviour: no dedupe (PRD §5)."""
    _post(client)
    _post(client)

    assert len(client.get("/items").json()) == 4


# --------------------------------------------------------------------------
# POST /extract — success
# --------------------------------------------------------------------------


def test_extract_returns_the_validated_menu(client: TestClient, extraction: MagicMock) -> None:
    response = _post(client)

    assert response.status_code == 200
    assert response.json() == MENU.model_dump()


@pytest.mark.parametrize("media_type", ["image/png", "image/jpeg", "image/webp", "image/gif"])
def test_accepted_media_types(client: TestClient, extraction: MagicMock, media_type: str) -> None:
    response = _post(client, ("menu", b"fake image bytes", media_type))

    assert response.status_code == 200


# --------------------------------------------------------------------------
# POST /extract — failure
# --------------------------------------------------------------------------


def test_exhausted_retries_returns_422_and_writes_nothing(
    client: TestClient, extraction: MagicMock
) -> None:
    extraction.side_effect = ExtractionFailedError("all attempts failed")

    response = _post(client)

    assert response.status_code == 422
    assert "extraction failed" in response.json()["detail"]
    assert client.get("/items").json() == []


# --------------------------------------------------------------------------
# POST /extract — upload validation (must cost no API spend)
# --------------------------------------------------------------------------


def test_non_image_upload_is_rejected(client: TestClient, extraction: MagicMock) -> None:
    response = _post(client, ("doc.pdf", b"%PDF-1.4", "application/pdf"))

    assert response.status_code == 415
    extraction.assert_not_called()


def test_empty_upload_is_rejected(client: TestClient, extraction: MagicMock) -> None:
    response = _post(client, ("empty.png", b"", "image/png"))

    assert response.status_code == 400
    extraction.assert_not_called()


def test_oversized_upload_is_rejected(client: TestClient, extraction: MagicMock) -> None:
    oversized = b"x" * (get_settings().upload.max_bytes + 1)

    response = _post(client, ("big.png", oversized, "image/png"))

    assert response.status_code == 413
    extraction.assert_not_called()


def test_upload_at_the_size_limit_is_accepted(client: TestClient, extraction: MagicMock) -> None:
    """The limit is inclusive — an exactly-limit image is not oversized."""
    at_limit = b"x" * get_settings().upload.max_bytes

    response = _post(client, ("edge.png", at_limit, "image/png"))

    assert response.status_code == 200


def test_size_limit_comes_from_config(
    client: TestClient, extraction: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A configured limit reaches the endpoint, not just the settings object."""
    monkeypatch.setenv("MENUFORGE_MAX_UPLOAD_BYTES", "64")
    reset_settings()

    assert _post(client, ("small.png", b"x" * 64, "image/png")).status_code == 200
    assert _post(client, ("big.png", b"x" * 65, "image/png")).status_code == 413


def test_allowed_media_types_come_from_config(
    client: TestClient,
    extraction: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Narrowing the allow-list in YAML narrows what the endpoint accepts."""
    (tmp_path / "development.yaml").write_text(
        "upload:\n  allowed_media_types:\n    - image/gif\n", encoding="utf-8"
    )
    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(tmp_path))
    reset_settings()

    assert _post(client, ("menu.png", b"fake image bytes", "image/png")).status_code == 415
    assert _post(client, ("menu.gif", b"fake image bytes", "image/gif")).status_code == 200


def test_rejected_upload_writes_nothing(client: TestClient, extraction: MagicMock) -> None:
    _post(client, ("doc.pdf", b"%PDF-1.4", "application/pdf"))

    assert client.get("/items").json() == []


# --------------------------------------------------------------------------
# Logging (PRD SC-7)
# --------------------------------------------------------------------------


def test_request_logs_duration_but_not_image_bytes(
    client: TestClient, extraction: MagicMock, log_capture: io.StringIO
) -> None:
    _post(client, ("menu.png", b"SENTINELIMAGEBYTES", "image/png"))

    output = log_capture.getvalue()
    assert "SENTINELIMAGEBYTES" not in output
    assert "extract.start" in output
    assert "extract.success" in output
    assert "duration_ms" in output


def test_failure_logs_an_error_event(
    client: TestClient, extraction: MagicMock, log_capture: io.StringIO
) -> None:
    extraction.side_effect = ExtractionFailedError("all attempts failed")

    _post(client)

    assert "extract.error" in log_capture.getvalue()


def test_rejected_upload_is_logged(
    client: TestClient, extraction: MagicMock, log_capture: io.StringIO
) -> None:
    _post(client, ("doc.pdf", b"%PDF-1.4", "application/pdf"))

    assert "extract.rejected" in log_capture.getvalue()
