"""
K3s Throttle Requests Strategy
===============================

Implements the `throttle_requests` healing action for K3s clusters.

Mechanism:
    Reduces the Crave backend Deployment replica count by 1
    (minimum 1 replica — never scales to 0).

    This is a conservative proxy for request throttling:
    fewer pods = fewer concurrent requests accepted = back-pressure
    applied to clients naturally via K3s service load balancing.

    After THROTTLE_RESTORE_SECONDS (default 60s), a background task
    restores the original replica count.

    Full Istio/Envoy-based rate limiting can replace this in Phase 3.

When used:
    - failure_tag = rate_limiting (429 responses)
    - anomaly_reason = rate_limit
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

# How long to keep the throttled state before restoring
THROTTLE_RESTORE_SECONDS = 300  # 5 minutes
THROTTLE_RATE_LIMIT_RPS = 10


class K3sThrottleStrategy(BaseHealingStrategy):
    """
    K3s implementation of `throttle_requests`.

    Scales down the Deployment by 1 replica to reduce capacity,
    then restores after THROTTLE_RESTORE_SECONDS.
    """

    async def execute(
        self, machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        service = machine_alert.get("service", "unknown")
        alert_id = machine_alert.get("alert_id", "unknown")

        logger.info(
            "K3sThrottleStrategy: starting",
            service=service,
            alert_id=alert_id,
        )

        # ── Part 1: Write Redis throttle signal for CRAVE middleware ──
        try:
            signal_key = f"healing:signals:{service}:throttle"
            signal_value = json.dumps({
                "rate_limit_rps": THROTTLE_RATE_LIMIT_RPS,
                "duration_seconds": THROTTLE_RESTORE_SECONDS,
                "set_at": datetime.now(timezone.utc).isoformat(),
                "set_by": "component_a",
                "alert_id": alert_id,
            })
            redis_client.setex(
                signal_key,
                THROTTLE_RESTORE_SECONDS,
                signal_value,
            )
            logger.info(
                "K3sThrottleStrategy: Redis throttle signal written",
                key=signal_key,
                rps=THROTTLE_RATE_LIMIT_RPS,
            )
        except Exception as e:
            logger.warning(
                "K3sThrottleStrategy: Redis signal failed (non-fatal)",
                error=str(e),
            )

        # ── Part 2: Scale down by 1 via K3s ────────────────────
        apps = get_apps_v1()
        if apps is None:
            return self._failure(
                healing_action="throttle_requests",
                message="K3s client unavailable — cannot throttle",
                error="K3s AppsV1Api returned None.",
                service=service,
            )

        deployment_name = settings.K3S_CRAVE_DEPLOYMENT_NAME
        namespace = settings.K3S_NAMESPACE

        try:
            # Read current replica count
            deployment = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: apps.read_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace,
                )
            )
            current_replicas = deployment.spec.replicas or 1

            if current_replicas <= 1:
                logger.warning(
                    "K3sThrottleStrategy: already at minimum replicas",
                    current=current_replicas,
                )
                return self._failure(
                    healing_action="throttle_requests",
                    message=(
                        f"Deployment '{deployment_name}' already at "
                        f"1 replica — cannot scale down further."
                    ),
                    error="Already at minimum replicas",
                    service=service,
                    previous_replicas=current_replicas,
                    throttled_replicas=current_replicas,
                )

            throttled_replicas = current_replicas - 1

            # Scale down
            patch_body = {
                "spec": {"replicas": throttled_replicas}
            }

            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: apps.patch_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace,
                    body=patch_body,
                )
            )

            logger.info(
                "K3sThrottleStrategy: throttled (scaled down)",
                deployment=deployment_name,
                previous_replicas=current_replicas,
                throttled_replicas=throttled_replicas,
            )

            # Schedule background restore task
            asyncio.create_task(
                self._restore_replicas(
                    deployment_name,
                    namespace,
                    current_replicas,
                )
            )

            return self._success(
                healing_action="throttle_requests",
                message=(
                    f"Deployment '{deployment_name}' throttled: "
                    f"scaled from {current_replicas} to "
                    f"{throttled_replicas} replicas. "
                    f"Will restore in {THROTTLE_RESTORE_SECONDS}s."
                ),
                service=service,
                previous_replicas=current_replicas,
                throttled_replicas=throttled_replicas,
                restore_in_seconds=THROTTLE_RESTORE_SECONDS,
            )

        except Exception as e:
            logger.error(
                "K3sThrottleStrategy: failed",
                deployment=deployment_name,
                error=str(e),
            )
            return self._failure(
                healing_action="throttle_requests",
                message=(
                    f"K3s throttle failed for '{deployment_name}'"
                ),
                error=str(e),
                service=service,
            )

    @staticmethod
    async def _restore_replicas(
        deployment_name: str,
        namespace: str,
        original_replicas: int,
    ):
        """
        Background task: wait THROTTLE_RESTORE_SECONDS,
        then restore the original replica count.
        """
        try:
            await asyncio.sleep(THROTTLE_RESTORE_SECONDS)

            apps = get_apps_v1()
            if apps is None:
                logger.warning(
                    "K3sThrottleStrategy: restore failed — "
                    "K3s client unavailable"
                )
                return

            patch_body = {
                "spec": {"replicas": original_replicas}
            }

            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: apps.patch_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace,
                    body=patch_body,
                )
            )

            logger.info(
                "K3sThrottleStrategy: replicas restored",
                deployment=deployment_name,
                restored_replicas=original_replicas,
            )
        except Exception as e:
            logger.error(
                "K3sThrottleStrategy: restore failed",
                deployment=deployment_name,
                error=str(e),
            )
