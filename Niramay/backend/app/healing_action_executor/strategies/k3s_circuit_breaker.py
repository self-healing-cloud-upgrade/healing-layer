"""
K3s Circuit Breaker Strategy
==============================

Implements the `circuit_breaker` healing action for K3s clusters.

Mechanism:
    Two-part circuit breaker implementation:
    1. Write Redis signal so CRAVE middleware returns
       503 with fallback message instead of crashing
    2. Scale to minimum 1 replica (NOT zero — zero causes
       connection refused which is worse than a clean 503)

    IMPORTANT: This is NOT scale-to-zero.
    Scale-to-zero = connection refused for ALL clients
    = worse than the original failure.
    Scale-to-1 + Redis signal = clean 503 with a message
    while the pod recovers.

    After K3S_CIRCUIT_BREAKER_DURATION_SECONDS the service
    is restored to its original replica count via a background task.

When used:
    - failure_tag = dependency (external service unavailable)
    - Cascading failure: 3+ detection engines fired simultaneously
"""
import asyncio
import json
import structlog
from datetime import datetime, timezone
from typing import Dict, Any
from app.healing_action_executor.strategies.base import BaseHealingStrategy
from app.shared.k3s_client import get_apps_v1
from app.core.redis_client import redis_client
from app.core.config import settings

logger = structlog.get_logger(__name__)


class K3sCircuitBreakerStrategy(BaseHealingStrategy):
    """
    K3s implementation of `circuit_breaker`.

    Writes Redis signal + scales to 1 (not 0) →
    schedules background restore after circuit duration.
    """

    async def execute(
        self, machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        service = machine_alert.get("service", "unknown")
        alert_id = machine_alert.get("alert_id", "unknown")
        duration = settings.K3S_CIRCUIT_BREAKER_DURATION_SECONDS

        logger.info(
            "K3sCircuitBreakerStrategy: starting",
            service=service,
            alert_id=alert_id,
        )

        # ── Part 1: Write Redis circuit breaker signal ─────────────
        try:
            signal_key = (
                f"healing:signals:{service}:circuit_breaker"
            )
            signal_value = json.dumps({
                "open": True,
                "fallback_response": (
                    "Service temporarily unavailable. "
                    "Healing in progress."
                ),
                "duration_seconds": duration,
                "set_at": datetime.now(timezone.utc).isoformat(),
                "set_by": "component_a",
                "alert_id": alert_id,
            })
            redis_client.setex(signal_key, duration, signal_value)
            logger.info(
                "K3sCircuitBreakerStrategy: Redis signal written",
                key=signal_key,
                duration=duration,
            )
        except Exception as e:
            logger.warning(
                "K3sCircuitBreakerStrategy: Redis signal failed (non-fatal)",
                error=str(e),
            )

        # ── Part 2: Scale to minimum 1 replica via K3s ─────────────
        apps = get_apps_v1()
        if apps is None:
            return self._success(
                healing_action="circuit_breaker",
                message=(
                    "Circuit breaker Redis signal written. "
                    "K3s scale skipped (API unavailable)."
                ),
                service=service,
            )

        deployment_name = settings.K3S_CRAVE_DEPLOYMENT_NAME
        namespace = settings.K3S_NAMESPACE

        try:
            deployment = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: apps.read_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace,
                ),
            )
            original_replicas = deployment.spec.replicas or 1

            # Scale to 1 — NOT 0 (avoids connection refused)
            if original_replicas > 1:
                patch_body = {"spec": {"replicas": 1}}
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: apps.patch_namespaced_deployment(
                        name=deployment_name,
                        namespace=namespace,
                        body=patch_body,
                    ),
                )
                logger.info(
                    "K3sCircuitBreakerStrategy: circuit OPEN "
                    "(scaled to 1 — not 0)",
                    deployment=deployment_name,
                    original_replicas=original_replicas,
                )

            # Schedule background restore after circuit duration
            asyncio.create_task(
                self._restore_circuit(
                    apps,
                    deployment_name,
                    namespace,
                    original_replicas,
                    duration,
                    service,
                )
            )

            return self._success(
                healing_action="circuit_breaker",
                message=(
                    f"Circuit breaker open. Redis signal written + "
                    f"scaled to 1 replica. "
                    f"Restoring to {original_replicas} in {duration}s."
                ),
                service=service,
                original_replicas=original_replicas,
                circuit_duration=duration,
            )

        except Exception as e:
            logger.error(
                "K3sCircuitBreakerStrategy: K3s scale failed",
                deployment=deployment_name,
                error=str(e),
            )
            return self._failure(
                healing_action="circuit_breaker",
                message=(
                    f"K3s circuit breaker scale failed for "
                    f"'{deployment_name}'"
                ),
                error=str(e),
                service=service,
            )

    async def _restore_circuit(
        self,
        apps,
        deployment_name: str,
        namespace: str,
        original_replicas: int,
        wait_seconds: int,
        service: str,
    ):
        """
        Background task: wait for circuit duration,
        then restore original replica count and clear Redis signal.
        """
        await asyncio.sleep(wait_seconds)
        try:
            patch_body = {"spec": {"replicas": original_replicas}}
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: apps.patch_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace,
                    body=patch_body,
                ),
            )
            # Clear Redis signal
            try:
                redis_client.delete(
                    f"healing:signals:{service}:circuit_breaker"
                )
            except Exception:
                pass
            logger.info(
                "K3sCircuitBreakerStrategy: circuit CLOSED (restored)",
                deployment=deployment_name,
                replicas=original_replicas,
            )
        except Exception as e:
            logger.error(
                "K3sCircuitBreakerStrategy: restore failed",
                deployment=deployment_name,
                error=str(e),
            )
