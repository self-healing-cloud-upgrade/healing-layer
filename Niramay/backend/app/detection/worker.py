"""
Detection Worker — Async Pipeline Loop

Consumes normalized logs from Redis observation:pending_detection,
runs the detection service, and handles all storage dispatch:

    If anomaly:
        → Redis: observation:anomalies (capped 1000)
        → Redis: anomaly_stats:type + anomaly_stats:endpoint
        → OpenSearch: b-anomaly-records
        → Redis: analyser:pending (queue for Analyser Worker)

    If healthy:
        → OpenSearch: b-healthy-logs (lightweight record)

No SQLite. No dead Redis keys.
"""
import asyncio
import json
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


async def detection_worker_loop():
    """
    Main async loop — pops logs from Redis, runs detection,
    dispatches results to Redis + OpenSearch.

    Automatically reconnects if the Redis connection goes stale.
    """
    logger.info("Detection Worker started")
    r = await get_async_redis()

    while True:
        try:
            # Non-blocking pop to avoid uvicorn/aioredis brpop deadlock bug
            result = await r.lpop(PENDING_DETECTION_KEY)
            if result is None:
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
                await _handle_anomaly(r, detection_result)
            else:
                _handle_healthy(detection_result)

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


async def _handle_anomaly(r, detection_result: dict):
    """
    Handle a detected anomaly:
        1. Push to Redis anomalies list
        2. Update Redis stats
        3. Write to OpenSearch b-anomaly-records
        4. Push to Analyser Worker queue
    """
    # ── 1. Causal Engine moved to Analyser Worker ──
    # ai_analysis = None
    # if detection_result.get("requires_llm"):
    #     try:
    #         from app.causal_engine.client import analyze_anomaly
    #         ai_analysis = await analyze_anomaly(detection_result)
    #         detection_result["ai_analysis"] = ai_analysis
    #     except Exception as e:
    #         logger.warning("Causal engine failed", error=str(e))
    #         detection_result["ai_analysis"] = {
    #             "root_cause": "Analysis unavailable",
    #             "confidence": 0.0,
    #             "suggested_action": "none",
    #             "skipped": True,
    #             "reason": str(e),
    #         }
    ai_analysis = None  # will be set by Analyser Worker

    # ── 2. Healing Engine (COMMENTED OUT) ──
    # Component A healing actions not yet finalized.
    # Preserved for when Component A design is complete.
    # healing_result = None
    # try:
    #     action_key = healing_service.decide_healing_action(
    #         detection_result)
    #     healing_result = await healing_service.execute_healing(
    #         action_key, detection_result)
    #     detection_result["healing"] = healing_result
    # except Exception as e:
    #     logger.error("Healing engine failed", error=str(e))
    healing_result = None  # placeholder until A is designed

    # ── 3. Push to Redis: observation:anomalies ──
    try:
        anomaly_json = json.dumps(detection_result)
        await r.lpush(ANOMALIES_KEY, anomaly_json)
        await r.ltrim(ANOMALIES_KEY, 0, LIST_CAP - 1)
    except Exception as e:
        logger.warning("Failed to push anomaly to Redis", error=str(e))

    # ── 4. Update Redis stats ──
    try:
        reasons = detection_result.get("anomaly_reasons", [])
        if reasons:
            await r.hincrby(STATS_TYPE_KEY, reasons[0], 1)
        endpoint = detection_result.get("endpoint", "unknown")
        await r.hincrby(STATS_ENDPOINT_KEY, endpoint, 1)
    except Exception as e:
        logger.warning("Failed to update Redis stats", error=str(e))

    # ── 5. Write to OpenSearch: b-anomaly-records ──
    try:
        opensearch_writer.write_anomaly_record(detection_result)
    except Exception as e:
        logger.warning("Failed to write anomaly to OpenSearch", error=str(e))

    # ── 6. Push to Analyser Worker queue ──
    try:
        await r.rpush(
            ANALYSER_QUEUE_KEY,
            json.dumps(detection_result)
        )
    except Exception as e:
        logger.warning(
            "Failed to push to Analyser Worker queue",
            error=str(e)
        )

    # ── 7. Update pipeline stage ──
    try:
        await r.set(
            settings.PIPELINE_STAGE_KEY,
            json.dumps({
                "stage": "stage_2_complete",
                "timestamp": datetime.now(
                    timezone.utc).isoformat(),
                "message": "Anomaly detected, analysis starting",
                "service": detection_result.get("service"),
                "severity": detection_result.get("severity"),
                "failure_tag": detection_result.get(
                    "failure_tag", "none"),
                "anomaly_score": detection_result.get(
                    "anomaly_score"),
            })
        )
    except Exception:
        pass

    # ── 7. Healing result storage (COMMENTED OUT) ──
    # Will be re-enabled when Component A is designed.
    # if healing_result and healing_result.get(
    #     "status") != "skipped":
    #     try:
    #         healing_json = json.dumps(healing_result)
    #         await r.lpush(HEALING_KEY, healing_json)
    #         await r.ltrim(HEALING_KEY, 0, LIST_CAP - 1)
    #     except Exception as e:
    #         logger.warning("Failed to push healing to Redis", error=str(e))
    #
    #     try:
    #         healing_record = {
    #             **healing_result,
    #             "service": detection_result.get("service"),
    #             "endpoint": detection_result.get("endpoint"),
    #             "detection_id": detection_result.get("detection_id"),
    #         }
    #         opensearch_writer.write_healing_record(healing_record)
    #     except Exception as e:
    #         logger.warning("Failed to write healing to OpenSearch", error=str(e))

    # ── 8. Report generation moved to Analyser Worker ──
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
