"""
Tests for the /api/v1/pipeline/stage endpoint.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_pipeline_stage_endpoint_returns_idle_when_empty(client):
    """Returns idle stage dict when Redis has no pipeline key."""
    with patch(
        "app.api.v1.endpoints.redis_client"
    ) as mock_redis:
        mock_redis.get.return_value = None
        response = client.get("/api/v1/pipeline/stage")

    assert response.status_code == 200
    data = response.json()
    assert data["stage"] == "idle"
    assert "message" in data


def test_pipeline_stage_endpoint_returns_current_stage(client):
    """Returns current stage dict when Redis has pipeline key."""
    stage_data = {
        "stage": "stage_2_complete",
        "message": "Anomaly detected, analysis starting",
        "timestamp": "2024-01-15T10:30:00Z",
        "service": "crave-payments",
    }

    with patch(
        "app.api.v1.endpoints.redis_client"
    ) as mock_redis:
        mock_redis.get.return_value = json.dumps(stage_data)
        response = client.get("/api/v1/pipeline/stage")

    assert response.status_code == 200
    data = response.json()
    assert data["stage"] == "stage_2_complete"
    assert "Anomaly detected" in data["message"]
