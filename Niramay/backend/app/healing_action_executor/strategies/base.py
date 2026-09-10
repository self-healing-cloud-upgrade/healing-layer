"""
Base strategy interface for all healing actions.
Every strategy must implement this interface.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseHealingStrategy(ABC):
    """
    Abstract base class for all healing strategies.

    Every strategy receives the full machine alert
    and returns a standardized result dict.

    Result dict must always contain:
        healing_action: str (vocabulary action name)
        status: "success" | "failed"
        message: str (human readable outcome)
        error: str | None (error detail if failed)
        executed_at: str (ISO8601 timestamp)
    """

    @abstractmethod
    async def execute(
        self,
        machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute the healing action.

        Never raises exceptions.
        Always returns a result dict.
        Always sets status to success or failed.
        """
        pass

    def _success(
        self,
        healing_action: str,
        message: str,
        **extra
    ) -> Dict[str, Any]:
        from datetime import datetime, timezone
        return {
            "healing_action": healing_action,
            "status": "success",
            "message": message,
            "error": None,
            "executed_at": datetime.now(
                timezone.utc).isoformat(),
            **extra
        }

    def _failure(
        self,
        healing_action: str,
        message: str,
        error: str,
        **extra
    ) -> Dict[str, Any]:
        from datetime import datetime, timezone
        return {
            "healing_action": healing_action,
            "status": "failed",
            "message": message,
            "error": error,
            "executed_at": datetime.now(
                timezone.utc).isoformat(),
            **extra
        }
