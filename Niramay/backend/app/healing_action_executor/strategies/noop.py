"""
No-op Strategy

Used when recommended action is none.
Returns success immediately without doing anything.
"""
import structlog
from typing import Dict, Any
from app.healing_action_executor.strategies.base import (
    BaseHealingStrategy
)

logger = structlog.get_logger(__name__)


class NoopStrategy(BaseHealingStrategy):

    async def execute(
        self,
        machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(
            "NoopStrategy: no action required",
            service=machine_alert.get("service"),
            alert_id=machine_alert.get("alert_id"),
        )
        return self._success(
            healing_action="none",
            message="No healing action required.",
            service=machine_alert.get("service"),
            container_restarted=None,
            scenarios_disabled=[],
        )
