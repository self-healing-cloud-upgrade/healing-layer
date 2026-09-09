"""
OpenSearch Client — Non-blocking Writer + Reader

Provides non-blocking writes to OpenSearch for the detection pipeline
and read methods for the verification worker and history API endpoints.

All writes are dispatched to a background thread pool so the main
detection pipeline is never blocked by storage latency or failures.

Six indices are managed (all crave- prefixed):
    - crave-raw-logs        : Exact raw messages from RabbitMQ
    - crave-normalized-logs : All normalized log entries (Stage 1 output)
    - crave-anomaly-records : Full enriched anomaly detections (Stage 2)
    - crave-healthy-logs    : Lightweight healthy log records (Stage 2)
    - crave-incident-reports: Incident reports from Analyser Worker
    - crave-healed-reports  : Healed incident reports after verification
"""
import structlog
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from opensearchpy import OpenSearch, exceptions as os_exceptions
from app.core.config import settings

logger = structlog.get_logger(__name__)

# Index mappings — keyed by settings values at module load time
def _build_index_mappings() -> Dict[str, Any]:
    return {
        settings.OPENSEARCH_INDEX_RAW_LOGS: {
            "mappings": {
                "properties": {
                    "received_at": {"type": "date"},
                    "raw_payload": {"type": "text"},
                    "queue": {"type": "keyword"},
                }
            }
        },
        settings.OPENSEARCH_INDEX_NORMALIZED: {
            "mappings": {
                "properties": {
                    "timestamp": {"type": "date"},
                    "service": {"type": "keyword"},
                    "endpoint": {"type": "keyword"},
                    "method": {"type": "keyword"},
                    "status_code": {"type": "integer"},
                    "response_time_ms": {"type": "float"},
                    "failure_tag": {"type": "keyword"},
                    "request_id": {"type": "keyword"},
                    "raw": {"type": "text"},
                    "is_malformed": {"type": "boolean"},
                    "incomplete_fields": {"type": "keyword"},
                }
            }
        },
        settings.OPENSEARCH_INDEX_ANOMALIES: {
            "mappings": {
                "properties": {
                    "detection_id": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "service": {"type": "keyword"},
                    "endpoint": {"type": "keyword"},
                    "method": {"type": "keyword"},
                    "status_code": {"type": "integer"},
                    "response_time_ms": {"type": "float"},
                    "failure_tag": {"type": "keyword"},
                    "engines_triggered": {"type": "keyword"},
                    "anomaly_reasons": {"type": "keyword"},
                    "anomaly_score": {"type": "float"},
                    "severity": {"type": "keyword"},
                    "is_anomaly": {"type": "boolean"},
                    "requires_llm": {"type": "boolean"},
                    "ai_analysis": {"type": "object", "enabled": False},
                    "healing": {"type": "object", "enabled": False},
                }
            }
        },
        settings.OPENSEARCH_INDEX_HEALTHY: {
            "mappings": {
                "properties": {
                    "timestamp": {"type": "date"},
                    "service": {"type": "keyword"},
                    "endpoint": {"type": "keyword"},
                    "status_code": {"type": "integer"},
                    "response_time_ms": {"type": "float"},
                }
            }
        },
        settings.OPENSEARCH_INDEX_INCIDENTS: {
            "mappings": {
                "properties": {
                    "timestamp": {"type": "date"},
                    "detection_id": {"type": "keyword"},
                    "alert_id": {"type": "keyword"},
                    "service": {"type": "keyword"},
                    "endpoint": {"type": "keyword"},
                    "severity": {"type": "keyword"},
                    "anomaly_score": {"type": "float"},
                    "root_cause": {"type": "text"},
                    "healing_action": {"type": "keyword"},
                    "healing_status": {"type": "keyword"},
                    "verification_status": {"type": "keyword"},
                    "human_report": {"type": "text"},
                }
            }
        },
        settings.OPENSEARCH_INDEX_HEALED: {
            "mappings": {
                "properties": {
                    "detection_id": {"type": "keyword"},
                    "healed_at": {"type": "date"},
                    "time_to_heal_seconds": {"type": "float"},
                    "final_status": {"type": "keyword"},
                }
            }
        },
    }


class OpenSearchWriter:
    """
    Non-blocking OpenSearch writer + reader.

    Uses a thread pool to dispatch index operations so the detection
    pipeline is never blocked. All write failures are logged and swallowed.
    Read methods are synchronous and intended for API/verification use.
    """

    def __init__(self):
        self._client = None
        self._connected = False
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="opensearch")

    def _get_client(self) -> Optional[OpenSearch]:
        """Lazy-initialize the OpenSearch client."""
        if self._client is not None and self._connected:
            return self._client

        try:
            # pool_maxsize=20 prevents "Connection pool is full,
            # discarding connection" warnings under concurrent
            # write load from multiple async workers.
            auth = None
            if settings.OPENSEARCH_USER and settings.OPENSEARCH_PASSWORD:
                auth = (settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD)

            self._client = OpenSearch(
                hosts=[{
                    "host": settings.OPENSEARCH_HOST,
                    "port": settings.OPENSEARCH_PORT,
                }],
                http_auth=auth,
                pool_maxsize=20,
                http_compress=True,
                use_ssl=False,
                verify_certs=False,
                ssl_show_warn=False,
                timeout=10,
                max_retries=3,
                retry_on_timeout=True,
            )
            info = self._client.info()
            self._connected = True
            logger.info(
                "OpenSearch connected",
                version=info.get("version", {}).get("number", "unknown"),
            )
            return self._client
        except Exception as e:
            self._connected = False
            logger.warning("OpenSearch connection failed", error=str(e))
            return None

    # ── Index Management ──

    def ensure_indices(self) -> None:
        """Create all required indices if they don't already exist."""
        client = self._get_client()
        if not client:
            logger.warning("Cannot create indices — OpenSearch not available")
            return

        index_mappings = _build_index_mappings()
        for index_name, body in index_mappings.items():
            try:
                if not client.indices.exists(index=index_name):
                    client.indices.create(index=index_name, body=body)
                    logger.info("Created OpenSearch index", index=index_name)
                else:
                    logger.info("OpenSearch index already exists", index=index_name)
            except Exception as e:
                logger.error(
                    "Failed to create OpenSearch index",
                    index=index_name,
                    error=str(e),
                )

    # ── Write Methods (non-blocking via thread pool) ──

    def _write_document(self, index: str, document: Dict[str, Any]) -> None:
        """Synchronous write — runs inside the thread pool."""
        client = self._get_client()
        if not client:
            return
        try:
            client.index(index=index, body=document)
        except Exception as e:
            logger.error(
                "OpenSearch write failed",
                index=index,
                error=str(e),
                doc_keys=list(document.keys()),
            )

    def _update_by_query(self, index: str, body: dict) -> None:
        """Synchronous update_by_query — runs inside the thread pool."""
        client = self._get_client()
        if not client:
            return
        try:
            client.update_by_query(index=index, body=body)
        except Exception as e:
            logger.error(
                "OpenSearch update_by_query failed",
                index=index,
                error=str(e),
            )

    def write_raw_log(self, raw_message: str,
                      queue: str = "component-c-logs") -> None:
        """
        Writes the exact raw message received from
        RabbitMQ before any normalization occurs.
        Stored in crave-raw-logs for debugging and
        before/after comparison in the UI.
        """
        doc = {
            "received_at": datetime.now(timezone.utc).isoformat(),
            "raw_payload": raw_message,
            "queue": queue,
        }
        # Write async in thread pool, never block pipeline
        self._executor.submit(
            self._write_document,
            settings.OPENSEARCH_INDEX_RAW_LOGS,
            doc
        )

    def write_normalized_log(self, document: Dict[str, Any]) -> None:
        """Non-blocking write to crave-normalized-logs."""
        self._executor.submit(
            self._write_document,
            settings.OPENSEARCH_INDEX_NORMALIZED,
            document
        )

    def write_anomaly_record(self, document: Dict[str, Any]) -> None:
        """Non-blocking write to crave-anomaly-records."""
        self._executor.submit(
            self._write_document,
            settings.OPENSEARCH_INDEX_ANOMALIES,
            document
        )

    def write_healthy_log(self, document: Dict[str, Any]) -> None:
        """Non-blocking write to crave-healthy-logs."""
        self._executor.submit(
            self._write_document,
            settings.OPENSEARCH_INDEX_HEALTHY,
            document
        )

    def write_incident_report(self, document: Dict[str, Any]) -> None:
        """Non-blocking write to crave-incident-reports."""
        self._executor.submit(
            self._write_document,
            settings.OPENSEARCH_INDEX_INCIDENTS,
            document
        )

    def write_healed_report(self, report: dict) -> None:
        """
        Writes the CRAVE Anomaly Healed Report after
        successful verification. Stored permanently in
        crave-healed-reports.
        """
        self._executor.submit(
            self._write_document,
            settings.OPENSEARCH_INDEX_HEALED,
            report
        )

    def _update_incident_status(self, detection_id: str, status: str) -> None:
        """Synchronous update — runs inside the thread pool."""
        client = self._get_client()
        if not client:
            return

        body = {
            "script": {
                "source": "ctx._source.verification_status = params.status",
                "lang": "painless",
                "params": {"status": status}
            },
            "query": {
                "term": {"detection_id": detection_id}
            }
        }

        try:
            client.update_by_query(
                index=settings.OPENSEARCH_INDEX_INCIDENTS,
                body=body
            )
        except Exception as e:
            logger.error(
                "OpenSearch update_by_query failed",
                index=settings.OPENSEARCH_INDEX_INCIDENTS,
                error=str(e)
            )

    def update_incident_report_status(
        self, detection_id: str, status: str
    ) -> None:
        """Non-blocking update of verification_status in crave-incident-reports."""
        self._executor.submit(
            self._update_incident_status, detection_id, status
        )

    def update_incident_with_healing_result(
        self,
        detection_id: str,
        healing_result: dict,
        verification_status: str,
        failure_rate: float = None,
        attempts: int = None,
    ) -> None:
        """
        Updates crave-incident-reports document after
        healing and verification completes.
        Sets final status, healing details and outcome.
        """
        update_body = {
            "script": {
                "source": """
                    ctx._source.verification_status =
                        params.verification_status;
                    ctx._source.healing_action_taken =
                        params.healing_action;
                    ctx._source.healing_status =
                        params.healing_status;
                    ctx._source.scenarios_disabled =
                        params.scenarios_disabled;
                    ctx._source.container_restarted =
                        params.container_restarted;
                    if (params.failure_rate != null) {
                        ctx._source.failure_rate_after =
                            params.failure_rate;
                    }
                    if (params.attempts != null) {
                        ctx._source.total_attempts =
                            params.attempts;
                    }
                """,
                "lang": "painless",
                "params": {
                    "verification_status": verification_status,
                    "healing_action": healing_result.get("healing_action"),
                    "healing_status": healing_result.get("status"),
                    "scenarios_disabled": healing_result.get(
                        "scenarios_disabled", []
                    ),
                    "container_restarted": healing_result.get(
                        "container_restarted"
                    ),
                    "failure_rate": failure_rate,
                    "attempts": attempts,
                }
            },
            "query": {
                "term": {
                    "detection_id": detection_id
                }
            }
        }
        self._executor.submit(
            self._update_by_query,
            settings.OPENSEARCH_INDEX_INCIDENTS,
            update_body
        )

    # ── Read Methods (synchronous, for API + verification worker) ──

    def _search(self, index: str, body: dict, size: int = 100) -> List[Dict]:
        """Execute a search query and return the hits as a list of dicts."""
        client = self._get_client()
        if not client:
            return []
        try:
            result = client.search(index=index, body=body, size=size)
            return [hit["_source"] for hit in result["hits"]["hits"]]
        except Exception as e:
            logger.warning("OpenSearch search failed", index=index, error=str(e))
            return []

    def get_recent_logs(
        self, service: Optional[str] = None, limit: int = 100
    ) -> List[Dict]:
        """
        Query crave-normalized-logs, optionally filter by service,
        sort by timestamp descending, return last N entries.
        """
        query: Dict[str, Any] = {"match_all": {}}
        if service:
            query = {"term": {"service": service}}

        body = {
            "query": query,
            "sort": [{"timestamp": {"order": "desc"}}],
        }
        return self._search(
            settings.OPENSEARCH_INDEX_NORMALIZED, body, size=limit
        )

    def get_anomaly_history(
        self, service: Optional[str] = None, limit: int = 100
    ) -> List[Dict]:
        """
        Query crave-anomaly-records, optionally filter by service,
        sort by timestamp descending.
        """
        query: Dict[str, Any] = {"match_all": {}}
        if service:
            query = {"term": {"service": service}}

        body = {
            "query": query,
            "sort": [{"timestamp": {"order": "desc"}}],
        }
        return self._search(
            settings.OPENSEARCH_INDEX_ANOMALIES, body, size=limit
        )

    def get_logs_after_timestamp(
        self,
        service: Optional[str],
        endpoint: Optional[str],
        timestamp: str,
        service_prefix: Optional[str] = None,
    ) -> List[Dict]:
        """
        Query crave-normalized-logs for entries after a given timestamp.

        Filtering modes:
            service_prefix — prefix query on service field (e.g. "crave-")
                             Used after healing a CRAVE service to check
                             all crave-* endpoints simultaneously.
            service + endpoint — exact term match (single service/endpoint)
            timestamp only  — all logs after timestamp (no service filter)

        Used by the verification worker to check if anomaly signals
        persist after a healing action.
        """
        must_clauses: list = [
            {"range": {"timestamp": {"gt": timestamp}}}
        ]

        if service_prefix:
            # Widen to all services matching prefix (e.g. all crave-*)
            must_clauses.append(
                {"prefix": {"service": service_prefix}}
            )
        elif service:
            must_clauses.append({"term": {"service": service}})
            if endpoint:
                must_clauses.append({"term": {"endpoint": endpoint}})

        body = {
            "query": {
                "bool": {
                    "must": must_clauses
                }
            },
            "sort": [{"timestamp": {"order": "asc"}}],
        }
        return self._search(
            settings.OPENSEARCH_INDEX_NORMALIZED, body, size=50
        )

    def get_incident_reports(self, limit: int = 50) -> List[Dict]:
        """Fetch the most recent incident reports."""
        query = {
            "query": {"match_all": {}},
            "sort": [{"timestamp": {"order": "desc"}}]
        }
        return self._search(
            settings.OPENSEARCH_INDEX_INCIDENTS, query, size=limit
        )

    def get_raw_logs(self, limit: int = 100) -> list:
        """
        Fetch recent raw logs from crave-raw-logs index.
        Sorted by received_at descending.
        """
        try:
            body = {
                "query": {"match_all": {}},
                "sort": [{"received_at": {"order": "desc"}}],
                "size": limit,
            }
            return self._search(
                settings.OPENSEARCH_INDEX_RAW_LOGS, body, size=limit
            )
        except Exception as e:
            logger.warning(
                "Failed to fetch raw logs from OpenSearch",
                error=str(e)
            )
            return []


# Singleton instance
opensearch_writer = OpenSearchWriter()
