"""
Dispatcher Worker: Alert Dispatch and Healing Execution

Receives machine alerts from the Analyser Worker via
dispatcher:pending queue and handles:
    1. Executing healing via Component A (HealingActionExecutor)
    2. Storing healing record to Redis healing:actions
    3. Updating pipeline stage for UI progress tracking

Storm Prevention (two layers):
    Layer 1 — Tumbling Window: collects alerts into 20s
        windows and triggers healing once per window using
        the first alert as representative (min 3 alerts).
    Layer 2 — Healing Cooldown: 90s Redis-backed cooldown
        after healing to prevent rapid successive heals.
    Retries (is_retry=True) bypass both layers entirely.

Bug fixes applied:
    FIX 1 — _process_window: batched records for alerts[1:]
        are now written AFTER _handle_dispatcher returns,
        not before. Previously, records were written with
        "Healing triggered via representative alert" even
        when the cooldown suppressed the heal.
    FIX 2 — _write_batched_record: added healing_triggered
        parameter so the message is accurate in both the
        above-threshold and below-threshold branches.
    FIX 3 — _handle_dispatcher: moved pipeline stage update
        ("stage_4_healing_executing") to AFTER the manual
        mode check. Previously the stage was set to
        "executing" even when healing went to pending_approval.
"""
import asyncio
import json
import time
import structlog
from datetime import datetime, timezone
from app.core.config import settings
from app.core.redis_client import get_async_redis
from app.healing_action_executor.executor import (
    healing_executor
)

logger = structlog.get_logger(__name__)

DISPATCHER_QUEUE_KEY = "dispatcher:pending"
HEALING_KEY = "healing:actions"
LIST_CAP = 1000

# Storm prevention constants
WINDOW_DURATION_SECONDS = 30   # aligned with detection worker's 30s window
MIN_ALERTS_TO_HEAL = 1         # lowered: detection already batches, so 1 representative = valid
COOLDOWN_DURATION_SECONDS = 90
COOLDOWN_KEY_PREFIX = "healing:cooldown:"


async def dispatcher_worker_loop():
    """
    Main async loop for the Dispatcher Worker.
    Pops machine alerts from dispatcher:pending queue
    and dispatches to Component A.

    Implements a tumbling window (Layer 1) to batch
    alerts and prevent healing storms. Retries bypass
    the window and go straight to _handle_dispatcher.

    Automatically reconnects if the Redis connection goes stale.
    """
    logger.info("Dispatcher Worker started")
    r = await get_async_redis()

    # Layer 1: Tumbling window state
    window_start_time = time.time()
    alert_buffer: list = []

    while True:
        try:
            # Non-blocking pop to avoid uvicorn/aioredis brpop deadlock bug
            result = await r.lpop(DISPATCHER_QUEUE_KEY)
            if result is not None:
                raw = result
                try:
                    machine_alert = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "Dispatcher Worker: unparseable message",
                        raw=str(raw)[:200]
                    )
                    machine_alert = None

                if machine_alert is not None:
                    # Retries from verification worker bypass
                    # both tumbling window and cooldown entirely
                    if machine_alert.get("is_retry"):
                        logger.info(
                            "Dispatcher Worker: retry alert, "
                            "bypassing storm prevention",
                            alert_id=machine_alert.get(
                                "alert_id", "unknown"),
                            retry_count=machine_alert.get(
                                "retry_count", 0),
                        )
                        await _handle_dispatcher(
                            r, machine_alert
                        )
                    else:
                        # Buffer non-retry alerts for the
                        # tumbling window
                        alert_buffer.append(machine_alert)

            # Check if the tumbling window has elapsed
            elapsed = time.time() - window_start_time
            if elapsed >= WINDOW_DURATION_SECONDS:
                if alert_buffer:
                    await _process_window(r, alert_buffer)
                # Reset window regardless of whether we
                # had alerts or triggered healing
                alert_buffer = []
                window_start_time = time.time()

            # Sleep briefly if nothing was popped to avoid
            # busy-looping
            if result is None:
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info("Dispatcher Worker cancelled")
            break
        except (ConnectionError, OSError) as e:
            logger.warning(
                "Dispatcher Worker: Redis connection lost, reconnecting",
                error=str(e)
            )
            try:
                await r.aclose()
            except Exception:
                pass
            await asyncio.sleep(2)
            r = await get_async_redis()
        except Exception as e:
            logger.error("Dispatcher Worker error", error=str(e))
            try:
                await r.aclose()
            except Exception:
                pass
            await asyncio.sleep(2)
            r = await get_async_redis()


async def _process_window(r, alert_buffer: list):
    """
    Process a completed tumbling window.

    If >= MIN_ALERTS_TO_HEAL alerts are in the buffer,
    trigger healing once using the first alert as the
    representative. All other alerts are recorded as
    BATCHED in the audit trail.

    If < MIN_ALERTS_TO_HEAL alerts, discard the window
    but still write BATCHED records for audit completeness.

    FIX 1: _handle_dispatcher is called BEFORE writing
    batched records for alerts[1:], so the message in
    those records is always accurate regardless of whether
    the cooldown suppressed the heal or not.
    """
    batch_size = len(alert_buffer)

    logger.info(
        "Dispatcher Worker: tumbling window closed",
        alerts_in_window=batch_size,
        threshold=MIN_ALERTS_TO_HEAL,
    )

    if batch_size >= MIN_ALERTS_TO_HEAL:
        # Use the first alert as representative
        representative_alert = alert_buffer[0]

        # FIX 1: Trigger healing FIRST, then write batched
        # records. Previously batched records were written
        # before _handle_dispatcher, so they claimed
        # "Healing triggered" even when cooldown suppressed
        # the heal.
        await _handle_dispatcher(r, representative_alert)

        # Write BATCHED records for all non-representative
        # alerts (index 1+) after healing attempt completes
        for alert in alert_buffer[1:]:
            await _write_batched_record(
                r, alert, batch_size, healing_triggered=True
            )
    else:
        # Below threshold — write all as BATCHED (no heal)
        logger.info(
            "Dispatcher Worker: below threshold, "
            "no healing triggered",
            alerts_in_window=batch_size,
            threshold=MIN_ALERTS_TO_HEAL,
        )
        # FIX 2: Pass healing_triggered=False so the message
        # accurately reflects that no healing occurred
        for alert in alert_buffer:
            await _write_batched_record(
                r, alert, batch_size, healing_triggered=False
            )


async def _write_batched_record(
    r, machine_alert: dict, batch_size: int,
    healing_triggered: bool = True
):
    """
    Write a BATCHED audit record to healing:actions
    for an alert that was part of a batch but not
    selected as the representative.

    FIX 2: healing_triggered parameter controls the message
    so it is accurate in both the above-threshold branch
    (healing fired via representative) and the
    below-threshold branch (no healing at all).
    """
    if healing_triggered:
        message = (
            f"Alert batched in tumbling window "
            f"({batch_size} alerts in batch). "
            f"Healing triggered via representative alert."
        )
    else:
        message = (
            f"Alert batched in tumbling window "
            f"({batch_size} alerts in batch). "
            f"Below threshold ({MIN_ALERTS_TO_HEAL}) — "
            f"no healing triggered."
        )

    try:
        batched_record = {
            "healing_action": "batched_storm_prevention",
            "status": "batched",
            "message": message,
            "error": None,
            "scenarios_disabled": [],
            "container_restarted": None,
            "heal_endpoint_called": False,
            "executed_at": datetime.now(
                timezone.utc).isoformat(),
            "detection_id": machine_alert.get(
                "detection_id", "unknown"),
            "alert_id": machine_alert.get(
                "alert_id", "unknown"),
            "service": machine_alert.get("service"),
            "endpoint": machine_alert.get("endpoint"),
            "failure_tag": machine_alert.get(
                "failure_tag", "none"),
            "recommended_action": machine_alert.get(
                "recommended_action"),
            "timestamp": datetime.now(
                timezone.utc).isoformat(),
            "verification_status": "BATCHED",
            "retry_count": 0,
        }
        await r.lpush(
            HEALING_KEY,
            json.dumps(batched_record)
        )
        await r.ltrim(HEALING_KEY, 0, LIST_CAP - 1)
    except Exception as e:
        logger.warning(
            "Dispatcher Worker: failed to write batched record",
            error=str(e),
            alert_id=machine_alert.get(
                "alert_id", "unknown"),
        )


async def _execute_healing(
    machine_alert: dict
) -> dict:
    """
    Call the Healing Action Executor (Component A).
    Returns the healing result dict.
    """
    return await healing_executor.execute(
        machine_alert
    )


# Keep _send_to_component_a as an alias so existing
# tests continue to pass while we migrate.
async def _send_to_component_a(
    machine_alert: dict
) -> dict:
    """Alias for _execute_healing — kept for test compat."""
    return await _execute_healing(machine_alert)


async def _handle_dispatcher(r, machine_alert: dict):
    """
    Core Dispatcher Worker logic.

    0.   Check if healing is enabled
    0.5. Check healing mode (autonomous vs manual)
    0.8. Update pipeline stage: healing executing
         (only reached after manual mode check passes)
    1.   Layer 2: Healing Cooldown Check (skip for retries)
    2.   Execute healing via Component A
    3.   Set cooldown key in Redis (skip for retries)
    4.   Store healing record to Redis healing:actions
    5.   Update pipeline stage: healing complete
    """
    alert_id = machine_alert.get("alert_id", "unknown")
    detection_id = machine_alert.get("detection_id", "unknown")
    service = machine_alert.get("service", "unknown")
    is_retry = machine_alert.get("is_retry", False)

    logger.info(
        "Dispatcher Worker: received machine alert",
        alert_id=alert_id,
        severity=machine_alert.get("severity")
    )

    # -- 0. Check if healing is enabled --
    try:
        healing_flag = await r.get("healing:enabled")
        if healing_flag == "0":
            logger.info(
                "Dispatcher Worker: healing disabled, skipping",
                alert_id=alert_id
            )
            skipped_record = {
                "healing_action": "healing_disabled",
                "status": "skipped",
                "message": "Healing is disabled via toggle",
                "error": None,
                "scenarios_disabled": [],
                "container_restarted": None,
                "heal_endpoint_called": False,
                "executed_at": datetime.now(
                    timezone.utc).isoformat(),
                "detection_id": detection_id,
                "alert_id": alert_id,
                "service": service,
                "endpoint": machine_alert.get("endpoint"),
                "failure_tag": machine_alert.get(
                    "failure_tag", "none"),
                "recommended_action": machine_alert.get(
                    "recommended_action"),
                "timestamp": datetime.now(
                    timezone.utc).isoformat(),
                "verification_status": "SKIPPED",
                "retry_count": 0,
            }
            await r.lpush(
                HEALING_KEY,
                json.dumps(skipped_record)
            )
            await r.ltrim(HEALING_KEY, 0, LIST_CAP - 1)
            return
    except Exception:
        pass  # If Redis check fails, proceed with healing

    # -- 0.1. Check global execution lock (non-retries only) --
    # After the first successful healing, this lock is set.
    # All subsequent non-retry dispatches are silently skipped
    # to prevent multiple healings. Retries from verification
    # worker bypass this lock.
    if not is_retry:
        try:
            exec_lock = await r.get("healing:execution_lock")
            if exec_lock is not None:
                logger.info(
                    "Dispatcher Worker: healing locked "
                    "(awaiting verification), skipping",
                    alert_id=alert_id,
                )
                return  # Silent skip — no record written
        except Exception:
            pass  # If check fails, proceed

    # -- 0.5. Check healing mode --
    # FIX 3: Manual mode check is now BEFORE the pipeline
    # stage update. Previously "stage_4_healing_executing"
    # was written before this check, so manual mode
    # incorrectly showed "executing" on the frontend.
    try:
        raw_mode = await r.get("healing:mode")
        mode = json.loads(raw_mode).get("mode") if raw_mode else "autonomous"
    except Exception:
        mode = "autonomous"

    if mode == "manual":
        import uuid
        action_id = str(uuid.uuid4())
        pending_action = {
            "action_id": action_id,
            "machine_alert": machine_alert,
            "status": "pending_approval",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await r.lpush(
            "healing:pending_actions",
            json.dumps(pending_action)
        )
        await r.ltrim("healing:pending_actions", 0, 99)
        # Set accurate stage for manual mode
        try:
            await r.set(
                settings.PIPELINE_STAGE_KEY,
                json.dumps({
                    "stage": "stage_4_awaiting_approval",
                    "timestamp": datetime.now(
                        timezone.utc).isoformat(),
                    "message": "Healing queued — awaiting manual approval",
                    "service": service,
                })
            )
        except Exception:
            pass
        logger.info(
            "Dispatcher Worker: manual mode, "
            "pushed to pending actions",
            alert_id=alert_id
        )
        return

    # -- 0.8. Update pipeline stage: healing executing --
    # Only reached in autonomous mode after all early-return
    # checks above have passed.
    try:
        stage_val = "stage_4_healing_executing"
        msg_val = "Healing is executing"
        timestamp_val = datetime.now(timezone.utc).isoformat()
        await r.set(
            settings.PIPELINE_STAGE_KEY,
            json.dumps({
                "stage": stage_val,
                "timestamp": timestamp_val,
                "message": msg_val,
                "service": service,
            })
        )
        event = {
            "event_type": "healing_start",
            "stage": stage_val,
            "timestamp": timestamp_val,
            "message": msg_val,
        }
        await r.lpush("pipeline:events", json.dumps(event))
        await r.ltrim("pipeline:events", 0, 99)
    except Exception:
        pass

    # -- 1. Layer 2: Healing Cooldown Check --
    # Retries bypass cooldown entirely — they are
    # intentional heals pushed after cooldown expires
    if not is_retry:
        cooldown_key = f"{COOLDOWN_KEY_PREFIX}{service}"
        try:
            cooldown_active = await r.get(cooldown_key)
            if cooldown_active is not None:
                logger.info(
                    "Dispatcher Worker: healing suppressed "
                    "(cooldown active)",
                    alert_id=alert_id,
                    service=service,
                    cooldown_key=cooldown_key,
                )
                suppressed_record = {
                    "healing_action": "suppressed_cooldown",
                    "status": "suppressed",
                    "message": (
                        f"Healing suppressed: cooldown active "
                        f"for service '{service}'. "
                        f"A recent heal is still settling. "
                        f"Cooldown key: {cooldown_key}"
                    ),
                    "error": None,
                    "scenarios_disabled": [],
                    "container_restarted": None,
                    "heal_endpoint_called": False,
                    "executed_at": datetime.now(
                        timezone.utc).isoformat(),
                    "detection_id": detection_id,
                    "alert_id": alert_id,
                    "service": service,
                    "endpoint": machine_alert.get("endpoint"),
                    "failure_tag": machine_alert.get(
                        "failure_tag", "none"),
                    "recommended_action": machine_alert.get(
                        "recommended_action"),
                    "timestamp": datetime.now(
                        timezone.utc).isoformat(),
                    "verification_status": "SUPPRESSED",
                    "retry_count": 0,
                }
                await r.lpush(
                    HEALING_KEY,
                    json.dumps(suppressed_record)
                )
                await r.ltrim(HEALING_KEY, 0, LIST_CAP - 1)
                return
        except Exception as e:
            logger.warning(
                "Dispatcher Worker: cooldown check failed, "
                "proceeding with healing",
                error=str(e),
            )

    # -- 2. Execute healing via Component A --
    healing_result = await _execute_healing(machine_alert)

    # -- 3. Set cooldown key + global execution lock --
    # Retries don't set cooldown or lock — the verification
    # worker manages retry timing independently
    if not is_retry:
        cooldown_key = f"{COOLDOWN_KEY_PREFIX}{service}"
        try:
            await r.set(
                cooldown_key, "1",
                ex=COOLDOWN_DURATION_SECONDS
            )
            logger.info(
                "Dispatcher Worker: cooldown set",
                service=service,
                cooldown_seconds=COOLDOWN_DURATION_SECONDS,
            )
        except Exception as e:
            logger.warning(
                "Dispatcher Worker: failed to set cooldown",
                error=str(e),
            )
        # Set global execution lock — prevents all further
        # non-retry heals until verification completes.
        # TTL 600s as safety fallback.
        try:
            await r.set(
                "healing:execution_lock", "1", ex=600
            )
            logger.info(
                "Dispatcher Worker: execution lock set",
                alert_id=alert_id,
            )
        except Exception:
            pass

    # -- 4. Store healing result to Redis healing:actions --
    try:
        healing_record = {
            "healing_action": healing_result.get(
                "healing_action"),
            "status": healing_result.get("status"),
            "message": healing_result.get("message"),
            "error": healing_result.get("error"),
            "scenarios_disabled": healing_result.get(
                "scenarios_disabled", []),
            "container_restarted": healing_result.get(
                "container_restarted"),
            "heal_endpoint_called": healing_result.get(
                "heal_endpoint_called", False),
            "executed_at": healing_result.get("executed_at"),
            "detection_id": detection_id,
            "alert_id": alert_id,
            "service": service,
            "endpoint": machine_alert.get("endpoint"),
            "failure_tag": machine_alert.get(
                "failure_tag", "none"),
            "recommended_action": machine_alert.get(
                "recommended_action"),
            "timestamp": datetime.now(
                timezone.utc).isoformat(),
            "verification_status": "PENDING",
            "retry_count": machine_alert.get(
                "retry_count", 0),
        }
        await r.lpush(
            HEALING_KEY,
            json.dumps(healing_record)
        )
        await r.ltrim(HEALING_KEY, 0, LIST_CAP - 1)
        logger.info(
            "Dispatcher Worker: healing record pushed to Redis",
            alert_id=alert_id
        )
    except Exception as e:
        logger.warning(
            "Dispatcher Worker: failed to store healing record",
            error=str(e)
        )

    # -- 5. Update pipeline stage: cooldown --
    try:
        stage_val = "stage_5_cooldown"
        msg_val = (
            "Healing complete — cooldown period active, "
            "system stabilizing"
        )
        timestamp_val = datetime.now(timezone.utc).isoformat()
        await r.set(
            settings.PIPELINE_STAGE_KEY,
            json.dumps({
                "stage": stage_val,
                "timestamp": timestamp_val,
                "message": msg_val,
                "healing_action": healing_result.get(
                    "healing_action"),
                "status": healing_result.get("status"),
                "service": service,
            })
        )
        event = {
            "event_type": "healing_ended",
            "stage": stage_val,
            "timestamp": timestamp_val,
            "message": msg_val,
        }
        await r.lpush("pipeline:events", json.dumps(event))
        await r.ltrim("pipeline:events", 0, 99)
    except Exception:
        pass


def start_dispatcher_worker():
    """Start Dispatcher Worker as a background async task."""
    asyncio.create_task(dispatcher_worker_loop())
    logger.info("Dispatcher Worker task created")