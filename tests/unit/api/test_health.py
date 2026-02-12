"""
Tests for health endpoint.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app


@pytest.fixture
def client():
    """Create test client (runs lifespan for app.state)."""
    with TestClient(app) as tc:
        yield tc


def test_health_returns_correct_structure(client):
    """GET /health returns JSON with all required status fields."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    # All required fields present
    assert "status" in data
    assert "neo4j_connected" in data
    assert "wal_backlog_depth" in data
    assert "circuit_breaker_state" in data
    assert "uptime_seconds" in data

    # Types
    assert isinstance(data["status"], str)
    assert data["status"] in ("healthy", "degraded")
    assert isinstance(data["neo4j_connected"], bool)
    assert isinstance(data["wal_backlog_depth"], int)
    assert isinstance(data["circuit_breaker_state"], str)
    assert isinstance(data["uptime_seconds"], (int, float))


def test_health_circuit_breaker_state_valid(client):
    """Circuit breaker state is CLOSED, OPEN, or HALF_OPEN."""
    response = client.get("/health")
    assert response.status_code == 200
    state = response.json()["circuit_breaker_state"]
    assert state in ("CLOSED", "OPEN", "HALF_OPEN", "UNKNOWN")


def test_cors_headers_present(client):
    """CORS headers present for configured origins."""
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    # CORS middleware adds Access-Control-Allow-Origin when Origin matches
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin == "http://localhost:3000"
