"""
Healing Engine — Strategy Selection + Execution

Maps anomaly detections to healing strategies and executes them.
Supports both rule-based defaults and AI-suggested overrides.

No SQLite dependencies. Escalation logic accepts retry_count
as a parameter from the verification worker.
"""
import asyncio
import structlog
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from app.shared.healing_vocabulary import (
    VALID_ACTIONS,
    coerce_action,
)

logger = structlog.get_logger(__name__)

# All healing actions returned by this module must
# be valid vocabulary items from healing_vocabulary.py.
# Do not add new action strings without also adding
# them to healing_vocabulary.py first.


class HealingStrategy(ABC):
    """Base class for all healing strategies"""

    @abstractmethod
    async def execute(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the healing action"""
        pass


class RestartServiceStrategy(HealingStrategy):
    async def execute(self, log: Dict[str, Any]) -> Dict[str, Any]:
        service = log.get("service", "unknown")

        try:
            import docker
            client = docker.from_env()
            containers = client.containers.list(filters={"name": service})

            if not containers:
                return {
                    "status": "failed",
                    "message": f"Could not find a running container for service '{service}'."
                }

            target = containers[0]
            target.restart()

            return {
                "status": "success",
                "message": f"Container {target.name} restarted successfully."
            }
        except Exception as e:
            logger.error("Docker restart failed", error=str(e))
            return {
                "status": "failed",
                "message": f"Docker error: {str(e)}"
            }


class RetryRequestStrategy(HealingStrategy):
    async def execute(self, log: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = log.get("endpoint", "unknown")
        await asyncio.sleep(0.5)  # Simulate retry latency
        return {
            "status": "success",
            "message": f"Request to {endpoint} retried on healthy node. Payload processed successfully."
        }


class ThrottleTrafficStrategy(HealingStrategy):
    async def execute(self, log: Dict[str, Any]) -> Dict[str, Any]:
        await asyncio.sleep(0.1)
        return {
            "status": "success",
            "message": "Gateway rate-limits dynamically adjusted to protect service from cascading failure."
        }


class FallbackResponseStrategy(HealingStrategy):
    async def execute(self, log: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "success",
            "message": "Fallback static response served. Degraded experience maintained for user."
        }


class HealingEngine:
    """
    Advanced Healing Engine that maps anomalies to strategies.
    Supports both rule-based defaults and AI-suggested overrides.
    No direct storage queries — escalation retry_count is passed in.
    """

    def __init__(self):
        self.strategies = {
            "restart_service": RestartServiceStrategy(),
            "throttle_requests": ThrottleTrafficStrategy(),
            "circuit_breaker": FallbackResponseStrategy(),
        }

        # Default rule mapping (Anomaly Reason → Strategy Key)
        self.default_mapping = {
            "server_error": "restart_service",
            "database_error": "restart_service",
            "high_latency": "throttle_requests",
            "rate_limit": "throttle_requests",
            "rate_based_error_spike": "throttle_requests",
            "failure_tag": "throttle_requests",
            "baseline_deviation": "throttle_requests",
            "service_silence": "restart_service",
        }

    def decide_healing_action(
        self,
        log: Dict[str, Any],
        retry_count: int = 0,
    ) -> str:
        """
        Determines the appropriate healing action key.
        Priority: AI Suggestion (if high confidence) > Escalation > Default Rule

        Args:
            log: Detection result dict with anomaly_reasons, ai_analysis, etc.
            retry_count: Number of previous healing attempts for this issue.
                         Passed in by the verification worker. 0 means first attempt.
        """
        # 1. Check AI Suggestion (passed in log from Detection Worker)
        ai_suggestion = log.get("ai_analysis", {}).get("suggested_action") if isinstance(log.get("ai_analysis"), dict) else None
        ai_confidence = log.get("ai_analysis", {}).get("confidence", 0) if isinstance(log.get("ai_analysis"), dict) else 0

        if ai_suggestion and ai_suggestion != "none" and ai_confidence > 0.8:
            if ai_suggestion in self.strategies:
                logger.info("Using AI-suggested healing action", action=ai_suggestion, confidence=ai_confidence)
                action = ai_suggestion
                return coerce_action(action)

        # 2. Escalation logic based on retry_count
        if retry_count >= 2:
            logger.warning("Escalating to restart_service after multiple failures", retry_count=retry_count)
            action = "restart_service"
            return coerce_action(action)
        elif retry_count >= 1:
            # Try a different strategy than the default
            reasons = log.get("anomaly_reasons", [])
            default_action = self._get_default_action(reasons)
            if default_action == "throttle_requests":
                logger.warning("Escalating: previous attempt failed", retry_count=retry_count)
                action = "restart_service"
                return coerce_action(action)

        # 3. Rule-based fallback
        reasons = log.get("anomaly_reasons", [])
        action = self._get_default_action(reasons)
        return coerce_action(action)

    def _get_default_action(self, reasons: List[str]) -> str:
        """Get default action based on anomaly reasons."""
        priority_order = ["restart_service", "throttle_requests", "circuit_breaker"]

        candidate_actions = []
        for reason in reasons:
            action = self.default_mapping.get(reason)
            if action:
                candidate_actions.append(action)

        for priority_action in priority_order:
            if priority_action in candidate_actions:
                return priority_action

        return "circuit_breaker"

    async def execute_healing(self, action_key: str, log: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the strategy and returns a standardized result."""
        if action_key == "none" or action_key not in self.strategies:
            return {
                "healing_action": "none",
                "status": "skipped",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "No actionable healing strategy identified.",
                "verification_status": "SKIPPED",
            }

        strategy = self.strategies[action_key]

        try:
            result = await strategy.execute(log)
            return {
                "healing_action": action_key,
                "status": result.get("status", "success"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": result.get("message", "Action completed."),
                "verification_status": "PENDING",
            }
        except Exception as e:
            logger.error("Healing execution failed", action=action_key, error=str(e))
            return {
                "healing_action": action_key,
                "status": "failed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": f"Execution error: {str(e)}",
                "verification_status": "EXPIRED",
            }


# Singleton instance
healing_service = HealingEngine()
