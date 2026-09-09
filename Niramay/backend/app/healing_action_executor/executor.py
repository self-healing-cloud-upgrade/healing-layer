"""
Healing Action Executor

Main Component A class. Receives a machine alert
from the Dispatcher Worker and executes the
appropriate healing strategy.

This is the single entry point for all healing
execution. The Dispatcher Worker calls
HealingActionExecutor.execute() and receives back
a standardized result dict.

Strategy routing:
    restart_service   → RestartServiceStrategy
                        (uses K3s rolling restart when K3S_ENABLED,
                         Docker socket restart otherwise)
    escalate_only     → EscalateOnlyStrategy
    none              → NoopStrategy

    When K3S_ENABLED=true (K3s cluster available):
        throttle_requests   → K3sThrottleStrategy
        flush_cache         → K3sFlushCacheStrategy
        scale_up            → K3sScaleUpStrategy
        circuit_breaker     → K3sCircuitBreakerStrategy
        rollback_deployment → K3sRollbackStrategy

    When K3S_ENABLED=false (Docker Compose / no cluster):
        (all above)         → StubStrategy (returns failed)

All strategies return the same result dict structure.
The executor never raises exceptions.
"""
import asyncio
import structlog
from typing import Dict, Any
from app.shared.healing_vocabulary import (
    VALID_ACTIONS,
    coerce_action,
)
from app.healing_action_executor.strategies.restart import (
    RestartServiceStrategy,
)
from app.healing_action_executor.strategies.escalate import (
    EscalateOnlyStrategy,
)
from app.healing_action_executor.strategies.noop import (
    NoopStrategy,
)
from app.healing_action_executor.strategies.stub import (
    StubStrategy,
)
from app.core.config import settings

logger = structlog.get_logger(__name__)

# ── Strategy registry ─────────────────────────────────────────────────────
# Core strategies (always available, regardless of K3S_ENABLED)
_STRATEGY_REGISTRY: Dict[str, Any] = {
    "restart_service": RestartServiceStrategy(),
    "escalate_only": EscalateOnlyStrategy(),
    "none": NoopStrategy(),
}

# K3s strategies (only when K3S_ENABLED=true and cluster is reachable)
if settings.K3S_ENABLED:
    try:
        from app.healing_action_executor.strategies.k3s_scale_up import (
            K3sScaleUpStrategy,
        )
        from app.healing_action_executor.strategies.k3s_rollback import (
            K3sRollbackStrategy,
        )
        from app.healing_action_executor.strategies.k3s_throttle import (
            K3sThrottleStrategy,
        )
        from app.healing_action_executor.strategies.k3s_circuit_breaker import (
            K3sCircuitBreakerStrategy,
        )
        from app.healing_action_executor.strategies.k3s_flush_cache import (
            K3sFlushCacheStrategy,
        )
        _STRATEGY_REGISTRY.update({
            "scale_up": K3sScaleUpStrategy(),
            "rollback_deployment": K3sRollbackStrategy(),
            "throttle_requests": K3sThrottleStrategy(),
            "circuit_breaker": K3sCircuitBreakerStrategy(),
            "flush_cache": K3sFlushCacheStrategy(),
        })
        logger.info(
            "HealingActionExecutor: K3s strategies loaded "
            "(K3S_ENABLED=true)"
        )
    except ImportError as e:
        logger.warning(
            "HealingActionExecutor: K3S_ENABLED=true but "
            "K3s strategy import failed — falling back to stubs",
            error=str(e),
        )
        _STRATEGY_REGISTRY.update({
            "throttle_requests": StubStrategy("throttle_requests"),
            "flush_cache": StubStrategy("flush_cache"),
            "scale_up": StubStrategy("scale_up"),
            "circuit_breaker": StubStrategy("circuit_breaker"),
            "rollback_deployment": StubStrategy("rollback_deployment"),
        })
else:
    # Docker Compose mode — stubs for all K3s actions
    # These return status="failed" so the verification worker
    # escalates after max retries. This is the existing behavior.
    _STRATEGY_REGISTRY.update({
        "throttle_requests": StubStrategy("throttle_requests"),
        "flush_cache": StubStrategy("flush_cache"),
        "scale_up": StubStrategy("scale_up"),
        "circuit_breaker": StubStrategy("circuit_breaker"),
        "rollback_deployment": StubStrategy("rollback_deployment"),
    })


class HealingActionExecutor:
    """
    Main Component A executor.

    Receives machine alert from Dispatcher Worker.
    Routes to correct strategy based on
    recommended_action field.
    Returns standardized result dict.

    Never raises exceptions. If anything unexpected
    happens, returns a failed result with clear error.
    """

    async def execute(
        self,
        machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute the healing action for the given alert.

        Args:
            machine_alert: The full machine alert dict
                from the Analyser Worker. Must contain
                recommended_action field.

        Returns:
            Result dict with at minimum:
                healing_action: str
                status: "success" | "failed"
                message: str
                error: str | None
                executed_at: ISO8601 str
        """
        alert_id = machine_alert.get("alert_id", "unknown")

        # Get and validate the recommended action
        raw_action = machine_alert.get(
            "recommended_action", "none"
        )
        action = coerce_action(raw_action)

        if action != raw_action:
            logger.warning(
                "HealingActionExecutor: action coerced "
                "to vocabulary value",
                original=raw_action,
                coerced=action,
                alert_id=alert_id
            )

        logger.info(
            "HealingActionExecutor: executing",
            action=action,
            service=machine_alert.get("service"),
            severity=machine_alert.get("severity"),
            alert_id=alert_id,
        )

        # Get the strategy
        strategy = _STRATEGY_REGISTRY.get(action)
        if strategy is None:
            # Should never happen if coerce_action works
            # but handle defensively
            logger.error(
                "HealingActionExecutor: no strategy "
                "found for action",
                action=action,
                alert_id=alert_id,
            )
            from datetime import datetime, timezone
            return {
                "healing_action": action,
                "status": "failed",
                "message": f"No strategy registered "
                           f"for action: {action}",
                "error": "Missing strategy",
                "executed_at": datetime.now(
                    timezone.utc).isoformat(),
                "service": machine_alert.get("service"),
                "container_restarted": None,
                "scenarios_disabled": [],
            }

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                strategy.execute(machine_alert),
                timeout=settings.COMPONENT_A_TIMEOUT_SECONDS
            )
            logger.info(
                "HealingActionExecutor: complete",
                action=action,
                status=result.get("status"),
                alert_id=alert_id,
            )
            return result

        except asyncio.TimeoutError:
            logger.error(
                "HealingActionExecutor: execution timed out",
                action=action,
                timeout=settings.COMPONENT_A_TIMEOUT_SECONDS,
                alert_id=alert_id,
            )
            from datetime import datetime, timezone
            return {
                "healing_action": action,
                "status": "failed",
                "message": f"Healing action timed out "
                           f"after "
                           f"{settings.COMPONENT_A_TIMEOUT_SECONDS}s",
                "error": "Timeout",
                "executed_at": datetime.now(
                    timezone.utc).isoformat(),
                "service": machine_alert.get("service"),
                "container_restarted": None,
                "scenarios_disabled": [],
            }
        except Exception as e:
            logger.error(
                "HealingActionExecutor: unexpected error",
                action=action,
                error=str(e),
                alert_id=alert_id,
            )
            from datetime import datetime, timezone
            return {
                "healing_action": action,
                "status": "failed",
                "message": "Unexpected error during healing",
                "error": str(e),
                "executed_at": datetime.now(
                    timezone.utc).isoformat(),
                "service": machine_alert.get("service"),
                "container_restarted": None,
                "scenarios_disabled": [],
            }


# Singleton instance for use by Dispatcher Worker
healing_executor = HealingActionExecutor()
