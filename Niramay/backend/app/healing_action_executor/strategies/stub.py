"""
Stub Strategy for Phase 2 actions

Placeholder for actions that require Kubernetes
and will be implemented in Phase 2:
    scale_up
    rollback_deployment
    throttle_requests
    flush_cache
    circuit_breaker

Returns a clear message that the action is not
yet implemented and escalates automatically.
"""
import structlog
from typing import Dict, Any
from app.healing_action_executor.strategies.base import (
    BaseHealingStrategy
)

logger = structlog.get_logger(__name__)


class StubStrategy(BaseHealingStrategy):
    """
    Stub for Phase 2 healing actions.
    Returns failed status so the verification worker
    will escalate after max retries.
    """

    def __init__(self, action_name: str):
        self.action_name = action_name

    async def execute(
        self,
        machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.warning(
            f"StubStrategy: {self.action_name} is not "
            f"yet implemented (Phase 2)",
            service=machine_alert.get("service"),
            alert_id=machine_alert.get("alert_id"),
        )
        return self._failure(
            healing_action=self.action_name,
            message=f"{self.action_name} requires "
                    f"Kubernetes and will be implemented "
                    f"in Phase 2.",
            error=f"Not implemented in Phase 1. "
                  f"Action {self.action_name} escalated.",
            service=machine_alert.get("service"),
            container_restarted=None,
            scenarios_disabled=[],
        )
