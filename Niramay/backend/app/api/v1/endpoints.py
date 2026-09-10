"""
Consolidated API Routes for the Healing Layer

All data endpoints read from Redis (real-time) or OpenSearch (history).
Niramay monitors CRAVE — no failure simulation in this service.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Query, Request, BackgroundTasks, HTTPException, Path
from typing import List, Dict, Any, Optional
import json
import hashlib
import structlog
import httpx
import uuid
import io
import csv as csv_module
from fastapi.responses import StreamingResponse
from app.core.config import settings
from app.core.redis_client import redis_client
from app.ingestion.opensearch_client import opensearch_writer

logger = structlog.get_logger(__name__)

router = APIRouter()

# ── Healing toggle state (in-memory, resets on restart — starts OFF) ──
_healing_enabled = False


# ──────────────────────────────────────────────────────────────────────────────
# CONSUMER CONTROL — Start/Stop/Status RabbitMQ consumer
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/consumer/start", tags=["Consumer Control"])
async def start_consumer():
    """Start the RabbitMQ consumer."""
    from app.ingestion.rabbitmq_consumer import start_rabbitmq_consumer, get_consumer_status
    start_rabbitmq_consumer()
    return {"success": True, "status": get_consumer_status()}


@router.post("/consumer/stop", tags=["Consumer Control"])
async def stop_consumer():
    """Stop the RabbitMQ consumer."""
    from app.ingestion.rabbitmq_consumer import stop_rabbitmq_consumer, get_consumer_status
    stop_rabbitmq_consumer()
    return {"success": True, "status": get_consumer_status()}


@router.get("/consumer/status", tags=["Consumer Control"])
async def consumer_status():
    """Get current consumer status."""
    from app.ingestion.rabbitmq_consumer import get_consumer_status
    return get_consumer_status()


@router.get("/consumer/events", tags=["Consumer Control"])
async def consumer_events(limit: int = Query(50, ge=1, le=200)):
    """Get recent consumer lifecycle events (connected, errors, etc.)."""
    try:
        data = redis_client.lrange("consumer:events", 0, limit - 1)
        return [json.loads(x) for x in data]
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────────
# HEALING TOGGLE — Enable/Disable healing execution
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/healing/enabled", tags=["Healing Control"])
async def get_healing_enabled():
    """Check if healing is enabled."""
    return {"enabled": _healing_enabled}


@router.post("/healing/toggle", tags=["Healing Control"])
async def toggle_healing(request: Request):
    """Toggle healing on/off."""
    global _healing_enabled
    try:
        body = await request.json()
        _healing_enabled = bool(body.get("enabled", not _healing_enabled))
    except Exception:
        _healing_enabled = not _healing_enabled

    # Store in Redis so dispatcher worker can check
    try:
        redis_client.set("healing:enabled", "1" if _healing_enabled else "0")
    except Exception:
        pass

    return {"enabled": _healing_enabled}


# ──────────────────────────────────────────────────────────────────────────────
# OBSERVATION LAYER — Real-time + History
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/observation/logs", tags=["Observation"])
async def get_observation_logs(
    limit: int = Query(100, ge=1, le=1000, description="Number of logs to return"),
):
    try:
        data = redis_client.lrange("observation:logs", 0, limit - 1)
        logs = [json.loads(x) for x in data]
        # Add a fingerprint so frontend can detect actual data changes
        fingerprint = hashlib.md5(
            json.dumps([l.get("request_id", l.get("timestamp", "")) for l in logs[:10]]).encode()
        ).hexdigest()[:12]
        return {"logs": logs, "fingerprint": fingerprint, "count": len(logs)}
    except Exception:
        return {"logs": [], "fingerprint": "empty", "count": 0}


@router.get("/observation/logs/raw", tags=["Observation"])
async def get_raw_logs(limit: int = 100):
    try:
        logs = opensearch_writer.get_raw_logs(limit=limit)
        return logs
    except Exception as e:
        logger.warning("Failed to fetch raw logs", error=str(e))
        return []


@router.get("/observation/logs/history", tags=["Observation"])
async def get_observation_logs_history(
    service: Optional[str] = Query(None, description="Filter by service name"),
    limit: int = Query(500, ge=1, le=5000, description="Number of logs to return"),
):
    return opensearch_writer.get_recent_logs(service=service, limit=limit)


@router.get("/pipeline/stage", tags=["Pipeline"])
async def get_pipeline_stage():
    try:
        raw = redis_client.get(settings.PIPELINE_STAGE_KEY)
        if raw:
            stage_data = json.loads(raw)
            # Add staleness check: if stage timestamp is >60s old
            # and stage is not a terminal state, mark as idle
            ts = stage_data.get("timestamp")
            if ts:
                try:
                    stage_time = datetime.fromisoformat(
                        ts.replace("Z", "+00:00"))
                    elapsed = (
                        datetime.now(timezone.utc) - stage_time
                    ).total_seconds()
                    stage = stage_data.get("stage", "")
                    terminal_stages = {
                        "healing_complete",
                        "healing_failed_escalated",
                        "healing_failed_email_sent",
                    }
                    if elapsed > 60 and stage not in terminal_stages:
                        stage_data["stale"] = True
                except Exception:
                    pass
            return stage_data
        return {
            "stage": "idle",
            "message": "No active pipeline processing",
            "timestamp": None,
        }
    except Exception as e:
        logger.warning("Failed to read pipeline stage", error=str(e))
        return {
            "stage": "unknown",
            "message": str(e),
            "timestamp": None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# DETECTION LAYER — Real-time + History
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/detection/anomalies", tags=["Detection"])
async def get_anomalies(limit: int = Query(50, ge=1, le=1000)):
    try:
        data = redis_client.lrange("observation:anomalies", 0, limit - 1)
        anomalies = [json.loads(x) for x in data]
        fingerprint = hashlib.md5(
            json.dumps([a.get("detection_id", a.get("timestamp", "")) for a in anomalies[:10]]).encode()
        ).hexdigest()[:12]
        return {"anomalies": anomalies, "fingerprint": fingerprint, "count": len(anomalies)}
    except Exception:
        return {"anomalies": [], "fingerprint": "empty", "count": 0}


@router.get("/detection/anomalies/history", tags=["Detection"])
async def get_anomaly_history(
    service: Optional[str] = Query(None, description="Filter by service name"),
    limit: int = Query(200, ge=1, le=2000),
):
    return opensearch_writer.get_anomaly_history(service=service, limit=limit)


@router.get("/stats", tags=["Dashboard"])
async def get_system_stats():
    try:
        total_logs = redis_client.llen("observation:logs")
        by_type = {}
        by_endpoint = {}

        try:
            raw_types = redis_client.hgetall("anomaly_stats:type")
            by_type = {k: int(v) for k, v in raw_types.items()}
        except Exception:
            pass

        try:
            raw_endpoints = redis_client.hgetall("anomaly_stats:endpoint")
            by_endpoint = {k: int(v) for k, v in raw_endpoints.items()}
        except Exception:
            pass

        total_anomaly_count = sum(by_type.values()) if by_type else 0

        try:
            if total_logs == 0:
                health_score = 100.0
            else:
                capped = min(total_anomaly_count, total_logs * 10)
                raw_rate = capped / (total_logs * 10)
                health_score = round(max(0.0, (1 - raw_rate) * 100), 1)
        except Exception:
            health_score = 100.0

        return {
            "total_logs": total_logs,
            "total_anomalies": total_anomaly_count,
            "health_score": health_score,
            "by_endpoint": by_endpoint,
            "by_type": by_type,
            "healing_enabled": _healing_enabled,
        }
    except Exception:
        return {
            "total_logs": 0,
            "total_anomalies": 0,
            "health_score": 100.0,
            "by_endpoint": {},
            "by_type": {},
            "healing_enabled": _healing_enabled,
        }


# ──────────────────────────────────────────────────────────────────────────────
# HEALING LAYER
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/healing/actions", tags=["Healing"])
async def get_healing_actions(limit: int = Query(50, ge=1, le=1000)):
    try:
        data = redis_client.lrange("healing:actions", 0, limit - 1)
        actions = [json.loads(x) for x in data]
        fingerprint = hashlib.md5(
            json.dumps([a.get("alert_id", a.get("timestamp", "")) for a in actions[:10]]).encode()
        ).hexdigest()[:12]
        return {"actions": actions, "fingerprint": fingerprint, "count": len(actions)}
    except Exception:
        return {"actions": [], "fingerprint": "empty", "count": 0}


# ──────────────────────────────────────────────────────────────────────────────
# ESCALATION EMAIL SETTINGS
# ──────────────────────────────────────────────────────────────────────────────

ESCALATION_EMAIL_REDIS_KEY = "escalation:email_to"


@router.get("/escalation/email", tags=["Escalation"])
async def get_escalation_email():
    """Get the currently configured escalation email address."""
    try:
        email = redis_client.get(ESCALATION_EMAIL_REDIS_KEY)
        return {"email": email or ""}
    except Exception:
        return {"email": ""}


@router.post("/escalation/email", tags=["Escalation"])
async def set_escalation_email(request: Request):
    """
    Set the developer email address for escalation alerts.
    When healing fails after 3 attempts, an email is sent
    to this address.
    """
    try:
        body = await request.json()
        email = body.get("email", "").strip()
        if not email:
            return {"success": False, "error": "Email address is required"}
        # Basic validation
        if "@" not in email or "." not in email:
            return {"success": False, "error": "Invalid email address"}
        redis_client.set(ESCALATION_EMAIL_REDIS_KEY, email)
        logger.info("Escalation email updated", email=email)
        return {"success": True, "email": email}
    except Exception as e:
        logger.error("Failed to set escalation email", error=str(e))
        return {"success": False, "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# ESCALATION ALERTS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/escalations", tags=["Healing"])
async def get_escalation_alerts(limit: int = Query(50, ge=1, le=100)):
    try:
        data = redis_client.lrange("escalation:alerts", 0, limit - 1)
        return [json.loads(x) for x in data]
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────────
# INCIDENT REPORTS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/incident/reports", tags=["Incidents"])
async def get_incident_reports(limit: int = Query(50, ge=1, le=1000)):
    try:
        data = redis_client.lrange("incident:reports", 0, limit - 1)
        return [json.loads(x) for x in data]
    except Exception:
        return []


@router.get("/incident/reports/history", tags=["Incidents"])
async def get_incident_reports_history(limit: int = Query(200, ge=1, le=2000)):
    return opensearch_writer.get_incident_reports(limit=limit)


# ──────────────────────────────────────────────────────────────────────────────
# DEMO CONTROL — Triggers failures in CRAVE (not Niramay)
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/demo/trigger-failure", tags=["Demo Control"])
async def trigger_failure(request: Request):
    """
    Triggers a failure scenario in CRAVE via its API.
    Niramay does not simulate failures itself — it monitors CRAVE.
    """
    try:
        body = await request.json()
        scenario = body.get("scenario", "database_error")

        async with httpx.AsyncClient(timeout=10.0) as client:
            login = await client.post(
                f"{settings.CRAVE_BACKEND_URL}/api/v1/auth/login",
                json={
                    "email": settings.CRAVE_DEVELOPER_EMAIL,
                    "password": settings.CRAVE_DEVELOPER_PASSWORD,
                },
            )
            if login.status_code != 200:
                return {
                    "success": False,
                    "error": "CRAVE auth failed",
                    "status_code": login.status_code,
                }
            token = login.json().get("access_token")

            enable = await client.post(
                f"{settings.CRAVE_BACKEND_URL}/api/v1/failure-simulator/scenarios/{scenario}/enable",
                headers={"Authorization": f"Bearer {token}"},
            )
            return {
                "success": enable.status_code == 200,
                "scenario": scenario,
                "response": enable.json() if enable.status_code == 200 else enable.text[:200],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# HEALING MODE — Feature 6: Autonomous vs Manual selection
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/healing/mode", tags=["Healing Control"])
async def get_healing_mode():
    """Return the current healing mode (autonomous/manual) and when it was set."""
    try:
        raw = redis_client.get("healing:mode")
        if raw:
            return json.loads(raw)
        return {"mode": None, "set_at": None}
    except Exception:
        return {"mode": None, "set_at": None}


@router.post("/healing/mode", tags=["Healing Control"])
async def set_healing_mode(request: Request):
    """
    Set healing mode to 'autonomous' or 'manual'.
    Called by the HealingModeModal when the user makes a selection.
    Stores result in Redis key healing:mode.
    """
    try:
        body = await request.json()
        mode = body.get("mode")
        if mode not in ("autonomous", "manual"):
            raise HTTPException(status_code=422, detail="mode must be 'autonomous' or 'manual'")
        payload = {"mode": mode, "set_at": datetime.now(timezone.utc).isoformat()}
        redis_client.set("healing:mode", json.dumps(payload))
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/healing/pending", tags=["Healing Control"])
async def get_pending_healing_actions(limit: int = Query(20, ge=1, le=100)):
    """
    Return pending manual healing actions awaiting user approval.
    Used by ManualHealingPanel when mode='manual'.
    """
    try:
        data = redis_client.lrange("healing:pending_actions", 0, limit - 1)
        return [json.loads(x) for x in data]
    except Exception:
        return []


@router.post("/healing/pending/{action_id}/decision", tags=["Healing Control"])
async def decide_pending_action(action_id: str = Path(...), request: Request = None):
    """
    Approve or reject a pending manual healing action.
    Removes the action from the pending list and stores the decision.
    Body: { decision: 'approve' | 'reject' }
    """
    try:
        body = await request.json()
        decision = body.get("decision")
        if decision not in ("approve", "reject"):
            raise HTTPException(status_code=422, detail="decision must be 'approve' or 'reject'")

        # Find and remove the action from Redis list
        raw_actions = redis_client.lrange("healing:pending_actions", 0, -1)
        for raw in raw_actions:
            action = json.loads(raw)
            if action.get("action_id") == action_id:
                redis_client.lrem("healing:pending_actions", 1, raw)
                action["decision"] = decision
                action["decided_at"] = datetime.now(timezone.utc).isoformat()
                redis_client.lpush("healing:decisions", json.dumps(action))
                redis_client.ltrim("healing:decisions", 0, 199)
                return {"success": True, "action_id": action_id, "decision": decision}

        return {"success": False, "error": "Action not found"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE EVENTS — Feature 4: Live event feed history
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/pipeline/events", tags=["Pipeline"])
async def get_pipeline_events(limit: int = Query(20, ge=1, le=100)):
    """
    Return the last N pipeline stage transition events from Redis pipeline:events list.
    Each event: { event_type, stage, timestamp, message }.
    The detection/healing workers push to this list when stages change.
    """
    try:
        data = redis_client.lrange("pipeline:events", 0, limit - 1)
        return [json.loads(x) for x in data]
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────────────────────
# PAGINATED LOGS — Feature 1: Raw + Normalized log viewers
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/logs/raw", tags=["Logs"])
async def get_raw_logs_paginated(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    keyword: Optional[str] = Query(None),
    level: Optional[str] = Query(None, description="Comma-separated log levels"),
    from_ts: Optional[str] = Query(None, alias="from"),
    to_ts: Optional[str] = Query(None, alias="to"),
):
    """
    Paginated raw logs from crave-raw-logs OpenSearch index.
    Supports keyword search, level filter, and time-range filter.
    Returns { total, page, size, hits: [{ timestamp, source, message, level, traceId }] }.
    """
    try:
        client = opensearch_writer._get_client()
        if not client:
            return {"total": 0, "page": page, "size": size, "hits": []}

        must_clauses: List[Dict] = []

        if keyword:
            must_clauses.append({"multi_match": {"query": keyword, "fields": ["raw_payload", "queue"]}})

        if from_ts or to_ts:
            range_q: Dict[str, Any] = {}
            if from_ts:
                range_q["gte"] = from_ts
            if to_ts:
                range_q["lte"] = to_ts
            must_clauses.append({"range": {"received_at": range_q}})

        query = {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}}

        body = {
            "query": query,
            "sort": [{"received_at": {"order": "desc"}}],
            "from": (page - 1) * size,
            "size": size,
        }

        result = client.search(index=settings.OPENSEARCH_INDEX_RAW_LOGS, body=body)
        total = result["hits"]["total"]["value"] if isinstance(result["hits"]["total"], dict) else result["hits"]["total"]
        hits = []
        for h in result["hits"]["hits"]:
            src = h["_source"]
            hits.append({
                "timestamp": src.get("received_at", ""),
                "source": src.get("queue", "rabbitmq"),
                "message": src.get("raw_payload", "")[:500],
                "level": "INFO",
                "traceId": h.get("_id", ""),
                "_raw": src,
            })
        return {"total": total, "page": page, "size": size, "hits": hits}
    except Exception as e:
        logger.warning("Raw logs paginated fetch failed", error=str(e))
        return {"total": 0, "page": page, "size": size, "hits": []}


@router.get("/logs/normalized", tags=["Logs"])
async def get_normalized_logs_paginated(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    keyword: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, description="Min anomaly_score filter"),
    from_ts: Optional[str] = Query(None, alias="from"),
    to_ts: Optional[str] = Query(None, alias="to"),
):
    """
    Paginated normalized logs from crave-normalized-logs OpenSearch index.
    Additional field: anomaly_score (float).
    Returns { total, page, size, hits }.
    """
    try:
        client = opensearch_writer._get_client()
        if not client:
            return {"total": 0, "page": page, "size": size, "hits": []}

        must_clauses: List[Dict] = []

        if keyword:
            must_clauses.append({"multi_match": {"query": keyword, "fields": ["endpoint", "service", "failure_tag", "raw"]}})

        if level:
            levels = [l.strip().upper() for l in level.split(",")]
            status_ranges = []
            for lv in levels:
                if lv == "ERROR":
                    status_ranges.append({"range": {"status_code": {"gte": 500}}})
                elif lv == "WARN":
                    status_ranges.append({"range": {"status_code": {"gte": 400, "lt": 500}}})
                elif lv == "INFO":
                    status_ranges.append({"range": {"status_code": {"gte": 200, "lt": 400}}})
            if status_ranges:
                must_clauses.append({"bool": {"should": status_ranges}})

        if from_ts or to_ts:
            range_q: Dict[str, Any] = {}
            if from_ts:
                range_q["gte"] = from_ts
            if to_ts:
                range_q["lte"] = to_ts
            must_clauses.append({"range": {"timestamp": range_q}})

        if min_score is not None:
            must_clauses.append({"range": {"anomaly_score": {"gte": min_score}}})

        query = {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}}

        body = {
            "query": query,
            "sort": [{"timestamp": {"order": "desc"}}],
            "from": (page - 1) * size,
            "size": size,
        }

        result = client.search(index=settings.OPENSEARCH_INDEX_NORMALIZED, body=body)
        total = result["hits"]["total"]["value"] if isinstance(result["hits"]["total"], dict) else result["hits"]["total"]
        hits = [h["_source"] for h in result["hits"]["hits"]]
        return {"total": total, "page": page, "size": size, "hits": hits}
    except Exception as e:
        logger.warning("Normalized logs paginated fetch failed", error=str(e))
        return {"total": 0, "page": page, "size": size, "hits": []}


# ──────────────────────────────────────────────────────────────────────────────
# OPENSEARCH SEARCH PROXY — Feature 5b: Full-text search panel
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/opensearch/search", tags=["OpenSearch"])
async def opensearch_search(
    q: str = Query(..., description="Full-text search query"),
    index: str = Query("crave-normalized-logs"),
    size: int = Query(20, ge=1, le=100),
):
    """
    Full-text search across any crave-* OpenSearch index.
    Returns { total, hits: [{ _score, timestamp, snippet, _source }] }.
    """
    try:
        client = opensearch_writer._get_client()
        if not client:
            return {"total": 0, "hits": []}

        body = {
            "query": {
                "multi_match": {
                    "query": q,
                    "fields": ["*"],
                    "type": "best_fields",
                }
            },
            "size": size,
        }

        result = client.search(index=index, body=body)
        total = result["hits"]["total"]["value"] if isinstance(result["hits"]["total"], dict) else result["hits"]["total"]
        hits = []
        for h in result["hits"]["hits"]:
            src = h["_source"]
            # Build a short snippet from the most informative field
            snippet = src.get("raw_payload") or src.get("human_report") or src.get("failure_tag") or ""
            hits.append({
                "_score": h.get("_score", 0),
                "timestamp": src.get("timestamp") or src.get("received_at") or "",
                "snippet": str(snippet)[:200],
                "_source": src,
            })
        return {"total": total, "hits": hits}
    except Exception as e:
        logger.warning("OpenSearch search proxy failed", error=str(e))
        return {"total": 0, "hits": [], "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# ARTIFACT CARDS — Feature 2: Pipeline artifact index counts + records
# ──────────────────────────────────────────────────────────────────────────────

_ARTIFACT_INDICES = {
    "raw-logs": settings.OPENSEARCH_INDEX_RAW_LOGS,
    "anomaly-records": settings.OPENSEARCH_INDEX_ANOMALIES,
    "incident-reports": settings.OPENSEARCH_INDEX_INCIDENTS,
    "heal-report": settings.OPENSEARCH_INDEX_HEALED,
}

_ARTIFACT_SORT_FIELD = {
    "raw-logs": "received_at",
    "anomaly-records": "timestamp",
    "incident-reports": "timestamp",
    "heal-report": "healed_at",
}


@router.get("/artifacts/counts", tags=["Artifacts"])
async def get_artifact_counts():
    """
    Return record count + last-updated timestamp for all 4 pipeline artifact indices.
    Used by PipelineArtifactCards (auto-refreshes every 30s).
    """
    try:
        client = opensearch_writer._get_client()
        result = []
        for key, index in _ARTIFACT_INDICES.items():
            count = 0
            last_updated = None
            if client:
                try:
                    count_res = client.count(index=index, body={"query": {"match_all": {}}})
                    count = count_res.get("count", 0)
                    # Get last document timestamp
                    sort_field = _ARTIFACT_SORT_FIELD.get(key, "timestamp")
                    latest = client.search(
                        index=index,
                        body={"query": {"match_all": {}}, "sort": [{sort_field: {"order": "desc"}}], "size": 1},
                    )
                    if latest["hits"]["hits"]:
                        src = latest["hits"]["hits"][0]["_source"]
                        last_updated = src.get(sort_field)
                except Exception:
                    pass
            result.append({"key": key, "index": index, "count": count, "last_updated": last_updated})
        return result
    except Exception as e:
        logger.warning("Artifact counts fetch failed", error=str(e))
        return []


@router.get("/artifacts/{artifact_key}/records", tags=["Artifacts"])
async def get_artifact_records(
    artifact_key: str = Path(...),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=1000),
    keyword: Optional[str] = Query(None),
):
    """
    Paginated records from a pipeline artifact index.
    artifact_key: raw-logs | anomaly-records | incident-reports | heal-report
    """
    index = _ARTIFACT_INDICES.get(artifact_key)
    if not index:
        raise HTTPException(status_code=404, detail=f"Unknown artifact key: {artifact_key}")

    try:
        client = opensearch_writer._get_client()
        if not client:
            return {"total": 0, "page": page, "size": size, "hits": []}

        sort_field = _ARTIFACT_SORT_FIELD.get(artifact_key, "timestamp")
        must_clauses: List[Dict] = []
        if keyword:
            must_clauses.append({"multi_match": {"query": keyword, "fields": ["*"]}})

        query = {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}}
        body = {
            "query": query,
            "sort": [{sort_field: {"order": "desc"}}],
            "from": (page - 1) * size,
            "size": size,
        }
        result = client.search(index=index, body=body)
        total = result["hits"]["total"]["value"] if isinstance(result["hits"]["total"], dict) else result["hits"]["total"]
        hits = [h["_source"] for h in result["hits"]["hits"]]
        return {"total": total, "page": page, "size": size, "hits": hits}
    except Exception as e:
        logger.warning("Artifact records fetch failed", error=str(e))
        return {"total": 0, "page": page, "size": size, "hits": []}


# ──────────────────────────────────────────────────────────────────────────────
# REPORTS — Feature 3: Report generation + history
# ──────────────────────────────────────────────────────────────────────────────

def _generate_report_task(report_id: str, report_type: str, date_from: str,
                           date_to: str, severities: List[str], fmt: str) -> None:
    """
    Background task: queries OpenSearch for the requested report data,
    serialises to JSON/CSV, and stores in Redis reports:{report_id}.
    """
    try:
        client = opensearch_writer._get_client()
        rows: List[Dict] = []

        must_clauses: List[Dict] = [
            {"range": {"timestamp": {"gte": date_from, "lte": date_to}}}
        ]
        if severities:
            must_clauses.append({"terms": {"severity": [s.lower() for s in severities]}})

        query = {"bool": {"must": must_clauses}}

        if report_type in ("incident_summary", "full_pipeline"):
            rows += (client.search(
                index=settings.OPENSEARCH_INDEX_INCIDENTS,
                body={"query": query, "sort": [{"timestamp": {"order": "desc"}}], "size": 1000},
            )["hits"]["hits"]) if client else []

        if report_type in ("heal_summary", "full_pipeline"):
            heal_rows = (client.search(
                index=settings.OPENSEARCH_INDEX_HEALED,
                body={"query": {"match_all": {}}, "sort": [{"healed_at": {"order": "desc"}}], "size": 1000},
            )["hits"]["hits"]) if client else []
            rows += heal_rows

        sources = [h["_source"] for h in rows if isinstance(h, dict) and "_source" in h]

        if fmt == "csv" and sources:
            keys = list(sources[0].keys()) if sources else []
            buf = io.StringIO()
            w = csv_module.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            w.writerows(sources)
            content = buf.getvalue()
        else:
            content = json.dumps(sources, default=str)

        report_data = {
            "report_id": report_id,
            "report_type": report_type,
            "date_from": date_from,
            "date_to": date_to,
            "severities": severities,
            "format": fmt,
            "status": "ready",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "row_count": len(sources),
            "content": content,
        }
        redis_client.set(f"reports:{report_id}", json.dumps(report_data))
        # Update list entry status
        list_raw = redis_client.lrange("reports:list", 0, -1)
        for i, raw in enumerate(list_raw):
            entry = json.loads(raw)
            if entry.get("report_id") == report_id:
                entry["status"] = "ready"
                entry["generated_at"] = report_data["generated_at"]
                entry["row_count"] = len(sources)
                redis_client.lset("reports:list", i, json.dumps(entry))
                break
    except Exception as e:
        logger.error("Report generation failed", report_id=report_id, error=str(e))
        try:
            list_raw = redis_client.lrange("reports:list", 0, -1)
            for i, raw in enumerate(list_raw):
                entry = json.loads(raw)
                if entry.get("report_id") == report_id:
                    entry["status"] = "failed"
                    entry["error"] = str(e)
                    redis_client.lset("reports:list", i, json.dumps(entry))
                    break
        except Exception:
            pass


@router.post("/reports/generate", tags=["Reports"])
async def generate_report(request: Request, background_tasks: BackgroundTasks):
    """
    Schedule async report generation.
    Body: { report_type, date_from, date_to, severities, format }
    Returns { report_id, status: 'pending' } immediately.
    """
    try:
        body = await request.json()
        report_id = str(uuid.uuid4())
        report_type = body.get("report_type", "incident_summary")
        date_from = body.get("date_from", "now-7d")
        date_to = body.get("date_to", "now")
        severities = body.get("severities", [])
        fmt = body.get("format", "json")

        entry = {
            "report_id": report_id,
            "report_type": report_type,
            "date_from": date_from,
            "date_to": date_to,
            "severities": severities,
            "format": fmt,
            "status": "pending",
            "generated_at": None,
            "row_count": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        redis_client.lpush("reports:list", json.dumps(entry))
        redis_client.ltrim("reports:list", 0, 99)

        background_tasks.add_task(
            _generate_report_task, report_id, report_type, date_from, date_to, severities, fmt
        )
        return {"report_id": report_id, "status": "pending"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports", tags=["Reports"])
async def list_reports():
    """List all generated reports (newest first) from Redis reports:list."""
    try:
        data = redis_client.lrange("reports:list", 0, 99)
        return [json.loads(x) for x in data]
    except Exception:
        return []


@router.get("/reports/{report_id}/download", tags=["Reports"])
async def download_report(report_id: str = Path(...)):
    """
    Download a ready report by ID.
    Returns the serialised content (JSON string or CSV text).
    """
    try:
        raw = redis_client.get(f"reports:{report_id}")
        if not raw:
            raise HTTPException(status_code=404, detail="Report not found")
        data = json.loads(raw)
        if data.get("status") != "ready":
            raise HTTPException(status_code=409, detail=f"Report status is {data.get('status')}")

        content = data.get("content", "")
        fmt = data.get("format", "json")
        media_type = "text/csv" if fmt == "csv" else "application/json"
        filename = f"niramay_report_{report_id[:8]}.{fmt}"
        return StreamingResponse(
            io.StringIO(content),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# HEALED REPORTS — Stage 4 Crave Heal Reports from OpenSearch
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/healing/healed-reports", tags=["Reports"])
async def get_healed_reports(
    limit: int = Query(50, ge=1, le=500),
):
    """
    Return healed reports from OpenSearch crave-healed-reports index.
    These are generated by the Verification Worker when healing succeeds.
    """
    try:
        reports = opensearch_writer.get_healed_reports(limit=limit)
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# ANOMALY RECORDS HISTORY — Stage 2 Anomaly Records from OpenSearch
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/detection/anomalies/records", tags=["Detection"])
async def get_anomaly_records(
    limit: int = Query(50, ge=1, le=500),
    severity: Optional[str] = Query(None, description="Filter by severity"),
):
    """
    Return anomaly records from OpenSearch crave-anomaly-records index.
    These are the full enriched anomaly detections from Stage 2.
    """
    try:
        records = opensearch_writer.get_anomaly_records(
            limit=limit, severity=severity
        )
        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# INCIDENT REPORTS HISTORY — Stage 3 Incident Reports from OpenSearch
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/incident/reports/history", tags=["Reports"])
async def get_incident_reports_history(
    limit: int = Query(50, ge=1, le=500),
):
    """
    Return incident reports from OpenSearch crave-incident-reports index.
    These are generated by the Analyser Worker after causal analysis.
    """
    try:
        reports = opensearch_writer.get_incident_reports(limit=limit)
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))