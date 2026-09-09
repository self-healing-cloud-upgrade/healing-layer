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
from app.core.config import settings
from app.core.redis_client import get_async_redis
from app.ingestion.opensearch_client import opensearch_writer
from app.reporting.email_service import send_escalation_email

logger = structlog.get_logger(__name__)

# Redis keys
HEALING_KEY = "healing:actions"
ESCALATION_KEY = "escalation:alerts"

# Settling windows per action type (seconds)
# These define how long the verification worker waits after a healing
# action before checking OpenSearch for subsequent traffic.
# K3s pod operations are slightly slower than Docker restarts,
# so windows are tuned to allow K3s pods to become Ready.
SETTLING_WINDOWS = {
    "restart_service": 60,       # K3s rolling restart — pods replaced one-by-one
    "throttle_requests": 20,     # K3s scale-down is near-instant
    "flush_cache": 15,           # Redis FLUSHDB exec is instant, allow cache rebuild
    "scale_up": 45,              # New K3s pod needs ~45s to pass readiness checks
    "circuit_breaker": 70,       # 30s at 0 replicas + 40s for pod restart
    "rollback_deployment": 90,   # Previous ReplicaSet deployment takes ~90s
    "escalate_only": 0,
    "none": 0,
}
DEFAULT_SETTLING_WINDOW = 15

MAX_RETRY_ATTEMPTS = 3


def _parse_timestamp(ts: str):
    """Parse ISO8601 timestamp, return UTC datetime."""
    try:
        return datetime.fromisoformat(
            ts.replace("Z", "+00:00")
        )
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


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
                        "last_action": action.get(
                            "healing_action", "unknown"),
                        "scenarios_disabled": action.get(
                            "scenarios_disabled", []),
                        "container_restarted": action.get(
                            "container_restarted"),
                    }
                    pending_verifications[detection_id] = pv

                # Check settling window
                healing_action = action.get("healing_action", "unknown")
                wait_seconds = SETTLING_WINDOWS.get(
                    healing_action, DEFAULT_SETTLING_WINDOW
                )

                try:
                    action_time = datetime.fromisoformat(
                        action.get("timestamp", "").replace(
                            "Z", "+00:00")
                    )
                    elapsed = (
                        datetime.now(timezone.utc) - action_time
                    ).total_seconds()
                except (ValueError, TypeError):
                    elapsed = 0

                if elapsed < wait_seconds:
                    continue  # Not enough time has passed

                # ── Query OpenSearch for subsequent logs ──
                # After healing a crave-* service, widen query to
                # all crave-* services — failures often spread across
                # multiple endpoints simultaneously in K3s.
                if "crave" in pv.get("service", "").lower():
                    subsequent_logs = (
                        opensearch_writer.get_logs_after_timestamp(
                            service=None,
                            endpoint=None,
                            timestamp=pv["timestamp"],
                            service_prefix="crave-",
                        )
                    )
                else:
                    subsequent_logs = (
                        opensearch_writer.get_logs_after_timestamp(
                            service=pv["service"],
                            endpoint=pv["endpoint"],
                            timestamp=pv["timestamp"],
                        )
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

                failure_rate = (
                    anomaly_count / len(subsequent_logs)
                    if subsequent_logs else 0
                )

                # ── Dual verification conditions ──

                # Condition 1: failure rate below threshold
                # in the total window
                rate_ok = failure_rate <= \
                    settings.VERIFICATION_FAILURE_RATE_THRESHOLD

                # Condition 2: no failure_tag != none in the
                # clean window (last N seconds)
                clean_cutoff = datetime.now(timezone.utc) - \
                    timedelta(
                        seconds=settings.VERIFICATION_CLEAN_WINDOW_SECONDS
                    )
                recent_with_failure = [
                    log for log in subsequent_logs
                    if log.get("failure_tag", "none") != "none"
                    and _parse_timestamp(
                        log.get("timestamp", "")
                    ) >= clean_cutoff
                ]
                clean_ok = len(recent_with_failure) == 0

                healing_succeeded = rate_ok and clean_ok

                if healing_succeeded:
                    # ✅ Healing verified — anomaly resolved
                    pv["outcomes"].append("SUCCESS")

                    # Calculate time to heal
                    try:
                        detection_time = _parse_timestamp(
                            pv.get("timestamp", "")
                        )
                        heal_time = datetime.now(timezone.utc)
                        time_to_heal = (
                            heal_time - detection_time
                        ).total_seconds()
                    except Exception:
                        time_to_heal = None

                    logger.info(
                        "Healing verified: SUCCESS",
                        detection_id=detection_id,
                        failure_rate=f"{failure_rate:.1%}",
                        time_to_heal=time_to_heal,
                    )

                    # Generate CRAVE Anomaly Healed Report
                    healed_report = {
                        "report_type": "CRAVE Anomaly Healed Report",
                        "detection_id": detection_id,
                        "service": pv["service"],
                        "endpoint": pv["endpoint"],
                        "failure_tag": pv["failure_tag"],
                        "healing_action_taken": pv.get(
                            "last_action", "unknown"),
                        "scenarios_disabled": pv.get(
                            "scenarios_disabled", []),
                        "container_restarted": pv.get(
                            "container_restarted"),
                        "verification_result": "SUCCESS",
                        "failure_rate_after": round(failure_rate, 4),
                        "time_to_heal_seconds": time_to_heal,
                        "total_attempts": pv["attempts"] + 1,
                        "healed_at": datetime.now(
                            timezone.utc).isoformat(),
                        "final_status": "HEALED",
                        "outcomes": pv["outcomes"],
                    }

                    # Store healed report to OpenSearch
                    opensearch_writer.write_healed_report(healed_report)

                    # Update original incident report status
                    opensearch_writer.update_incident_with_healing_result(
                        detection_id=detection_id,
                        healing_result={
                            "healing_action": pv.get(
                                "last_action", "unknown"),
                            "status": "success",
                            "scenarios_disabled": pv.get(
                                "scenarios_disabled", []),
                            "container_restarted": pv.get(
                                "container_restarted"),
                        },
                        verification_status="HEALED",
                        failure_rate=failure_rate,
                        attempts=pv["attempts"] + 1,
                    )

                    # Update pipeline stage
                    try:
                        await r.set(
                            settings.PIPELINE_STAGE_KEY,
                            json.dumps({
                                "stage": "healing_complete",
                                "timestamp": datetime.now(
                                    timezone.utc).isoformat(),
                                "message": "Healing complete, "
                                           "system healthy",
                                "service": pv["service"],
                                "time_to_heal": time_to_heal,
                            })
                        )
                    except Exception:
                        pass

                    del pending_verifications[detection_id]

                else:
                    # ❌ Anomaly persists
                    pv["attempts"] += 1
                    pv["healing_actions_tried"].append(healing_action)
                    pv["outcomes"].append("FAILURE")

                    if pv["attempts"] >= MAX_RETRY_ATTEMPTS:
                        # Generate escalation alert + send email
                        email_sent = await _escalate(
                            r, pv, detection_id
                        )

                        # Update pipeline stage with email status
                        stage_name = (
                            "healing_failed_email_sent"
                            if email_sent
                            else "healing_failed_escalated"
                        )
                        stage_msg = (
                            "Healing failed after 3 attempts, "
                            "developer notified via email"
                            if email_sent
                            else "Healing failed after 3 attempts, "
                                 "escalated (email not configured)"
                        )
                        try:
                            await r.set(
                                settings.PIPELINE_STAGE_KEY,
                                json.dumps({
                                    "stage": stage_name,
                                    "timestamp": datetime.now(
                                        timezone.utc).isoformat(),
                                    "message": stage_msg,
                                    "service": pv["service"],
                                    "attempts": MAX_RETRY_ATTEMPTS,
                                    "email_sent": email_sent,
                                })
                            )
                        except Exception:
                            pass

                        # Update incident report status to ESCALATED
                        opensearch_writer.update_incident_with_healing_result(
                            detection_id=detection_id,
                            healing_result={
                                "healing_action": pv.get(
                                    "last_action", "unknown"),
                                "status": "failed",
                                "scenarios_disabled": [],
                                "container_restarted": None,
                            },
                            verification_status="ESCALATED",
                            failure_rate=failure_rate,
                            attempts=MAX_RETRY_ATTEMPTS,
                        )
                        del pending_verifications[detection_id]
                    else:
                        # Retry: push back to Dispatcher Worker
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
                                "recommended_action": action.get(
                                    "healing_action", "restart_service"),
                                "alert_id": action.get("alert_id"),
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
        except (ConnectionError, OSError) as e:
            logger.warning(
                "Verification worker: Redis connection lost, reconnecting",
                error=str(e)
            )
            try:
                await r.aclose()
            except Exception:
                pass
            await asyncio.sleep(5)
            r = await get_async_redis()
        except Exception as e:
            logger.error("Verification worker error", error=str(e))
            try:
                await r.aclose()
            except Exception:
                pass
            await asyncio.sleep(5)
            r = await get_async_redis()


async def _escalate(r, pv: dict, detection_id: str) -> bool:
    """
    Generate and store an escalation alert after max retries.
    Also sends an email notification to the developer.

    Returns True if email was sent successfully, False otherwise.
    """
    escalated_at = datetime.now(timezone.utc)

    escalation = {
        "type": "escalation",
        "service": pv["service"],
        "endpoint": pv["endpoint"],
        "failure_tag": pv["failure_tag"],
        "attempts": pv["attempts"],
        "healing_actions_tried": pv["healing_actions_tried"],
        "outcomes": pv["outcomes"],
        "timestamp": escalated_at.isoformat(),
        "message": (
            f"Healing failed after {pv['attempts']} attempts for "
            f"{pv['service']}:{pv['endpoint']}. "
            f"Actions tried: {', '.join(pv['healing_actions_tried'])}. "
            f"Manual intervention required."
        ),
    }

    # Step 1: Push escalation alert to Redis
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

    # Step 2: Send escalation email to developer
    # Read recipient from Redis (set by frontend UI),
    # fall back to config default
    email_sent = False
    try:
        recipient_from_redis = await r.get("escalation:email_to")
        if isinstance(recipient_from_redis, bytes):
            recipient_from_redis = recipient_from_redis.decode()
        recipient = (
            recipient_from_redis
            if recipient_from_redis
            else None
        )

        email_sent = await send_escalation_email(
            {
                "service": pv["service"],
                "endpoint": pv["endpoint"],
                "failure_tag": pv["failure_tag"],
                "attempts": pv["attempts"],
                "healing_actions_tried": pv[
                    "healing_actions_tried"
                ],
                "outcomes": pv["outcomes"],
                "escalated_at": escalated_at.strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                ),
            },
            recipient_override=recipient,
        )
        if email_sent:
            logger.info(
                "Escalation email sent to developer",
                detection_id=detection_id,
                to=settings.ESCALATION_EMAIL_TO,
            )
        else:
            logger.info(
                "Escalation email not sent "
                "(SMTP disabled or failed)",
                detection_id=detection_id,
            )
    except Exception as e:
        logger.error(
            "Failed to send escalation email",
            detection_id=detection_id,
            error=str(e),
        )

    return email_sent


def start_verification_worker():
    """Start the verification worker in the background."""
    asyncio.create_task(verification_worker_loop())
    logger.info("Verification worker task created")
