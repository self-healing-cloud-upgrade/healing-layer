# Niramay

AI-powered self-healing cloud monitoring system.
Detects failures in a simulated cloud environment
and automatically remediates them with minimal
human intervention.

---

## What It Does

Niramay monitors a food delivery demo application
that simulates a cloud environment. When failures
occur, the system detects them, classifies the root
cause and executes automated healing actions.

The pipeline has three main components:

**Component C** is the demo application. A food
delivery app that simulates cloud failures including
API errors, latency spikes and service outages.

**Component B** is the detection and analysis layer.
It ingests logs from Component C, runs them through
a multi-engine detection system, performs AI-powered
root cause analysis and produces structured failure
alerts with incident reports.

**Component A** is the self-healing layer. It
receives alerts from Component B and executes
the appropriate remediation action automatically.

---

## Architecture

```
Traffic Generator
      |
      v
Failure Middleware (injects simulated failures)
      |
      v
Observation Middleware
      |
      v (publish)
RabbitMQ (component-c-logs)
      |
      v (consume)
Normalizer
      |
      |---> OpenSearch: b-normalized-logs (permanent)
      |---> Redis: observation:logs (real-time, capped 1000)
      |---> Redis: observation:pending_detection (queue)
                          |
                          v
              Detection Worker (Stage 2)
              (4 engines in parallel)
                          |
              +-----------+-----------+
              |                       |
           Anomaly               Healthy
              |                       |
              v                       v
   Redis: observation:anomalies   OpenSearch: b-healthy-logs
   OpenSearch: b-anomaly-records
   Redis: analyser:pending (queue)
              |
              v
       Analyser Worker (Stage 3)
       (Causal Engine + Report Gen)
              |
              |---> Redis: incident:reports
              |---> OpenSearch: b-incident-reports
              |---> Redis: dispatcher:pending (queue)
                          |
                          v
              Dispatcher Worker (Stage 4)
              (Component A communication)
                          |
                          v
              Redis: healing:actions
                          |
                          v
              Verification Worker
              (Checks if healing worked)
                          |
              +-----------+-----------+
              |           |           |
           SUCCESS    RETRY      ESCALATE
              |           |           |
              v           v           v
           OpenSearch  dispatcher  Redis:
           update     :pending    escalation:alerts
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Demo application | Python FastAPI |
| Message queue | RabbitMQ |
| Real-time storage | Redis |
| Permanent storage | OpenSearch |
| AI analysis | Ollama with LLaMA3 |
| Frontend | React TypeScript |
| Infrastructure | Docker Compose |

---

## Pipeline Workers

| Worker | Stage | Responsibility |
|---|---|---|
| Detection Worker | Stage 2 | Runs 4 detection engines, scores anomalies, pushes to analyser queue |
| Analyser Worker | Stage 3 | Runs causal engine (LLM or rule fallback), generates incident reports |
| Dispatcher Worker | Stage 4 | Sends alerts to Component A, stores healing records for verification |
| Verification Worker | Stage 4 | Verifies healing outcomes, retries or escalates on failure |

---

## Detection Engines

| Engine | What it detects | State |
|---|---|---|
| Feature Rule Engine | Status codes, latency, failure tags | Stateless |
| Rate Based Engine | Sustained error rate over time window | Redis |
| Silence Detection Engine | Service stops producing logs | Redis |
| Baseline Anomaly Engine | Deviation from historical average | Redis |

---

## Causal Engine

The Analyser Worker runs a causal engine for every detected anomaly:

- **LLM mode**: When `requires_llm` is true, queries a local Ollama
  instance (LLaMA3) with enriched anomaly context to produce root
  cause analysis with confidence scoring.
- **Rule fallback**: When LLM is disabled or fails, uses a rule-based
  fallback that maps anomaly reasons to known root causes.

Output: `{ root_cause, confidence, suggested_action, analysis_type }`

---

## Redis Keys

| Key | Type | Written by | Read by |
|---|---|---|---|
| observation:logs | List capped 1000 | Consumer | API |
| observation:pending_detection | Queue | Consumer | Detection Worker |
| observation:anomalies | List capped 1000 | Detection Worker | API |
| analyser:pending | Queue | Detection Worker | Analyser Worker |
| incident:reports | List capped 1000 | Analyser Worker | API |
| dispatcher:pending | Queue | Analyser Worker | Dispatcher Worker |
| healing:actions | List capped 1000 | Dispatcher Worker | API, Verification Worker |
| escalation:alerts | List capped 100 | Verification Worker | API |
| anomaly_stats:type | Hash | Detection Worker | API |
| anomaly_stats:endpoint | Hash | Detection Worker | API |
| rate:{service}:{endpoint}:errors | Counter TTL | Rate engine | Rate engine |
| last_seen:{service} | String | Silence engine | Silence checker |
| baseline:{service}:{endpoint} | Hash | Baseline engine | Baseline engine |

---

## OpenSearch Indices

| Index | Written by | Contents |
|---|---|---|
| b-normalized-logs | Consumer | All normalized log entries |
| b-anomaly-records | Detection Worker | Full enriched anomaly detections |
| b-healthy-logs | Detection Worker | Lightweight healthy log records |
| b-healing-records | Dispatcher Worker | Healing action results |
| b-incident-reports | Analyser Worker | Human + machine incident reports |

---

## Project Structure

```
Niramay/
├── backend/
│   ├── app/
│   │   ├── simulation/          # Demo traffic and failure injection
│   │   │   ├── traffic_generator.py
│   │   │   ├── failure_config.py
│   │   │   └── failure_middleware.py
│   │   ├── observation/         # HTTP traffic capture
│   │   │   └── middleware.py
│   │   ├── ingestion/           # Log ingestion pipeline
│   │   │   ├── rabbitmq_consumer.py
│   │   │   ├── rabbitmq_publisher.py
│   │   │   ├── normalizer.py
│   │   │   └── opensearch_client.py
│   │   ├── detection/           # Stage 2: Anomaly detection
│   │   │   ├── index.py         # Pure detection scoring function
│   │   │   ├── worker.py        # Async detection pipeline loop
│   │   │   └── engines/         # Individual detection engines
│   │   │       ├── feature_rule_engine.py
│   │   │       ├── rate_based_engine.py
│   │   │       ├── silence_detection_engine.py
│   │   │       └── baseline_anomaly_engine.py
│   │   ├── causal_engine/       # AI root cause analysis
│   │   │   └── client.py        # Ollama LLaMA3 + rule fallback
│   │   ├── analyser/            # Stage 3: Classification + reporting
│   │   │   └── worker.py        # Causal analysis + incident reports
│   │   ├── dispatcher/          # Stage 4: Alert dispatch (skeleton)
│   │   │   └── worker.py        # Component A communication placeholder
│   │   ├── healing/             # Healing strategies + verification
│   │   │   ├── index.py         # Strategy selection + execution
│   │   │   └── verification_worker.py
│   │   ├── reporting/           # Incident report generation
│   │   │   ├── report_generator.py
│   │   │   └── templates/
│   │   ├── api/v1/              # REST API
│   │   │   ├── endpoints.py
│   │   │   └── schemas.py
│   │   └── core/                # Config and shared clients
│   │       ├── config.py
│   │       └── redis_client.py
│   └── tests/
│       ├── test_analyser_worker.py
│       └── test_dispatcher_worker.py
├── frontend/                    # React TypeScript dashboard
│   └── src/
│       ├── pages/
│       ├── components/
│       └── hooks/
├── docker-compose.yml
└── README.md
```

---

## Getting Started

### Prerequisites

- Docker Desktop
- Python 3.11 or higher
- Node 18 or higher

### Run with Docker

```bash
docker-compose up -d
```

Wait for all services to be healthy then open:
- Frontend dashboard: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- RabbitMQ management: http://localhost:15672
- OpenSearch: http://localhost:9200

### Run traffic simulation

```bash
cd backend
python simulation/traffic_generator.py
```

### Run tests

#### Backend (pytest)
```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

#### Frontend (vitest)
```bash
cd frontend
npm install
npm run test
```

---

## CI/CD Pipeline (Jenkins)

The project includes a declarative `Jenkinsfile` at the root for automated integration and testing.

### Local CI Execution
You can simulate the Jenkins pipeline locally using the provided script:
```bash
./scripts/local_ci.sh
```
This script will:
1. Run all backend unit tests.
2. Run all frontend unit tests.
3. Attempt a trial Docker build of both services.

### Jenkins Setup
To establish the pipeline in a Jenkins instance:
1. Create a new **Pipeline** job.
2. Set **Definition** to "Pipeline script from SCM".
3. Point to this repository and specify the `healing-ui` branch.
4. Ensure Jenkins has **Docker** and **Node.js** installed on the worker nodes.

---

---

## API Endpoints

| Method | Endpoint | Source | Description |
|---|---|---|---|
| GET | /api/v1/observation/logs | Redis | Real-time log feed |
| GET | /api/v1/observation/logs/history | OpenSearch | Historical logs |
| GET | /api/v1/detection/anomalies | Redis | Real-time anomaly feed |
| GET | /api/v1/detection/anomalies/history | OpenSearch | Historical anomalies |
| GET | /api/v1/healing/actions | Redis | Healing action results |
| GET | /api/v1/escalations | Redis | Escalation alerts |
| GET | /api/v1/incident/reports | Redis | Incident reports |
| GET | /api/v1/incident/reports/history | OpenSearch | Historical reports |
| GET | /api/v1/stats | Redis | System statistics |
| GET | /api/v1/failure-simulator/status | Config | Simulator status |
| GET | /api/v1/failure-simulator/scenarios | Config | Available scenarios |

---

## Current Implementation Status

| Component | Status |
|---|---|
| Component C: Demo application | In progress |
| Component B Stage 1: Log ingestion | Complete |
| Component B Stage 2: Rule based detection | Complete |
| Component B Stage 3: LLM classification + reporting | Complete |
| Component B Stage 4: Alert dispatch (skeleton) | Complete |
| Component A: Self healing | Planned |

---

## Team

[Add team member names here]
