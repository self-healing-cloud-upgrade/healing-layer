"""
Tests for RestartServiceStrategy
"""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


SAMPLE_ALERT = {
    "alert_id": "alert-restart-001",
    "detection_id": "det-restart-001",
    "service": "crave-payments",
    "endpoint": "/api/v1/payments",
    "severity": "high",
    "recommended_action": "restart_service",
    "failure_tag": "database_error",
    "timestamp": "2024-01-15T10:30:00Z",
}


def test_resolve_container_name_crave_service():
    """crave- service maps to crave-backend."""
    from app.healing_action_executor.strategies.restart import (
        _resolve_container_name,
    )
    result = _resolve_container_name("crave-payments")
    assert result == "crave-backend"


def test_resolve_container_name_unknown_service():
    """Unknown service returns None."""
    from app.healing_action_executor.strategies.restart import (
        _resolve_container_name,
    )
    result = _resolve_container_name("unknown-service")
    assert result is None


def test_resolve_container_name_case_insensitive():
    """Container resolution is case-insensitive."""
    from app.healing_action_executor.strategies.restart import (
        _resolve_container_name,
    )
    result = _resolve_container_name("CRAVE-orders")
    assert result == "crave-backend"


@pytest.mark.asyncio
async def test_restart_strategy_returns_failure_no_mapping():
    """Strategy returns failure when service has no container mapping."""
    from app.healing_action_executor.strategies.restart import (
        RestartServiceStrategy,
    )
    alert = {**SAMPLE_ALERT, "service": "unknown-service"}
    strategy = RestartServiceStrategy()
    result = await strategy.execute(alert)

    assert result["status"] == "failed"
    assert result["container_restarted"] is None


@pytest.mark.asyncio
async def test_restart_strategy_success_when_all_steps_pass():
    """Strategy succeeds when heal endpoint and Docker restart both work."""
    from app.healing_action_executor.strategies.restart import (
        RestartServiceStrategy,
    )

    mock_restart = MagicMock(return_value={
        "success": True,
        "container": "crave-backend",
        "message": "Restarted",
        "error": None,
    })

    with patch(
        "app.healing_action_executor.strategies.restart"
        "._get_crave_auth_token",
        new_callable=AsyncMock,
        return_value="fake_token"
    ):
        with patch(
            "app.healing_action_executor.strategies.restart"
            "._call_crave_heal_endpoint",
            new_callable=AsyncMock,
            return_value={
                "success": True,
                "scenarios_disabled": ["database_error"],
            }
        ):
            with patch(
                "app.healing_action_executor.strategies.restart"
                ".restart_container",
                mock_restart
            ):
                strategy = RestartServiceStrategy()
                result = await strategy.execute(SAMPLE_ALERT)

    assert result["status"] == "success"
    assert result["container_restarted"] == "crave-backend"
    assert isinstance(result["scenarios_disabled"], list)


@pytest.mark.asyncio
async def test_restart_strategy_proceeds_if_heal_endpoint_fails():
    """Strategy still succeeds if heal endpoint fails but Docker restart works."""
    from app.healing_action_executor.strategies.restart import (
        RestartServiceStrategy,
    )

    mock_restart = MagicMock(return_value={
        "success": True,
        "container": "crave-backend",
        "message": "Restarted",
        "error": None,
    })

    with patch(
        "app.healing_action_executor.strategies.restart"
        "._get_crave_auth_token",
        new_callable=AsyncMock,
        return_value="fake_token"
    ):
        with patch(
            "app.healing_action_executor.strategies.restart"
            "._call_crave_heal_endpoint",
            new_callable=AsyncMock,
            return_value={
                "success": False,
                "scenarios_disabled": [],
                "error": "endpoint down",
            }
        ):
            with patch(
                "app.healing_action_executor.strategies.restart"
                ".restart_container",
                mock_restart
            ):
                strategy = RestartServiceStrategy()
                result = await strategy.execute(SAMPLE_ALERT)

    # Docker restart worked, so overall success
    assert result["status"] == "success"
    assert result["scenarios_disabled"] == []


@pytest.mark.asyncio
async def test_restart_strategy_fails_if_docker_restart_fails():
    """Strategy fails when Docker restart fails."""
    from app.healing_action_executor.strategies.restart import (
        RestartServiceStrategy,
    )

    mock_restart = MagicMock(return_value={
        "success": False,
        "container": "crave-backend",
        "message": "Failed",
        "error": "container not found",
    })

    with patch(
        "app.healing_action_executor.strategies.restart"
        "._get_crave_auth_token",
        new_callable=AsyncMock,
        return_value="fake_token"
    ):
        with patch(
            "app.healing_action_executor.strategies.restart"
            "._call_crave_heal_endpoint",
            new_callable=AsyncMock,
            return_value={"success": True, "scenarios_disabled": []}
        ):
            with patch(
                "app.healing_action_executor.strategies.restart"
                ".restart_container",
                mock_restart
            ):
                strategy = RestartServiceStrategy()
                result = await strategy.execute(SAMPLE_ALERT)

    assert result["status"] == "failed"
    assert result["container_restarted"] is None


def test_crave_heal_enabled_flag_is_true():
    """CRAVE_HEAL_ENABLED must be True — CRAVE confirmed reachable and heal endpoint returns 200."""
    from app.healing_action_executor.strategies import restart
    assert restart.CRAVE_HEAL_ENABLED is True, (
        "CRAVE_HEAL_ENABLED must be True now that "
        "CRAVE is confirmed reachable and heal endpoint returns 200"
    )


@pytest.mark.asyncio
async def test_restart_strategy_proceeds_if_no_auth_token():
    """Strategy succeeds with restart even when no auth token available."""
    from app.healing_action_executor.strategies.restart import (
        RestartServiceStrategy,
    )

    mock_restart = MagicMock(return_value={
        "success": True,
        "container": "crave-backend",
        "message": "Restarted",
        "error": None,
    })

    with patch(
        "app.healing_action_executor.strategies.restart"
        "._get_crave_auth_token",
        new_callable=AsyncMock,
        return_value=None
    ):
        with patch(
            "app.healing_action_executor.strategies.restart"
            ".restart_container",
            mock_restart
        ):
            strategy = RestartServiceStrategy()
            result = await strategy.execute(SAMPLE_ALERT)

    assert result["status"] == "success"
    assert result["heal_endpoint_called"] is False
