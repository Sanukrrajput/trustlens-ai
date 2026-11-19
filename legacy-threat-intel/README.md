# Intelligent Cybersecurity Threat Intelligence Platform

A full-stack SOC platform that ingests **authorized** security telemetry, detects threats with configurable rules and optional machine learning, enriches indicators, correlates incidents, computes explainable risk scores, and presents everything in an interactive React dashboard. All state is persisted in MongoDB and all background work runs in-process via APScheduler.

> **Safety by design:** the platform never blocks IPs, disables accounts, isolates assets, deletes data, or contacts unauthorized sources automatically. Response actions are proposals only; execution is a manual, out-of-band operator decision and every approval is written to `audit_logs`.

---

## Table of contents

1. [Architecture](#architecture)
2. [Technology stack](#technology-stack)
3. [Quick start with Docker Compose](#quick-start-with-docker-compose)
4. [Local development](#local-development)
5. [Configuration](#configuration)
6. [Authorized data sources](#authorized-data-sources)
7. [MongoDB collections](#mongodb-collections)
8. [Detection, ML and risk scoring](#detection-ml-and-risk-scoring)
9. [API reference](#api-reference)
10. [Dashboard pages](#dashboard-pages)
11. [Testing](#testing)
12. [Operational notes and troubleshooting](#operational-notes-and-troubleshooting)

---

## Architecture

```
┌───────────────┐      REST / JSON (X-API-Key)      ┌────────────────────┐
│  React/Vite   │ ────────────────────────────────▶ │  FastAPI backend   │
│  SOC dashboard│ ◀──────────────────────────────── │  (single worker)   │
└───────────────┘                                    └─────────┬──────────┘
                                                               │
                       ┌───────────────────────────────────────┼──────────────────────┐
                       ▼                                       ▼                      ▼
            ┌────────────────────┐                 ┌──────────────────┐    ┌──────────────────┐
            │ Ingestion managers │                 │ Rule engine + ML │    │ Enrichment, risk │
            │ (auth + availability│                │ + correlation    │    │ alerting, audit  │
            │ gates, retries)    │                 │                  │    │                  │
            └─────────┬──────────┘                 └────────┬─────────┘    └────────┬─────────┘
                      │                                     │                       │
                      └──────────────────────────────▶ MongoDB ◀────────────────────┘
                                                   (12+ collections,
                                                    indexes, TTL, change streams)
```

* **Backend** (`backend/app/`) — FastAPI, PyMongo repositories, change-stream listener with polling fallback, APScheduler jobs, detection/ML, enrichment, correlation, risk scoring, alerting, response proposals and audit logging.
* **Frontend** (`frontend/src/`) — Vite + React + React Router + Recharts; every widget is backed by a real API call with loading/error/empty states, pagination, search, sorting and date filters.
* **Deployment** — `docker-compose.yml` runs MongoDB 7, the backend and an nginx-served production build of the frontend.

Collections, indexes and TTL policies are created automatically at startup from `backend/app/db/mongo.py`.

---

## Technology stack

| Layer | Technologies |
| --- | --- |
| API | Python 3.11+, FastAPI, Pydantic v2, Pydantic Settings, Uvicorn |
| Database | MongoDB 7 (also Atlas-compatible) via PyMongo |
| Detection / ML | scikit-learn (Isolation Forest, Random Forest, DBSCAN), pandas, NumPy, joblib |
| Automation | APScheduler, change streams + polling fallback |
| Frontend | React 18, Vite 5, React Router 6, Recharts 2, Bootstrap 5 |
| Ops | Docker Compose, structured JSON/console logging, env-driven config |
| Tests | pytest, mongomock |

---

## Quick start with Docker Compose

1. **Copy and edit the environment file.** Replace every placeholder secret with a long random value (for example from `openssl rand -hex 32`):

   ```bash
   cp env.example .env
   # edit .env: set API_KEY and VITE_API_KEY to the SAME value
   ```

2. **Build and start the stack:**

   ```bash
   docker compose up --build -d
   ```

3. **Open the dashboard** at <http://localhost:3000>. The API docs are at <http://localhost:8000/docs>.

4. **Verify health:**

   ```bash
   curl http://localhost:8000/health
   curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/status
   ```

5. **Stop the stack** (persisted data stays in named volumes):

   ```bash
   docker compose down
   ```

`VITE_API_URL=/api/v1` is proxied by nginx to `http://backend:8000`, so the browser never needs the backend port. The frontend build embeds `VITE_API_KEY`, which must match the backend `API_KEY`.

---

## Local development

### Backend

Requires Python 3.11+ and a reachable MongoDB (local or Atlas).

```bash
cd backend
python -m venv ..\.venv
..\.venv\Scripts\activate          # Windows
# source ../.venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

# from the repository root, create .env from env.example and set MONGODB_URI to
# mongodb://localhost:27017 for a local mongod, plus a real API_KEY

uvicorn app.main:app --reload --port 8000 --app-dir backend
```

Run Uvicorn with **one worker** in production — APScheduler and the change-stream listener must not be duplicated.

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to localhost:8000
npm run build      # production bundle in frontend/dist
```

For local Vite development set `VITE_API_URL=http://localhost:8000/api/v1` and `VITE_API_KEY` to the same key as the backend.

### Seed and training scripts

```bash
# Optional synthetic data for a development demo (never used to make operational decisions)
..\.venv\Scripts\python.exe backend\scripts\seed_synthetic.py

# Train ML models from labeled human-verified events
..\.venv\Scripts\python.exe backend\scripts\train_models.py
```

---

## Configuration

All configuration is environment-driven through `backend/app/config.py`. See `env.example` for the full annotated list. Important groups:

| Group | Variables | Notes |
| --- | --- | --- |
| Core | `ENVIRONMENT`, `LOG_LEVEL`, `MONGODB_URI`, `MONGODB_DB`, `API_KEY`, `AUTH_ENABLED`, `CORS_ORIGINS` | Secrets are never written to source; public settings views mask them. |
| Scheduler | `SCHEDULER_ENABLED`, `CHANGE_STREAM_ENABLED`, `*_INTERVAL_MINUTES` | Set intervals in minutes. |
| Sources | `AUTHORIZED_SOURCES`, `ENABLED_SOURCES`, `WINDOWS_*`, `APPLICATION_LOG_*`, `URLHAUS_FEED_ENABLED` | A source is read **only** when listed in both authorized and enabled lists. |
| Threat intel | `TI_ENABLED`, `ABUSEIPDB_API_KEY`, `URLHAUS_API_KEY`, `TI_CACHE_TTL_HOURS`, `TI_RATE_LIMIT_PER_MINUTE` | External lookups honor rate limits; private/internal indicators are never transmitted. |
| Rules | `RULE_*`, `CRITICAL_ASSET_CRITICALITY`, `ML_MIN_TRAIN_SAMPLES` | Tunable via `.env` and (for supported keys) live via the settings API. |
| Risk | `RISK_WEIGHT_TI`, `RISK_WEIGHT_ML`, `RISK_WEIGHT_RULE`, `RISK_WEIGHT_ASSET`, `RISK_WEIGHT_CORRELATION` | Normalized to sum to 1. |
| Retention | `EVENT_RETENTION_DAYS`, `DETECTION_RETENTION_DAYS`, `*_RETENTION_DAYS` | Implemented as MongoDB TTL indexes. |
| Alerting | `ALERT_MIN_SEVERITY`, `ALERT_EMAILS`, `SMTP_*`, `WEBHOOK_*`, `RESPONSE_ACTIONS_ENABLED` | Delivery is deduplicated and retried; response is read-only by default. |
| Models | `MODEL_DIR`, `IF_CONTAMINATION` | Model artifacts are versioned and stored here. |

Secrets (`API_KEY`, `ABUSEIPDB_API_KEY`, `URLHAUS_API_KEY`, `SMTP_PASSWORD`, `WEBHOOK_SECRET`) are returned as `***configured***` by `/api/v1/intel/settings` and never by any other endpoint.

---

## Authorized data sources

The ingestion framework enforces two gates before any read: **authorization** (explicit operator trust) and **availability** (the source exists and is readable). Failed reads produce error records and exponential-backoff retries; events are normalized to UTC, validated and deduplicated by a stable fingerprint.

| Source | Enabled by default | How it works |
| --- | --- | --- |
| `windows_eventlog` | yes | On a Windows host, reads selected channels/event IDs with `wevtutil`. Configure `WINDOWS_EVENTLOG_CHANNELS`, `WINDOWS_EVENTLOG_EVENT_IDS` and lookback/max events. Disabled automatically on non-Windows hosts or without permission. |
| `windows_eventlog_file` | yes | Reads a portable exported Windows Event Log XML file from `WINDOWS_EVENTLOG_XML_PATH` (mount it into the backend container). Useful in Docker/Linux. |
| `application_log` | no | Reads local JSONL application logs at `APPLICATION_LOG_PATH`. Enable only for authorized paths. |
| `urlhaus_feed` | no | Optional URLhaus feed ingestion via `URLHAUS_FEED_ENABLED`; enable only if you are authorized to use that feed. |

Do **not** add other sources to `ENABLED_SOURCES` without explicit authorization. The **Data Collection Status** page shows per-source authorization, availability, cursors and recent job outcomes, and lets an operator run a collection or toggle a source on/off (each toggle is audited).

---

## MongoDB collections

Created/validated automatically at startup:

`events`, `detections`, `incidents`, `indicators`, `assets`, `notifications`, `audit_logs`, `jobs`, `source_status`, `health_checks`, `models`, `feedback`, plus `platform_settings` and `response_actions`.

* **Indexes** are created for common filters (timestamps, event type, source/destination IP, incident status, indicator value, audit actor/action).
* **TTL indexes** apply only where retention is defined (events, detections, notifications, jobs, audit logs, incidents).
* **Aggregation pipelines** power the overview time series, distributions and indicator summaries.
* **Change streams** refresh live views with a polling fallback when change streams are unavailable, and the database service reconnects automatically.

---

## Detection, ML and risk scoring

* **Rules** (`backend/app/detection/rules.py`) — 10 configurable rules (failed-login bursts, brute force, success-after-failures, unusual hours, API rate spikes, impossible travel, new admin tokens, service installs, high-severity correlation, malicious-confidence indicators). Every rule emits evidence and a reason.
* **ML** (`backend/app/detection/ml.py`) — Isolation Forest (unsupervised), Random Forest (supervised) and DBSCAN (clustering). Features are engineered in `detection/features.py` from normalized events. Models are versioned with joblib in `MODEL_DIR` and stored in the `models` collection.
* **Honest evaluation** — training uses a **grouped** train/test split (by host/account) to avoid leakage; precision, recall, F1 and false-positive rate are recorded per version. **No model is used for inference until it is trained and validated.** Untrained models never produce detections; rules keep operating.
* **Explainable risk** (`backend/app/risk/scoring.py`) — a 0–100 score built from weighted, normalized signals (threat intelligence, ML anomaly, rule severity, asset criticality, correlation). Each score records contributing signals, human-readable reasons, weights version, confidence/uncertainty and references to the source events. It is **not** a calibrated probability.
* **Correlation** (`backend/app/correlation/engine.py`) — groups detections/events into deduplicated incidents with a timeline, evidence, recommended analyst steps and a status (`new`, `investigating`, `contained`, `resolved`, `closed`, `false_positive`).
* **Investigation assistant** (`backend/app/investigation/assistant.py`) — produces structured, evidence-based narrative summaries. It never fabricates outcomes or attributes actions that are not in the data.

Analysts can submit verdict feedback (true/false positive), which is stored in `feedback` and becomes labeled training data after review.

---

## API reference

Interactive Swagger UI: <http://localhost:8000/docs>. All `/api/v1/*` endpoints require the `X-API-Key` header unless `AUTH_ENABLED=false` (not recommended).

| Area | Endpoints |
| --- | --- |
| System | `GET /health`, `GET /api/v1/status`, `GET /api/v1` |
| Overview | `GET /api/v1/core/overview/summary`, `GET /api/v1/core/overview/events-over-time` |
| Events & detections | `GET /api/v1/core/events`, `GET /api/v1/core/detections` (search, sort, date filters, pagination) |
| Incidents | `GET /api/v1/core/incidents`, `PATCH /api/v1/core/incidents/{id}/status`, `GET /api/v1/core/incidents/{id}/investigation` |
| Indicators | `GET /api/v1/intel/indicators`, `POST /api/v1/intel/indicators/enrich` |
| Assets | `GET/POST /api/v1/intel/assets`, `PATCH /api/v1/intel/assets/{id}` |
| Models | `GET /api/v1/intel/models`, `POST /api/v1/intel/models/train` |
| Sources & jobs | `GET /api/v1/intel/sources`, `POST /api/v1/intel/sources/{name}/collect`, `PATCH /api/v1/intel/sources/{name}`, `GET /api/v1/intel/jobs` |
| Settings & health | `GET/PUT /api/v1/intel/settings`, `GET /api/v1/intel/system/health` |
| Notifications & audit | `GET /api/v1/admin/notifications`, `POST /api/v1/admin/notifications/{id}/read`, `GET /api/v1/admin/audit-logs` |
| Response | `POST/GET /api/v1/admin/response-actions`, `POST /api/v1/admin/response-actions/{id}/approve` |

Manual job triggers are available under `/api/v1/core/run/{job_name}` for operators who want to force collection, detection, enrichment or correlation.

---

## Dashboard pages

All 14 pages read live API data; none contain hardcoded operational data.

| Group | Pages |
| --- | --- |
| Operations | Overview, Live Events, Incidents, Investigation |
| Intelligence | Threat Intelligence, Suspicious IPs, Domain & URL, AI Anomaly Detection |
| Assets & Models | Monitored Assets, ML Model Performance |
| Automation & Governance | Data Collection Status, Notification Center, Audit Logs, System Settings |

Common UI behavior: loading spinners, error boxes with retry, empty states, pagination, search, sorting (where supported) and date filters. The top bar polls `/api/v1/status` every 30 seconds to show database health and automation state.

---

## Testing

```bash
# Backend unit/integration tests (mongomock, no live MongoDB required)
..\.venv\Scripts\python.exe -m pytest backend/tests -q --tb=short

# Frontend production build (verifies all imports and JSX compile)
cd frontend && npm run build
```

The suite covers rule detection, ML training/metrics, risk explanation, correlation, API routes and the end-to-end ingestion→detection→incident pipeline. Tests use mongomock so they are CI-friendly.

---

## Operational notes and troubleshooting

* **Single worker.** Run one Uvicorn process; APScheduler and change streams are process-local.
* **API key mismatch.** If the dashboard shows authentication errors, confirm `VITE_API_KEY` and `API_KEY` are identical and rebuild the frontend after changing either.
* **No events in Docker.** The live Windows Event Log collector cannot read the host log from inside Linux. Use `windows_eventlog_file` with a mounted exported XML (`WINDOWS_EVENTLOG_XML_PATH`), run the backend on a Windows host, or enable `application_log` for an authorized path.
* **Models untrained.** ML stays disabled until `train_models.py` produces a validated version backed by labeled data; this is intentional and visible on the ML Model Performance page.
* **Change streams unavailable.** The listener automatically falls back to polling; check `/api/v1/intel/system/health` for the active mode.
* **Slow first load.** The first overview render waits on aggregation queries; subsequent loads are faster once indexes exist.
* **Secrets.** Never commit `.env`. Rotate `API_KEY` and provider keys regularly; the repository contains only `env.example`.

---

## Safety and compliance summary

* Only explicitly authorized and enabled sources are read; availability and permissions are checked first.
* Private/internal IPs and hostnames are never sent to external enrichment providers.
* Rules are explainable; ML output is labeled with model version and metrics and is never presented as a confirmed attack without validation.
* Risk scores are explainable signals, not calibrated probabilities or automated verdicts.
* Response actions are proposals; the platform performs **no** blocking, disabling, isolation, deletion or other disruptive action. Approvals are logged in `audit_logs` and require a human to execute out of band.
