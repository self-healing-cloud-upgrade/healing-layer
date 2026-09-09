"""
test_niramay_crave_integration.py
==================================
Integration test suite for the Niramay self-healing pipeline
using real Crave traffic as the log source.

Transition context
------------------
Previously, tests injected synthetic logs directly via Niramay's
POST /observe endpoint. Now Crave is the actual traffic source:
  crave-injector → crave-backend → ObservationMiddleware → RabbitMQ
  → Niramay Consumer Thread → Detection → Analyser → Dispatcher

This test suite:
  1. Calls Crave APIs directly to generate real HTTP traffic
  2. Enables RabbitMQ publishing on Crave (so logs reach Niramay)
  3. Validates each Niramay pipeline stage in order
  4. Respects async delays between pipeline stages

Environment variables
---------------------
  BASE_URL   : Niramay backend base URL  (default: http://niramay-backend:8000)
  CRAVE_URL  : Crave backend base URL    (default: http://crave-backend:8000)
  CRAVE_DEV_TOKEN : Crave developer bearer token (required for heal + toggle)

Async timing constants (tunable via env vars)
----------------------------------------------
  TRAFFIC_BURST_COUNT       : number of Crave requests to fire per burst (default: 20)
  RABBITMQ_SETTLE_SECONDS   : wait after enabling RabbitMQ toggle (default: 5)
  LOG_PROPAGATION_SECONDS   : wait for logs to reach Niramay Redis (default: 25)
  ANOMALY_PROPAGATION_SECONDS : wait for Detection Worker to process (default: 20)
  ANALYSER_PROPAGATION_SECONDS: wait for Analyser Worker to produce reports (default: 20)
  DISPATCHER_PROPAGATION_SECONDS: wait for Dispatcher Worker (default: 15)
  POLL_INTERVAL_SECONDS     : polling interval per endpoint (default: 3)
  POLL_MAX_RETRIES          : max polling attempts per check (default: 10)
"""

import os
import time
import random
import pytest
import requests

# ---------------------------------------------------------------------------
# Configuration — pulled from environment so the Jenkinsfile can override
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
CRAVE_URL = os.environ.get("CRAVE_URL", "http://localhost:8001").rstrip("/")
CRAVE_DEV_TOKEN = os.environ.get("CRAVE_DEV_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1IiwiZW1haWwiOiJkZXZlbG9wZXJAZXhhbXBsZS5jb20iLCJyb2xlIjoiZGV2ZWxvcGVyIiwiZXhwIjoxNzc3ODAyMjE5LCJ0eXBlIjoiYWNjZXNzIn0.JPPhmGb4QeAzOJcG_IFrmwFi7bz01HUGPagCGgOOqzo")

TRAFFIC_BURST_COUNT         = int(os.environ.get("TRAFFIC_BURST_COUNT", "20"))
RABBITMQ_SETTLE_SECONDS     = int(os.environ.get("RABBITMQ_SETTLE_SECONDS", "5"))
LOG_PROPAGATION_SECONDS     = int(os.environ.get("LOG_PROPAGATION_SECONDS", "25"))
ANOMALY_PROPAGATION_SECONDS = int(os.environ.get("ANOMALY_PROPAGATION_SECONDS", "20"))
ANALYSER_PROPAGATION_SECONDS= int(os.environ.get("ANALYSER_PROPAGATION_SECONDS", "20"))
DISPATCHER_PROPAGATION_SECONDS = int(os.environ.get("DISPATCHER_PROPAGATION_SECONDS", "15"))
POLL_INTERVAL_SECONDS       = int(os.environ.get("POLL_INTERVAL_SECONDS", "3"))
POLL_MAX_RETRIES            = int(os.environ.get("POLL_MAX_RETRIES", "10"))

# Crave developer auth header (used for toggling RabbitMQ and triggering heal)
CRAVE_AUTH_HEADERS = {}
if CRAVE_DEV_TOKEN:
    CRAVE_AUTH_HEADERS = {"Authorization": f"Bearer {CRAVE_DEV_TOKEN}"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _poll(description: str, fetch_fn, check_fn, wait_first: int = 0):
    """
    Poll an endpoint until check_fn(response_json) returns True, or timeout.

    Parameters
    ----------
    description   : human-readable label for error messages
    fetch_fn      : callable → requests.Response
    check_fn      : callable(json) → bool
    wait_first    : seconds to sleep before the first attempt
    """
    if wait_first:
        print(f"  [wait] sleeping {wait_first}s for async propagation ({description})")
        time.sleep(wait_first)

    for attempt in range(1, POLL_MAX_RETRIES + 1):
        try:
            resp = fetch_fn()
            resp.raise_for_status()
            data = resp.json()
            if check_fn(data):
                print(f"  [ok]   {description} — verified on attempt {attempt}")
                return data
        except Exception as exc:
            print(f"  [retry] {description} attempt {attempt}/{POLL_MAX_RETRIES}: {exc}")

        if attempt < POLL_MAX_RETRIES:
            time.sleep(POLL_INTERVAL_SECONDS)

    pytest.fail(
        f"Timeout: '{description}' did not satisfy condition after "
        f"{POLL_MAX_RETRIES} attempts × {POLL_INTERVAL_SECONDS}s "
        f"(+{wait_first}s initial wait)"
    )


def _crave_headers(auth: bool = False) -> dict:
    h = {"Content-Type": "application/json"}
    if auth and CRAVE_AUTH_HEADERS:
        h.update(CRAVE_AUTH_HEADERS)
    return h


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def enable_crave_rabbitmq_publishing():
    """
    Enable RabbitMQ publishing on Crave for the duration of the test session.
    This is the critical bridge: without it, Crave logs never reach Niramay.

    Crave docs state:
      POST /api/v1/failure-simulator/rabbitmq/enable   (developer-auth required)
    and the Redis key crave:rabbitmq:enabled is set to "1".

    If CRAVE_DEV_TOKEN is not set, we skip the toggle and assume publishing
    was manually enabled before the test run.
    """
    if not CRAVE_DEV_TOKEN:
        pytest.skip(
            "CRAVE_DEV_TOKEN not set — cannot enable RabbitMQ publishing. "
            "Enable it manually via the Crave developer UI before running tests."
        )

    toggle_url = f"{CRAVE_URL}/api/v1/failure-simulator/rabbitmq/enable"
    try:
        resp = requests.post(toggle_url, headers=_crave_headers(auth=True), timeout=10)
        resp.raise_for_status()
        print(f"\n[setup] Crave RabbitMQ publishing enabled: {resp.json()}")
    except Exception as exc:
        print(f"[setup] WARNING: could not enable Crave RabbitMQ publishing: {exc}")
        print("         Tests requiring RabbitMQ flow may fail.")

    # Give the log shipper thread time to initialise its connection
    time.sleep(RABBITMQ_SETTLE_SECONDS)

    yield

    # Teardown: disable publishing after tests complete
    disable_url = f"{CRAVE_URL}/api/v1/failure-simulator/rabbitmq/disable"
    try:
        requests.post(disable_url, headers=_crave_headers(auth=True), timeout=10)
        print("[teardown] Crave RabbitMQ publishing disabled")
    except Exception:
        pass  # best-effort teardown


@pytest.fixture(scope="session", autouse=True)
def start_niramay_consumer():
    """
    Ensure Niramay's RabbitMQ consumer thread is running.
    Niramay docs state: the consumer thread is a daemon started MANUALLY via API.
    """
    start_url = f"{BASE_URL}/api/v1/consumer/start"
    try:
        resp = requests.post(start_url, timeout=10)
        # 200 = started, 409/already running is also acceptable
        if resp.status_code not in (200, 409):
            resp.raise_for_status()
        print(f"[setup] Niramay consumer thread: {resp.status_code} {resp.text[:80]}")
    except Exception as exc:
        print(f"[setup] Warning — could not start consumer thread: {exc}")
        print("         Assuming consumer is already running.")

    yield


# ---------------------------------------------------------------------------
# Traffic generation helpers
# ---------------------------------------------------------------------------

# These are the exact endpoint patterns Crave's own injector uses (GET only).
# Source: crave docs §3.3 "What the traffic generator actually sends"
CRAVE_TRAFFIC_ENDPOINTS = [
    "/api/v1/restaurants?limit=100",
    "/api/v1/restaurants/1",
    "/api/v1/restaurants/1/menu",
    "/api/v1/auth/me",
    "/api/v1/orders/my-orders",
    "/api/v1/restaurants/2",
    "/api/v1/restaurants/2/menu",
    "/api/v1/restaurants/3",
]

# A handful of restaurant IDs to randomise (Crave uses random IDs)
SAMPLE_IDS = list(range(1, 20))


def generate_crave_traffic(count: int = TRAFFIC_BURST_COUNT, auth: bool = False):
    """
    Fire `count` GET requests against Crave's read-path endpoints.
    Returns list of (url, status_code) tuples.
    """
    results = []
    headers = _crave_headers(auth=auth)

    for i in range(count):
        rid = random.choice(SAMPLE_IDS)
        # Rotate through the endpoint patterns
        pattern = CRAVE_TRAFFIC_ENDPOINTS[i % len(CRAVE_TRAFFIC_ENDPOINTS)]
        # Substitute random restaurant ID where applicable
        url_path = pattern.replace("/1", f"/{rid}").replace("/2", f"/{rid}").replace("/3", f"/{rid}")
        full_url = f"{CRAVE_URL}{url_path}"

        try:
            resp = requests.get(full_url, headers=headers, timeout=5)
            results.append((full_url, resp.status_code))
        except Exception as exc:
            print(f"  [traffic] Request failed (non-fatal): {full_url} — {exc}")
            results.append((full_url, None))

    success = sum(1 for _, s in results if s is not None)
    print(f"  [traffic] Sent {count} requests to Crave — {success} reached the server")
    return results


def enable_crave_failure_scenario(scenario_name: str):
    """
    Enable one of Crave's 9 FailureSimulationMiddleware scenarios.
    The auto-injector cycles: database_error → service_overload → config_error
    We use service_overload (503, 80% probability, all endpoints) for maximum
    anomaly signal — it will affect all the GET-path traffic we generate.
    """
    url = f"{CRAVE_URL}/api/v1/failure-simulator/scenarios/{scenario_name}/enable"
    resp = requests.post(url, headers=_crave_headers(auth=True), timeout=10)
    resp.raise_for_status()
    print(f"  [failure] Enabled Crave scenario: {scenario_name} → {resp.status_code}")
    return resp.json()


def reset_crave_failures():
    """Disable all active Crave failure scenarios."""
    url = f"{CRAVE_URL}/api/v1/failure-simulator/reset"
    try:
        resp = requests.post(url, headers=_crave_headers(auth=True), timeout=10)
        resp.raise_for_status()
        print(f"  [failure] Reset all Crave scenarios → {resp.status_code}")
    except Exception as exc:
        print(f"  [failure] Reset warning (non-fatal): {exc}")


# ===========================================================================
# STAGE 1 — Health Checks
# ===========================================================================

class TestStage1HealthChecks:
    """Both systems must be up and healthy before any test proceeds."""

    def test_niramay_health(self):
        """Niramay FastAPI backend responds healthy."""
        resp = requests.get(f"{BASE_URL}/health", timeout=10)
        assert resp.status_code == 200, f"Niramay unhealthy: {resp.text}"
        data = resp.json()
        assert data.get("status") == "healthy", f"Unexpected health response: {data}"

    def test_crave_health(self):
        """Crave FastAPI backend responds healthy."""
        # Crave exposes a standard health check (common FastAPI pattern)
        resp = requests.get(f"{CRAVE_URL}/health", timeout=10)
        assert resp.status_code == 200, f"Crave unhealthy: {resp.text}"

    def test_crave_restaurants_endpoint_reachable(self):
        """Verify the primary Crave traffic endpoint is reachable."""
        resp = requests.get(
            f"{CRAVE_URL}/api/v1/restaurants?limit=5", timeout=10
        )
        # 200 = healthy, 503/500 = Crave is up but a failure may be active — both OK here
        assert resp.status_code in (200, 429, 500, 503), (
            f"Crave /restaurants returned unexpected status: {resp.status_code}"
        )

    def test_niramay_pipeline_stage_endpoint(self):
        """Niramay pipeline stage key is readable."""
        resp = requests.get(f"{BASE_URL}/api/v1/pipeline/stage", timeout=10)
        assert resp.status_code == 200, f"Pipeline stage endpoint failed: {resp.text}"


# ===========================================================================
# STAGE 2 — Crave Failure Scenario Controls
# ===========================================================================

class TestStage2CraveScenarioControls:
    """
    Validate that Crave's failure scenario CRUD works correctly.
    These endpoints are used by the test suite to drive anomaly generation.
    """

    def test_get_failure_simulator_status(self):
        resp = requests.get(
            f"{CRAVE_URL}/api/v1/failure-simulator/status",
            headers=_crave_headers(auth=True),
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should return some indication of active scenarios / injector state
        assert isinstance(data, dict), f"Expected dict, got: {data}"

    def test_enable_service_overload_scenario(self):
        """service_overload targets all endpoints (wildcard) at 80% probability —
        the most reliable scenario for generating observable 5xx in our GET traffic."""
        url = f"{CRAVE_URL}/api/v1/failure-simulator/scenarios/service_overload/enable"
        resp = requests.post(url, headers=_crave_headers(auth=True), timeout=10)
        assert resp.status_code == 200, f"Enable scenario failed: {resp.text}"

    def test_disable_service_overload_scenario(self):
        url = f"{CRAVE_URL}/api/v1/failure-simulator/scenarios/service_overload/disable"
        resp = requests.post(url, headers=_crave_headers(auth=True), timeout=10)
        assert resp.status_code == 200, f"Disable scenario failed: {resp.text}"

    def test_reset_all_scenarios(self):
        url = f"{CRAVE_URL}/api/v1/failure-simulator/reset"
        resp = requests.post(url, headers=_crave_headers(auth=True), timeout=10)
        assert resp.status_code == 200, f"Reset failed: {resp.text}"


# ===========================================================================
# STAGE 3 — Log Ingestion Validation
# ===========================================================================

class TestStage3LogIngestion:
    """
    Generate real Crave traffic → verify Niramay's observation:logs list
    receives entries.

    Pipeline path:
      Crave GET requests → ObservationMiddleware → RabbitMQ (crave:rabbitmq:enabled=1)
      → Niramay Consumer Thread → observation:logs (Redis, capped 1000)
    """

    @classmethod
    def setup_class(cls):
        """Fire a burst of normal (non-failure) Crave traffic."""
        print("\n[Stage 3] Generating baseline Crave traffic...")
        generate_crave_traffic(count=TRAFFIC_BURST_COUNT, auth=False)

    def test_observation_logs_are_non_empty(self):
        """Niramay's /observation/logs must contain entries from Crave traffic."""
        _poll(
            description="observation logs non-empty",
            fetch_fn=lambda: requests.get(f"{BASE_URL}/api/v1/observation/logs", timeout=10),
            check_fn=lambda data: isinstance(data, dict) and len(data.get("logs", [])) > 0,
            wait_first=LOG_PROPAGATION_SECONDS,
        )

    def test_observation_log_schema(self):
        """Each log entry must contain the Niramay canonical fields."""
        required_fields = {
            "timestamp", "service", "endpoint", "method",
            "status_code", "response_time_ms", "failure_tag",
        }
        data = _poll(
            description="observation log schema",
            fetch_fn=lambda: requests.get(f"{BASE_URL}/api/v1/observation/logs", timeout=10),
            check_fn=lambda d: isinstance(d, dict) and len(d.get("logs", [])) > 0,
            wait_first=0,
        )
        entry = data.get("logs", [])[0]
        missing = required_fields - set(entry.keys())
        assert not missing, (
            f"Observation log missing required fields: {missing}\n"
            f"Got: {list(entry.keys())}"
        )

    def test_observation_log_service_field_populated(self):
        """service field must be derived from Crave's service_registry path mapping."""
        data = requests.get(f"{BASE_URL}/api/v1/observation/logs", timeout=10).json()
        data = data.get("logs", data) if isinstance(data, dict) else data
        assert isinstance(data, list) and len(data) > 0
        # At minimum, restaurant-path logs should carry a recognisable service label
        services_seen = {entry.get("service") for entry in data}
        assert any(s for s in services_seen if s), (
            f"All log entries have empty/None service field: {services_seen}"
        )

    def test_observation_log_endpoint_field_reflects_crave_paths(self):
        """Endpoint fields should reflect the Crave paths we called."""
        data = requests.get(f"{BASE_URL}/api/v1/observation/logs", timeout=10).json()
        data = data.get("logs", data) if isinstance(data, dict) else data
        assert isinstance(data, list) and len(data) > 0
        endpoints_seen = {entry.get("endpoint", "") for entry in data}
        crave_paths = {"/api/v1/restaurants", "/api/v1/auth/me", "/api/v1/orders"}
        matched = any(
            any(cp in ep for cp in crave_paths)
            for ep in endpoints_seen
        )
        assert matched, (
            f"No Crave-originated paths found in observation logs.\n"
            f"Endpoints seen: {endpoints_seen}"
        )


# ===========================================================================
# STAGE 4 — Anomaly Detection Validation
# ===========================================================================

class TestStage4AnomalyDetection:
    """
    Enable Crave's service_overload scenario (503, 80%, all endpoints),
    generate traffic under failure conditions, then verify Niramay's Detection
    Worker produces anomaly records.

    Pipeline path:
      observation:pending_detection → Detection Worker (4 engines)
      → observation:anomalies → analyser:pending
    """

    @classmethod
    def setup_class(cls):
        """Enable service_overload, fire traffic, then reset the scenario."""
        print("\n[Stage 4] Enabling Crave service_overload + generating anomalous traffic...")

        if CRAVE_DEV_TOKEN:
            try:
                enable_crave_failure_scenario("service_overload")
                time.sleep(1)  # Let middleware pick up the flag
            except Exception as exc:
                print(f"  [warning] Could not enable scenario: {exc}")

        # Fire traffic — under service_overload, ~80% will return 503
        generate_crave_traffic(count=TRAFFIC_BURST_COUNT, auth=False)

        if CRAVE_DEV_TOKEN:
            try:
                # Also enable config_error (500, 70%) for additional 5xx signal
                enable_crave_failure_scenario("config_error")
                time.sleep(1)
                generate_crave_traffic(count=10, auth=False)
                reset_crave_failures()
            except Exception as exc:
                print(f"  [warning] config_error scenario: {exc}")

    def test_anomalies_list_non_empty(self):
        """Detection Worker must have produced at least one anomaly."""
        _poll(
            description="anomalies list non-empty",
            fetch_fn=lambda: requests.get(f"{BASE_URL}/api/v1/detection/anomalies", timeout=10),
            check_fn=lambda data: isinstance(data, dict) and len(data.get("anomalies", [])) > 0,
            wait_first=ANOMALY_PROPAGATION_SECONDS,
        )

    def test_anomaly_schema(self):
        """Each anomaly record must contain the required Detection Worker fields."""
        required_fields = {
            "detection_id", "anomaly_score", "severity",
            "is_anomaly", "engines_triggered", "anomaly_reasons",
        }
        data = _poll(
            description="anomaly schema",
            fetch_fn=lambda: requests.get(f"{BASE_URL}/api/v1/detection/anomalies", timeout=10),
            check_fn=lambda d: isinstance(d, dict) and len(d.get("anomalies", [])) > 0,
            wait_first=0,
        )
        data = data.get("anomalies", [])
        entry = data[0]
        missing = required_fields - set(entry.keys())
        assert not missing, (
            f"Anomaly record missing required fields: {missing}\n"
            f"Got: {list(entry.keys())}"
        )

    def test_anomaly_score_range(self):
        """anomaly_score must be a float in [0.0, 1.0]."""
        data = requests.get(f"{BASE_URL}/api/v1/detection/anomalies", timeout=10).json()
        data = data.get("anomalies", data) if isinstance(data, dict) else data
        assert isinstance(data, list) and len(data) > 0
        for entry in data[:5]:  # spot-check first 5
            score = entry.get("anomaly_score")
            assert isinstance(score, (int, float)), f"anomaly_score not numeric: {score}"
            assert 0.0 <= score <= 1.0, f"anomaly_score out of range: {score}"

    def test_anomaly_severity_valid(self):
        """severity must be one of the four defined levels."""
        valid_severities = {"low", "medium", "high", "critical"}
        data = requests.get(f"{BASE_URL}/api/v1/detection/anomalies", timeout=10).json()
        data = data.get("anomalies", data) if isinstance(data, dict) else data
        assert isinstance(data, list) and len(data) > 0
        for entry in data[:5]:
            sev = entry.get("severity")
            assert sev in valid_severities, (
                f"Unexpected severity value: '{sev}' — expected one of {valid_severities}"
            )

    def test_anomaly_is_anomaly_true(self):
        """is_anomaly must be True for records in the anomalies list."""
        data = requests.get(f"{BASE_URL}/api/v1/detection/anomalies", timeout=10).json()
        data = data.get("anomalies", data) if isinstance(data, dict) else data
        assert isinstance(data, list) and len(data) > 0
        flagged = [e for e in data if e.get("is_anomaly") is True]
        assert len(flagged) > 0, (
            f"No records with is_anomaly=True found in {len(data)} anomaly records"
        )

    def test_anomaly_engines_triggered_populated(self):
        """At least one engine must have fired on each anomaly."""
        data = requests.get(f"{BASE_URL}/api/v1/detection/anomalies", timeout=10).json()
        data = data.get("anomalies", data) if isinstance(data, dict) else data
        assert isinstance(data, list) and len(data) > 0
        for entry in data[:5]:
            engines = entry.get("engines_triggered", [])
            assert isinstance(engines, list), f"engines_triggered not a list: {engines}"
            # At minimum FeatureRuleEngine should fire on 5xx responses
            assert len(engines) > 0, (
                f"No engines triggered for anomaly {entry.get('detection_id')}"
            )


# ===========================================================================
# STAGE 5 — Incident Report Validation
# ===========================================================================

class TestStage5IncidentReports:
    """
    Verify the Analyser Worker has processed anomalies and produced
    incident reports with the expected human + machine alert structure.

    Pipeline path:
      analyser:pending → Analyser Worker → rule_based_fallback()
      → incident:reports + dispatcher:pending
    """

    def test_incident_reports_non_empty(self):
        """Analyser Worker must have produced at least one incident report."""
        _poll(
            description="incident reports non-empty",
            fetch_fn=lambda: requests.get(f"{BASE_URL}/api/v1/incident/reports", timeout=10),
            check_fn=lambda data: isinstance(data, list) and len(data) > 0,
            wait_first=ANALYSER_PROPAGATION_SECONDS,
        )

    def test_incident_report_schema(self):
        """Each report must contain human_report (Markdown) and machine_alert."""
        data = _poll(
            description="incident report schema",
            fetch_fn=lambda: requests.get(f"{BASE_URL}/api/v1/incident/reports", timeout=10),
            check_fn=lambda d: isinstance(d, list) and len(d) > 0,
            wait_first=0,
        )
        entry = data[0]
        assert "human_report" in entry, f"Missing 'human_report' in: {list(entry.keys())}"
        assert "machine_alert" in entry, f"Missing 'machine_alert' in: {list(entry.keys())}"

    def test_human_report_is_markdown(self):
        """human_report must be a non-empty string (Markdown)."""
        data = requests.get(f"{BASE_URL}/api/v1/incident/reports", timeout=10).json()
        assert isinstance(data, list) and len(data) > 0
        report_text = data[0].get("human_report", "")
        assert isinstance(report_text, str) and len(report_text) > 10, (
            f"human_report is empty or too short: '{report_text[:100]}'"
        )

    def test_machine_alert_schema(self):
        """machine_alert must contain the fields used by the Dispatcher Worker."""
        required_fields = {
            "alert_id", "root_cause", "confidence", "recommended_action",
        }
        data = requests.get(f"{BASE_URL}/api/v1/incident/reports", timeout=10).json()
        assert isinstance(data, list) and len(data) > 0
        ma = data[0].get("machine_alert", {})
        assert isinstance(ma, dict), f"machine_alert is not a dict: {ma}"
        missing = required_fields - set(ma.keys())
        assert not missing, (
            f"machine_alert missing fields: {missing}\nGot: {list(ma.keys())}"
        )

    def test_machine_alert_recommended_action_in_vocabulary(self):
        """
        recommended_action must be from the healing vocabulary defined in
        the Analyser's rule-based fallback.
        """
        valid_actions = {
            "restart_service", "throttle_requests", "flush_cache",
            "scale_up", "circuit_breaker", "rollback_deployment",
            "escalate_only", "none",
        }
        data = requests.get(f"{BASE_URL}/api/v1/incident/reports", timeout=10).json()
        assert isinstance(data, list) and len(data) > 0
        for entry in data[:5]:
            ma = entry.get("machine_alert", {})
            action = ma.get("recommended_action")
            assert action in valid_actions, (
                f"recommended_action '{action}' not in known vocabulary: {valid_actions}"
            )

    def test_incident_report_healing_status_pending(self):
        """
        healing_status must be 'pending' — the Analyser does not execute healing,
        it only populates the machine alert for the Dispatcher.
        """
        data = requests.get(f"{BASE_URL}/api/v1/incident/reports", timeout=10).json()
        assert isinstance(data, list) and len(data) > 0
        entry = data[0]
        # healing_status is set at the report level (Analyser always sets "pending")
        healing_status = (entry.get("heal_data", {}).get("status") or entry.get("healing_status") or entry.get("status"))
        assert healing_status == "pending", (
            f"Expected healing_status='pending', got: '{healing_status}'"
        )

    def test_incident_report_verification_status_pending(self):
        """verification_status must be 'PENDING' at report creation time."""
        data = requests.get(f"{BASE_URL}/api/v1/incident/reports", timeout=10).json()
        assert isinstance(data, list) and len(data) > 0
        entry = data[0]
        vs = (entry.get("heal_data", {}).get("verification_status") or entry.get("verification_status"))
        assert vs == "PENDING", (
            f"Expected verification_status='PENDING', got: '{vs}'"
        )


# ===========================================================================
# STAGE 6 — Stats Validation
# ===========================================================================

class TestStage6Stats:
    """Validate the /stats aggregation endpoint reflects pipeline activity."""

    def test_stats_endpoint_returns_200(self):
        resp = requests.get(f"{BASE_URL}/api/v1/stats", timeout=10)
        assert resp.status_code == 200, f"Stats endpoint failed: {resp.text}"

    def test_stats_schema(self):
        data = requests.get(f"{BASE_URL}/api/v1/stats", timeout=10).json()
        required = {"total_logs", "total_anomalies", "health_score"}
        missing = required - set(data.keys())
        assert not missing, f"Stats missing fields: {missing}\nGot: {list(data.keys())}"

    def test_stats_total_logs_positive(self):
        data = requests.get(f"{BASE_URL}/api/v1/stats", timeout=10).json()
        total = data.get("total_logs", 0)
        assert total > 0, f"total_logs is 0 — no logs were ingested"

    def test_stats_total_anomalies_positive(self):
        data = requests.get(f"{BASE_URL}/api/v1/stats", timeout=10).json()
        total = data.get("total_anomalies", 0)
        assert total > 0, f"total_anomalies is 0 — no anomalies were detected"

    def test_stats_health_score_in_range(self):
        data = requests.get(f"{BASE_URL}/api/v1/stats", timeout=10).json()
        score = data.get("health_score")
        assert isinstance(score, (int, float)), f"health_score not numeric: {score}"
        assert 0 <= score <= 100, f"health_score out of range: {score}"


# ===========================================================================
# STAGE 7 — Healing Actions Validation
# ===========================================================================

class TestStage7HealingActions:
    """
    Validate Dispatcher Worker output.

    IMPORTANT CONSTRAINT (from Niramay docs §5):
      - healing:enabled is set to "0" on startup
      - When disabled, records are stored with status="skipped"
      - When enabled, RestartServiceStrategy is the only partial implementation
      - All other strategies return status="failed" (stubs)
      - verification_status will always eventually reach FAILED or ESCALATED
        because the Verification Worker cannot confirm real healing

    This test suite validates the record structure and expected statuses —
    NOT that healing actually resolves failures (that is not implemented).
    """

    def test_healing_actions_endpoint_returns_200(self):
        resp = requests.get(f"{BASE_URL}/api/v1/healing/actions", timeout=10)
        assert resp.status_code == 200, f"Healing actions endpoint failed: {resp.text}"

    def test_healing_actions_is_list(self):
        data = _poll(
            description="healing actions list available",
            fetch_fn=lambda: requests.get(f"{BASE_URL}/api/v1/healing/actions", timeout=10),
            check_fn=lambda d: isinstance(d, dict),
            wait_first=DISPATCHER_PROPAGATION_SECONDS,
        )
        data = data.get("actions", data) if isinstance(data, dict) else data
        assert isinstance(data, list)

    def test_healing_action_schema_when_present(self):
        """If healing:enabled=0 (default), records will have status='skipped'.
        If enabled, records have verification_status='PENDING'."""
        data = requests.get(f"{BASE_URL}/api/v1/healing/actions", timeout=10).json()
        data = data.get("actions", data) if isinstance(data, dict) else data

        if len(data) == 0:
            pytest.skip(
                "No healing action records yet — Dispatcher may not have processed "
                "any machine alerts. This is acceptable if healing:enabled=0 (default). "
                "Enable healing via API and re-run if you want to validate this stage."
            )

        entry = data[0]
        required_fields = {"detection_id", "verification_status", "timestamp"}
        missing = required_fields - set(entry.keys())
        assert not missing, (
            f"Healing action record missing fields: {missing}\n"
            f"Got: {list(entry.keys())}"
        )

    def test_healing_status_is_expected_value(self):
        """
        When healing:enabled=0 (default startup): status='skipped'
        When healing:enabled=1 and strategy runs: status='failed' (stubs) or
          'success' (restart_service if Docker socket available)
        All are acceptable — we validate the field exists with a known value.
        """
        data = requests.get(f"{BASE_URL}/api/v1/healing/actions", timeout=10).json()
        data = data.get("actions", data) if isinstance(data, dict) else data
        if len(data) == 0:
            pytest.skip("No healing records — see test above.")

        valid_statuses = {"skipped", "pending", "failed", "success"}
        for entry in data[:5]:
            status = entry.get("status")
            assert status in valid_statuses, (
                f"Healing action status '{status}' not in {valid_statuses}"
            )


# ===========================================================================
# STAGE 8 — Escalations
# ===========================================================================

class TestStage8Escalations:
    """
    Niramay docs state the Verification Worker escalates after 3 failed
    attempts. Since no real healing is implemented, escalation is the
    expected end-state. We validate the escalation endpoint is readable.
    """

    def test_escalations_endpoint_returns_200(self):
        resp = requests.get(f"{BASE_URL}/api/v1/escalations", timeout=10)
        assert resp.status_code == 200, f"Escalations endpoint failed: {resp.text}"

    def test_escalations_is_list(self):
        data = requests.get(f"{BASE_URL}/api/v1/escalations", timeout=10).json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        # Empty list is acceptable — escalation only occurs after 3 Verification
        # Worker retry cycles (each with settling windows), which may not have
        # completed in the test window.
        print(f"  [info] Escalations found: {len(data)}")


# ===========================================================================
# STAGE 9 — End-to-End Pipeline Flow
# ===========================================================================

class TestStage9EndToEnd:
    """
    Full pipeline smoke test:
    1. Enable Crave service_overload (high-signal failure)
    2. Generate traffic burst
    3. Disable failure
    4. Assert all pipeline stages show data (logs → anomalies → reports)

    This is the integration sanity check — pipeline must flow end-to-end.
    """

    @classmethod
    def setup_class(cls):
        print("\n[Stage 9] E2E: enabling service_overload + generating traffic...")
        if CRAVE_DEV_TOKEN:
            try:
                enable_crave_failure_scenario("service_overload")
                time.sleep(2)
            except Exception as exc:
                print(f"  [warning] Could not enable scenario: {exc}")

        generate_crave_traffic(count=30, auth=False)

        if CRAVE_DEV_TOKEN:
            try:
                reset_crave_failures()
            except Exception:
                pass

        print(f"  [E2E] Waiting for full pipeline propagation ({LOG_PROPAGATION_SECONDS + ANOMALY_PROPAGATION_SECONDS + ANALYSER_PROPAGATION_SECONDS}s total)...")

    def test_e2e_logs_present(self):
        data = _poll(
            description="E2E: logs present",
            fetch_fn=lambda: requests.get(f"{BASE_URL}/api/v1/observation/logs", timeout=10),
            check_fn=lambda d: isinstance(d, dict) and len(d.get("logs", [])) > 0,
            wait_first=LOG_PROPAGATION_SECONDS,
        )
        data = data.get("logs", data) if isinstance(data, dict) else data
        assert len(data) > 0

    def test_e2e_anomalies_present(self):
        data = _poll(
            description="E2E: anomalies present",
            fetch_fn=lambda: requests.get(f"{BASE_URL}/api/v1/detection/anomalies", timeout=10),
            check_fn=lambda d: isinstance(d, dict) and len(d.get("anomalies", [])) > 0,
            wait_first=ANOMALY_PROPAGATION_SECONDS,
        )
        data = data.get("anomalies", data) if isinstance(data, dict) else data
        assert len(data) > 0

    def test_e2e_incident_reports_present(self):
        data = _poll(
            description="E2E: incident reports present",
            fetch_fn=lambda: requests.get(f"{BASE_URL}/api/v1/incident/reports", timeout=10),
            check_fn=lambda d: isinstance(d, list) and len(d) > 0,
            wait_first=ANALYSER_PROPAGATION_SECONDS,
        )
        assert len(data) > 0

    def test_e2e_pipeline_stage_advanced(self):
        """pipeline:stage should reflect processing beyond stage_1."""
        resp = requests.get(f"{BASE_URL}/api/v1/pipeline/stage", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        stage = data.get("stage") or data.get("pipeline_stage") or str(data)
        stuck = stage in ("idle", "unknown", "")
        assert not stuck, (
            f"Pipeline has not advanced from idle/unknown: {stage}"
        )


# ===========================================================================
# STAGE 10 — Heal Endpoint Contract (Niramay → Crave)
# ===========================================================================

class TestStage10HealEndpointContract:
    """
    Verify the Niramay → Crave heal endpoint contract.
    Niramay Component A calls POST /api/v1/failure-simulator/heal on Crave.
    We validate this endpoint directly to confirm the contract works.

    From Crave docs §2: The heal endpoint
      1. Disables all FailureSimulationMiddleware scenarios
      2. Resets all 23 ChaosMiddleware experiments
      3. Writes Redis keys: crave:injector:paused="1", crave:injector:state="paused"
    """

    def test_crave_heal_endpoint_accessible(self):
        """The heal endpoint must accept requests (auth required)."""
        if not CRAVE_DEV_TOKEN:
            pytest.skip("CRAVE_DEV_TOKEN not set — cannot call authenticated heal endpoint")

        # First enable a scenario so heal has something to clear
        try:
            enable_crave_failure_scenario("database_error")
        except Exception:
            pass  # Doesn't matter if this fails

        resp = requests.post(
            f"{CRAVE_URL}/api/v1/failure-simulator/heal",
            headers=_crave_headers(auth=True),
            timeout=15,
        )
        assert resp.status_code == 200, (
            f"Heal endpoint returned {resp.status_code}: {resp.text}"
        )

    def test_crave_heal_response_structure(self):
        """Heal response should confirm what was cleared."""
        if not CRAVE_DEV_TOKEN:
            pytest.skip("CRAVE_DEV_TOKEN not set")

        resp = requests.post(
            f"{CRAVE_URL}/api/v1/failure-simulator/heal",
            headers=_crave_headers(auth=True),
            timeout=15,
        )
        data = resp.json()
        assert isinstance(data, dict), f"Heal response not a dict: {data}"
        # The response should indicate success in some form
        assert resp.status_code == 200

    def test_crave_injector_paused_after_heal(self):
        """After heal, traffic should continue (GET-only injector) but failures stop."""
        if not CRAVE_DEV_TOKEN:
            pytest.skip("CRAVE_DEV_TOKEN not set")

        # Re-enable a scenario, heal it, then verify traffic no longer returns high error rate
        try:
            enable_crave_failure_scenario("service_overload")
            time.sleep(1)
        except Exception:
            pytest.skip("Could not enable scenario to verify heal")

        requests.post(
            f"{CRAVE_URL}/api/v1/failure-simulator/heal",
            headers=_crave_headers(auth=True),
            timeout=15,
        )

        time.sleep(2)
        results = generate_crave_traffic(count=10, auth=False)
        statuses = [s for _, s in results if s is not None]
        error_rate = sum(1 for s in statuses if s and s >= 500) / max(len(statuses), 1)
        assert error_rate < 0.5, (
            f"After heal, error rate is still {error_rate:.0%} (expected < 50%). "
            f"Statuses: {statuses}"
        )