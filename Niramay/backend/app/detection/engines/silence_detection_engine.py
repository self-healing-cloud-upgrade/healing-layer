"""
Silence Detection Engine — Missing Signal / Timeout (Redis-backed)

Maintains a last-seen timestamp per service in Redis.
A background checker runs every SILENCE_CHECK_INTERVAL_SECONDS and
fires when a service has not produced a log for longer than
SILENCE_THRESHOLD_SECONDS.

Redis key format:  last_seen:{service}

The evaluate() method only updates the last-seen timestamp.
Actual firing happens in the background checker, which pushes
synthetic anomalies to the Redis anomaly queue and OpenSearch.
"""
import time
import json
import threading
import structlog
from typing import Dict, Any, List
from uuid import uuid4
from datetime import datetime, timezone
from app.detection.engines.base_engine import BaseEngine
from app.detection.rules.base import RuleResult
from app.core.config import settings

logger = structlog.get_logger(__name__)


class SilenceDetectionEngine(BaseEngine):
    """
    Redis-backed silence detection engine.

    evaluate() only updates the last_seen:{service} timestamp.
    Silence detection is performed by the background checker thread.
    """

    def __init__(
        self,
        silence_threshold: int = settings.SILENCE_THRESHOLD_SECONDS,
        check_interval: int = settings.SILENCE_CHECK_INTERVAL_SECONDS,
        score: int = 3,
    ):
        super().__init__(name="silence_detection_engine")
        self.silence_threshold = silence_threshold
        self.check_interval = check_interval
        self.score = score
        self._redis = None

    def _get_redis(self):
        """Lazy-load synchronous Redis client. Returns None if unavailable."""
        if self._redis is not None:
            return self._redis
        try:
            import redis
            self._redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            self._redis.ping()
            return self._redis
        except Exception as e:
            logger.warning("SilenceDetectionEngine: Redis unavailable", error=str(e))
            self._redis = None
            return None

    def evaluate(self, log: Dict[str, Any]) -> List[RuleResult]:
        """
        Update last-seen timestamp for the service.
        Does NOT fire inline — silence is detected by the background checker.
        Always returns an empty list.
        """
        service = log.get("service", "unknown")
        r = self._get_redis()
        if r is None:
            return []

        key = f"last_seen:{service}"
        try:
            r.set(key, str(time.time()))
        except Exception as e:
            logger.warning(
                "SilenceDetectionEngine: failed to update last_seen",
                service=service,
                error=str(e),
            )
            self._redis = None

        return []

    def check_silence(self) -> list:
        """
        Check all tracked services for silence violations.
        Returns a list of enriched anomaly dicts for silent services.
        """
        r = self._get_redis()
        if r is None:
            return []

        anomalies = []
        now = time.time()

        try:
            cursor = 0
            keys = []
            while True:
                cursor, batch = r.scan(cursor=cursor, match="last_seen:*", count=100)
                keys.extend(batch)
                if cursor == 0:
                    break

            if not keys:
                return []

            # N+1 optimization: use mget to fetch all last_seen values in one go
            last_seen_values = r.mget(keys)

            for key, last_seen_str in zip(keys, last_seen_values):
                try:
                    if last_seen_str is None:
                        continue

                    last_seen = float(last_seen_str)
                    gap = now - last_seen
                    service = key.replace("last_seen:", "", 1)

                    if gap > self.silence_threshold:
                        logger.info(
                            "Silence detected for service",
                            service=service,
                            gap_seconds=round(gap, 1),
                            threshold=self.silence_threshold,
                        )

                        anomaly = {
                            "detection_id": str(uuid4()),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "service": service,
                            "endpoint": "N/A",
                            "status_code": 0,
                            "response_time_ms": 0.0,
                            "failure_tag": "none",
                            "engines_triggered": ["silence_detection_engine"],
                            "anomaly_reasons": ["service_silence"],
                            "anomaly_score": self.score,
                            "severity": "medium",
                            "is_anomaly": True,
                            "requires_llm": False,
                        }
                        anomalies.append(anomaly)

                        # Update so we don't fire continuously
                        r.set(key, str(now))

                except Exception as e:
                    logger.warning("Error checking silence for key", key=key, error=str(e))

        except Exception as e:
            logger.warning("SilenceDetectionEngine: scan failed", error=str(e))
            self._redis = None

        return anomalies


# Singleton instance shared by detection pipeline and background checker
silence_engine = SilenceDetectionEngine()


def _silence_checker_loop():
    """
    Background loop that checks for silent services every N seconds.
    Dispatches anomalies to Redis observation:anomalies (frontend-visible)
    and OpenSearch b-anomaly-records (permanent).
    """
    from app.core.redis_client import get_sync_redis

    logger.info(
        "Silence checker started",
        interval=silence_engine.check_interval,
        threshold=silence_engine.silence_threshold,
    )

    while True:
        try:
            time.sleep(silence_engine.check_interval)
            anomalies = silence_engine.check_silence()

            if not anomalies:
                continue

            try:
                r = get_sync_redis()

                for anomaly in anomalies:
                    # Push to Redis observation:anomalies (frontend-visible)
                    try:
                        r.lpush("observation:anomalies", json.dumps(anomaly))
                        r.ltrim("observation:anomalies", 0, 999)
                    except Exception as e:
                        logger.error("Failed to push silence anomaly to Redis", error=str(e))

                    # Update stats
                    try:
                        r.hincrby("anomaly_stats:type", "service_silence", 1)
                        service = anomaly.get("service", "unknown")
                        r.hincrby("anomaly_stats:endpoint", f"{service}:silence", 1)
                    except Exception as e:
                        logger.warning("Failed to update silence stats", error=str(e))

                    # Write to OpenSearch
                    try:
                        from app.ingestion.opensearch_client import opensearch_writer
                        opensearch_writer.write_anomaly_record(anomaly)
                    except Exception as e:
                        logger.error("Failed to write silence anomaly to OpenSearch", error=str(e))

            except Exception as e:
                logger.warning("Silence checker: Redis unavailable for dispatch", error=str(e))

        except Exception as e:
            logger.error("Error in silence checker loop", error=str(e))
            time.sleep(5)


def start_silence_checker():
    """Start the silence checker in a background daemon thread."""
    thread = threading.Thread(
        target=_silence_checker_loop,
        name="silence-checker",
        daemon=True,
    )
    thread.start()
    logger.info("Silence checker thread started")

