# HireShield AI — Testing Guide

This document describes the automated tests and smoke checks that exist in this repository. Commands below are reproducible from the repository root unless a section says otherwise. No running MongoDB, Redis, external API credentials, or deployed environment is required for the automated suites.

## Test layout

### Backend (`backend/tests/`)

| File | Test functions | Coverage |
| --- | ---: | --- |
| `test_api.py` | 20 | End-to-end API flows with `TestClient`, `mongomock://`, Celery disabled/eager, development demo seeding, Razorpay order creation and signed webhook transitions. |
| `test_ml.py` | 17 | Dataset preparation, feature construction, evaluation metrics, inference fallback/approval, risk scoring, and training gates. |
| `test_intelligence.py` | 27 (one parametrized over 11 URLs) | Explainable intelligence, SSRF defences, safe fetching, consent gating, evidence rules, and limited-mode behavior. |

`pytest` collects **64 test cases** in total.

Backend tests do not need local MongoDB or Redis:

- `test_api.py` sets `MONGODB_URI=mongomock://`, `CELERY_ENABLED=false`, `TASK_ALWAYS_EAGER=true`, and `SEED_DEMO_DATA=true` before importing the app.
- `test_intelligence.py` mocks all network calls; it never contacts external services.
- `test_ml.py` uses temporary directories for generated artifacts and explicitly verifies that synthetic fallback models are never approved.

### Frontend (`frontend/src/test/`)

| File | Tests | Coverage |
| --- | ---: | --- |
| `validation.test.ts` | 6 | Form validation rules for registration, passwords, login, job/message/URL/company inputs, monitoring targets, and feedback details. |
| `auth.test.tsx` | 8 | Login validation, explicit User/Admin selector, secure admin/user routing, role-mismatch rejection, registration consent enforcement, remembered email/previous sign-in display, and Turnstile token/device options; `authApi` is mocked. |
| `analysis.test.tsx` | 4 | Short-text blocking, job submission with consent and report navigation, URL validation, and immediate-result pass-through; `analysisApi` is mocked. |
| `admin.test.tsx` | 2 | Admin account provisioning form success state, exact payload, callback/refresh behaviour, and honest display of server rejection; `adminApi` is mocked. |
| `razorpay.test.ts` | 2 | Checkout script wrapper opens the server-created order, resolves the payment response, and rejects on dismissal; the Razorpay constructor is faked. |
| `billing.test.tsx` | 1 | Billing page opens Razorpay with the server order and does not claim paid access before the signed webhook; APIs and checkout are mocked. |

Vitest collects **23 tests across 6 files**. The frontend tests use `jsdom`, Testing Library, and mocked API modules; they do not exercise a live backend.

## Install test dependencies

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt

cd frontend
npm ci
cd ..
```

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements-dev.txt

cd frontend
npm ci
cd ..
```

`backend/requirements-dev.txt` includes the runtime requirements plus `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx`, `mongomock`, and `ruff`.

## Exact test commands

### Backend

Windows (PowerShell) — verified result: **64 passed**:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q --tb=line
```

Linux / macOS:

```bash
.venv/bin/python -m pytest backend/tests -q --tb=line
```

Compile check used by CI:

```powershell
# Windows
.\.venv\Scripts\python.exe -m compileall -q backend\app backend\scripts
```

```bash
# Linux / macOS
.venv/bin/python -m compileall -q backend/app backend/scripts
```

To run a single backend suite:

```powershell
# Windows
.\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest backend/tests/test_ml.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest backend/tests/test_intelligence.py -q --tb=short
```

```bash
# Linux / macOS
.venv/bin/python -m pytest backend/tests/test_api.py -q --tb=short
.venv/bin/python -m pytest backend/tests/test_ml.py -q --tb=short
.venv/bin/python -m pytest backend/tests/test_intelligence.py -q --tb=short
```

### Frontend

Windows (PowerShell) — verified result: **6 files passed, 23 tests passed**:

```powershell
cd frontend
npm run test -- --run
```

Linux / macOS:

```bash
cd frontend
npm run test -- --run
```

Production build check — verified result: **build passes**:

```powershell
# Windows
cd frontend
npm run build
```

```bash
# Linux / macOS
cd frontend
npm run build
```

`npm run build` runs `tsc --noEmit && vite build`. `--run` is required for a one-shot Vitest run; plain `npm run test` starts watch mode.

### Container configuration checks

These mirror the CI `containers` job and work on all platforms with Docker Compose v2:

```bash
docker compose config --quiet
docker build --file backend/Dockerfile --tag hireshield-api:ci backend
docker build --file frontend/Dockerfile --tag hireshield-frontend:ci frontend
```

Local verification status in this working tree: `docker compose config --quiet` passed, but both `docker build` commands were blocked because the Docker daemon (`npipe:////./pipe/dockerDesktopLinuxEngine`) was not running. Image builds remain an explicit CI/operator verification step.

## What each backend suite covers

### `backend/tests/test_api.py`

Runs the FastAPI app through `TestClient` against an isolated in-memory database.

- **Health, public config, headers**: `/health` and `/api/v1/health`; public config does not leak `secret_key`; security headers such as `X-Content-Type-Options` and `X-Frame-Options` are present.
- **Auth lifecycle**: register, login, `GET /auth/me`, refresh, logout, and rejection of the logged-out access token.
- **Job analysis flow**: submit a fraudulent-sample job without external consent, verify bounded risk score and weights version, list/get persistence, generate a report and PDF (`%PDF` prefix), and submit false-positive feedback with `pending_review` status.
- **Message and URL analysis**: message submission with `channel=whatsapp` and URL submission without consent; risk remains bounded and can be inconclusive.
- **Billing**: plan listing, free subscription state, and `503 not configured` when checkout is attempted with Razorpay keys explicitly cleared by the test (so a developer's local `.env` cannot make this assertion flaky).
- **Razorpay checkout and webhook security**: with mocked provider HTTP, checkout sends the plan amount, currency and server-created `notes`; unsigned webhooks are rejected; a correctly HMAC-signed `payment.captured` event using order notes activates the paid plan; an amount-mismatched event is recorded without changing entitlement. All signing secrets are patched within the tests, not read from the local `.env`.
- **RBAC**: non-admin is denied `/admin/dashboard`; seeded admin can access dashboard, users, models, reports, audit logs, plans, tasks, and config endpoints.
- **Company and monitoring**: company verification without consent and monitoring create/list/delete CRUD.
- **Notifications**: paginated response shape (`items`, `total`, `page`, `page_size`, `pages`) and creation expectations tied to the explainable score threshold.

### `backend/tests/test_ml.py`

- **Data handling**: EMSCAD label parsing (`t`/`f`, booleans, numeric forms), invalid-label dropping, duplicate removal, and synthetic dataset provenance that explicitly marks data as non-production.
- **Features**: bounded, canonical anomaly vectors with alias handling and non-finite value sanitisation; text normalisation replaces URLs with a token.
- **Metrics**: confusion matrix, precision/recall/F1/FPR/FNR/accuracy/ROC-AUC/PR-AUC on known values, degenerate single-class handling, FNR-focused threshold selection, and anomaly metric orientation.
- **Inference**: prediction contract validation, honest rule-based fallback when artifacts are missing, short-text inconclusive results, and manifest loading that honours approval status.
- **Risk engine**: category boundaries, inconclusive/no-evidence output, verified evidence weighted above unverified evidence, model confidence not reused as the risk score, and actionable high-risk guidance.
- **Training gates**: approval rejects a flag-everything model (precision/FPR), and the synthetic fallback path produces no approved models and falls back to rule-based inference.

### `backend/tests/test_intelligence.py`

- **Extraction**: legitimate, fraudulent, and ambiguous text; company names, job titles, salary, locations, emails, phone numbers, payment demands, sensitive data requests, and URL candidates.
- **Message analysis**: legitimate text is not labelled confirmed malicious; fraudulent text produces fee-demand, sensitive-data, urgency, phishing-link, and personal-email signals.
- **SSRF and safe fetch**: rejects localhost, loopback, IPv6 loopback, RFC1918, link-local metadata, credentials in URLs, non-HTTP schemes, and unusual ports without network/DNS calls; blocks private DNS answers and private redirect targets; preserves SNI when connecting to a pinned IP; returns structured results with sensitive headers filtered and certificate details.
- **Honest unconfigured state**: VirusTotal, Safe Browsing, and Web Risk report `not_configured`; disabled RDAP/DNS/TLS report `disabled`; no `confirmed_malicious` indicators are fabricated.
- **Heuristics and rules**: lookalike domains are labelled heuristic only; rule indicators are complete, deduplicated, severity-sorted, and satisfy the evidence schema.
- **Company verification**: no external lookup without consent; with consent, website evidence yields a partial result while registry limitations remain explicit.
- **Anomaly engine**: limited status, unavailable historical counts, and unavailable model when repositories are absent.

## CI mapping

| CI job (`ci.yml`) | Local equivalent |
| --- | --- |
| Backend: compile source | `.\.venv\Scripts\python.exe -m compileall -q backend\app backend\scripts` (Windows) / `.venv/bin/python -m compileall -q backend/app backend/scripts` (Linux/macOS) |
| Backend: run tests | `.\.venv\Scripts\python.exe -m pytest backend/tests -q --tb=line` / `.venv/bin/python -m pytest backend/tests -q --tb=line` |
| Backend: training smoke | See below; CI writes to `${runner.temp}/hireshield-model-smoke` with `--log-level WARNING` |
| Frontend: `npm ci`, `npm run build` | `cd frontend && npm ci && npm run build` |
| Frontend: `npm run test -- --run` | `cd frontend && npm run test -- --run` |
| Containers: config + builds | `docker compose config --quiet`, then the two `docker build` commands above |

CI triggers on every branch push, pull requests, and manual dispatch. It performs no deployment. `container-release.yml` is separate: it publishes API and frontend images to GHCR on `main`, `v*` tags, or manual dispatch; rollout is an explicit server-side step described in [DEPLOYMENT.md](./DEPLOYMENT.md).

## Model training smoke test

The repository contains `backend/data/raw/emscad_v1.csv` and existing artifacts in `backend/models/`. The training CLI prints a JSON summary and writes bundles plus `model_manifest.json` to the requested model directory.

Windows (PowerShell) — command used locally:

```powershell
.\.venv\Scripts\python.exe backend/scripts/train_models.py `
  --data-dir backend/data `
  --model-dir backend/models `
  --log-level INFO
```

Linux / macOS:

```bash
.venv/bin/python backend/scripts/train_models.py \
  --data-dir backend/data \
  --model-dir backend/models \
  --log-level INFO
```

CI-safe variant that does not modify the checked-in model directory:

```bash
python backend/scripts/train_models.py \
  --data-dir backend/data \
  --model-dir "${RUNNER_TEMP:-/tmp}/hireshield-model-smoke" \
  --log-level WARNING
```

This CI-safe command was also verified locally against a temporary directory. It produced the same two approved models and the same metrics as the checked-in manifest, while rejecting the message and anomaly models with explicit reasons.

The script resolves relative storage paths against `backend/` when the given path does not exist. If the real corpus is unavailable, the training code uses an explicitly non-production synthetic fallback and does not approve those models, as asserted by `test_ml.py`.

## Manual verification checklist

Use this after `docker compose up --build -d` as described in [DEPLOYMENT.md](./DEPLOYMENT.md). These are operator checks, not automated test results.

- [ ] `docker compose ps` shows `mongodb`, `redis`, `api`, `worker`, `beat`, and `frontend` running; datastore and API health checks are healthy.
- [ ] `curl -fsS http://localhost:8000/health` returns JSON with `status: ok` and `in_memory_fallback: false`.
- [ ] `curl -fsS http://localhost:3000/health` returns `ok`.
- [ ] Opening `http://localhost:3000` shows the SPA; refreshing a deep link such as a report URL still resolves through the nginx fallback.
- [ ] Registering a user, logging in, and opening `auth/me` works through the same-origin `/api/v1` route.
- [ ] Submitting a job description produces a result with a bounded risk score, indicators, and a report; the PDF endpoint returns PDF content.
- [ ] Message and URL submissions work with external-consent toggles off and report honest limitations.
- [ ] Unconfigured integrations are displayed as unavailable rather than returning invented intelligence.
- [ ] With development seeding enabled, the seeded admin can open admin pages and a normal user receives `403`.
- [ ] `docker compose logs -f api worker beat` shows no startup or task errors.
- [ ] In a development-only run configured with `CELERY_ENABLED=false` or no `REDIS_URL` (and/or `TASK_ALWAYS_EAGER=true`), tasks execute eagerly instead of requiring a broker.
- [ ] In production-like configuration, `/docs` and `/openapi.json` are disabled and responses include HSTS.

## Known gaps

- No test runs against real MongoDB or Redis; API tests use `mongomock`, and Celery is disabled/eager in tests.
- No browser-level end-to-end test against the running Compose stack; frontend tests mock `analysisApi`, `authApi`, `adminApi`, `billingApi` and the Razorpay checkout constructor, so client/server contracts are not verified automatically.
- Celery worker startup, beat schedules, queue depth, retries, and task idempotency are not covered by automated tests.
- No TLS/reverse-proxy, container-runtime healthcheck, backup/restore, load, or performance tests are included.
- External providers, SMTP/SMS, and live payment gateways are not exercised; the Razorpay test signs a locally generated webhook with an in-test secret.
- Real production model quality is not guaranteed: tests enforce provenance, approval gates, and fallback honesty, but the synthetic fallback is explicitly non-production.
- Dependency warnings appear during verified runs: Starlette/httpx test-client deprecation, `mongomock` use of deprecated `datetime.utcnow()`, and React Router v7 future-flag warnings. They do not fail the suites.
- Frontend `VITE_API_URL` is baked in at build time; changing it requires rebuilding the frontend image.
