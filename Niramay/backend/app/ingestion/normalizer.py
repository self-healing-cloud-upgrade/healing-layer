"""
Stage 1 — Log Normalizer

Parses raw log messages from RabbitMQ (Component C) into a normalized
dictionary structure. Handles missing fields gracefully by applying
safe defaults and tracking normalization quality.

This normalizer produces the canonical field names required by the
Stage 2 detection pipeline:
    timestamp, service, endpoint, status_code, response_time_ms,
    failure_tag, request_id, raw, is_malformed
"""
import json
import structlog
from datetime import datetime, timezone
from typing import Dict, Any

logger = structlog.get_logger(__name__)


def _derive_crave_service(path: str) -> str:
    """
    Derive CRAVE service name from endpoint path.
    Used as fallback when service field is absent in the log message.
    Mirrors CRAVE's service_registry so that structlog-format messages
    (which carry path but no service) still get a meaningful service name.
    Returns "unknown" if path doesn't match any known CRAVE prefix.
    """
    if not path:
        return "unknown"
    p = path.lower()
    if p.startswith("/api/v1/auth"):
        return "crave-auth"
    if p.startswith("/api/v1/restaurants"):
        return "crave-restaurant"
    if p.startswith("/api/v1/orders"):
        return "crave-orders"
    if p.startswith("/api/v1/payments"):
        return "crave-payments"
    if p.startswith("/api/v1/delivery"):
        return "crave-delivery"
    if p.startswith("/api/v1/admin"):
        return "crave-admin"
    if p.startswith("/api/v1/contact"):
        return "crave-notification"
    if p.startswith("/api/v1/developer"):
        return "crave-developer"
    if p.startswith("/api/v1/chaos"):
        return "crave-chaos"
    if p.startswith("/api/v1/failure-simulator"):
        return "crave-simulator"
    if p.startswith("/api/v1/observation"):
        return "crave-observation"
    if p.startswith("/api/v1/"):
        return "crave-backend"
    if p in ("/health", "/", "/api/v1/"):
        return "crave-gateway"
    return "unknown"


def normalize_log(raw_message: str) -> Dict[str, Any]:
    """
    Parse a raw log message string into the normalized structure.

    Handling rules:
        - Missing timestamp      → current UTC time
        - Missing status_code    → 0, flag as incomplete
        - Missing endpoint       → "unknown", flag as incomplete
        - Missing response_time_ms → 0.0
        - Missing failure_tag    → "none"
        - Completely unparseable → store in raw, set defaults, is_malformed=True

    Returns:
        dict with the normalized log structure.
    """
    incomplete_fields = []

    # ── Attempt JSON parse ──
    try:
        data = json.loads(raw_message)
        if not isinstance(data, dict):
            raise ValueError("Parsed JSON is not a dictionary")
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "Completely unparseable message received",
            error=str(e),
            raw_preview=raw_message[:200]
        )
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "unknown",
            "endpoint": "unknown",
            "method": "UNKNOWN",
            "status_code": 0,
            "response_time_ms": 0.0,
            "failure_tag": "none",
            "request_id": None,
            "raw": raw_message,
            "is_malformed": True,
            "is_timestamp_assigned": True,
            "incomplete_fields": [
                "timestamp", "service", "endpoint",
                "status_code", "response_time_ms", "failure_tag"
            ],
        }

    # ── Timestamp ──
    timestamp = data.get("timestamp")
    is_timestamp_assigned = False
    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat()
        is_timestamp_assigned = True
        incomplete_fields.append("timestamp")
    else:
        # Validate it's a parseable ISO8601 string; if not, replace
        try:
            datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            timestamp = str(timestamp)
        except (ValueError, TypeError):
            timestamp = datetime.now(timezone.utc).isoformat()
            is_timestamp_assigned = True
            incomplete_fields.append("timestamp")

    # ── Service ──
    # Accept both "service" and "service_name" (Component C may use either)
    service = data.get("service") or data.get("service_name")
    service_derived = False
    if not service:
        service = "unknown"
        incomplete_fields.append("service")
    else:
        service = str(service)

    # ── Endpoint ──
    # Accept both "endpoint" and "path" (CRAVE structlog uses "path")
    endpoint = (
        data.get("endpoint")
        or data.get("path")
    )
    if not endpoint:
        endpoint = "unknown"
        incomplete_fields.append("endpoint")
    else:
        endpoint = str(endpoint)

    # ── Service fallback: derive from endpoint if still unknown ──
    # Handles CRAVE structlog format which has path/duration_ms but no service.
    # Must run after endpoint is resolved so we have a path to derive from.
    if service == "unknown" and endpoint != "unknown":
        derived = _derive_crave_service(endpoint)
        if derived != "unknown":
            service = derived
            service_derived = True
            if "service" in incomplete_fields:
                incomplete_fields.remove("service")

    # ── Status Code ──
    status_code = data.get("status_code")
    if status_code is None:
        status_code = 0
        incomplete_fields.append("status_code")
    else:
        try:
            status_code = int(status_code)
        except (ValueError, TypeError):
            status_code = 0
            incomplete_fields.append("status_code")

    # ── Response Time (ms) ──
    # Accept "response_time_ms", "response_time", and "duration_ms" (CRAVE structlog uses "duration_ms")
    response_time_ms = (
        data.get("response_time_ms")
        or data.get("response_time")
        or data.get("duration_ms")
    )
    if response_time_ms is None:
        response_time_ms = 0.0
    else:
        try:
            response_time_ms = float(response_time_ms)
        except (ValueError, TypeError):
            response_time_ms = 0.0

    # ── Failure Tag ──
    # Accept both "failure_tag" and "failure_type"
    failure_tag = data.get("failure_tag") or data.get("failure_type")
    if not failure_tag:
        failure_tag = "none"
    else:
        failure_tag = str(failure_tag)

    # ── Request ID ──
    request_id = data.get("request_id")
    if request_id is not None:
        request_id = str(request_id)

    # ── Method ──
    method = data.get("method", "UNKNOWN")
    method = str(method).upper() if method else "UNKNOWN"

    # ── Build normalized output ──
    normalized = {
        "timestamp": timestamp,
        "service": service,
        "endpoint": endpoint,
        "method": method,
        "status_code": status_code,
        "response_time_ms": response_time_ms,
        "failure_tag": failure_tag,
        "request_id": request_id,
        "raw": raw_message,
        "is_malformed": False,
        "is_timestamp_assigned": is_timestamp_assigned,
        "incomplete_fields": incomplete_fields,
    }

    if incomplete_fields:
        logger.info(
            "Log normalized with missing fields",
            missing=incomplete_fields,
            service=service,
            endpoint=endpoint,
        )

    return normalized
