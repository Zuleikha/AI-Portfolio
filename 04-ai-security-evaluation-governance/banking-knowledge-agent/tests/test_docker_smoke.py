"""Stage 12: smoke test against the running container (``docs/HANDOVER.md`` §12.E).

Skipped unless ``BKA_SMOKE_BASE_URL`` is set, so the normal suite never needs
Docker. Run after ``docker compose up -d``::

    BKA_SMOKE_BASE_URL=http://localhost:8000 python -m pytest tests/test_docker_smoke.py

Free: the container's provider defaults to ``mock``, and nothing here sets it.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest

BASE_URL = os.environ.get("BKA_SMOKE_BASE_URL", "")

# A knowledge_required question from data/eval/questions.yaml, so the route it
# takes is already measured rather than assumed.
KNOWLEDGE_QUESTION = "What component handles card authentication?"

pytestmark = pytest.mark.skipif(not BASE_URL, reason="BKA_SMOKE_BASE_URL is not set")


@pytest.fixture(scope="module")
def http() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
        yield client


def test_health_reports_ok(http):
    response = http.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_web_page_is_served(http):
    response = http.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_one_question_is_answered_from_the_baked_index(http):
    created = http.post("/api/sessions")
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    answer = http.post(
        "/api/sessions/ask",
        json={"session_id": session_id, "question": KNOWLEDGE_QUESTION},
    )

    assert answer.status_code == 200
    body = answer.json()
    assert body["rag_used"] is True
    assert body["sources"]
    assert body["insufficient"] is False


def test_metrics_are_served(http):
    response = http.get("/metrics")

    assert response.status_code == 200
    assert response.content
