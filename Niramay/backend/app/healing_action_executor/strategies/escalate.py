"""
Escalate Only Strategy

Used when no automated healing action is appropriate.
Logs the alert details and returns immediately.
The dispatcher will push to escalation:alerts.
"""
import structlog
from typing import Dict, Any
from app.healing_action_executor.strategies.base import (
    BaseHealingStrategy
)

logger = structlog.get_logger(__name__)


class EscalateOnlyStrategy(BaseHealingStrategy):

    async def execute(
        self,
        machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(
            "EscalateOnlyStrategy: no automated action, "
            "human intervention required",
            service=machine_alert.get("service"),
            severity=machine_alert.get("severity"),
            alert_id=machine_alert.get("alert_id"),
        )
        return self._success(
            healing_action="escalate_only",
            message="No automated action taken. "
                    "Alert escalated for human review.",
            service=machine_alert.get("service"),
            container_restarted=None,
            scenarios_disabled=[],
        )
