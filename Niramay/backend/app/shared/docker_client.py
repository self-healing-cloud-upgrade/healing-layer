"""
Docker Socket Client

Provides verified access to the Docker daemon via
the mounted socket at /var/run/docker.sock.

Used by Component A healing actions that require
container-level operations such as restart_service.

The socket is mounted in docker-compose.yml as:
    /var/run/docker.sock:/var/run/docker.sock

This module verifies the socket is accessible and
usable before any healing action attempts to use it.
If the socket is unavailable, healing actions that
require Docker fall back to escalate_only.
"""
import os
import structlog

logger = structlog.get_logger(__name__)

DOCKER_SOCKET_PATH = "/var/run/docker.sock"


def is_docker_available() -> bool:
    """
    Check if the Docker socket is mounted and accessible.

    Returns True only if:
    1. The socket file exists at the expected path
    2. The current process has read+write permission on it

    This must return True before any Docker-based
    healing action is attempted.
    """
    if not os.path.exists(DOCKER_SOCKET_PATH):
        logger.warning(
            "Docker socket not found",
            path=DOCKER_SOCKET_PATH,
            hint="Check docker-compose.yml volumes section"
        )
        return False

    if not os.access(DOCKER_SOCKET_PATH, os.R_OK | os.W_OK):
        logger.warning(
            "Docker socket exists but is not accessible",
            path=DOCKER_SOCKET_PATH,
            hint="Container may need to run as root or "
                 "docker group membership"
        )
        return False

    logger.info(
        "Docker socket verified",
        path=DOCKER_SOCKET_PATH,
        status="accessible"
    )
    return True


def get_docker_client():
    """
    Return a Docker client connected via the socket.

    Returns None if:
    - docker-py library is not installed
    - Socket is not accessible
    - Docker daemon is not responding

    Callers must check for None before using the client.
    """
    if not is_docker_available():
        return None

    _docker_mod = None
    try:
        import docker as _docker_mod
    except ImportError:
        pass

    if _docker_mod is None:
        try:
            logger.warning(
                "docker-py not installed",
                hint="Run: pip install docker"
            )
        except Exception:
            pass
        return None

    try:
        client = _docker_mod.DockerClient(base_url="unix:///var/run/docker.sock")
        client.ping()
        logger.info("Docker client connected and daemon responding")
        return client
    except Exception as e:
        logger.warning(
            "Docker client failed to connect",
            error=str(e)
        )
        return None


def restart_container(container_name: str) -> dict:
    """
    Restart a named Docker container.

    Returns a result dict with:
        success: bool
        container: container name attempted
        message: human readable outcome
        error: error string if failed, None if success

    Never raises exceptions. Always returns a result dict.
    """
    client = get_docker_client()
    if client is None:
        return {
            "success": False,
            "container": container_name,
            "message": "Docker unavailable, cannot restart",
            "error": "Docker socket not accessible or "
                     "docker-py not installed",
        }

    try:
        container = client.containers.get(container_name)
        container.restart(timeout=30)
        logger.info(
            "Container restarted successfully",
            container=container_name
        )
        return {
            "success": True,
            "container": container_name,
            "message": f"Container {container_name} "
                       f"restarted successfully",
            "error": None,
        }
    except Exception as e:
        logger.error(
            "Container restart failed",
            container=container_name,
            error=str(e)
        )
        return {
            "success": False,
            "container": container_name,
            "message": f"Failed to restart {container_name}",
            "error": str(e),
        }


def list_running_containers() -> list:
    """
    Return a list of currently running container names.
    Used to verify a container exists before attempting
    to restart it.

    Returns empty list if Docker is unavailable.
    """
    client = get_docker_client()
    if client is None:
        return []

    try:
        containers = client.containers.list()
        return [c.name for c in containers]
    except Exception as e:
        logger.warning(
            "Failed to list containers",
            error=str(e)
        )
        return []


# Run verification on import so startup logs show
# Docker status immediately
_docker_available = is_docker_available()
