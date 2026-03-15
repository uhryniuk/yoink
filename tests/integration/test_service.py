"""Integration tests for the FastAPI service."""

import json

import pytest
from fastapi.testclient import TestClient

from yoink.service.app import create_app


@pytest.fixture()
def client(test_config):
    app = create_app(test_config)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def authed_client(authed_config):
    app = create_app(authed_config)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def key_headers():
    return {"X-API-Key": "test-secret"}


# -- /health ------------------------------------------------------------------


def test_health_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_bypasses_auth(authed_client):
    """Health endpoint works without a key."""
    r = authed_client.get("/health")
    assert r.status_code == 200


# -- auth middleware ----------------------------------------------------------


def test_missing_key_rejected(authed_client):
    r = authed_client.post("/extract", json={"url": "http://x.com"})
    assert r.status_code == 401


def test_wrong_key_rejected(authed_client):
    r = authed_client.post("/extract", json={"url": "http://x.com"},
                           headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_correct_key_accepted(authed_client, local_server, key_headers):
    r = authed_client.post("/extract",
                           json={"url": local_server + "/", "timeout": 15.0},
                           headers=key_headers)
    assert r.status_code == 200


# -- /config ------------------------------------------------------------------


def test_config_returns_structure(client, local_server):
    r = client.get("/config")
    assert r.status_code == 200
    data = r.json()
    assert "workers" in data
    assert "rate_limit" in data
    assert "service" in data
    assert "log" in data


def test_config_redacts_api_key(authed_client, key_headers):
    r = authed_client.get("/config", headers=key_headers)
    assert r.json()["service"]["api_key"] == "***"


def test_config_no_key_shows_null(client):
    r = client.get("/config")
    assert r.json()["service"]["api_key"] is None


# -- /extract -----------------------------------------------------------------


def test_extract_returns_html(client, local_server):
    r = client.post("/extract", json={"url": local_server + "/", "timeout": 15.0})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "Yoink Test Page" in body["html"]
    assert body["duration_ms"] > 0
    assert body["error"] is None


def test_extract_clean_html(client, local_server):
    r = client.post("/extract", json={
        "url": local_server + "/",
        "clean_html": True,
        "timeout": 15.0,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"]
    assert "<script>" not in body["html"]


def test_extract_bad_url_returns_error_not_500(client):
    r = client.post("/extract", json={
        "url": "http://127.0.0.1:1/",
        "timeout": 3.0,
        "retry": {"max_attempts": 1},
    })
    assert r.status_code == 200  # we return result, not 5xx
    body = r.json()
    assert body["ok"] is False
    assert body["error"] is not None


# -- /extract/batch -----------------------------------------------------------


def test_batch_streams_ndjson(client, local_server):
    payload = [
        {"url": local_server + "/", "timeout": 15.0},
        {"url": local_server + "/", "timeout": 15.0},
    ]
    r = client.post("/extract/batch", json=payload)
    assert r.status_code == 200

    lines = [json.loads(l) for l in r.text.strip().splitlines() if l]
    assert len(lines) == 2
    assert all(l["ok"] for l in lines)


def test_batch_empty_list(client):
    r = client.post("/extract/batch", json=[])
    assert r.status_code == 200
    assert r.text.strip() == ""


# -- /status ------------------------------------------------------------------


def test_status_structure(client):
    r = client.get("/status")
    assert r.status_code == 200
    data = r.json()
    assert "workers" in data
    assert "queue_size" in data
    assert "total_processed" in data
    assert "avg_duration_ms" in data
    assert "uptime_secs" in data


def test_status_counts_processed(client, local_server):
    client.post("/extract", json={"url": local_server + "/", "timeout": 15.0})
    client.post("/extract", json={"url": local_server + "/", "timeout": 15.0})
    r = client.get("/status")
    assert r.json()["total_processed"] == 2
