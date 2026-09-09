"""Tests for the Docker socket client."""
from unittest.mock import patch, MagicMock
from app.shared.docker_client import (
    is_docker_available,
    get_docker_client,
    restart_container,
    list_running_containers,
)


def test_is_docker_available_false_when_no_socket():
    """Returns False if socket file does not exist."""
    with patch("os.path.exists", return_value=False):
        result = is_docker_available()
        assert result is False


def test_is_docker_available_false_when_no_permission():
    """Returns False if socket exists but not writable."""
    with patch("os.path.exists", return_value=True):
        with patch("os.access", return_value=False):
            result = is_docker_available()
            assert result is False


def test_is_docker_available_true_when_socket_accessible():
    """Returns True if socket exists and is accessible."""
    with patch("os.path.exists", return_value=True):
        with patch("os.access", return_value=True):
            result = is_docker_available()
            assert result is True


def test_get_docker_client_returns_none_when_unavailable():
    """Returns None when Docker is not accessible."""
    with patch(
        "app.shared.docker_client.is_docker_available",
        return_value=False
    ):
        result = get_docker_client()
        assert result is None


def test_get_docker_client_returns_none_when_import_fails():
    """Returns None gracefully when docker-py not installed."""
    with patch(
        "app.shared.docker_client.is_docker_available",
        return_value=True
    ):
        with patch("builtins.__import__",
                   side_effect=ImportError("no module")):
            result = get_docker_client()
            assert result is None


def test_restart_container_returns_failure_when_unavailable():
    """restart_container returns success=False dict when
    Docker unavailable."""
    with patch(
        "app.shared.docker_client.get_docker_client",
        return_value=None
    ):
        result = restart_container("test-container")
        assert result["success"] is False
        assert result["container"] == "test-container"
        assert result["error"] is not None


def test_restart_container_returns_success():
    """restart_container returns success=True on success."""
    mock_container = MagicMock()
    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container

    with patch(
        "app.shared.docker_client.get_docker_client",
        return_value=mock_client
    ):
        result = restart_container("test-container")
        assert result["success"] is True
        mock_container.restart.assert_called_once_with(
            timeout=30
        )


def test_restart_container_returns_failure_on_error():
    """restart_container returns success=False when
    container not found."""
    mock_client = MagicMock()
    mock_client.containers.get.side_effect = Exception(
        "Container not found"
    )

    with patch(
        "app.shared.docker_client.get_docker_client",
        return_value=mock_client
    ):
        result = restart_container("nonexistent-container")
        assert result["success"] is False
        assert "Container not found" in result["error"]


def test_list_running_containers_returns_empty_when_unavailable():
    """Returns empty list when Docker unavailable."""
    with patch(
        "app.shared.docker_client.get_docker_client",
        return_value=None
    ):
        result = list_running_containers()
        assert result == []


def test_list_running_containers_returns_names():
    """Returns container names when Docker available."""
    mock_c1 = MagicMock()
    mock_c1.name = "niramay-backend"
    mock_c2 = MagicMock()
    mock_c2.name = "niramay-redis"
    mock_client = MagicMock()
    mock_client.containers.list.return_value = [
        mock_c1, mock_c2
    ]

    with patch(
        "app.shared.docker_client.get_docker_client",
        return_value=mock_client
    ):
        result = list_running_containers()
        assert "niramay-backend" in result
        assert "niramay-redis" in result
