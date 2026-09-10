"""
Application Configuration Settings
Standalone Niramay — Redis + RabbitMQ + OpenSearch (no SQLite/PostgreSQL)
"""
from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # App Info
    APP_NAME: str = "Niramay"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None


    # RabbitMQ (Stage 1 — log ingestion from Component C)
    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: Optional[str] = None
    RABBITMQ_PASSWORD: Optional[str] = None
    RABBITMQ_QUEUE: str = "component-c-logs"
    RABBITMQ_QUEUE_NAME: str = "component-c-logs"  # alias used by publisher/consumer

    # OpenSearch (permanent storage)
    OPENSEARCH_HOST: str = "localhost"
    OPENSEARCH_PORT: int = 9200
    OPENSEARCH_USER: Optional[str] = None
    OPENSEARCH_PASSWORD: Optional[str] = None

    # OpenSearch index names
    # All indices use crave- prefix to reflect
    # that data originates from CRAVE
    OPENSEARCH_INDEX_RAW_LOGS: str = "crave-raw-logs"
    OPENSEARCH_INDEX_NORMALIZED: str = "crave-normalized-logs"
    OPENSEARCH_INDEX_HEALTHY: str = "crave-healthy-logs"
    OPENSEARCH_INDEX_ANOMALIES: str = "crave-anomaly-records"
    OPENSEARCH_INDEX_INCIDENTS: str = "crave-incident-reports"
    OPENSEARCH_INDEX_HEALED: str = "crave-healed-reports"

    # CRAVE connection details
    # Component A uses these to call CRAVE heal endpoint
    CRAVE_BACKEND_URL: str = "http://crave-backend:8000"
    CRAVE_DEVELOPER_EMAIL: str = "developer@example.com"
    CRAVE_DEVELOPER_PASSWORD: str = "developer123"

    # ── K3s Cluster Settings ──────────────────────────────────────────────
    # K3s is a lightweight Kubernetes distribution.
    # All K3s healing strategies are DISABLED when K3S_ENABLED=false.
    # Set K3S_ENABLED=true only when running inside or alongside a K3s cluster.
    # Docker Compose + test suite always use K3S_ENABLED=false (default).
    K3S_ENABLED: bool = False

    # Namespace where Crave and Niramay Deployments live in K3s
    K3S_NAMESPACE: str = "selfhealing"

    # Name of the Crave backend Deployment in K3s
    # Must match metadata.name in k3s/crave-deployment.yaml
    K3S_CRAVE_DEPLOYMENT_NAME: str = "crave-backend"

    # True  = load in-cluster service account (Niramay running as a K3s pod)
    # False = load ~/.kube/config (local WSL2 dev with K3s installed)
    K3S_IN_CLUSTER: bool = True

    # Maximum replicas scale_up is allowed to set
    K3S_MAX_REPLICAS: int = 5

    # How many seconds circuit_breaker holds Deployment at 0 replicas
    K3S_CIRCUIT_BREAKER_DURATION_SECONDS: int = 30

    # Label selector to find the CRAVE Redis pod for flush_cache exec
    # Must match labels in k3s/crave-deployment.yaml
    # IMPORTANT: targets CRAVE's Redis, NOT Niramay's Redis
    K3S_CRAVE_REDIS_POD_LABEL: str = "app=crave-redis"

    # CRAVE internal K3s service URL
    # Used by Component A to call heal endpoint inside the cluster
    CRAVE_K3S_URL: str = (
        "http://crave-backend.selfhealing.svc.cluster.local:8000"
    )

    # Healing enabled key in Redis
    HEALING_ENABLED_KEY: str = "niramay:healing:enabled"

    # Whether to auto-enable healing on startup
    # Keep False for tests, set True in K3s deployment
    HEALING_AUTO_ENABLE_ON_STARTUP: bool = False

    # Email Escalation (SMTP)
    # Set SMTP_ENABLED=True and configure credentials to
    # receive email alerts when healing fails after 3 attempts
    SMTP_ENABLED: bool = False
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None  # Gmail App Password
    SMTP_FROM_EMAIL: str = "niramay-alerts@example.com"
    ESCALATION_EMAIL_TO: str = "developer@example.com"

    # Healing executor timeout
    COMPONENT_A_TIMEOUT_SECONDS: int = 30

    # Verification thresholds
    # Both conditions must be met for SUCCESS
    VERIFICATION_FAILURE_RATE_THRESHOLD: float = 0.10
    VERIFICATION_CLEAN_WINDOW_SECONDS: int = 30
    VERIFICATION_TOTAL_WINDOW_SECONDS: int = 60

    # Pipeline stage tracking
    PIPELINE_STAGE_KEY: str = "pipeline:stage:current"

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Failure Simulator Settings
    FAILURE_SIMULATOR_ENABLED: bool = True

    # Detection Layer Thresholds
    DETECTION_LATENCY_THRESHOLD_MS: float = 300.0

    # Rate Rule Settings
    DETECTION_RATE_WINDOW_SECONDS: float = 60.0   # Sliding window size (seconds)
    DETECTION_RATE_THRESHOLD: int = 50             # Max requests per endpoint per window

    # Silence Rule Settings (in-memory, existing)
    DETECTION_SILENCE_THRESHOLD_SECONDS: float = 30.0  # Silence gap to trigger (seconds)

    # Stage 2 — Rate-Based Engine (Redis-backed)
    RATE_BASED_ERROR_THRESHOLD: int = 5      # Errors in window before firing
    RATE_BASED_WINDOW_SECONDS: int = 60      # Rolling window size

    # Stage 2 — Silence Detection Engine (Redis-backed)
    SILENCE_THRESHOLD_SECONDS: int = 600     # Silence gap before firing
    SILENCE_CHECK_INTERVAL_SECONDS: int = 60 # Background check frequency

    # Stage 2 — Integer-based anomaly score threshold (for DetectionService)
    DETECTION_ANOMALY_SCORE_THRESHOLD: int = 3

    # Stage 2 — Baseline Anomaly Engine (Redis-backed)
    BASELINE_DEVIATION_FACTOR: float = 2.0   # Fire when RT > factor * baseline avg
    BASELINE_MIN_SAMPLES: int = 20           # Min samples before baseline is valid

    # Weights for different anomaly indicators (must sum to 1.0)
    DETECTION_WEIGHT_LATENCY: float = 0.25
    DETECTION_WEIGHT_STATUS: float = 0.25
    DETECTION_WEIGHT_FAILURE: float = 0.20
    DETECTION_WEIGHT_RATE: float = 0.15
    DETECTION_WEIGHT_SILENCE: float = 0.15

    # Normalized Anomaly Threshold (0.0 to 1.0)
    DETECTION_ANOMALY_THRESHOLD: float = 0.4

    # Traffic Generator
    TRAFFIC_GENERATOR_ENABLED: bool = True
    TRAFFIC_GENERATOR_INTERVAL_MS: int = 2000  # Generate a request every 2 seconds

    # Ollama / LLM Settings
    OLLAMA_URL: str = "http://localhost:11434/api/generate"
    OLLAMA_MODEL: str = "llama3.2"
    ENABLE_AI_CAUSAL: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
