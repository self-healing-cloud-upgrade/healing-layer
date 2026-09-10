"""
Restart Service Strategy

Phase 1 implementation for restart_service action.

Two-step process:
    Step 1: Call CRAVE heal endpoint to disable all
            active failure scenarios and pause injector
    Step 2: Restart the container via Docker socket

Both steps are required. Calling heal without restart
leaves the service in a broken state. Restarting
without calling heal means the injector will
re-inject failures immediately after restart.

NOTE: Step 1 (CRAVE heal endpoint) is currently
DISABLED. The connection is built and tested but
will be enabled in Phase 2 integration once both
systems are confirmed healthy in production.
Use the CRAVE_HEAL_ENABLED flag to enable when ready.

Phase 1 container mapping:
    Any service name containing "crave" maps to
    the container named "crave-backend".
    This is because all CRAVE services are in one
    container in Phase 1.
"""
import asyncio
import structlog
import httpx
from typing import Dict, Any
from app.healing_action_executor.strategies.base import (
    BaseHealingStrategy
)
from app.shared.docker_client import restart_container
from app.core.config import settings

logger = structlog.get_logger(__name__)

# ── CRAVE heal endpoint integration ──
# Set to True to enable calling the CRAVE heal endpoint.
# Enabled: CRAVE confirmed reachable and heal endpoint returns 200.
CRAVE_HEAL_ENABLED = True

# Token cache to avoid logging in on every heal call
_cached_token: str | None = None
_token_cached_at: float = 0.0
TOKEN_TTL_SECONDS: float = 3500.0  # JWT tokens expire at 3600s


async def _get_crave_auth_token() -> str | None:
    """
    Get a valid auth token for the CRAVE API.
    Caches the token for TOKEN_TTL_SECONDS to avoid
    logging in on every heal call.
    Returns None if authentication fails.

    NOTE: This function is defined and ready but is NOT
    called in Phase 1. Will be wired in Phase 2.
    """
    import time
    global _cached_token, _token_cached_at

    now = time.monotonic()
    if _cached_token and (now - _token_cached_at) < TOKEN_TTL_SECONDS:
        return _cached_token

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.CRAVE_BACKEND_URL}"
                f"/api/v1/auth/login",
                json={
                    "email": settings.CRAVE_DEVELOPER_EMAIL,
                    "password": settings.CRAVE_DEVELOPER_PASSWORD,
                }
            )
            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                if token:
                    _cached_token = token
                    _token_cached_at = now
                    logger.info(
                        "CRAVE auth token obtained"
                    )
                    return token
            logger.warning(
                "CRAVE auth login failed",
                status=response.status_code
            )
            return None
    except Exception as e:
        logger.warning(
            "CRAVE auth request failed",
            error=str(e)
        )
        return None


async def _call_crave_heal_endpoint(
    token: str
) -> Dict[str, Any]:
    """
    Call the CRAVE failure simulator heal endpoint.
    Disables all active failure scenarios and
    permanently pauses the injector.

    Returns the response dict or an error dict.

    NOTE: This function is defined and ready but is NOT
    called in Phase 1. Will be wired in Phase 2.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.CRAVE_BACKEND_URL}"
                f"/api/v1/failure-simulator/heal",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
            )
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    "CRAVE heal endpoint called successfully",
                    scenarios_disabled=data.get(
                        "scenarios_disabled", []),
                    injector_state=data.get(
                        "injector_state"),
                )
                return {
                    "success": True,
                    "scenarios_disabled": data.get(
                        "scenarios_disabled", []),
                    "injector_state": data.get(
                        "injector_state"),
                    "message": data.get("message", ""),
                }
            else:
                logger.warning(
                    "CRAVE heal endpoint returned error",
                    status=response.status_code,
                    body=response.text[:200]
                )
                return {
                    "success": False,
                    "scenarios_disabled": [],
                    "error": f"HTTP {response.status_code}: "
                             f"{response.text[:200]}"
                }
    except Exception as e:
        logger.warning(
            "CRAVE heal endpoint request failed",
            error=str(e)
        )
        return {
            "success": False,
            "scenarios_disabled": [],
            "error": str(e)
        }


def _resolve_container_name(service: str) -> str | None:
    """
    Resolve a service name from the machine alert to
    the actual Docker container name.

    Phase 1 mapping:
        Any service containing "crave" → "crave-backend"

    Phase 2 will replace this with per-service mapping
    when CRAVE splits into separate containers.

    Returns None if no mapping found.
    """
    if "crave" in service.lower():
        return "crave-backend"
    return None


class RestartServiceStrategy(BaseHealingStrategy):
    """
    Healing strategy for restart_service action.

    Routing:
        K3S_ENABLED=true  → Delegates to K3sRestartStrategy
                             (K3s rolling restart via API annotation patch)
        K3S_ENABLED=false → Docker socket restart (existing Phase 1 logic)
                             Uses CRAVE heal endpoint + docker.sock

    Both paths call the CRAVE heal endpoint first to stop the
    failure injector before restarting the service.
    """

    async def execute(
        self,
        machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        # ── K3s path ──────────────────────────────────────────────────
        # When K3s cluster is available, use K3s rolling restart
        # instead of Docker socket restart
        if settings.K3S_ENABLED:
            try:
                from app.healing_action_executor.strategies.k3s_restart import (
                    K3sRestartStrategy,
                )
                return await K3sRestartStrategy().execute(machine_alert)
            except ImportError:
                logger.warning(
                    "RestartServiceStrategy: K3S_ENABLED=true but "
                    "K3sRestartStrategy import failed — "
                    "falling through to Docker socket restart"
                )

        # ── Docker socket path (existing Phase 1 logic) ──────────────
        service = machine_alert.get("service", "unknown")
        alert_id = machine_alert.get("alert_id", "unknown")

        logger.info(
            "RestartServiceStrategy: starting",
            service=service,
            alert_id=alert_id
        )

        # Resolve container name
        container_name = _resolve_container_name(service)
        if container_name is None:
            return self._failure(
                healing_action="restart_service",
                message=f"No container mapping found "
                        f"for service: {service}",
                error=f"Service '{service}' does not match "
                      f"any known container mapping",
                service=service,
                container_restarted=None,
                scenarios_disabled=[],
            )

        # ── Step 1: Call CRAVE heal endpoint ──
        scenarios_disabled = []
        heal_step_success = False

        if CRAVE_HEAL_ENABLED:
            token = await _get_crave_auth_token()
            if token is None:
                logger.warning(
                    "RestartServiceStrategy: could not get "
                    "auth token, skipping heal endpoint",
                    service=service
                )
            else:
                heal_result = await _call_crave_heal_endpoint(
                    token
                )
                heal_step_success = heal_result.get(
                    "success", False)
                scenarios_disabled = heal_result.get(
                    "scenarios_disabled", [])
                if not heal_step_success:
                    logger.warning(
                        "RestartServiceStrategy: heal endpoint "
                        "failed, proceeding with restart anyway",
                        error=heal_result.get("error"),
                        service=service
                    )
        else:
            logger.info(
                "RestartServiceStrategy: CRAVE heal endpoint "
                "disabled — skipping Step 1",
                service=service
            )

        # ── Step 2: Restart container via Docker socket ──
        # Always attempt. Works independently of Step 1.
        restart_result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                restart_container,
                container_name
            ),
            timeout=settings.COMPONENT_A_TIMEOUT_SECONDS
        )

        if restart_result.get("success"):
            logger.info(
                "RestartServiceStrategy: complete",
                container=container_name,
                scenarios_disabled=scenarios_disabled,
                heal_endpoint_called=heal_step_success
            )
            return self._success(
                healing_action="restart_service",
                message=f"Container {container_name} "
                        f"restarted successfully. "
                        f"Scenarios disabled: "
                        f"{scenarios_disabled}",
                service=service,
                container_restarted=container_name,
                scenarios_disabled=scenarios_disabled,
                heal_endpoint_called=heal_step_success,
            )
        else:
            return self._failure(
                healing_action="restart_service",
                message=f"Container restart failed for "
                        f"{container_name}",
                error=restart_result.get("error"),
                service=service,
                container_restarted=None,
                scenarios_disabled=scenarios_disabled,
                heal_endpoint_called=heal_step_success,
            )
