"""
Tests for Dispatcher Worker: Alert Dispatch Skeleton
"""
import asyncio
import pytest
import json
from unittest.mock import AsyncMock, patch

SAMPLE_ALERT = {
    "alert_id": "alert-001",
    "detection_id": "det-001",
    "severity": "high",
    "service": "order-service",
    "endpoint": "/api/orders",
    "healing_action": "restart_service",
    "failure_tag": "database_error",
    "timestamp": "2024-01-15T10:30:00Z",
    "verification_status": "PENDING",
}


@pytest.mark.asyncio
async def test_dispatcher_worker_consumes_from_queue():
    """Dispatcher Worker pops from dispatcher:pending queue"""
    from app.dispatcher.worker import dispatcher_worker_loop
    mock_redis = AsyncMock()
    mock_redis.brpop.return_value = (
        "dispatcher:pending",
        json.dumps(SAMPLE_ALERT)
    )
    with patch("app.dispatcher.worker.get_async_redis",
               return_value=mock_redis):
        with patch("app.dispatcher.worker._handle_dispatcher",
                   new_callable=AsyncMock) as mock_handle:
            mock_handle.side_effect = asyncio.CancelledError
            try:
                await dispatcher_worker_loop()
            except asyncio.CancelledError:
                pass
            mock_handle.assert_called_once()


@pytest.mark.asyncio
async def test_dispatcher_calls_component_a_placeholder():
    """Dispatcher Worker calls _execute_healing for every alert."""
    from app.dispatcher.worker import _handle_dispatcher
    mock_redis = AsyncMock()

    with patch("app.dispatcher.worker._execute_healing",
               new_callable=AsyncMock,
               return_value={
                   "healing_action": "restart_service",
                   "status": "success",
                   "message": "Container restarted",
                   "error": None,
                   "executed_at": "2024-01-15T10:30:01Z",
                   "scenarios_disabled": [],
                   "container_restarted": "crave-backend",
                   "heal_endpoint_called": False,
               }) as mock_a:
        await _handle_dispatcher(mock_redis, SAMPLE_ALERT)
        mock_a.assert_called_once_with(SAMPLE_ALERT)


@pytest.mark.asyncio
async def test_dispatcher_pushes_healing_record_to_redis():
    """Dispatcher Worker pushes healing record to
    healing:actions"""
    from app.dispatcher.worker import _handle_dispatcher
    mock_redis = AsyncMock()

    with patch("app.dispatcher.worker._send_to_component_a",
               new_callable=AsyncMock,
               return_value={
                   "healing_action": "restart_service",
                   "status": "pending",
                   "message": "placeholder",
                   "verification_status": "PENDING",
               }):
        await _handle_dispatcher(mock_redis, SAMPLE_ALERT)
        call_args = mock_redis.lpush.call_args_list
        keys_pushed = [c[0][0] for c in call_args]
        assert "healing:actions" in keys_pushed


@pytest.mark.asyncio
async def test_dispatcher_healing_record_has_required_fields():
    """Dispatcher Worker healing record contains detection_id,
    service, endpoint and verification_status"""
    from app.dispatcher.worker import _handle_dispatcher
    mock_redis = AsyncMock()
    captured = {}

    async def fake_push(key, value):
        if key == "healing:actions":
            captured["record"] = json.loads(value)

    mock_redis.lpush = AsyncMock(side_effect=fake_push)
    mock_redis.ltrim = AsyncMock()

    with patch("app.dispatcher.worker._send_to_component_a",
               new_callable=AsyncMock,
               return_value={
                   "healing_action": "restart_service",
                   "status": "pending",
                   "message": "placeholder",
                   "verification_status": "PENDING",
               }):
        await _handle_dispatcher(mock_redis, SAMPLE_ALERT)
        record = captured.get("record", {})
        assert record.get("detection_id") == "det-001"
        assert record.get("service") == "order-service"
        assert record.get("endpoint") == "/api/orders"
        assert record.get(
            "verification_status") == "PENDING"
