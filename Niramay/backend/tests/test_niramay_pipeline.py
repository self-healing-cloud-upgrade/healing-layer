"""
Niramay — End-to-End Pipeline Integration Tests
================================================
Tests the full pipeline: Observation → Detection → Analysis → (Healing placeholder)

How to run:
    python tests/test_nirame_pipeline.py

Requirements:
    pip install -r tests/requirements.txt

Assumption:
    All services (backend, redis, rabbitmq, opensearch) are already running.
    Backend is reachable at BASE_URL (default: http://localhost:8000).

What this tests:
    Stage 1 - Health check
    Stage 2 - Failure simulator controls (enable/disable/status)
    Stage 3 - Ingestion via POST /observe
    Stage 4 - Observation logs appear in Redis (via GET /observation/logs)
    Stage 5 - Anomaly detection fires (via GET /detection/anomalies)
    Stage 6 - Incident reports are generated (via GET /incident/reports)
    Stage 7 - Stats endpoint returns valid data
    Stage 8 - Escalation endpoint is reachable (may be empty, that is OK)
    Stage 9 - Healing actions endpoint is reachable (placeholder records)
    Stage 10 - End-to-end: inject failure via global-rate → observe → detect → report

What this does NOT test (not implemented in codebase):
    - Real healing execution (Dispatcher Worker is a placeholder skeleton)
    - LLM/Ollama responses (depends on local Ollama setup; graceful fallback assumed)
"""

import os
import sys
import time
import json
import requests
from datetime import datetime, timezone

# ── Config ───────────────────────────────────────────────────────────────────
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000/api/v1")
ROOT_URL = os.environ.get("ROOT_URL", "http://localhost:8000")

# How long to wait (seconds) after injecting traffic for the pipeline to process it.
# Pipeline: ObservationMiddleware → RabbitMQ → Consumer → Redis → Detection Worker
PIPELINE_PROPAGATION_WAIT = int(os.environ.get("PIPELINE_PROPAGATION_WAIT", "20"))

# How long to wait (seconds) after anomalies appear for Analyser Worker to generate reports.
ANALYSER_WAIT = int(os.environ.get("ANALYSER_WAIT", "15"))

# How many times to poll (with 3s gaps) when waiting for data to appear.
POLL_RETRIES = int(os.environ.get("POLL_RETRIES", "10"))
POLL_INTERVAL = 3  # seconds

PASSED = []
FAILED = []


# ── Helpers ──────────────────────────────────────────────────────────────────

def green(msg): return f"\033[92m{msg}\033[0m"
def red(msg):   return f"\033[91m{msg}\033[0m"
def yellow(msg):return f"\033[93m{msg}\033[0m"
def bold(msg):  return f"\033[1m{msg}\033[0m"


def pass_test(name, detail=""):
    msg = f"  ✅ PASS: {name}"
    if detail:
        msg += f"  ({detail})"
    print(green(msg))
    PASSED.append(name)


def fail_test(name, reason=""):
    msg = f"  ❌ FAIL: {name}"
    if reason:
        msg += f"  → {reason}"
    print(red(msg))
    FAILED.append(name)


def info(msg):
    print(f"  ℹ️  {msg}")


def section(title):
    print(f"\n{bold('━━━ ' + title + ' ━━━')}")


def get(path, params=None, timeout=10):
    """GET request with error handling."""
    try:
        r = requests.get(f"{BASE_URL}{path}", params=params, timeout=timeout)
        return r
    except requests.exceptions.ConnectionError:
        return None
    except Exception:
        return None


def post(path, json_body=None, params=None, timeout=10):
    """POST request with error handling."""
    try:
        r = requests.post(f"{BASE_URL}{path}", json=json_body, params=params, timeout=timeout)
        return r
    except requests.exceptions.ConnectionError:
        return None
    except Exception:
        return None


def poll_until_non_empty(path, params=None, retries=POLL_RETRIES, interval=POLL_INTERVAL):
    """
    Poll a GET endpoint until it returns a non-empty list.
    Returns the list if found, None if all retries exhausted.
    """
    for attempt in range(retries):
        r = get(path, params=params)
        if r and r.status_code == 200:
            try:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    return data
            except Exception:
                pass
        info(f"Polling {path} … attempt {attempt + 1}/{retries}")
        time.sleep(interval)
    return None


# ── Stage 1: Health Check ─────────────────────────────────────────────────────

def test_health_check():
    section("Stage 1: Health Check")
    try:
        r = requests.get(f"{ROOT_URL}/health", timeout=10)
        if r.status_code == 200 and r.json().get("status") == "healthy":
            pass_test("Backend is healthy", f"status={r.json()['status']}")
        else:
            fail_test("Backend health check", f"HTTP {r.status_code}, body={r.text[:200]}")
    except Exception as e:
        fail_test("Backend health check", f"Cannot connect: {e}")


# ── Stage 2: Failure Simulator Controls ──────────────────────────────────────

def test_failure_simulator_status():
    section("Stage 2: Failure Simulator")

    # GET /failure-simulator/status
    r = get("/failure-simulator/status")
    if r and r.status_code == 200:
        data = r.json()
        required = ["enabled", "global_failure_rate", "active_scenarios",
                    "total_scenarios", "request_count", "failure_count",
                    "success_rate", "failure_rate", "last_updated"]
        missing = [k for k in required if k not in data]
        if not missing:
            pass_test("GET /failure-simulator/status returns all required fields",
                      f"total_scenarios={data['total_scenarios']}")
        else:
            fail_test("GET /failure-simulator/status", f"Missing fields: {missing}")
    else:
        fail_test("GET /failure-simulator/status", f"HTTP {r.status_code if r else 'no response'}")

    # GET /failure-simulator/scenarios
    r = get("/failure-simulator/scenarios")
    if r and r.status_code == 200:
        data = r.json()
        expected_scenarios = [
            "rate_limiting", "auth_expiration", "payment_timeout",
            "database_error", "validation_error", "stripe_dependency",
            "maps_dependency", "config_error", "service_overload"
        ]
        found = [s for s in expected_scenarios if s in data]
        if len(found) == len(expected_scenarios):
            pass_test("GET /failure-simulator/scenarios lists all 9 default scenarios",
                      f"found={len(found)}")
        else:
            missing_s = [s for s in expected_scenarios if s not in data]
            fail_test("GET /failure-simulator/scenarios",
                      f"Missing scenarios: {missing_s}")
    else:
        fail_test("GET /failure-simulator/scenarios",
                  f"HTTP {r.status_code if r else 'no response'}")

    # POST enable scenario (service_overload targets "*" — all paths)
    r = post("/failure-simulator/scenarios/service_overload/enable")
    if r and r.status_code == 200:
        pass_test("POST /failure-simulator/scenarios/service_overload/enable")
    else:
        fail_test("Enable service_overload scenario",
                  f"HTTP {r.status_code if r else 'no response'}")

    # POST disable scenario
    r = post("/failure-simulator/scenarios/service_overload/disable")
    if r and r.status_code == 200:
        pass_test("POST /failure-simulator/scenarios/service_overload/disable")
    else:
        fail_test("Disable service_overload scenario",
                  f"HTTP {r.status_code if r else 'no response'}")

    # POST reset all
    r = post("/failure-simulator/reset")
    if r and r.status_code == 200:
        pass_test("POST /failure-simulator/reset")
    else:
        fail_test("POST /failure-simulator/reset",
                  f"HTTP {r.status_code if r else 'no response'}")


# ── Stage 3: Log Ingestion via POST /observe ──────────────────────────────────

def test_observation_ingestion():
    section("Stage 3: Log Ingestion (POST /observe)")

    # Inject a synthetic anomalous log — high latency + 500 status
    log_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "niramay-test",
        "endpoint": "/api/v1/test-endpoint",
        "method": "GET",
        "status_code": 500,
        "response_time_ms": 850.0,
        "failure_tag": "server_error",
        "request_id": "CI-TEST-001"
    }

    r = post("/observe", json_body=log_payload)
    if r and r.status_code == 200 and r.json().get("status") == "accepted":
        pass_test("POST /observe accepts a synthetic anomalous log",
                  "status=accepted")
    else:
        fail_test("POST /observe",
                  f"HTTP {r.status_code if r else 'no response'}, "
                  f"body={r.text[:100] if r else 'N/A'}")

    # Inject a healthy log
    healthy_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "niramay-test",
        "endpoint": "/api/v1/test-healthy",
        "method": "GET",
        "status_code": 200,
        "response_time_ms": 45.0,
        "failure_tag": "none",
        "request_id": "CI-TEST-002"
    }
    r = post("/observe", json_body=healthy_payload)
    if r and r.status_code == 200:
        pass_test("POST /observe accepts a synthetic healthy log")
    else:
        fail_test("POST /observe (healthy log)",
                  f"HTTP {r.status_code if r else 'no response'}")


# ── Stage 4: Observation Logs Endpoint ───────────────────────────────────────

def test_observation_logs():
    section("Stage 4: Observation Logs")

    # Note: traffic_generator is enabled by default every 2s.
    # By now there should be logs from it + our POST /observe calls.
    # We wait for pipeline propagation before polling.
    info(f"Waiting {PIPELINE_PROPAGATION_WAIT}s for pipeline propagation "
         f"(RabbitMQ → Consumer → Redis)…")
    time.sleep(PIPELINE_PROPAGATION_WAIT)

    r = get("/observation/logs", params={"limit": 50})
    if not r:
        fail_test("GET /observation/logs", "No response from server")
        return

    if r.status_code != 200:
        fail_test("GET /observation/logs", f"HTTP {r.status_code}")
        return

    logs = r.json()
    if isinstance(logs, list):
        pass_test("GET /observation/logs returns a list",
                  f"count={len(logs)}")
    else:
        fail_test("GET /observation/logs", f"Expected list, got {type(logs)}")
        return

    if len(logs) > 0:
        # Validate log schema
        required_fields = ["timestamp", "service", "endpoint",
                           "status_code", "response_time_ms", "failure_tag"]
        sample = logs[0]
        missing = [f for f in required_fields if f not in sample]
        if not missing:
            pass_test("Log objects contain all required fields",
                      f"service={sample.get('service')}, "
                      f"status={sample.get('status_code')}")
        else:
            fail_test("Log object schema", f"Missing fields: {missing}")
    else:
        fail_test("GET /observation/logs", "List is empty — pipeline may not be running")


# ── Stage 5: Anomaly Detection ────────────────────────────────────────────────

def test_anomaly_detection():
    section("Stage 5: Anomaly Detection")

    info("Injecting 5 anomalous logs (500 status + high latency + failure_tag)…")
    for i in range(5):
        log_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "niramay-test",
            "endpoint": "/api/v1/ci-anomaly-test",
            "method": "POST",
            "status_code": 500,
            "response_time_ms": 950.0,
            "failure_tag": "server_error",
            "request_id": f"CI-ANOMALY-{i:03}"
        }
        post("/observe", json_body=log_payload)
        time.sleep(0.5)

    info(f"Waiting {PIPELINE_PROPAGATION_WAIT}s for Detection Worker to process…")
    time.sleep(PIPELINE_PROPAGATION_WAIT)

    # Poll for anomalies
    anomalies = poll_until_non_empty("/detection/anomalies", params={"limit": 50})
    if anomalies:
        pass_test("GET /detection/anomalies returns detected anomalies",
                  f"count={len(anomalies)}")

        # Validate anomaly schema
        required_fields = [
            "detection_id", "timestamp", "service", "endpoint",
            "status_code", "response_time_ms", "anomaly_score",
            "severity", "is_anomaly", "engines_triggered", "anomaly_reasons"
        ]
        sample = anomalies[0]
        missing = [f for f in required_fields if f not in sample]
        if not missing:
            pass_test("Anomaly objects contain all required fields",
                      f"score={sample.get('anomaly_score')}, "
                      f"severity={sample.get('severity')}")
        else:
            fail_test("Anomaly object schema", f"Missing fields: {missing}")

        # Validate anomaly_score is in [0, 1]
        score = sample.get("anomaly_score", -1)
        if isinstance(score, (int, float)) and 0.0 <= score <= 1.0:
            pass_test("anomaly_score is normalized [0.0–1.0]", f"score={score}")
        else:
            fail_test("anomaly_score out of range", f"score={score}")

        # Validate severity is one of the known values
        severity = sample.get("severity")
        if severity in ("low", "medium", "high", "critical"):
            pass_test("severity is a valid label", f"severity={severity}")
        else:
            fail_test("Invalid severity label", f"severity={severity}")

        # Validate is_anomaly is True for items in the list
        if sample.get("is_anomaly") is True:
            pass_test("is_anomaly=True for anomaly records")
        else:
            fail_test("is_anomaly flag", f"got is_anomaly={sample.get('is_anomaly')}")

    else:
        fail_test("GET /detection/anomalies",
                  f"No anomalies detected after {POLL_RETRIES * POLL_INTERVAL}s. "
                  "Check RabbitMQ consumer and Detection Worker logs.")


# ── Stage 6: Incident Reports ─────────────────────────────────────────────────

def test_incident_reports():
    section("Stage 6: Incident Reports (Analyser Worker)")

    info(f"Waiting {ANALYSER_WAIT}s for Analyser Worker to generate reports…")
    time.sleep(ANALYSER_WAIT)

    reports = poll_until_non_empty("/incident/reports", params={"limit": 20})
    if reports:
        pass_test("GET /incident/reports returns incident reports",
                  f"count={len(reports)}")

        sample = reports[0]

        # Check top-level wrapper fields
        wrapper_fields = ["human_report", "machine_alert", "timestamp",
                          "detection_id", "service", "severity"]
        missing = [f for f in wrapper_fields if f not in sample]
        if not missing:
            pass_test("Incident report wrapper has all required fields")
        else:
            fail_test("Incident report wrapper schema", f"Missing: {missing}")

        # Validate machine_alert schema
        alert = sample.get("machine_alert", {})
        alert_fields = [
            "alert_id", "detection_id", "timestamp", "root_cause",
            "confidence", "analysis_type", "service", "endpoint",
            "severity", "anomaly_score", "recommended_action",
            "healing_status", "verification_status"
        ]
        missing_alert = [f for f in alert_fields if f not in alert]
        if not missing_alert:
            pass_test("machine_alert contains all required fields",
                      f"recommended_action={alert.get('recommended_action')}, "
                      f"analysis_type={alert.get('analysis_type')}")
        else:
            fail_test("machine_alert schema", f"Missing fields: {missing_alert}")

        # Validate recommended_action is from known vocabulary
        valid_actions = {
            "restart_service", "throttle_requests", "flush_cache",
            "scale_up", "circuit_breaker", "rollback_deployment",
            "escalate_only", "none"
        }
        action = alert.get("recommended_action", "")
        if action in valid_actions:
            pass_test("recommended_action is within healing vocabulary",
                      f"action={action}")
        else:
            fail_test("recommended_action outside vocabulary",
                      f"got={action}, expected one of {valid_actions}")

        # Validate human_report is a non-empty string (Markdown)
        hr = sample.get("human_report", "")
        if isinstance(hr, str) and len(hr) > 10:
            pass_test("human_report is a non-empty Markdown string",
                      f"length={len(hr)} chars")
        else:
            fail_test("human_report", f"Empty or invalid: {repr(hr[:50])}")

        # Verify healing_status is "pending" (Dispatcher is skeleton)
        h_status = alert.get("healing_status")
        if h_status == "pending":
            pass_test("healing_status is 'pending' (Dispatcher Worker is skeleton — expected)",
                      "This is correct behaviour, not a bug")
        else:
            info(f"healing_status={h_status} (unexpected — Dispatcher should return 'pending')")

        # Verify verification_status is "PENDING"
        v_status = alert.get("verification_status")
        if v_status == "PENDING":
            pass_test("verification_status is 'PENDING' (correct for new reports)")
        else:
            info(f"verification_status={v_status}")

    else:
        fail_test("GET /incident/reports",
                  f"No reports after {POLL_RETRIES * POLL_INTERVAL + ANALYSER_WAIT}s. "
                  "Check Analyser Worker logs. Causal Engine (Ollama) may not be running "
                  "— set ENABLE_AI_CAUSAL=false to use rule-based fallback.")


# ── Stage 7: Stats Endpoint ───────────────────────────────────────────────────

def test_stats():
    section("Stage 7: System Stats")

    r = get("/stats")
    if not r or r.status_code != 200:
        fail_test("GET /stats", f"HTTP {r.status_code if r else 'no response'}")
        return

    data = r.json()
    required = ["total_logs", "total_anomalies", "health_score",
                "by_endpoint", "by_type"]
    missing = [k for k in required if k not in data]
    if not missing:
        pass_test("GET /stats returns all required fields",
                  f"total_logs={data['total_logs']}, "
                  f"total_anomalies={data['total_anomalies']}, "
                  f"health_score={data['health_score']}")
    else:
        fail_test("GET /stats schema", f"Missing: {missing}")

    # health_score should be between 0 and 100
    hs = data.get("health_score", -1)
    if isinstance(hs, (int, float)) and 0.0 <= hs <= 100.0:
        pass_test("health_score is in valid range [0–100]", f"score={hs}")
    else:
        fail_test("health_score out of range", f"health_score={hs}")


# ── Stage 8: Escalation Alerts Endpoint ──────────────────────────────────────

def test_escalations():
    section("Stage 8: Escalation Alerts")

    r = get("/escalations")
    if r and r.status_code == 200:
        data = r.json()
        if isinstance(data, list):
            pass_test("GET /escalations returns a list",
                      f"count={len(data)} (empty is OK at this stage)")
        else:
            fail_test("GET /escalations", f"Expected list, got {type(data)}")
    else:
        fail_test("GET /escalations",
                  f"HTTP {r.status_code if r else 'no response'}")


# ── Stage 9: Healing Actions Endpoint ────────────────────────────────────────

def test_healing_actions():
    section("Stage 9: Healing Actions (Dispatcher Placeholder)")

    r = get("/healing/actions")
    if r and r.status_code == 200:
        data = r.json()
        if isinstance(data, list):
            pass_test("GET /healing/actions returns a list",
                      f"count={len(data)}")
            if len(data) > 0:
                sample = data[0]
                # Dispatcher Worker always produces pending records
                h_status = sample.get("status")
                if h_status == "pending":
                    pass_test("Healing action has status='pending' (Dispatcher skeleton — expected)")
                else:
                    info(f"Healing action status={h_status}")
                # Verify required fields
                req = ["detection_id", "verification_status", "timestamp"]
                missing = [f for f in req if f not in sample]
                if not missing:
                    pass_test("Healing action record has required fields")
                else:
                    fail_test("Healing action schema", f"Missing: {missing}")
        else:
            fail_test("GET /healing/actions", f"Expected list, got {type(data)}")
    else:
        fail_test("GET /healing/actions",
                  f"HTTP {r.status_code if r else 'no response'}")


# ── Stage 10: End-to-End via Global Failure Rate ──────────────────────────────

def test_e2e_global_failure_rate():
    section("Stage 10: Full E2E via Global Failure Rate")

    # Reset simulator first
    post("/failure-simulator/reset")

    # Set global failure rate to 1.0 (100% of non-excluded requests will fail)
    r = post("/failure-simulator/global-rate", params={"rate": "1.0"})
    if r and r.status_code == 200:
        pass_test("POST /failure-simulator/global-rate?rate=1.0",
                  "All non-excluded requests will be intercepted as server_error")
    else:
        fail_test("Set global failure rate",
                  f"HTTP {r.status_code if r else 'no response'}")
        return

    # Inject logs via POST /observe — these go directly to RabbitMQ,
    # bypassing the middleware failure injection. This is the correct
    # way to inject known anomalies without depending on path matching.
    info("Injecting 3 anomalous logs via POST /observe to guarantee detection…")
    for i in range(3):
        r = post("/observe", json_body={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "niramay-e2e-test",
            "endpoint": "/api/v1/e2e-probe",
            "method": "GET",
            "status_code": 500,
            "response_time_ms": 1200.0,
            "failure_tag": "server_error",
            "request_id": f"E2E-{i:03}"
        })
        time.sleep(0.3)

    if r and r.status_code == 200:
        pass_test("3 anomalous logs accepted via POST /observe")
    else:
        fail_test("POST /observe during E2E test",
                  f"HTTP {r.status_code if r else 'no response'}")

    # Wait for pipeline to fully process
    info(f"Waiting {PIPELINE_PROPAGATION_WAIT + ANALYSER_WAIT}s for full pipeline…")
    time.sleep(PIPELINE_PROPAGATION_WAIT + ANALYSER_WAIT)

    # Check logs appeared
    logs = get("/observation/logs", params={"limit": 200})
    if logs and logs.status_code == 200 and len(logs.json()) > 0:
        pass_test("E2E: Logs propagated to observation:logs")
    else:
        fail_test("E2E: No logs in observation:logs")

    # Check anomalies appeared
    anomalies = get("/detection/anomalies", params={"limit": 100})
    if anomalies and anomalies.status_code == 200 and len(anomalies.json()) > 0:
        pass_test("E2E: Anomalies detected and stored")
    else:
        fail_test("E2E: No anomalies in observation:anomalies")

    # Check incident reports appeared
    reports = get("/incident/reports", params={"limit": 50})
    if reports and reports.status_code == 200 and len(reports.json()) > 0:
        pass_test("E2E: Incident reports generated by Analyser Worker")
    else:
        fail_test("E2E: No incident reports in incident:reports",
                  "Analyser Worker or Causal Engine may be failing. "
                  "Check logs. Set ENABLE_AI_CAUSAL=false to skip Ollama.")

    # Clean up: reset failure rate to 0
    post("/failure-simulator/global-rate", params={"rate": "0.0"})
    post("/failure-simulator/reset")
    pass_test("Cleanup: Reset failure simulator")


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary():
    total = len(PASSED) + len(FAILED)
    print("\n" + "="*60)
    print(bold("NIRAMAY E2E PIPELINE TEST SUMMARY"))
    print("="*60)
    print(green(f"  ✅ PASSED : {len(PASSED)}/{total}"))
    if FAILED:
        print(red(f"  ❌ FAILED : {len(FAILED)}/{total}"))
        print(red("\n  Failed tests:"))
        for f in FAILED:
            print(red(f"    - {f}"))
    else:
        print(green("  🎉 All tests passed!"))
    print("="*60)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(bold("\n🔬 Niramay — End-to-End Pipeline Integration Tests"))
    print(f"   BASE_URL : {BASE_URL}")
    print(f"   ROOT_URL : {ROOT_URL}")
    print(f"   PIPELINE WAIT : {PIPELINE_PROPAGATION_WAIT}s")
    print(f"   ANALYSER WAIT : {ANALYSER_WAIT}s")
    print(f"   POLL RETRIES  : {POLL_RETRIES} × {POLL_INTERVAL}s\n")

    test_health_check()
    test_failure_simulator_status()
    test_observation_ingestion()
    test_observation_logs()          # includes sleep for pipeline propagation
    test_anomaly_detection()         # injects more logs + polls
    test_incident_reports()          # waits for Analyser Worker
    test_stats()
    test_escalations()
    test_healing_actions()
    test_e2e_global_failure_rate()   # full loop with global failure rate

    print_summary()

    # Exit with non-zero code if any test failed (Jenkins picks this up)
    if FAILED:
        sys.exit(1)
    sys.exit(0)
