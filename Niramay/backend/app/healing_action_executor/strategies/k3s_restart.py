"""
K3s Restart Service Strategy
=============================

Implements the `restart_service` healing action for K3s clusters.

Mechanism:
    Patches the Crave backend Deployment with a restart annotation:
        kubectl.kubernetes.io/restartedAt: <ISO timestamp>

    This is exactly what `kubectl rollout restart deployment/<name>` does
    internally. K3s then performs a rolling update — replacing pods one by
    one while keeping the service available.

    Upstream heal call (CRAVE_HEAL_ENABLED):
    Before the K3s restart, this strategy also calls the CRAVE heal
    endpoint to disable the FailureSimulationMiddleware injector.
    This prevents the injector from re-injecting failures immediately
    after the pod restarts, giving the verification worker a clean window.

When used:
    - failure_tag = database_error
    - failure_tag = payment_timeout
    - failure_tag = stripe_dependency
    - failure_tag = maps_dependency
    - anomaly_reason = server_error (no failure_tag, resource exhaustion)
"""
import asyncio
import structlog
import httpx
from datetime import datetime, timezone
from typing import Dict, Any
from app.healing_action_executor.strategies.base import BaseHealingStrategy
from app.shared.k3s_client import get_apps_v1
from app.core.config import settings

logger = structlog.get_logger(__name__)

# K3s annotation used to trigger a rolling restart
# Same annotation kubectl rollout restart uses
_RESTART_ANNOTATION = "kubectl.kubernetes.io/restartedAt"


async def _call_crave_heal(token: str) -> Dict[str, Any]:
    """
    Call the CRAVE /heal endpoint to disable the failure injector.
    Returns result dict with success flag and scenarios_disabled list.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.CRAVE_BACKEND_URL}"
                f"/api/v1/failure-simulator/heal",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "scenarios_disabled": data.get("scenarios_disabled", []),
                }
            return {"success": False, "scenarios_disabled": [],
                    "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "scenarios_disabled": [], "error": str(e)}


async def _get_crave_token() -> str | None:
    """Login to CRAVE and return a bearer token. Returns None on failure."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.CRAVE_BACKEND_URL}/api/v1/auth/login",
                json={
                    "email": settings.CRAVE_DEVELOPER_EMAIL,
                    "password": settings.CRAVE_DEVELOPER_PASSWORD,
                },
            )
            if resp.status_code == 200:
                return resp.json().get("access_token")
            return None
    except Exception:
        return None


class K3sRestartStrategy(BaseHealingStrategy):
    """
    K3s implementation of `restart_service`.

    Two steps:
        Step 1: Call CRAVE heal endpoint to stop failure injector
                (prevents re-injection after pod restarts)
        Step 2: Patch K3s Deployment restart annotation
                (triggers rolling pod replacement)
    """

    async def execute(
        self, machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        service = machine_alert.get("service", "unknown")
        alert_id = machine_alert.get("alert_id", "unknown")

        logger.info(
            "K3sRestartStrategy: starting",
            service=service,
            alert_id=alert_id,
        )

        # ── Step 1: Call CRAVE heal endpoint ──────────────────────────────
        scenarios_disabled = []
        heal_called = False

        try:
            token = await _get_crave_token()
            if token:
                heal_result = await _call_crave_heal(token)
                heal_called = heal_result.get("success", False)
                scenarios_disabled = heal_result.get("scenarios_disabled", [])
                if heal_called:
                    logger.info(
                        "K3sRestartStrategy: CRAVE heal endpoint succeeded",
                        scenarios_disabled=scenarios_disabled,
                    )
                else:
                    logger.warning(
                        "K3sRestartStrategy: CRAVE heal endpoint failed "
                        "— proceeding with K3s restart anyway",
                        error=heal_result.get("error"),
                    )
            else:
                logger.warning(
                    "K3sRestartStrategy: could not get CRAVE token "
                    "— proceeding with K3s restart anyway"
                )
        except Exception as e:
            logger.warning(
                "K3sRestartStrategy: heal step error (non-fatal)",
                error=str(e),
            )

        # ── Step 2: Patch K3s Deployment restart annotation ───────────────
        apps = get_apps_v1()
        if apps is None:
            return self._failure(
                healing_action="restart_service",
                message="K3s client unavailable — cannot restart Deployment",
                error="K3s AppsV1Api returned None. "
                      "Check K3S_ENABLED and kubeconfig.",
                service=service,
                container_restarted=None,
                scenarios_disabled=scenarios_disabled,
            )

        deployment_name = settings.K3S_CRAVE_DEPLOYMENT_NAME
        namespace = settings.K3S_NAMESPACE
        restart_ts = datetime.now(timezone.utc).isoformat()

        patch_body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            _RESTART_ANNOTATION: restart_ts
                        }
                    }
                }
            }
        }

        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: apps.patch_namespaced_deployment(
                    name=deployment_name,
                    namespace=namespace,
                    body=patch_body,
                )
            )

            logger.info(
                "K3sRestartStrategy: rolling restart triggered",
                deployment=deployment_name,
                namespace=namespace,
                restarted_at=restart_ts,
                scenarios_disabled=scenarios_disabled,
                heal_endpoint_called=heal_called,
            )

            return self._success(
                healing_action="restart_service",
                message=(
                    f"K3s rolling restart triggered for "
                    f"Deployment '{deployment_name}' in namespace "
                    f"'{namespace}'. "
                    f"Scenarios disabled: {scenarios_disabled}"
                ),
                service=service,
                container_restarted=deployment_name,
                scenarios_disabled=scenarios_disabled,
                heal_endpoint_called=heal_called,
                restarted_at=restart_ts,
            )

        except Exception as e:
            logger.error(
                "K3sRestartStrategy: patch failed",
                deployment=deployment_name,
                error=str(e),
            )
            return self._failure(
                healing_action="restart_service",
                message=f"K3s restart patch failed for '{deployment_name}'",
                error=str(e),
                service=service,
                container_restarted=None,
                scenarios_disabled=scenarios_disabled,
            )
