"""
Tests for HealingActionExecutor (Component A)
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


SAMPLE_ALERT = {
    "alert_id": "alert-exec-001",
    "detection_id": "det-exec-001",
    "service": "crave-payments",
    "endpoint": "/api/v1/payments",
    "severity": "high",
    "recommended_action": "restart_service",
    "failure_tag": "database_error",
    "timestamp": "2024-01-15T10:30:00Z",
}


@pytest.mark.asyncio
async def test_executor_routes_restart_service():
    """Executor routes restart_service to RestartServiceStrategy."""
    from app.healing_action_executor.executor import HealingActionExecutor

    mock_result = {
        "healing_action": "restart_service",
        "status": "success",
        "message": "Container restarted",
        "error": None,
        "executed_at": "2024-01-15T10:30:01Z",
        "service": "crave-payments",
        "container_restarted": "crave-backend",
        "scenarios_disabled": [],
    }

    with patch(
        "app.healing_action_executor.executor"
        "._STRATEGY_REGISTRY",
        {
            "restart_service": AsyncMock(
                execute=AsyncMock(return_value=mock_result)
            )
        }
    ):
        executor = HealingActionExecutor()
        result = await executor.execute(SAMPLE_ALERT)

    assert result["healing_action"] == "restart_service"
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_executor_routes_escalate_only():
    """Executor routes escalate_only and returns success."""
    from app.healing_action_executor.executor import HealingActionExecutor

    alert = {**SAMPLE_ALERT, "recommended_action": "escalate_only"}
    executor = HealingActionExecutor()
    result = await executor.execute(alert)

    assert result["status"] == "success"
    assert "escalated for human review" in result["message"]


@pytest.mark.asyncio
async def test_executor_routes_noop():
    """Executor routes none action and returns success."""
    from app.healing_action_executor.executor import HealingActionExecutor

    alert = {**SAMPLE_ALERT, "recommended_action": "none"}
    executor = HealingActionExecutor()
    result = await executor.execute(alert)

    assert result["status"] == "success"
    assert "No healing action required" in result["message"]


@pytest.mark.asyncio
async def test_executor_routes_stub_for_phase2_actions():
    """Phase 2 actions return failed with Phase 2 message."""
    from app.healing_action_executor.executor import HealingActionExecutor

    phase2_actions = [
        "throttle_requests",
        "flush_cache",
        "scale_up",
        "circuit_breaker",
        "rollback_deployment",
    ]
    executor = HealingActionExecutor()

    for action in phase2_actions:
        alert = {**SAMPLE_ALERT, "recommended_action": action}
        result = await executor.execute(alert)
        assert result["status"] == "failed", (
            f"{action} should return failed"
        )
        assert "Phase 2" in result["message"], (
            f"{action} message should mention Phase 2"
        )


@pytest.mark.asyncio
async def test_executor_coerces_invalid_action():
    """Unknown action is coerced to escalate_only."""
    from app.healing_action_executor.executor import HealingActionExecutor

    alert = {**SAMPLE_ALERT, "recommended_action": "reboot_everything"}
    executor = HealingActionExecutor()
    result = await executor.execute(alert)

    # coerce_action defaults to escalate_only
    assert result["healing_action"] == "escalate_only"


@pytest.mark.asyncio
async def test_executor_returns_failure_on_timeout():
    """Executor returns failed dict when strategy times out."""
    from app.healing_action_executor.executor import HealingActionExecutor
    from app.core.config import settings

    async def slow_execute(_):
        await asyncio.sleep(settings.COMPONENT_A_TIMEOUT_SECONDS + 5)

    mock_strategy = MagicMock()
    mock_strategy.execute = slow_execute

    with patch(
        "app.healing_action_executor.executor._STRATEGY_REGISTRY",
        {"restart_service": mock_strategy}
    ):
        with patch.object(settings, "COMPONENT_A_TIMEOUT_SECONDS", 0):
            executor = HealingActionExecutor()
            result = await executor.execute(SAMPLE_ALERT)

    assert result["status"] == "failed"
    assert result["error"] == "Timeout"


@pytest.mark.asyncio
async def test_executor_never_raises():
    """Executor returns failed dict instead of raising."""
    from app.healing_action_executor.executor import HealingActionExecutor

    async def boom(_):
        raise RuntimeError("Unexpected crash")

    mock_strategy = MagicMock()
    mock_strategy.execute = boom

    with patch(
        "app.healing_action_executor.executor._STRATEGY_REGISTRY",
        {"restart_service": mock_strategy}
    ):
        executor = HealingActionExecutor()
        result = await executor.execute(SAMPLE_ALERT)

    assert result["status"] == "failed"
    assert "Unexpected crash" in result["error"]
