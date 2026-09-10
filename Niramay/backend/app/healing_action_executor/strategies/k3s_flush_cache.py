"""
K3s Flush Cache Strategy
=========================

Implements the `flush_cache` healing action for K3s clusters.

Mechanism:
    Finds the Redis pod in the K3s cluster using the label selector
    configured in K3S_CRAVE_REDIS_POD_LABEL, then executes
    `redis-cli FLUSHDB` inside the pod via the K3s API.

    This clears stale or corrupted cache data that may be causing
    the service to return incorrect responses.

When used:
    - Stale cache data suspected (uncommon — manual trigger)
    - After rollback_deployment to ensure clean state
"""
import asyncio
import structlog
from typing import Dict, Any
from app.healing_action_executor.strategies.base import BaseHealingStrategy
from app.shared.k3s_client import get_core_v1
from app.core.config import settings

logger = structlog.get_logger(__name__)


class K3sFlushCacheStrategy(BaseHealingStrategy):
    """
    K3s implementation of `flush_cache`.

    Execs redis-cli FLUSHDB inside the Redis pod via K3s API.
    """

    async def execute(
        self, machine_alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        service = machine_alert.get("service", "unknown")
        alert_id = machine_alert.get("alert_id", "unknown")

        logger.info(
            "K3sFlushCacheStrategy: starting",
            service=service,
            alert_id=alert_id,
        )

        core = get_core_v1()
        if core is None:
            return self._failure(
                healing_action="flush_cache",
                message="K3s client unavailable — cannot flush cache",
                error="K3s CoreV1Api returned None.",
                service=service,
            )

        namespace = settings.K3S_NAMESPACE
        label_selector = settings.K3S_CRAVE_REDIS_POD_LABEL

        try:
            # Step 1: Find the Redis pod by label
            pods = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: core.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=label_selector,
                )
            )

            if not pods.items:
                return self._failure(
                    healing_action="flush_cache",
                    message=(
                        f"No Redis pod found with label "
                        f"'{label_selector}' in namespace "
                        f"'{namespace}'."
                    ),
                    error="Redis pod not found",
                    service=service,
                )

            redis_pod = pods.items[0]
            pod_name = redis_pod.metadata.name

            # Check pod is running
            if redis_pod.status.phase != "Running":
                return self._failure(
                    healing_action="flush_cache",
                    message=(
                        f"Redis pod '{pod_name}' is not Running "
                        f"(current phase: {redis_pod.status.phase})"
                    ),
                    error="Redis pod not in Running state",
                    service=service,
                )

            # Step 2: Exec redis-cli FLUSHDB inside the pod
            from kubernetes.stream import stream

            exec_output = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: stream(
                    core.connect_get_namespaced_pod_exec,
                    name=pod_name,
                    namespace=namespace,
                    command=["redis-cli", "FLUSHDB"],
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                )
            )

            output_str = str(exec_output).strip()

            logger.info(
                "K3sFlushCacheStrategy: FLUSHDB executed",
                pod=pod_name,
                output=output_str,
            )

            return self._success(
                healing_action="flush_cache",
                message=(
                    f"Redis cache flushed in pod '{pod_name}'. "
                    f"Output: {output_str}"
                ),
                service=service,
                redis_pod=pod_name,
                exec_output=output_str,
            )

        except Exception as e:
            logger.error(
                "K3sFlushCacheStrategy: failed",
                error=str(e),
            )
            return self._failure(
                healing_action="flush_cache",
                message="K3s flush_cache exec failed",
                error=str(e),
                service=service,
            )
