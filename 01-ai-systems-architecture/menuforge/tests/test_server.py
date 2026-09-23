"""End-to-end tests against a real HTTP server on a real socket.

`test_api.py` drives the ASGI app in-process with `TestClient`, which never
opens a socket. These tests run **uvicorn** on an ephemeral port and talk to it
with a real `httpx` client, so the parts `TestClient` substitutes for — HTTP/1.1
parsing, multipart framing over the wire, `Content-Length` handling, the server's
own error responses — are actually exercised.

The LLM is still patched; nothing here calls Anthropic. `test_live.py` is the
one that does.

The server runs in a **thread inside the test process**, not a subprocess, so
`patch.object(main, "extract_menu")` still reaches the code the server executes.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from unittest.mock import MagicMock, patch

import httpx
import pytest
import uvicorn

from menuforge import main
from menuforge.config.settings import reset_settings
from menuforge.llm.client import ExtractionFailedError
from menuforge.schemas import ExtractedMenu

MENU = ExtractedMenu.model_validate(
    {
        "items": [
            {"name": "Tomato Soup", "price": 4.5, "description": "slow-roasted"},
            {"name": "Espresso", "price": 2.8},
        ]
    }
)

PNG = ("menu.png", b"fake image bytes", "image/png")

# Generous: covers a cold start on a loaded CI runner, and only the failure
# path ever waits this long.
STARTUP_TIMEOUT_SECONDS = 30.0


@pytest.fixture
def base_url(database: None) -> Iterator[str]:
    """Run uvicorn on an ephemeral port and yield its base URL.

    Port 0 lets the OS pick a free port, so concurrent runs cannot collide.
    The real port is read back off the bound socket once the server is up.
    """
    config = uvicorn.Config(main.app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="uvicorn-test", daemon=True)
    thread.start()

    started = _wait_for(lambda: server.started, STARTUP_TIMEOUT_SECONDS)
    if not started:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("uvicorn did not start within the timeout")

    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _wait_for(condition: Callable[[], bool], timeout: float) -> bool:
    """Poll `condition` until it is true or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def extraction() -> Iterator[MagicMock]:
    with patch.object(main, "extract_menu") as mock:
        mock.return_value = MENU
        yield mock


@pytest.fixture
def http() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=30.0) as client:
        yield client


# --------------------------------------------------------------------------
# The server is really serving
# --------------------------------------------------------------------------


def test_serves_get_items_over_a_socket(base_url: str, http: httpx.Client) -> None:
    response = http.get(f"{base_url}/items")

    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["content-type"].startswith("application/json")
    # Proof this went over HTTP, not through an in-process shortcut.
    assert response.http_version == "HTTP/1.1"


def test_unknown_route_is_404(base_url: str, http: httpx.Client) -> None:
    assert http.get(f"{base_url}/nope").status_code == 404


def test_openapi_schema_is_served(base_url: str, http: httpx.Client) -> None:
    """A cheap check that the app mounted fully, not just one router."""
    schema = http.get(f"{base_url}/openapi.json").json()

    assert "/extract" in schema["paths"]
    assert "/items" in schema["paths"]


# --------------------------------------------------------------------------
# A real multipart upload
# --------------------------------------------------------------------------


def test_multipart_upload_round_trip(
    base_url: str, http: httpx.Client, extraction: MagicMock
) -> None:
    """The full path: multipart over the wire, extraction, persistence, read back."""
    response = http.post(f"{base_url}/extract", files={"file": PNG})

    assert response.status_code == 200
    assert response.json() == MENU.model_dump()

    stored = http.get(f"{base_url}/items").json()
    assert [item["name"] for item in stored] == ["Tomato Soup", "Espresso"]
    assert stored[0]["price"] == 4.5


def test_upload_reaches_the_extractor_intact(
    base_url: str, http: httpx.Client, extraction: MagicMock
) -> None:
    """Bytes survive multipart encoding and decoding unchanged."""
    payload = bytes(range(256)) * 4

    http.post(f"{base_url}/extract", files={"file": ("menu.png", payload, "image/png")})

    sent_bytes, sent_media_type = extraction.call_args.args
    assert sent_bytes == payload
    assert sent_media_type == "image/png"


# --------------------------------------------------------------------------
# Error responses come back over the wire, not as a dropped connection
# --------------------------------------------------------------------------


def test_unsupported_media_type_over_the_wire(
    base_url: str, http: httpx.Client, extraction: MagicMock
) -> None:
    response = http.post(
        f"{base_url}/extract", files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")}
    )

    assert response.status_code == 415
    assert "unsupported media type" in response.json()["detail"]
    extraction.assert_not_called()


def test_oversized_upload_over_the_wire(
    base_url: str, http: httpx.Client, extraction: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real Content-Length larger than the limit is refused with a 413.

    The limit is lowered through config rather than sending 10 MiB down a socket:
    the point is the server's handling, not the transfer.
    """
    monkeypatch.setenv("MENUFORGE_MAX_UPLOAD_BYTES", "512")
    reset_settings()

    response = http.post(
        f"{base_url}/extract", files={"file": ("big.png", b"x" * 513, "image/png")}
    )

    assert response.status_code == 413
    extraction.assert_not_called()


def test_extraction_failure_is_422_over_the_wire(
    base_url: str, http: httpx.Client, extraction: MagicMock
) -> None:
    extraction.side_effect = ExtractionFailedError("all attempts failed")

    response = http.post(f"{base_url}/extract", files={"file": PNG})

    assert response.status_code == 422
    assert "extraction failed" in response.json()["detail"]
    assert http.get(f"{base_url}/items").json() == []


def test_missing_file_field_is_422(base_url: str, http: httpx.Client) -> None:
    """FastAPI's own validation, exercised through the real server."""
    assert http.post(f"{base_url}/extract").status_code == 422
