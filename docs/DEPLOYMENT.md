# TrustLens AI — Deployment Guide

This document describes how the application is configured and deployed from the files in this repository. It does **not** assume that a live environment or production credentials exist. A local root `.env` holds Razorpay **test** keys and a generated webhook secret only; `.env.example` is the canonical template, and an old copy is kept only as `legacy-threat-intel/.env.backup` (it is not read by the application or Compose). Never commit `.env`.

> **Render:** A [Render Blueprint](../render.yaml) and [step-by-step guide](RENDER_DEPLOYMENT.md) are included for API, Celery worker/beat, Redis and the static frontend. They are **manifests only**: no Render deployment was performed. Render requires a Git repository and an external MongoDB URI; the Compose instructions below remain the local/full-stack reference.

## Prerequisites

| Requirement | Why it is needed | Notes |
| --- | --- | --- |
| Docker Engine + Docker Compose v2 | Runs the full stack | Compose must support `env_file: { path, required: false }`; CI validates with `docker compose config --quiet`. |
| Python 3.12 | Local backend / test runs | The backend image uses `python:3.12-slim`. Dependencies are pinned in `backend/requirements.txt` and `backend/requirements-dev.txt`. |
| Node.js 20 + npm | Local frontend / test runs | The frontend image builds with `node:20-alpine`. |
| `tesseract-ocr` and `libjpeg` | OCR/document handling | Installed in the backend image. Install OS packages locally only if you exercise OCR outside Docker. |
| Ports `8000` and `3000` free | Default Compose publishing | Override with `API_PORT` / `WEB_PORT`. |
| MongoDB / Redis | Production and Compose runtime | **Not required locally**: the API falls back to `mongomock` outside production, and Celery falls back to eager/in-memory execution when no broker is available. |

## Architecture at a glance

The Compose project is named `trustlens-ai`.

| Service | Image / build | Role | Published port | Persistent state |
| --- | --- | --- | --- | --- |
| `mongodb` | `mongo:7.0` | Primary document store | none (internal) | `mongodb_data` volume at `/data/db` |
| `redis` | `redis:7.4-alpine` | Celery broker/result backend; started with `--appendonly yes` | none (internal) | `redis_data` volume at `/data` |
| `api` | Built from `backend/Dockerfile` | FastAPI/Uvicorn API | `${API_PORT:-8000}:8000` | none (uses the two services above) |
| `worker` | Same backend image | Celery worker on queue `celery`, concurrency `2` | none | none |
| `beat` | Same backend image | Celery beat scheduler | none | none |
| `frontend` | Built from `frontend/Dockerfile` | React SPA served by nginx | `${WEB_PORT:-3000}:80` | none |

Backend image details: `python:3.12-slim`, installs `curl`, `tesseract-ocr`, and `libjpeg62-turbo`, copies `requirements.txt`, `app/`, `scripts/`, and `models/`, runs as `appuser` with UID `10001`, sets `MODEL_DIR=/app/models` and `DATA_DIR=/app/data`, exposes `8000`, and starts:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
```

Frontend image details: multi-stage `node:20-alpine` dependency/build stages, then `nginx:1.27-alpine`. `VITE_API_URL` is a **build-time** `ARG` defaulting to `/api/v1`. `nginx.conf` proxies `/api/` to `http://api:8000` with the full URI preserved, serves `GET /health` as plain `ok`, and uses `try_files ... /index.html` for SPA fallback.

## Local development without Docker

No MongoDB or Redis needs to be started. If MongoDB is unreachable, the API logs a warning and starts with an in-memory store; `GET /health` then reports `"status": "degraded"` and `"in_memory_fallback": true`. In production this fallback is disabled and startup fails instead.

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt

$env:PYTHONPATH = "backend"
$env:MODEL_DIR = "backend\models"
$env:DATA_DIR = "backend\data"
$env:CELERY_ENABLED = "false"
$env:TASK_ALWAYS_EAGER = "true"

.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt

PYTHONPATH=backend \
MODEL_DIR=backend/models \
DATA_DIR=backend/data \
CELERY_ENABLED=false \
TASK_ALWAYS_EAGER=true \
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Vite listens on `http://localhost:5173` and proxies `/api` to `http://localhost:8000`, so the frontend can use the same-origin default `VITE_API_URL=/api/v1`. The API default CORS origins already include `http://localhost:5173` and `http://localhost:3000`.

> Path note: the current root `.env` only sets billing variables, so backend settings still default to `./models` and `./data` relative to the process working directory. The explicit `MODEL_DIR` / `DATA_DIR` above point at the artifacts that actually exist in this repository. `backend/scripts/train_models.py` resolves relative paths against `backend/` when the path does not exist.

## Docker Compose deployment

Run all commands from the repository root.

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Expected published endpoints after startup:

| URL | Expected result |
| --- | --- |
| `http://localhost:8000/health` | JSON with `status: ok` (or `degraded` only if the development in-memory fallback was used) |
| `http://localhost:8000/api/v1/health` | API health route |
| `http://localhost:3000/health` | Plain text `ok` |
| `http://localhost:3000/` | React SPA |

Stop without deleting data:

```bash
docker compose down
```

`docker compose down -v` removes the `mongodb_data` and `redis_data` volumes and is destructive.

### Compose environment precedence

The root `.env` is optional (`env_file` uses `required: false`). If present, it supplies values to all backend services. However, the Compose `environment:` block **overrides** these keys for `api`, `worker`, and `beat`:

| Key | Compose value |
| --- | --- |
| `MONGODB_URI` | `mongodb://mongodb:27017` |
| `MONGODB_DB` | `${MONGODB_DB:-trustlens}` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `MODEL_DIR` | `/app/models` |
| `DATA_DIR` | `/app/data` |
| `CELERY_ENABLED` | `"true"` |
| `TASK_ALWAYS_EAGER` | `"false"` |

Other settings (for example `ENVIRONMENT`, `SECRET_KEY`, API credentials, retention values) come from the root `.env` or the process environment. The frontend API URL is set at image build time via `VITE_API_URL` (`${VITE_API_URL:-/api/v1}` in Compose).

## Environment configuration

1. Copy the canonical template: `cp .env.example .env` (Windows: `copy .env.example .env`).
2. Edit `.env`. Never commit it; `.gitignore` excludes `.env` and `.env.*` except `.env.example`.
3. Keep empty values empty unless you deliberately configure that integration. Empty means "not configured" and the platform reports integrations honestly instead of inventing results.

| Group | Representative keys | Guidance |
| --- | --- | --- |
| Core | `APP_NAME`, `ENVIRONMENT`, `LOG_LEVEL`, `SECRET_KEY`, `JWT_ALGORITHM`, token lifetimes | Set `ENVIRONMENT=production` and a strong `SECRET_KEY` in production. |
| Network | `CORS_ORIGINS`, `ALLOWED_HOSTS`, `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_WINDOW_SECONDS` | Replace `ALLOWED_HOSTS=*` and localhost CORS values for real deployments. Rate limiting is per-process; tune the window with the limit. |
| Persistence/workers | `MONGODB_URI`, `MONGODB_DB`, `REDIS_URL`, `CELERY_ENABLED`, `TASK_ALWAYS_EAGER`, scheduler intervals, `RETENTION_ENABLED`, `RETENTION_DAYS`, `AUDIT_RETENTION_DAYS` | Compose supplies the service URLs shown above. Retention is enforced by a nightly beat task and the admin trigger; see [RETENTION.md](RETENTION.md). |
| Storage/uploads | `MODEL_DIR`, `DATA_DIR`, `MAX_UPLOAD_MB`, `ALLOWED_UPLOAD_MIME`, URL fetch limits | Compose fixes model/data paths at `/app/models` and `/app/data`. |
| Demo seeding | `SEED_DEMO_DATA`, `DEMO_*`, `ADMIN_*` | Development only. See production hardening below. |
| Login verification | `TURNSTILE_ENABLED`, `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`, `TURNSTILE_EXPECTED_HOSTNAME` | Both keys required. Create a Turnstile widget for the production hostname; the secret stays server-side. Without keys the API reports `not_configured` and login is not challenged. |
| External intelligence | `VIRUSTOTAL_API_KEY`, `GOOGLE_*`, `MCA_*`, `RDAP_ENABLED`, `DNS_ENABLED`, `TLS_ENABLED` | All credentials are empty in the template; MCA has no official public API. |
| Notifications | `SMTP_*`, `SMS_*`, `NOTIFY_EMAIL_ON_HIGH_RISK` | Empty provider settings mean notifications are unavailable. |
| Billing | `RAZORPAY_*`, `STRIPE_*`, `PAYMENT_CURRENCY` | Paid access is granted only by verified webhooks; checkout returns `503` when unconfigured. Razorpay dashboard/webhook steps: [RAZORPAY_SETUP.md](RAZORPAY_SETUP.md). |
| Plans/risk weights | `*_SCAN_LIMIT`, `RISK_WEIGHT_CONTENT/URL/BRAND/THREAT/COMMUNITY`, `RISK_BAND_*_MAX` | Seeded defaults `0.30 / 0.25 / 0.25 / 0.10 / 0.10` and bands `19 / 39 / 59 / 79`; plans are editable through the admin API, weights are normalised at runtime, and band bounds must be ordered 0–100. Legacy six-weight variables are ignored. |

The backend config validator rejects production startup when `ENVIRONMENT` is `production`/`prod` and `SECRET_KEY` is still the development default. Generate one with:

```bash
openssl rand -hex 48
```

Demo/admin seeding is automatically disabled in production when weak default passwords or the development secret are used. Do not rely on the demo/admin accounts in a real deployment.

## Production hardening

- [ ] Set `ENVIRONMENT=production` and a unique high-entropy `SECRET_KEY`.
- [ ] Set `ALLOWED_HOSTS` to the exact external hostname(s); FastAPI installs `TrustedHostMiddleware` whenever the value is not `*`.
- [ ] Set `CORS_ORIGINS` explicitly; do not use `*` in production.
- [ ] Configure `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY` for the production hostname (optionally pin `TURNSTILE_EXPECTED_HOSTNAME`); leave both empty only for local development.
- [ ] Leave `SEED_DEMO_DATA` disabled or ensure strong non-default credentials are supplied; never expose the development demo/admin accounts.
- [ ] Configure only the external credentials you actually intend to use; leave the rest empty so "not configured" status remains truthful.
- [ ] Terminate TLS at a trusted reverse proxy; see below.
- [ ] Restrict access to the Docker host and the internal MongoDB/Redis network. The Compose file does not enable authentication on either service.
- [ ] Back up named volumes before upgrades; see below.
- [ ] Keep the root `.env` out of source control. The `legacy-threat-intel/.env.backup` file is a historical artifact, not a deployment source.
- [ ] Note that FastAPI disables `/docs` and `/openapi.json` in production and adds an HSTS response header; do not treat that as a substitute for TLS.

## TLS and reverse proxy

The shipped nginx configuration listens on plain HTTP port `80`; Compose does not include a TLS-terminating proxy or certificates. Put a TLS-terminating reverse proxy in front of the `frontend` service (or replace the frontend container with your own TLS-enabled configuration) for any non-local deployment.

The proxy should:

- forward requests for `/` to `frontend:80` and preserve `Host`, `X-Forwarded-Proto`, and `X-Forwarded-Host`;
- send `/api` traffic through the frontend nginx route (it already proxies to `api:8000`) or proxy directly to `api:8000` with equivalent headers;
- use the external hostname in `ALLOWED_HOSTS` and `CORS_ORIGINS`;
- keep `VITE_API_URL=/api/v1` so browser calls stay same-origin;
- redirect HTTP to HTTPS and manage certificate renewal outside this repository.

Uvicorn is started with `--proxy-headers`, and the frontend nginx sets `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-For`, and `X-Real-IP`. Note that the shipped `nginx.conf` sets `X-Forwarded-Proto $scheme` from its own HTTP listener, so an outer TLS proxy that needs the API to observe `https` must either proxy directly to the API with the correct header or use an adjusted nginx configuration.

## Backups and restore

`scripts/backup_tool.py` provides a real logical backup/verify/restore workflow using JSON Lines and SHA-256 manifests. The backup contains personal data: keep it outside the web root, restrict permissions and encrypt it at rest. The lower-level `mongodump` and volume-snapshot examples below remain available for full-fidelity operational copies.

```bash
# Create a checksummed logical backup under backups/
python scripts/backup_tool.py create --uri mongodb://localhost:27017 --db hireshield --out backups

# Verify hashes and document counts without touching the database
python scripts/backup_tool.py verify --dir backups/trustlens-<timestamp>

# Restore into a scratch database; --confirm is mandatory
python scripts/backup_tool.py restore --uri mongodb://localhost:27017 \
  --db hireshield_restore_test --dir backups/trustlens-<timestamp> --confirm
```

Restore without `--confirm` returns `{"status": "refused"}` and makes no changes. A real production restore should be performed into an isolated database first and compared with the manifest before replacing service data.

Confirm the actual Compose volume names first (the project name `hireshield-ai` is deliberately preserved):

```bash
docker volume ls --filter name=hireshield-ai
```

Compose normally creates `hireshield-ai_mongodb_data` and `hireshield-ai_redis_data`.

### Logical MongoDB dump

```bash
docker compose exec mongodb mongodump --archive=/tmp/mongo.archive.gz --gzip
docker compose cp mongodb:/tmp/mongo.archive.gz ./mongo.archive.gz
docker compose exec mongodb rm /tmp/mongo.archive.gz
```

Restore (destructive; `--drop` replaces existing collections):

```bash
docker compose cp ./mongo.archive.gz mongodb:/tmp/mongo.archive.gz
docker compose stop api worker beat frontend
docker compose exec -T mongodb mongorestore --archive=/tmp/mongo.archive.gz --gzip --drop
docker compose exec mongodb rm /tmp/mongo.archive.gz
docker compose start api worker beat frontend
```

### Volume-level snapshot (MongoDB + Redis)

Take the snapshot with the stack stopped so the database and AOF files are consistent:

```bash
docker compose stop
docker run --rm -v hireshield-ai_mongodb_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/mongodb_data.tgz -C /data .
docker run --rm -v hireshield-ai_redis_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/redis_data.tgz -C /data .
docker compose start
```

Restore into stopped containers (this **replaces** the volume contents):

```bash
docker compose stop
docker run --rm -v hireshield-ai_mongodb_data:/data -v "$PWD":/backup alpine \
  sh -c 'find /data -mindepth 1 -delete && tar xzf /backup/mongodb_data.tgz -C /data'
docker run --rm -v hireshield-ai_redis_data:/data -v "$PWD":/backup alpine \
  sh -c 'find /data -mindepth 1 -delete && tar xzf /backup/redis_data.tgz -C /data'
docker compose start
```

On Windows, replace `"$PWD"` with an absolute host path accepted by Docker. Model artifacts are baked into the backend image (`/app/models`) and are **not** in a named volume; retrained models require a new image build or an explicit volume override.

## Upgrades and rollback

1. Record the currently running image tags/digests (for example `docker compose images`) and back up the volumes.
2. Apply your configuration changes to the root `.env` or your deployment override.
3. Validate and roll out:

   ```bash
   docker compose config --quiet
   docker compose pull
   docker compose up -d
   docker compose ps
   ```

4. Verify `/health` on the API and frontend and check `docker compose logs -f api worker beat` for startup errors.

Rollback options:

- If deploying published GHCR images, pin the override back to the previous image tag and run `docker compose up -d`.
- If deploying local builds, check out the previous known-good revision, rebuild with `docker compose up --build -d`, and redeploy.
- Restore volume backups only if the failure included data corruption or an incompatible data change; simply restarting old images against unchanged data is usually safer.

> Compose detail: the checked-in file defines `build:` for `api`, `worker`, `beat`, and `frontend` but no `image:`. As written, `docker compose pull` refreshes the MongoDB and Redis images; it does not pull the application images from GHCR. A server-side override that sets `image:` for those services is required to consume the published release artifacts with the rollout command above.

## Health checks

| Component | Check | Schedule (Compose unless noted) |
| --- | --- | --- |
| `mongodb` | `mongosh --quiet --eval "db.adminCommand('ping').ok"` | every `10s`, timeout `5s`, 5 retries, `20s` start period |
| `redis` | `redis-cli ping` | every `10s`, timeout `5s`, 5 retries |
| `api` | `curl -fsS http://127.0.0.1:8000/health` | every `30s`, timeout `5s`, 3 retries, `30s` start period |
| `api` image (Dockerfile) | `curl -fsS http://localhost:8000/health` | every `30s`, timeout `5s`, 3 retries, `20s` start period |
| `frontend` image | `wget -q -O /dev/null http://127.0.0.1/health` | every `30s`, timeout `5s`, 3 retries, `10s` start period |

`GET /health` on the API returns `status`, `version`, `environment`, `database`, `in_memory_fallback`, and `started_at`. The frontend `/health` route returns plain text `ok`. Worker and beat liveness is visible through process state and logs; there is no dedicated queue-depth health check.

Useful commands:

```bash
docker compose ps
docker compose logs -f api worker beat
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:3000/health
```

## Troubleshooting

| Symptom | Check / likely cause |
| --- | --- |
| `docker compose config` fails on `env_file` | Use a recent Compose v2 that supports `required: false`. |
| API health says `degraded` | Development-only MongoDB fallback is active; data is in memory. In production the API would fail startup instead. |
| `503 database temporarily unavailable` | MongoDB is unreachable or unhealthy; inspect `docker compose logs mongodb api`. |
| External intelligence shows `not_configured` | Expected when provider keys are empty in `.env`. |
| Checkout returns `503 not configured` | Expected for Stripe, or for Razorpay when keys are absent. This workspace has Razorpay test keys locally, so Razorpay checkout should create a test order; see [RAZORPAY_SETUP.md](RAZORPAY_SETUP.md). |
| Razorpay payment succeeds but plan stays free | The signed webhook was not received or verified. Check `RAZORPAY_WEBHOOK_SECRET`, the registered webhook URL/events and the `payments` collection for `amount_mismatch`/`ignored` events. |
| Login/dashboard rejected by host checks | `ALLOWED_HOSTS` is too narrow or the reverse proxy forwards the wrong `Host`. |
| Browser CORS errors | Set `CORS_ORIGINS` to the real frontend origin; localhost defaults only cover development. |
| Deep-link refresh shows 404 | Confirm the runtime uses `frontend/nginx.conf` with `try_files ... /index.html`. |
| OCR/document parsing fails locally | Install `tesseract-ocr` and `libjpeg` on the host; they are already in the backend image. |
| `docker compose pull` does not update API/frontend | The checked-in Compose services are build-based; supply an override with `image:` as described above. |
| Workers do not process tasks | Confirm `redis` is healthy, `CELERY_ENABLED=true`, and `TASK_ALWAYS_EAGER=false` under Compose. |

## CI/CD explanation

### `.github/workflows/ci.yml`

Triggers: pushes to any branch, pull requests, and manual `workflow_dispatch`. It performs no deployment.

| Job | Steps |
| --- | --- |
| `backend` | Python 3.12 setup, install `backend/requirements-dev.txt`, `python -m pip check`, `compileall` over app/tests/scripts, `python -m pytest backend/tests -q --tb=line`, training smoke into `${runner.temp}/hireshield-model-smoke` with `--log-level WARNING`. |
| `frontend` | Node 20 setup, `npm ci`, `npm ls --omit=dev`, `npm run build`, `npm run test -- --run` from `frontend/`. |
| `browser-extension` | Node 20 setup and `npm test` from `browser-extension/` (permission and extraction contract tests). |
| `security` | Blocking `python scripts/secret_scan.py`; report-only `pip-audit` and `npm audit --omit=dev --audit-level=high` JSON artifacts. Dependency updates are handled by `.github/dependabot.yml`. |
| `containers` | `docker compose config --quiet`, build `hireshield-api:ci` from `backend/Dockerfile`, build `hireshield-frontend:ci` from `frontend/Dockerfile`. |

### `.github/workflows/container-release.yml`

Triggers: pushes to `main`, pushes of `v*` tags, and manual `workflow_dispatch`. It publishes two images to `ghcr.io`:

- `<owner>/<repo>/hireshield-api`
- `<owner>/<repo>/hireshield-frontend`

Tags include branch, tag, commit SHA, and `latest` for the default branch. The workflow authenticates with the built-in `GITHUB_TOKEN` (`packages: write`). The frontend is built with `VITE_API_URL=/api/v1`.

Publishing is **not** deployment. The documented production rollout remains an explicit server-side action after configuring `.env`:

```bash
docker compose pull && docker compose up -d
```

## Known limitations

- No MongoDB, Redis, or live deployed environment is configured in this working tree.
- No external API, SMTP, SMS, or payment credentials are configured; empty values are intentional.
- Compose does not enable MongoDB/Redis authentication, TLS, or a separate reverse proxy.
- Compose has no `image:` for application services, so GHCR release artifacts require a deployment override.
- Model artifacts are copied into the backend image; retraining does not automatically update a running container.
- Health checks cover HTTP readiness and datastore pings but do not validate Celery beat schedules, queue depth, external integrations, or backup integrity.
- MongoDB/Redis data durability depends on the named volumes and the operator procedures above. A logical backup/verify/restore tool is included, but scheduling, encryption at rest and restore drills remain operator responsibilities.
- `pip-audit` reports `python-jose`/`ecdsa` advisories without published fixes; npm reports two moderate React Router advisories. See [SECURITY.md](SECURITY.md) for mitigations and upgrade path.
- Development falls back to in-memory MongoDB and eager Celery; that behavior is intentionally unavailable in production.
- In this working tree `docker compose config --quiet` passed, but Docker image builds could not be executed locally because the Docker daemon was unavailable. CI performs those builds on a runner with Docker.
