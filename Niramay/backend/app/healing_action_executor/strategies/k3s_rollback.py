"""
K3s Rollback Deployment Strategy
=================================

Implements the `rollback_deployment` healing action for K3s clusters.

Mechanism:
    Performs the equivalent of `kubectl rollout undo deployment/<name>`.

    Steps:
        1. List all ReplicaSets owned by the target Deployment
        2. Sort by creation timestamp (newest first)
        3. Identify the previous ReplicaSet (second in sorted list)
        4. Patch the Deployment's spec.template to match the previous
           ReplicaSet's pod template

    K3s then performs a rolling update back to the previous pod spec.
    If no previous ReplicaSet exists (first deployment), returns failure
    with a clear message.

When used:
    - failure_tag = config_error (500 from misconfigured deployment)
"""
import asyncio
import structlog
from typing import Dict, Any, Optional
from app.healing_action_executor.strategies.base import BaseHealingStrategy
from app.shared.k3s_client import get_apps_v1
from app.core.config import settings

logger = structlog.get_logger(__name__)


class K3sRollbackStrategy(BaseHealingStrategy):
    """
    K3s implementation of `rollback_deployment`.

    Restores the previous ReplicaSet's pod template,
    effectively undoing the most recent deployment change.
    """

    async def execute(
        self, machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        service = machine_alert.get("service", "unknown")
        alert_id = machine_alert.get("alert_id", "unknown")

        logger.info(
            "K3sRollbackStrategy: starting",
            service=service,
            alert_id=alert_id,
        )

        apps = get_apps_v1()
        if apps is None:
            return self._failure(
                healing_action="rollback_deployment",
                message="K3s client unavailable — cannot rollback",
                error="K3s AppsV1Api returned None. "
                      "Check K3S_ENABLED and kubeconfig.",
                service=service,
            )

        deployment_name = settings.K3S_CRAVE_DEPLOYMENT_NAME
        namespace = settings.K3S_NAMESPACE

        try:
            # Step 1: Read the current Deployment
            deployment = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: apps.read_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace,
                )
            )

            # Step 2: List all ReplicaSets in the namespace
            all_rs = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: apps.list_namespaced_replica_set(
                    namespace=namespace,
                )
            )

            # Step 3: Filter ReplicaSets owned by this Deployment
            dep_uid = deployment.metadata.uid
            owned_rs = [
                rs for rs in all_rs.items
                if rs.metadata.owner_references
                and any(
                    ref.uid == dep_uid
                    for ref in rs.metadata.owner_references
                )
            ]

            # Sort by creation timestamp, newest first
            owned_rs.sort(
                key=lambda rs: rs.metadata.creation_timestamp,
                reverse=True,
            )

            if len(owned_rs) < 2:
                return self._failure(
                    healing_action="rollback_deployment",
                    message=(
                        f"No previous ReplicaSet found for "
                        f"Deployment '{deployment_name}'. "
                        f"Cannot rollback — this is the first revision."
                    ),
                    error="Only one ReplicaSet exists",
                    service=service,
                )

            # Step 4: Get the previous ReplicaSet's pod template
            previous_rs = owned_rs[1]
            previous_template = previous_rs.spec.template

            logger.info(
                "K3sRollbackStrategy: found previous ReplicaSet",
                previous_rs_name=previous_rs.metadata.name,
                created_at=str(
                    previous_rs.metadata.creation_timestamp
                ),
            )

            # Step 5: Patch the Deployment spec.template
            # with the previous ReplicaSet's template
            patch_body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "labels": (
                                previous_template.metadata.labels
                                if previous_template.metadata
                                else {}
                            )
                        },
                        "spec": (
                            previous_template.spec.to_dict()
                            if previous_template.spec
                            else {}
                        ),
                    }
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
                "K3sRollbackStrategy: rollback triggered",
                deployment=deployment_name,
                rolled_back_to=previous_rs.metadata.name,
            )

            return self._success(
                healing_action="rollback_deployment",
                message=(
                    f"Deployment '{deployment_name}' rolled back "
                    f"to previous ReplicaSet "
                    f"'{previous_rs.metadata.name}'."
                ),
                service=service,
                rolled_back_to=previous_rs.metadata.name,
            )

        except Exception as e:
            logger.error(
                "K3sRollbackStrategy: failed",
                deployment=deployment_name,
                error=str(e),
            )
            return self._failure(
                healing_action="rollback_deployment",
                message=(
                    f"K3s rollback failed for '{deployment_name}'"
                ),
                error=str(e),
                service=service,
            )
