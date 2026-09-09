"""
OpenSearch Client — Non-blocking Writer + Reader

Provides non-blocking writes to OpenSearch for the detection pipeline
and read methods for the verification worker and history API endpoints.

All writes are dispatched to a background thread pool so the main
detection pipeline is never blocked by storage latency or failures.

Four indices are managed:
    - b-normalized-logs   : All normalized log entries (Stage 1 output)
    - b-anomaly-records   : Full enriched anomaly detections (Stage 2)
    - b-healthy-logs      : Lightweight healthy log records (Stage 2)
    - b-healing-records   : Healing action results (Stage 3)
"""
import structlog
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List
from opensearchpy import OpenSearch, exceptions as os_exceptions
from app.core.config import settings

logger = structlog.get_logger(__name__)

# Index names
INDEX_NORMALIZED_LOGS = "b-normalized-logs"
INDEX_ANOMALY_RECORDS = "b-anomaly-records"
INDEX_HEALTHY_LOGS = "b-healthy-logs"
INDEX_HEALING_RECORDS = "b-healing-records"
INDEX_INCIDENT_REPORTS = "b-incident-reports"

# Index mappings
_INDEX_MAPPINGS = {
    INDEX_NORMALIZED_LOGS: {
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
    INDEX_ANOMALY_RECORDS: {
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
    INDEX_HEALTHY_LOGS: {
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
    INDEX_HEALING_RECORDS: {
        "mappings": {
            "properties": {
                "timestamp": {"type": "date"},
                "service": {"type": "keyword"},
                "endpoint": {"type": "keyword"},
                "healing_action": {"type": "keyword"},
                "status": {"type": "keyword"},
                "message": {"type": "text"},
                "verification_status": {"type": "keyword"},
                "detection_id": {"type": "keyword"},
            }
        }
    },
    INDEX_INCIDENT_REPORTS: {
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
            self._client = OpenSearch(
                hosts=[{
                    "host": settings.OPENSEARCH_HOST,
                    "port": settings.OPENSEARCH_PORT,
                }],
                http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
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

        for index_name, body in _INDEX_MAPPINGS.items():
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

    def write_normalized_log(self, document: Dict[str, Any]) -> None:
        """Non-blocking write to b-normalized-logs."""
        self._executor.submit(self._write_document, INDEX_NORMALIZED_LOGS, document)

    def write_anomaly_record(self, document: Dict[str, Any]) -> None:
        """Non-blocking write to b-anomaly-records."""
        self._executor.submit(self._write_document, INDEX_ANOMALY_RECORDS, document)

    def write_healthy_log(self, document: Dict[str, Any]) -> None:
        """Non-blocking write to b-healthy-logs."""
        self._executor.submit(self._write_document, INDEX_HEALTHY_LOGS, document)

    def write_healing_record(self, document: Dict[str, Any]) -> None:
        """Non-blocking write to b-healing-records."""
        self._executor.submit(self._write_document, INDEX_HEALING_RECORDS, document)

    def write_incident_report(self, document: Dict[str, Any]) -> None:
        """Non-blocking write to b-incident-reports."""
        self._executor.submit(self._write_document, INDEX_INCIDENT_REPORTS, document)

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
            client.update_by_query(index=INDEX_INCIDENT_REPORTS, body=body)
        except Exception as e:
            logger.error("OpenSearch update_by_query failed", index=INDEX_INCIDENT_REPORTS, error=str(e))

    def update_incident_report_status(self, detection_id: str, status: str) -> None:
        """Non-blocking update of verification_status in b-incident-reports."""
        self._executor.submit(self._update_incident_status, detection_id, status)

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

    def get_recent_logs(self, service: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        Query b-normalized-logs, optionally filter by service,
        sort by timestamp descending, return last N entries.
        """
        query: Dict[str, Any] = {"match_all": {}}
        if service:
            query = {"term": {"service": service}}

        body = {
            "query": query,
            "sort": [{"timestamp": {"order": "desc"}}],
        }
        return self._search(INDEX_NORMALIZED_LOGS, body, size=limit)

    def get_anomaly_history(self, service: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        Query b-anomaly-records, optionally filter by service,
        sort by timestamp descending.
        """
        query: Dict[str, Any] = {"match_all": {}}
        if service:
            query = {"term": {"service": service}}

        body = {
            "query": query,
            "sort": [{"timestamp": {"order": "desc"}}],
        }
        return self._search(INDEX_ANOMALY_RECORDS, body, size=limit)

    def get_logs_after_timestamp(
        self, service: str, endpoint: str, timestamp: str
    ) -> List[Dict]:
        """
        Query b-normalized-logs for entries from a specific service
        and endpoint after a given timestamp.
        Used by the verification worker to check if anomaly signals
        persist after a healing action.
        """
        body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"service": service}},
                        {"term": {"endpoint": endpoint}},
                        {"range": {"timestamp": {"gt": timestamp}}},
                    ]
                }
            },
            "sort": [{"timestamp": {"order": "asc"}}],
        }
        return self._search(INDEX_NORMALIZED_LOGS, body, size=50)

    def get_incident_reports(self, limit: int = 50) -> List[Dict]:
        """Fetch the most recent incident reports."""
        query = {
            "query": {"match_all": {}},
            "sort": [{"timestamp": {"order": "desc"}}]
        }
        return self._search(INDEX_INCIDENT_REPORTS, query, size=limit)


# Singleton instance
opensearch_writer = OpenSearchWriter()
