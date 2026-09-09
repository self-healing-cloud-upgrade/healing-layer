"""
K3s Client Factory
==================

Shared entry point for all K3s healing strategies.

K3s is a lightweight Kubernetes distribution that exposes the standard
Kubernetes REST API. This module uses the official `kubernetes` Python
library to talk to the K3s API server.

Authentication modes (controlled by K3S_IN_CLUSTER setting):
    True  — In-cluster service account (Niramay running as a K3s pod).
             K3s mounts the token at /var/run/secrets/kubernetes.io/serviceaccount/
    False — Local kubeconfig from ~/.kube/config (WSL2 dev environment
             where K3s is installed and kubectl is configured).

Usage in strategies:
    from app.shared.k3s_client import get_apps_v1, get_core_v1

    apps = get_apps_v1()
    if apps is None:
        return self._failure(..., error="K3s client unavailable")
    apps.patch_namespaced_deployment(...)

Safety:
    - Returns None if the `kubernetes` library is not installed.
      This prevents ImportError crashes in Docker Compose mode.
    - Returns None if authentication fails (wrong kubeconfig, no cluster).
    - All callers must check for None before using the client.
    - Never raises exceptions out of this module.
"""
import structlog
from typing import Optional

logger = structlog.get_logger(__name__)


def _load_k3s_config() -> bool:
    """
    Load K3s cluster configuration into the kubernetes library.

    Tries in-cluster config first (if K3S_IN_CLUSTER=True),
    then falls back to local kubeconfig (for WSL2 local dev).

    Returns True if config was loaded successfully, False otherwise.
    """
    try:
        from kubernetes import config as k8s_config
        from app.core.config import settings

        if settings.K3S_IN_CLUSTER:
            try:
                k8s_config.load_incluster_config()
                logger.info(
                    "K3s client: loaded in-cluster service account config"
                )
                return True
            except k8s_config.ConfigException:
                logger.warning(
                    "K3s client: in-cluster config failed, "
                    "falling back to kubeconfig"
                )

        # Fall back to local kubeconfig (WSL2 dev)
        k8s_config.load_kube_config()
        logger.info(
            "K3s client: loaded local kubeconfig (~/.kube/config)"
        )
        return True

    except ImportError:
        logger.warning(
            "K3s client: `kubernetes` library not installed. "
            "Install with: pip install kubernetes>=28.1.0. "
            "K3s healing strategies will not be available."
        )
        return False
    except Exception as e:
        logger.error(
            "K3s client: failed to load cluster config",
            error=str(e)
        )
        return False


# Track whether config has been loaded (load once per process)
_config_loaded: bool = False


def _ensure_config() -> bool:
    """Load K3s config once. Returns True if ready."""
    global _config_loaded
    if not _config_loaded:
        _config_loaded = _load_k3s_config()
    return _config_loaded


def get_apps_v1():
    """
    Return an authenticated AppsV1Api client for K3s.

    Used by strategies that manage Deployments:
        - k3s_restart.py    (patch deployment annotation)
        - k3s_scale_up.py   (patch spec.replicas)
        - k3s_rollback.py   (restore previous ReplicaSet)
        - k3s_throttle.py   (scale down replicas)
        - k3s_circuit_breaker.py (scale to 0 and restore)

    Returns None if K3s is unreachable or library not installed.
    Callers must check for None.
    """
    if not _ensure_config():
        return None
    try:
        from kubernetes import client
        return client.AppsV1Api()
    except Exception as e:
        logger.error("K3s client: failed to create AppsV1Api", error=str(e))
        return None


def get_core_v1():
    """
    Return an authenticated CoreV1Api client for K3s.

    Used by strategies that manage Pods:
        - k3s_flush_cache.py (exec into Redis pod)

    Returns None if K3s is unreachable or library not installed.
    Callers must check for None.
    """
    if not _ensure_config():
        return None
    try:
        from kubernetes import client
        return client.CoreV1Api()
    except Exception as e:
        logger.error("K3s client: failed to create CoreV1Api", error=str(e))
        return None


def get_custom_objects():
    """
    Return an authenticated CustomObjectsApi client for K3s.

    Used by: chaos injection verification (Chaos Mesh CRDs).
    Returns None if K3s is unreachable or library not installed.
    Callers must check for None.
    """
    if not _ensure_config():
        return None
    try:
        from kubernetes import client
        return client.CustomObjectsApi()
    except Exception as e:
        logger.error(
            "K3s client: failed to create CustomObjectsApi", error=str(e)
        )
        return None
