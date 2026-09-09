"""
Dispatcher Worker: Alert Dispatch and Healing Execution

Receives machine alerts from the Analyser Worker via
dispatcher:pending queue and handles:
    1. Executing healing via Component A (HealingActionExecutor)
    2. Storing healing record to Redis healing:actions
    3. Updating pipeline stage for UI progress tracking
"""
import asyncio
import json
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


async def dispatcher_worker_loop():
    """
    Main async loop for the Dispatcher Worker.
    Pops machine alerts from dispatcher:pending queue
    and dispatches to Component A.

    Automatically reconnects if the Redis connection goes stale.
    """
    logger.info("Dispatcher Worker started")
    r = await get_async_redis()

    while True:
        try:
            # Non-blocking pop to avoid uvicorn/aioredis brpop deadlock bug
            result = await r.lpop(DISPATCHER_QUEUE_KEY)
            if result is None:
                await asyncio.sleep(0.5)
                continue
                
            raw = result
            try:
                machine_alert = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "Dispatcher Worker: unparseable message",
                    raw=str(raw)[:200]
                )
                continue

            await _handle_dispatcher(r, machine_alert)

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

    0. Check if healing is enabled
    1. Execute healing via Component A
    2. Store healing record to Redis healing:actions
    3. Update pipeline stage key
    """
    alert_id = machine_alert.get("alert_id", "unknown")
    detection_id = machine_alert.get("detection_id", "unknown")

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
            # Store a skipped record so the frontend sees it
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
                "service": machine_alert.get("service"),
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

    # -- 1. Execute healing via Component A --
    healing_result = await _execute_healing(machine_alert)

    # -- 2. Store healing result to Redis healing:actions --
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
            "service": machine_alert.get("service"),
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

    # -- 3. Update pipeline stage --
    try:
        await r.set(
            settings.PIPELINE_STAGE_KEY,
            json.dumps({
                "stage": "stage_4_healing_complete",
                "timestamp": datetime.now(
                    timezone.utc).isoformat(),
                "message": "Healing executed, "
                           "verification starting",
                "healing_action": healing_result.get(
                    "healing_action"),
                "status": healing_result.get("status"),
                "service": machine_alert.get("service"),
            })
        )
    except Exception:
        pass


def start_dispatcher_worker():
    """Start Dispatcher Worker as a background async task."""
    asyncio.create_task(dispatcher_worker_loop())
    logger.info("Dispatcher Worker task created")
