"""
Healing Verification Worker

Background async loop that verifies whether healing actions
actually resolved the anomaly by querying OpenSearch for
subsequent traffic logs.

Flow:
    1. Read pending healing actions from Redis healing:actions
    2. Wait for settling window
    3. Query OpenSearch for subsequent logs
    4. If anomaly signals persist → retry healing (up to 3 times)
    5. After 3 failures → generate escalation alert
"""
import asyncio
import json
import structlog
from datetime import datetime, timezone, timedelta
from app.core.redis_client import get_async_redis
from app.ingestion.opensearch_client import opensearch_writer
from app.healing.index import healing_service

logger = structlog.get_logger(__name__)

# Redis keys
HEALING_KEY = "healing:actions"
ESCALATION_KEY = "escalation:alerts"

# Settling windows per action type (seconds)
SETTLING_WINDOWS = {
    "restart_service": 45,
    "throttle_requests": 15,
    "flush_cache": 10,
    "scale_up": 30,
    "circuit_breaker": 20,
    "rollback_deployment": 60,
    "escalate_only": 0,
    "none": 0,
}
DEFAULT_SETTLING_WINDOW = 15

MAX_RETRY_ATTEMPTS = 3


async def verification_worker_loop():
    """
    Background worker that verifies pending healing actions.
    Checks subsequent traffic via OpenSearch to determine if
    anomaly signals have subsided.
    """
    logger.info("Healing Verification Worker started")
    r = await get_async_redis()

    # Track verification state in-memory
    # Key: detection_id, Value: {attempts, last_action, settled_at, ...}
    pending_verifications: dict = {}

    while True:
        try:
            # Read current healing actions from Redis
            raw_actions = await r.lrange(HEALING_KEY, 0, 99)

            for raw in raw_actions:
                try:
                    action = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue

                detection_id = action.get("detection_id")
                if not detection_id:
                    continue

                # Skip already verified or non-pending
                v_status = action.get("verification_status", "PENDING")
                if v_status != "PENDING":
                    continue

                # Check if we're already tracking this
                if detection_id in pending_verifications:
                    pv = pending_verifications[detection_id]
                else:
                    pv = {
                        "attempts": 0,
                        "healing_actions_tried": [],
                        "outcomes": [],
                        "service": action.get("service", "unknown"),
                        "endpoint": action.get("endpoint", "unknown"),
                        "failure_tag": action.get("failure_tag", "none"),
                        "timestamp": action.get("timestamp", ""),
                        "last_action": action.get("healing_action", "unknown"),
                    }
                    pending_verifications[detection_id] = pv

                # Check settling window
                healing_action = action.get("healing_action", "unknown")
                wait_seconds = SETTLING_WINDOWS.get(healing_action, DEFAULT_SETTLING_WINDOW)

                try:
                    action_time = datetime.fromisoformat(
                        action.get("timestamp", "").replace("Z", "+00:00")
                    )
                    elapsed = (datetime.now(timezone.utc) - action_time).total_seconds()
                except (ValueError, TypeError):
                    elapsed = 0

                if elapsed < wait_seconds:
                    continue  # Not enough time has passed

                # ── Query OpenSearch for subsequent logs ──
                service = pv["service"]
                endpoint = pv["endpoint"]
                timestamp = pv["timestamp"]

                subsequent_logs = opensearch_writer.get_logs_after_timestamp(
                    service=service,
                    endpoint=endpoint,
                    timestamp=timestamp,
                )

                if not subsequent_logs:
                    # No traffic yet — check if expired (10 min)
                    if elapsed > 600:
                        pv["outcomes"].append("EXPIRED")
                        logger.warning(
                            "Healing verification expired (no traffic)",
                            detection_id=detection_id,
                        )
                        del pending_verifications[detection_id]
                    continue

                # Analyze subsequent logs for anomaly signals
                anomaly_count = 0
                for slog in subsequent_logs:
                    status = slog.get("status_code", 200)
                    failure = slog.get("failure_tag", "none")
                    if status >= 500 or (failure and failure != "none"):
                        anomaly_count += 1

                failure_rate = anomaly_count / len(subsequent_logs) if subsequent_logs else 0

                if failure_rate <= 0.3:
                    # ✅ Healing verified — anomaly resolved
                    pv["outcomes"].append("SUCCESS")
                    logger.info(
                        "Healing verified: SUCCESS",
                        detection_id=detection_id,
                        failure_rate=f"{failure_rate:.1%}",
                    )
                    opensearch_writer.update_incident_report_status(detection_id, "SUCCESS")
                    del pending_verifications[detection_id]
                else:
                    # ❌ Anomaly persists
                    pv["attempts"] += 1
                    pv["healing_actions_tried"].append(healing_action)
                    pv["outcomes"].append("FAILURE")

                    if pv["attempts"] >= MAX_RETRY_ATTEMPTS:
                        # Generate escalation alert
                        await _escalate(r, pv, detection_id)
                        opensearch_writer.update_incident_report_status(detection_id, "ESCALATED")
                        del pending_verifications[detection_id]
                    else:
                        # Retry: push the original detection back
                        # to Dispatcher Worker queue with incremented
                        # retry context so Dispatcher Worker
                        # re-dispatches to Component A
                        logger.warning(
                            "Healing failed, retrying",
                            detection_id=detection_id,
                            attempt=pv["attempts"],
                        )
                        try:
                            retry_payload = {
                                "detection_id": detection_id,
                                "service": pv["service"],
                                "endpoint": pv["endpoint"],
                                "failure_tag": pv["failure_tag"],
                                "retry_count": pv["attempts"],
                                "anomaly_reasons": action.get(
                                    "anomaly_reasons", []),
                                "severity": action.get(
                                    "severity", "medium"),
                                "timestamp": action.get("timestamp"),
                                "is_retry": True,
                            }
                            await r.rpush(
                                "dispatcher:pending",
                                json.dumps(retry_payload)
                            )
                        except Exception as e:
                            logger.error(
                                "Failed to push retry to Dispatcher Worker",
                                error=str(e)
                            )
                        opensearch_writer.update_incident_report_status(
                            detection_id, "FAILED_RETRYING")

            await asyncio.sleep(15)

        except asyncio.CancelledError:
            logger.info("Verification worker cancelled")
            break
        except Exception as e:
            logger.error("Verification worker error", error=str(e))
            await asyncio.sleep(5)


async def _escalate(r, pv: dict, detection_id: str):
    """Generate and store an escalation alert after max retries."""
    escalation = {
        "type": "escalation",
        "service": pv["service"],
        "endpoint": pv["endpoint"],
        "failure_tag": pv["failure_tag"],
        "attempts": pv["attempts"],
        "healing_actions_tried": pv["healing_actions_tried"],
        "outcomes": pv["outcomes"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": (
            f"Healing failed after {pv['attempts']} attempts for "
            f"{pv['service']}:{pv['endpoint']}. "
            f"Actions tried: {', '.join(pv['healing_actions_tried'])}. "
            f"Manual intervention required."
        ),
    }

    try:
        await r.lpush(ESCALATION_KEY, json.dumps(escalation))
        await r.ltrim(ESCALATION_KEY, 0, 99)
    except Exception as e:
        logger.error("Failed to push escalation alert", error=str(e))

    logger.warning(
        "ESCALATION: Healing exhausted all retries",
        detection_id=detection_id,
        service=pv["service"],
        endpoint=pv["endpoint"],
        attempts=pv["attempts"],
    )


def start_verification_worker():
    """Start the verification worker in the background."""
    asyncio.create_task(verification_worker_loop())
    logger.info("Verification worker task created")
