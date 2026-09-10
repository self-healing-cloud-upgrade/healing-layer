"""
K3s Scale Up Strategy
=====================

Implements the `scale_up` healing action for K3s clusters.

Mechanism:
    Reads the current replica count from the Crave backend Deployment,
    then patches spec.replicas to current + 1, capped at K3S_MAX_REPLICAS.

    K3s schedules the new pod, which starts with a clean middleware state.
    The K3s service load-balances traffic across all replicas, so the
    overall failure rate drops even if the original pod is still broken.

When used:
    - failure_tag = service_overload (503 on 80% of all requests)
    - anomaly_reason = high_latency (ChaosMiddleware latency injection)
"""
import asyncio
import structlog
from typing import Dict, Any
from app.healing_action_executor.strategies.base import BaseHealingStrategy
from app.shared.k3s_client import get_apps_v1
from app.core.config import settings

logger = structlog.get_logger(__name__)


class K3sScaleUpStrategy(BaseHealingStrategy):
    """
    K3s implementation of `scale_up`.

    Increases the Crave backend Deployment replica count by 1,
    capped at K3S_MAX_REPLICAS to prevent runaway scaling.
    """

    async def execute(
        self, machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        service = machine_alert.get("service", "unknown")
        alert_id = machine_alert.get("alert_id", "unknown")

        logger.info(
            "K3sScaleUpStrategy: starting",
            service=service,
            alert_id=alert_id,
        )

        apps = get_apps_v1()
        if apps is None:
            return self._failure(
                healing_action="scale_up",
                message="K3s client unavailable — cannot scale Deployment",
                error="K3s AppsV1Api returned None. "
                      "Check K3S_ENABLED and kubeconfig.",
                service=service,
                previous_replicas=None,
                new_replicas=None,
            )

        deployment_name = settings.K3S_CRAVE_DEPLOYMENT_NAME
        namespace = settings.K3S_NAMESPACE
        max_replicas = settings.K3S_MAX_REPLICAS

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

            if current_replicas >= max_replicas:
                logger.warning(
                    "K3sScaleUpStrategy: already at max replicas",
                    current=current_replicas,
                    max=max_replicas,
                )
                return self._failure(
                    healing_action="scale_up",
                    message=(
                        f"Deployment '{deployment_name}' already at "
                        f"max replicas ({max_replicas}). "
                        f"Cannot scale further."
                    ),
                    error="Max replica limit reached",
                    service=service,
                    previous_replicas=current_replicas,
                    new_replicas=current_replicas,
                )

            new_replicas = current_replicas + 1

            # Patch replica count
            patch_body = {
                "spec": {
                    "replicas": new_replicas
                }
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
                "K3sScaleUpStrategy: scaled up",
                deployment=deployment_name,
                previous_replicas=current_replicas,
                new_replicas=new_replicas,
            )

            return self._success(
                healing_action="scale_up",
                message=(
                    f"Deployment '{deployment_name}' scaled from "
                    f"{current_replicas} to {new_replicas} replicas."
                ),
                service=service,
                previous_replicas=current_replicas,
                new_replicas=new_replicas,
                max_replicas=max_replicas,
            )

        except Exception as e:
            logger.error(
                "K3sScaleUpStrategy: failed",
                deployment=deployment_name,
                error=str(e),
            )
            return self._failure(
                healing_action="scale_up",
                message=f"K3s scale_up failed for '{deployment_name}'",
                error=str(e),
                service=service,
                previous_replicas=None,
                new_replicas=None,
            )
