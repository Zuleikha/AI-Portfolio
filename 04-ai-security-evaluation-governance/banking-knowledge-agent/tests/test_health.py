"""Health endpoint and application startup tests."""

from __future__ import annotations


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "Banking Knowledge Agent"
    assert body["environment"] == "test"
    assert body["version"]


def test_health_response_has_no_unexpected_fields(client):
    body = client.get("/health").json()
    assert set(body) == {"status", "service", "version", "environment"}


def test_app_exposes_openapi_schema(client):
    schema = client.get("/openapi.json").json()
    assert "/health" in schema["paths"]
    assert schema["info"]["title"] == "Banking Knowledge Agent"


def test_unknown_route_returns_404(client):
    assert client.get("/does-not-exist").status_code == 404


def test_app_stores_settings_on_state(app, settings):
    assert app.state.settings is settings
