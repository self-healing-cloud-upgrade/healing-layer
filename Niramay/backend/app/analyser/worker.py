"""
Analyser Worker: LLM Classification and Report Generation

Consumes anomaly objects from Redis analyser:pending queue.
For every anomaly:
    1. Runs causal engine (LLM or rule fallback)
    2. Generates human readable incident report
    3. Generates machine readable alert object
    4. Stores both to Redis and OpenSearch
    5. Pushes machine alert to Dispatcher Worker queue
       (placeholder)

This is where all AI analysis and reporting lives.
The Detection Worker (Stage 2) only detects and scores.
The Analyser Worker understands and reports.
"""
import asyncio
import json
import structlog
from datetime import datetime, timezone
from app.core.config import settings
from app.core.redis_client import get_async_redis
from app.causal_engine.client import analyze_anomaly
from app.reporting.report_generator import generate_incident_report
from app.ingestion.opensearch_client import opensearch_writer

logger = structlog.get_logger(__name__)

# Redis keys
ANALYSER_QUEUE_KEY = "analyser:pending"
INCIDENT_REPORTS_KEY = "incident:reports"
DISPATCHER_QUEUE_KEY = "dispatcher:pending"
LIST_CAP = 1000


async def analyser_worker_loop():
    """
    Main async loop for the Analyser Worker.
    Pops anomaly objects from analyser:pending queue,
    runs causal analysis, generates reports, dispatches
    to Dispatcher Worker.

    Automatically reconnects if the Redis connection goes stale.
    """
    logger.info("Analyser Worker started")
    r = await get_async_redis()

    while True:
        try:
            # Non-blocking pop to avoid uvicorn/aioredis brpop deadlock bug
            result = await r.lpop(ANALYSER_QUEUE_KEY)
            if result is None:
                await asyncio.sleep(0.5)
                continue
                
            raw = result
            try:
                detection_result = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "Analyser Worker: unparseable message",
                    raw=str(raw)[:200]
                )
                continue

            await _handle_analyser(r, detection_result)

        except asyncio.CancelledError:
            logger.info("Analyser Worker cancelled")
            break
        except (ConnectionError, OSError) as e:
            logger.warning(
                "Analyser Worker: Redis connection lost, reconnecting",
                error=str(e)
            )
            try:
                await r.aclose()
            except Exception:
                pass
            await asyncio.sleep(2)
            r = await get_async_redis()
        except Exception as e:
            logger.error("Analyser Worker error", error=str(e))
            try:
                await r.aclose()
            except Exception:
                pass
            await asyncio.sleep(2)
            r = await get_async_redis()


async def _handle_analyser(r, detection_result: dict):
    """
    Core Analyser Worker logic:
        1. Run causal engine (always, LLM or fallback)
        2. Generate incident report
        3. Store to Redis and OpenSearch
        4. Push machine alert to Dispatcher Worker queue
    """
    detection_id = detection_result.get("detection_id", "unknown")

    # -- 0. Update pipeline stage: causal engine starting --
    try:
        stage_val = "stage_3_causal_engine_running"
        msg_val = "AI causal analysis running"
        timestamp_val = datetime.now(timezone.utc).isoformat()
        await r.set(
            settings.PIPELINE_STAGE_KEY,
            json.dumps({
                "stage": stage_val,
                "timestamp": timestamp_val,
                "message": msg_val,
                "detection_id": detection_id,
            })
        )
        event = {
            "event_type": "analysis_started",
            "stage": stage_val,
            "timestamp": timestamp_val,
            "message": msg_val,
        }
        await r.lpush("pipeline:events", json.dumps(event))
        await r.ltrim("pipeline:events", 0, 99)
    except Exception:
        pass

    # -- 1. Run Causal Engine --
    # Always runs. Uses LLM if requires_llm is True,
    # falls back to rule-based analysis otherwise.
    ai_analysis = {}
    try:
        if detection_result.get("requires_llm"):
            logger.info(
                "Analyser Worker: running LLM causal analysis",
                detection_id=detection_id
            )
            ai_analysis = await analyze_anomaly(detection_result)
        else:
            logger.info(
                "Analyser Worker: running rule-based causal analysis",
                detection_id=detection_id
            )
            from app.causal_engine.client import causal_engine
            ai_analysis = causal_engine._rule_based_fallback(
                detection_result
            )
    except Exception as e:
        logger.warning(
            "Analyser Worker: causal engine failed",
            error=str(e)
        )
        ai_analysis = {
            "root_cause": "Analysis unavailable",
            "confidence": 0.0,
            "suggested_action": "none",
            "skipped": True,
            "reason": str(e),
        }

    # Attach ai_analysis to detection_result for report
    detection_result["ai_analysis"] = ai_analysis

    # -- 2. Generate Incident Report --
    # heal_data is empty because healing has not happened yet.
    # Verification worker will update status after A acts.
    heal_data = {
        "healing_action": "pending",
        "status": "pending",
        "message": "Awaiting Component A remediation.",
        "verification_status": "PENDING",
    }

    try:
        incident_report = generate_incident_report(
            detection_result, ai_analysis, heal_data
        )
    except Exception as e:
        logger.error(
            "Analyser Worker: report generation failed",
            error=str(e)
        )
        incident_report = {
            "human_report": f"Report generation failed: {str(e)}",
            "machine_alert": {},
            "detection_id": detection_id,
            "service": detection_result.get("service"),
            "severity": detection_result.get("severity"),
            "verification_status": "PENDING",
        }

    # -- 3. Store incident report to Redis --
    try:
        report_json = json.dumps(incident_report)
        await r.lpush(INCIDENT_REPORTS_KEY, report_json)
        await r.ltrim(INCIDENT_REPORTS_KEY, 0, LIST_CAP - 1)
    except Exception as e:
        logger.warning(
            "Analyser Worker: failed to push report to Redis",
            error=str(e)
        )

    # -- 4. Store incident report to OpenSearch --
    try:
        opensearch_writer.write_incident_report(incident_report)
    except Exception as e:
        logger.warning(
            "Analyser Worker: failed to write report to OpenSearch",
            error=str(e)
        )

    # -- 5. Push machine alert to Dispatcher Worker queue --
    try:
        machine_alert = incident_report.get("machine_alert", {})
        if machine_alert:
            await r.rpush(
                DISPATCHER_QUEUE_KEY,
                json.dumps(machine_alert)
            )
        logger.info(
            "Analyser Worker: complete",
            detection_id=detection_id,
            analysis_type=ai_analysis.get("analysis_type"),
            severity=detection_result.get("severity")
        )
    except Exception as e:
        logger.warning(
            "Analyser Worker: failed to push to "
            "Dispatcher Worker queue",
            error=str(e)
        )

    # -- 6. Update pipeline stage: analysis complete --
    try:
        stage_val = "stage_3_complete"
        msg_val = "Analysis complete, healing initiated"
        timestamp_val = datetime.now(timezone.utc).isoformat()
        await r.set(
            settings.PIPELINE_STAGE_KEY,
            json.dumps({
                "stage": stage_val,
                "timestamp": timestamp_val,
                "message": msg_val,
                "recommended_action": ai_analysis.get(
                    "suggested_action"),
                "service": detection_result.get("service"),
                "failure_tag": detection_result.get(
                    "failure_tag", "none"),
            })
        )
        event = {
            "event_type": "analysis_complete",
            "stage": stage_val,
            "timestamp": timestamp_val,
            "message": msg_val,
        }
        await r.lpush("pipeline:events", json.dumps(event))
        await r.ltrim("pipeline:events", 0, 99)
    except Exception:
        pass


def start_analyser_worker():
    """Start Analyser Worker as a background async task."""
    asyncio.create_task(analyser_worker_loop())
    logger.info("Analyser Worker task created")
