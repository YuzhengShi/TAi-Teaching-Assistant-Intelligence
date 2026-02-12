"""
Tests for rate limit middleware.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app


@pytest.fixture
def client():
    """Create test client (runs lifespan for app.state)."""
    with TestClient(app) as tc:
        yield tc


def test_rate_limiter_returns_429_after_threshold(client):
    """Rate limiter returns 429 with Retry-After after threshold exceeded."""
    # Root "/" is rate limited. Use X-Rate-Limit-Key for consistent client ID (TestClient has no IP)
    headers = {"X-Rate-Limit-Key": "test-student-001"}
    # Default: 30 requests/minute. Make 31 requests from same key
    for i in range(31):
        response = client.get("/", headers=headers)
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after") or response.headers.get("Retry-After")
            assert retry_after is not None
            return  # Pass: got 429 as expected
    pytest.fail("Expected 429 after 31 requests, all succeeded")
