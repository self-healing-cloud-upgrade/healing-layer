"""
Detection Worker — Async Pipeline Loop

Consumes normalized logs from Redis observation:pending_detection,
runs the detection service, and handles all storage dispatch:

    If anomaly:
        → Redis: observation:anomalies (capped 1000)
        → Redis: anomaly_stats:type + anomaly_stats:endpoint
        → OpenSearch: b-anomaly-records
        → Redis: analyser:pending (queue for Analyser Worker)
          ** Batched via 30s tumbling window to prevent storm **

    If healthy:
        → OpenSearch: b-healthy-logs (lightweight record)

No SQLite. No dead Redis keys.
"""
import asyncio
import json
import time
import structlog
from datetime import datetime, timezone
from app.core.config import settings
from app.core.redis_client import get_async_redis
from app.detection.index import detection_service
# from app.healing.index import healing_service
# HEALING COMMENTED OUT: Component A healing actions
# not yet finalized. Uncomment when Component A
# design is complete.
from app.ingestion.opensearch_client import opensearch_writer
# from app.reporting.report_generator import generate_incident_report
# REPORT GENERATION MOVED: Now handled by Analyser Worker.

logger = structlog.get_logger(__name__)

# Redis Key Ownership for this worker:
# WRITES:
#   observation:anomalies  - anomaly feed for API
#   anomaly_stats:type     - stats hash for API
#   anomaly_stats:endpoint - stats hash for API
#   analyser:pending       - queue to Analyser Worker
#
# DOES NOT WRITE (written by RabbitMQ consumer):
#   observation:logs       - raw log feed for API
#   observation:pending_detection - detection queue
#
# DOES NOT WRITE (written by verification worker):
#   escalation:alerts      - escalation feed for API
#
# DOES NOT WRITE (written by Dispatcher Worker):
#   dispatcher:pending     - queue to Dispatcher Worker
#   healing:actions        - updated by Dispatcher Worker
#
# This separation is intentional. Each worker owns
# its own write responsibilities.

# Redis key names
PENDING_DETECTION_KEY = "observation:pending_detection"
ANOMALIES_KEY = "observation:anomalies"
ANALYSER_QUEUE_KEY = "analyser:pending"
STATS_TYPE_KEY = "anomaly_stats:type"
STATS_ENDPOINT_KEY = "anomaly_stats:endpoint"
LIST_CAP = 1000

# Tumbling window for anomaly batching (prevents
# pipeline stage storm from individual anomalies)
DETECTION_WINDOW_SECONDS = 30


async def detection_worker_loop():
    """
    Main async loop — pops logs from Redis, runs detection,
    dispatches results to Redis + OpenSearch.

    Uses a 30-second tumbling window to batch anomalies before
    pushing to the analyser queue. This prevents every individual
    anomaly from triggering a full pipeline run and causing
    rapid back-and-forth stage transitions in the UI.

    Automatically reconnects if the Redis connection goes stale.
    """
    logger.info("Detection Worker started")
    r = await get_async_redis()

    # Tumbling window state for anomaly batching
    window_start_time = time.time()
    anomaly_buffer: list = []

    while True:
        try:
            # Non-blocking pop to avoid uvicorn/aioredis brpop deadlock bug
            result = await r.lpop(PENDING_DETECTION_KEY)
            if result is None:
                # Check if window elapsed even when idle
                elapsed = time.time() - window_start_time
                if elapsed >= DETECTION_WINDOW_SECONDS and anomaly_buffer:
                    await _flush_anomaly_window(r, anomaly_buffer)
                    anomaly_buffer = []
                    window_start_time = time.time()
                await asyncio.sleep(0.5)
                continue
                
            raw = result
            try:
                log = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Detection worker: unparseable message", raw=str(raw)[:200])
                continue

            # ── Run Detection (pure function — no side effects) ──
            detection_result = detection_service.detect_anomaly(log)

            # Carry method forward from the source log.
            # detect_anomaly does not include method in its output
            # but the frontend AnomalyLog type expects it.
            if "method" not in detection_result:
                detection_result["method"] = log.get("method", "")

            if detection_result["is_anomaly"]:
                await _handle_anomaly(r, detection_result, anomaly_buffer)
            else:
                _handle_healthy(detection_result)

            # Check if the tumbling window has elapsed
            elapsed = time.time() - window_start_time
            if elapsed >= DETECTION_WINDOW_SECONDS and anomaly_buffer:
                await _flush_anomaly_window(r, anomaly_buffer)
                anomaly_buffer = []
                window_start_time = time.time()

        except asyncio.CancelledError:
            logger.info("Detection worker cancelled")
            break
        except (ConnectionError, OSError) as e:
            logger.warning(
                "Detection worker: Redis connection lost, reconnecting",
                error=str(e)
            )
            try:
                await r.aclose()
            except Exception:
                pass
            await asyncio.sleep(2)
            r = await get_async_redis()
        except Exception as e:
            logger.error("Detection worker error", error=str(e))
            # Reconnect on any unexpected error to avoid stuck loops
            try:
                await r.aclose()
            except Exception:
                pass
            await asyncio.sleep(2)
            r = await get_async_redis()


async def _handle_anomaly(r, detection_result: dict, anomaly_buffer: list):
    """
    Handle a detected anomaly:
        1. Push to Redis anomalies list (immediate — feeds UI)
        2. Update Redis stats (immediate)
        3. Write to OpenSearch b-anomaly-records (immediate)
        4. Buffer for analyser queue (deferred to window flush)

    The analyser queue push and pipeline stage update are
    DEFERRED to the tumbling window flush (_flush_anomaly_window).
    This prevents every individual anomaly from triggering a
    full pipeline run.
    """
    # ── 1. Causal Engine moved to Analyser Worker ──
    ai_analysis = None  # will be set by Analyser Worker

    # ── 2. Healing Engine (COMMENTED OUT) ──
    # Component A healing actions not yet finalized.
    healing_result = None  # placeholder until A is designed

    # ── 3. Push to Redis: observation:anomalies (immediate — feeds frontend) ──
    try:
        anomaly_json = json.dumps(detection_result)
        await r.lpush(ANOMALIES_KEY, anomaly_json)
        await r.ltrim(ANOMALIES_KEY, 0, LIST_CAP - 1)
    except Exception as e:
        logger.warning("Failed to push anomaly to Redis", error=str(e))

    # ── 4. Update Redis stats (immediate) ──
    try:
        reasons = detection_result.get("anomaly_reasons", [])
        if reasons:
            await r.hincrby(STATS_TYPE_KEY, reasons[0], 1)
        endpoint = detection_result.get("endpoint", "unknown")
        await r.hincrby(STATS_ENDPOINT_KEY, endpoint, 1)
    except Exception as e:
        logger.warning("Failed to update Redis stats", error=str(e))

    # ── 5. Write to OpenSearch: b-anomaly-records (immediate) ──
    try:
        opensearch_writer.write_anomaly_record(detection_result)
    except Exception as e:
        logger.warning("Failed to write anomaly to OpenSearch", error=str(e))

    # ── 6. Buffer for analyser queue (DEFERRED) ──
    # Instead of pushing to analyser immediately (which caused
    # rapid pipeline stage switching), we buffer anomalies.
    # The tumbling window flush will select the representative
    # anomaly and push only that one to the analyser queue.
    anomaly_buffer.append(detection_result)
    logger.info(
        "Detection worker: anomaly buffered",
        buffer_size=len(anomaly_buffer),
        detection_id=detection_result.get("detection_id", "unknown"),
    )


async def _flush_anomaly_window(r, anomaly_buffer: list):
    """
    Flush the anomaly tumbling window.

    Selects the highest-scored anomaly as the representative
    and pushes only that one to the Analyser Worker queue.
    Updates the pipeline stage exactly once.

    This prevents the rapid back-and-forth stage transitions
    that happened when every individual anomaly triggered a
    full pipeline run.
    """
    batch_size = len(anomaly_buffer)
    if batch_size == 0:
        return

    logger.info(
        "Detection worker: flushing anomaly window",
        anomalies_in_window=batch_size,
    )

    # Pick the highest-scored anomaly as representative
    representative = max(
        anomaly_buffer,
        key=lambda a: a.get("anomaly_score", 0)
    )

    # Tag representative with batch context
    representative["batch_size"] = batch_size
    if batch_size > 1:
        representative["batch_note"] = (
            f"Representative of {batch_size} anomalies "
            f"detected in {DETECTION_WINDOW_SECONDS}s window"
        )

    # ── Push representative to Analyser Worker queue ──
    try:
        await r.rpush(
            ANALYSER_QUEUE_KEY,
            json.dumps(representative)
        )
        logger.info(
            "Detection worker: representative anomaly pushed to analyser",
            detection_id=representative.get("detection_id", "unknown"),
            anomaly_score=representative.get("anomaly_score"),
            batch_size=batch_size,
        )
    except Exception as e:
        logger.warning(
            "Failed to push to Analyser Worker queue",
            error=str(e)
        )

    # ── Update pipeline stage ONCE for the whole batch ──
    try:
        stage_val = "stage_2_complete"
        msg_val = (
            f"Detection complete — {batch_size} anomal"
            f"{'y' if batch_size == 1 else 'ies'} "
            f"detected, analysis starting"
        )
        timestamp_val = datetime.now(timezone.utc).isoformat()
        await r.set(
            settings.PIPELINE_STAGE_KEY,
            json.dumps({
                "stage": stage_val,
                "timestamp": timestamp_val,
                "message": msg_val,
                "service": representative.get("service"),
                "severity": representative.get("severity"),
                "failure_tag": representative.get(
                    "failure_tag", "none"),
                "anomaly_score": representative.get(
                    "anomaly_score"),
                "batch_size": batch_size,
            })
        )
        # Push single pipeline event for the batch
        event = {
            "event_type": "detection_complete",
            "stage": stage_val,
            "timestamp": timestamp_val,
            "message": msg_val,
        }
        await r.lpush("pipeline:events", json.dumps(event))
        await r.ltrim("pipeline:events", 0, 99)
    except Exception:
        pass

    # ── Report generation moved to Analyser Worker ──
    # Incident reports are now generated by the
    # Analyser Worker after causal analysis completes.


def _handle_healthy(detection_result: dict):
    """Write lightweight healthy record to OpenSearch only."""
    try:
        healthy_record = {
            "timestamp": detection_result.get("timestamp"),
            "service": detection_result.get("service"),
            "endpoint": detection_result.get("endpoint"),
            "status_code": detection_result.get("status_code"),
            "response_time_ms": detection_result.get("response_time_ms"),
        }
        opensearch_writer.write_healthy_log(healthy_record)
    except Exception as e:
        logger.warning("Failed to write healthy log to OpenSearch", error=str(e))


def start_detection_worker():
    """Start the detection worker as a background async task."""
    asyncio.create_task(detection_worker_loop())
    logger.info("Detection worker task created")
