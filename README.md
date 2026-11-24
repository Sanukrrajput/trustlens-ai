# TrustLens AI

**Explainable online-offer verification and digital fraud intelligence for ordinary internet users.**

TrustLens AI screens offers, advertisements, giveaways, scholarships, investments, promotions, recruitment messages, URLs and screenshots for fraud indicators. It combines transparent rules, consent-gated public-source intelligence and historical patterns into an evidence-backed assessment. Every score is accompanied by the signals that produced it, the sources that were attempted, the sources that succeeded, explicit limitations and next steps. Recruitment is supported as one offer category, never as the product identity. See [TRUSTLENS_CONCEPT.md](TRUSTLENS_CONCEPT.md) for the authoritative product definition, then [TRUSTLENS_ARCHITECTURE.md](docs/TRUSTLENS_ARCHITECTURE.md) and [TRUSTLENS_ROADMAP.md](docs/TRUSTLENS_ROADMAP.md) for implementation history.

**Live frontend (free static hosting):** <https://sanukrrajput.github.io/trustlens-ai/>. It is the same React UI served locally on port `5174`; API-backed actions require a running backend.

> **Honest framing:** TrustLens AI is a decision-support tool, not a background-check bureau, legal adviser, fraud insurer or guarantee of legitimacy. A low score is not proof that an opportunity is safe; an inconclusive score means the available evidence was insufficient. See the [Honesty and current limits](#honesty-and-current-limits) section.

---

## What it does

| Capability | What the code actually provides |
| --- | --- |
| Multi-format screening | `POST /api/v1/analysis/offer` (generic offers with category), `/job` (recruitment alias), `/message`, `/url`, `/document` (PDF, PNG/JPEG/WebP, plain text). Uploads are limited to 10 MB by default and MIME-validated. Image uploads use the optional local OCR engine; when no `tesseract` binary is installed the result is explicitly `not_configured`, and an image, logo or screenshot is never treated as proof of authenticity. |
| Generic-offer rules | Category-aware indicators for advance fees, credential requests, urgency, unrealistic claims, giveaway manipulation, scholarship fees and investment guarantees. No general-offer model is approved, so the primary offer signal is an explicitly named `offer_rule_fallback`. |
| Entity extraction | Company names, job titles, salary, recruiter emails, phone numbers, URLs, payment demands, sensitive-data requests, locations and text statistics. |
| Explainable risk scoring | Five weighted evidence categories (content 30%, URL 25%, brand 25%, threat 10%, community 10%) renormalised over the categories actually available. Five bands from `Low observed risk` (0–19) to `Critical risk indicators` (80–100), with an explicit `inconclusive` flag when coverage is low. Verified evidence receives boosts; missing evidence is never treated as a clean result. |
| Consent-gated intelligence | RDAP, DNS and TLS checks are enabled by default and require no credentials. External URL/domain/company lookups run only when `consent_external_lookups` is true. Corporate-registry verification has a *separate* `consent_corporate_registry_lookup` gate on `/company/verify`. |
| Brand and campaign states | Reports distinguish `verified_company`, `verified_official_campaign`, `unverified_advertisement`, `suspected_impersonation` and `not_attempted`. A registry match or logo never verifies a specific campaign; independent evidence is required for that state. |
| Threat-indicator store | MongoDB-backed, normalised and deduplicated indicators with source registry, timestamps, expiry/TTL, admin JSON import and optional SSRF-safe public feed refresh. No feed is configured by default; no match is never presented as a clean result. |
| Optional threat and registry feeds | VirusTotal, Google Safe Browsing v4, Google Web Risk v1 and a licensed corporate-registry intermediary are used only when configured. Unconfigured providers are reported as `not_configured`, never simulated. Safe Browsing v4 is documented in-code as non-commercial; commercial deployments should use Web Risk. MCA has no official public API, so a licensed/bulk intermediary with consent is required. |
| Reports and corrections | JSON report view, generated PDF report, admin CSV export, and a correction/feedback workflow (`false_positive`, `missed_fraud`, `identity_correction`, `other`) stored with `pending_review` status. |
| Monitoring and alerts | User-defined monitoring rules for companies, job titles, source URLs and keywords, with in-app notifications; email and SMS only when SMTP/SMS providers are configured. Only explicitly allow-listed job source URLs are fetched. |
| Accounts and administration | Registration with terms/privacy consent, login, refresh, logout, email verification and password reset flows; Argon2 password hashing; role-based admin endpoints for users, plans, models, reports, audit logs and task triggers. |
| Plan enforcement and billing | Plans seeded from code into MongoDB, scan-limit enforcement, Razorpay/Stripe checkout. Paid access is activated **only** by HMAC-verified webhooks; frontend success/cancel redirects never grant a paid plan. |
| Operational transparency | Public `GET /health`, `GET /api/v1/system/config` capability flags, security headers, audit logging and a 120-per-minute in-process rate limit on analysis endpoints. |
| Support assistant | A global chat widget answers common questions from curated project documentation. Questions and answers are logged in MongoDB under a random browser session ID, restored on later visits, and removable with a one-click clear action (30-day expiry). It is rate limited and returns an explicit fallback with suggested questions instead of generating or inventing an answer. |

---

## Architecture snapshot

| Layer | Implementation in this repository |
| --- | --- |
| API | FastAPI (Python 3.12 in CI), all product routes under `/api/v1`; docs/OpenAPI disabled when `ENVIRONMENT=production`. |
| Persistence | MongoDB via PyMongo, with repositories and audit collections. `mongomock` in-memory fallback is allowed **only outside production**; production startup fails if MongoDB is unavailable. |
| Background work | Celery 5 + Redis 7, with Celery Beat schedules for monitoring, domain refresh, analytics and health checks. If no broker is available, tasks run eagerly in-process (`task_always_eager`). |
| Machine learning | scikit-learn TF-IDF bundles with approval gates: EMSCAD job models, optional DIFrauD message/job models trained on real labelled deception text, and honest rule fallbacks for generic offers and rejected families. Artifacts are governed by `backend/models/model_manifest.json`; only `approved: true`, loadable artifacts are used. |
| Intelligence | Dedicated modules for extraction, rules, domain analysis, safe URL fetching (SSRF-protected), message analysis, company verification and anomaly/history checks. |
| Frontend | React 18 + TypeScript + Vite 5 + Tailwind CSS 3; `VITE_API_URL` defaults to `/api/v1`. Vite proxies `/api` to `http://localhost:8000` in development; nginx proxies `/api/` to `http://api:8000` in the container. |
| Reporting | ReportLab PDF generation and CSV export. |
| Packaging | `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `docker-compose.yml`, root `render.yaml`, `.dockerignore` files, `.env.example`. |
| CI/CD | `.github/workflows/ci.yml` (compile, tests, training smoke test, build, container config/builds) and `.github/workflows/container-release.yml` (GHCR images). |

Runtime capability flags are discoverable at `GET /api/v1/system/config`; secrets are redacted in the admin config view.

---

## Quick start — local development

Prerequisites: Python 3.12 and Node.js 20. No MongoDB or Redis installation is required for local development; the API falls back to in-memory storage and eager tasks if they are unavailable.

```powershell
# 1. From the repository root (Windows PowerShell)
Copy-Item .env.example .env          # optional for local dev; never commit .env

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

Open <http://localhost:5173>. The API root is <http://localhost:8000/> and interactive docs are at <http://localhost:8000/docs> outside production.

Linux/macOS equivalent:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
PYTHONPATH=backend MODEL_DIR=backend/models DATA_DIR=backend/data \
CELERY_ENABLED=false TASK_ALWAYS_EAGER=true \
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> The explicit `MODEL_DIR` / `DATA_DIR` values point at the artifacts that actually exist in this repository. The local root `.env` only sets billing variables, so backend path defaults remain relative to the process working directory.

### Quick start — Docker Compose

```powershell
Copy-Item .env.example .env          # review before any non-local use
docker compose config --quiet
docker compose up --build -d
```

Compose starts MongoDB, Redis, API, Celery worker, Celery Beat and the frontend nginx image. The UI is published on `${WEB_PORT:-3000}` (default <http://localhost:3000>) and the API on `${API_PORT:-8000}`. nginx proxies same-origin `/api/v1` calls to the API service. `VITE_API_URL` is a **build-time** argument (`/api/v1` by default).

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for environment precedence, production hardening, TLS, backups and upgrade/rollback notes. A **free-plan** Render Blueprint is provided in [`render.yaml`](render.yaml) and was previously deployed as an evaluation environment. It deploys only a free API web service and a static site; Redis, workers and beat are disabled because Render does not offer them free. Historical hosts (not verified in the latest local run): <https://hireshield-api-wets.onrender.com> and <https://hireshield-web-j72o.onrender.com>. MongoDB Atlas M0 is the external datastore; its URI exists only as a Render secret. This is **not a production launch**. See [docs/RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md).

---

## Local demo credentials

These accounts are created by `_seed_accounts` only when `SEED_DEMO_DATA=true` (the development default):

| Role | Email | Password |
| --- | --- | --- |
| Demo user | `demo@hireshield.io` | `DemoPass123!` |
| Admin | `admin@hireshield.io` | `AdminPass123!` |

The login page now offers an explicit **User login / Admin login** choice. Choose **Admin login** with `admin@hireshield.io` to open the admin console at `/app/admin`; choose **User login** with `demo@hireshield.io` to open the workspace at `/app`. The choice only routes the sign-in: `/auth/login` checks `access_mode` against the verified account role and returns **403** on a mismatch, admin endpoints still require an `admin`/`owner` token, and non-admins are redirected away from `/app/admin`. Selecting Admin never grants privileges by itself.

From the admin console, an admin or owner can provision additional `user`, `student`, `staff` or `admin` accounts in **Create account**. The role can never exceed the signed-in administrator's own role; `owner` is intentionally excluded and must be granted or seeded explicitly. Creation records an audit event and attempts a verification email when SMTP is configured.

### Remembered sign-ins and Cloudflare verification

- The sign-in form can remember the account email and the last successful sign-in (device, time, masked IP and Cloudflare country header) **on the local device only**. The server stores a keyed hash of a random browser identifier, never the identifier itself.
- Each successful login is persisted in `signin_events` and visible under **Settings → Sign-in security** (`GET /auth/signin-activity`). A sign-in from an unrecognised device raises an in-app notification and, when SMTP is configured, an email.
- Set `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY` (see `.env.example`) to enforce [Cloudflare Turnstile](https://developers.cloudflare.com/turnstile/) on login. The server calls Turnstile `siteverify` and denies the login on a missing, invalid or unverifiable token; the frontend never decides success. With no keys, `/auth/security-config` reports `status=not_configured` and no challenge is simulated.

### Plans, Razorpay and billing

Plan prices are loaded live from the admin-editable `plans` collection. With `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` configured, the API creates a real Razorpay order and the billing page opens the official Razorpay Checkout script with that order id. The checkout response and `/app/billing?checkout=success` callback are display-only; a subscription becomes paid only after the signed webhook is verified. `RAZORPAY_WEBHOOK_SECRET` is required for activation. Missing credentials return `503 not configured` rather than a simulated checkout.

This workspace now has a local `.env` with Razorpay **test** keys and a generated webhook secret; `/system/config` reports `razorpay=true`, `razorpay_mode=test`, `razorpay_webhook=true` and `billing_enabled=true`, and a real test order was created. The generated secret still needs to be registered in the Razorpay dashboard, and the test purchase → signed webhook → subscription drill has not yet been run. No live keys are configured. See [docs/RAZORPAY_SETUP.md](docs/RAZORPAY_SETUP.md) for dashboard, webhook, plan-price and test-mode instructions; PAN/KYC details stay in the Razorpay dashboard.

Production behaviour is deliberately restrictive: `ENVIRONMENT=production` requires a strong `SECRET_KEY` or startup fails, and demo seeding is automatically disabled when the weak default passwords are still present. Do not rely on auto-disable as a substitute for explicitly setting `SEED_DEMO_DATA=false`, rotating credentials and removing demo data before launch.

---

## Verification commands

Verified in this working tree on 20 November 2026:

```powershell
# Backend: 115 passed
.\.venv\Scripts\python.exe -m pytest backend/tests -q --tb=line

# Frontend: 29 passed across 7 files
cd frontend
npm run test -- --run

# Frontend production build: passed (tsc --noEmit && vite build)
npm run build

# Browser extension: 6 passed
cd ../browser-extension
npm test

# From the repository root: lint, config, secret and dependency checks
cd ..
.\.venv\Scripts\python.exe -m ruff check backend/app backend/tests backend/scripts scripts
docker compose config --quiet
.\.venv\Scripts\python.exe scripts/secret_scan.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit --requirement backend\requirements.txt --format json

# Dependency audits: both returned 0 vulnerabilities
cd frontend
npm audit --json
```

All checks above passed. The final structured E2E evidence was generated at `2026-11-20T08:49:58.788151+00:00` (15 PASS, 1 PARTIAL, 0 FAIL). `npm audit --json` and `pip-audit --format json` both report **0 vulnerabilities** after replacing `python-jose` with `PyJWT` and upgrading React Router to 7.x plus the Vite/Vitest toolchain. Both audits are blocking CI checks. Container *image builds* were not verified locally because the Docker daemon was not running; CI runs both builds. Full details are in [END_TO_END_VERIFICATION.md](END_TO_END_VERIFICATION.md) and [docs/TESTING.md](docs/TESTING.md).

---

## Configuration summary

The canonical template is [`.env.example`](.env.example). Empty values mean “not configured” and the platform reports the integration as unavailable.

| Area | Key variables | Default / rule |
| --- | --- | --- |
| Core | `APP_NAME`, `ENVIRONMENT`, `SECRET_KEY`, `LOG_LEVEL`, `CORS_ORIGINS`, `ALLOWED_HOSTS`, `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_WINDOW_SECONDS` | `development`; dev secret placeholder; dev CORS origins `localhost:5173`/`3000`; `ALLOWED_HOSTS=*` (TrustedHost middleware not added when `*`). Production requires a strong `SECRET_KEY`. Rate limits default to `120` requests per `60` seconds per client/path with `Retry-After` on `429`. |
| Storage/workers | `MONGODB_URI`, `MONGODB_DB`, `REDIS_URL`, `CELERY_ENABLED`, `TASK_ALWAYS_EAGER`, `SCHEDULER_ENABLED`, `RETENTION_ENABLED`, `RETENTION_DAYS`, `AUDIT_RETENTION_DAYS` | Localhost defaults; dev in-memory fallback; eager tasks without a broker. Retention is enforced by the nightly Celery task and admin trigger; see [docs/RETENTION.md](docs/RETENTION.md). |
| Uploads | `MAX_UPLOAD_MB`, `ALLOWED_UPLOAD_MIME`, `MAX_FETCH_BYTES`, `FETCH_TIMEOUT_SECONDS`, `MAX_REDIRECTS` | 10 MB; PDF/images/text; 256 KiB fetch cap; 8 s timeout; 4 redirects. |
| Intelligence | `RDAP_ENABLED`, `DNS_ENABLED`, `TLS_ENABLED`, `VIRUSTOTAL_API_KEY`, `GOOGLE_SAFEBROWSING_API_KEY`, `GOOGLE_WEBRISK_API_KEY`, `MCA_API_URL`, `MCA_API_KEY`, `MCA_REQUIRE_CONSENT`, `JOB_SOURCE_URLS` | RDAP/DNS/TLS on by default without keys; all external feeds off until keys are supplied; MCA requires a licensed intermediary and separate consent. |
| Notifications | `SMTP_*`, `SMS_*`, `NOTIFY_EMAIL_ON_HIGH_RISK` | Empty by default; in-app notifications still work. |
| Billing | `RAZORPAY_*`, `STRIPE_*`, `PAYMENT_CURRENCY` | Empty by default (checkout returns `503 not configured`). The free Render evaluation deployment leaves both providers blank; `/api/v1/system/config` is authoritative. `INR` is the currency default. |
| Plans | `FREE_SCAN_LIMIT`, `STUDENT_SCAN_LIMIT`, `PROFESSIONAL_SCAN_LIMIT`, `UNIVERSITY_SCAN_LIMIT`, `ENTERPRISE_SCAN_LIMIT` | `10 / 100 / 500 / 5000 / 100000`; seeded once, then admin-editable. |
| Risk weights | `RISK_WEIGHT_CONTENT/URL/BRAND/THREAT/COMMUNITY` | `0.30 / 0.25 / 0.25 / 0.10 / 0.10` (specification split), renormalised over available signal categories. Legacy `RISK_WEIGHT_ML/RULES/DOMAIN/COMPANY/HISTORY/MESSAGE` variables are ignored. |
| Score bands | `RISK_BAND_LOW_MAX`, `RISK_BAND_LIMITED_MAX`, `RISK_BAND_MODERATE_MAX`, `RISK_BAND_HIGH_MAX` | `19 / 39 / 59 / 79`; ordered 0–100 bounds produce the five documented category labels. |
| Frontend | `VITE_API_URL` | `/api/v1`; baked in at build time for the container. |

---

## Honesty and current limits

* **Most external API credentials remain unconfigured.** The free Render evaluation deployment leaves billing, Turnstile, SMTP/SMS and credentialed intelligence providers unconfigured, and `/api/v1/system/config` reports them honestly. Never commit or paste local credential files into chat.
* **No paid access from the browser.** Checkout initiation is server-side; only signed provider webhooks change subscription state.
* **Models are limited.** Two EMSCAD job models and two DIFrauD text models (message and job) are approved. DIFrauD models are preferred only when approved and loadable; rejected families and all generic offers use explicit rule fallbacks. DIFrauD is a real-world research corpus, not production-validated TrustLens traffic. See [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md), [docs/ML.md](docs/ML.md) and the active manifest for metrics and limitations.
* **Local fallback is not production.** The in-memory store and eager Celery execution are development conveniences. Production fails closed when MongoDB is unavailable.
* **Not launch-ready.** Legal drafts are unreviewed, no production secrets or **live** payment provider are configured (only Razorpay test keys), container images were not built locally, and there is no penetration test or production deployment evidence. Secret and dependency audits are clean and blocking in CI; details are in [docs/SECURITY.md](docs/SECURITY.md). See [docs/LAUNCH_READINESS.md](docs/LAUNCH_READINESS.md).
* **Repository state.** The TrustLens AI source of truth is <https://github.com/Sanukrrajput/trustlens-ai>. The frontend is published on free GitHub Pages at <https://sanukrrajput.github.io/trustlens-ai/> by [`.github/workflows/deploy-pages.yml`](.github/workflows/deploy-pages.yml); this is a static frontend only, so API-backed features still require the backend. The older HireShield Render hosts above are historical evaluation links and were not verified in the latest local run. Protected branches, release approvals and a production deployment process are still required before launch.
* **Legacy code.** The previous SOC application is preserved under `legacy-threat-intel/` for reference. It is **not** active code, is not referenced by the running application or Compose files, and should not be described as part of the TrustLens AI product.

---

## Documentation

* [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) — staged status, test evidence, model manifest, limitations and next steps.
* [docs/TRUSTLENS_ROADMAP.md](docs/TRUSTLENS_ROADMAP.md) — derived Stage 1–8 execution plan and acceptance evidence.
* [docs/TRUSTLENS_ARCHITECTURE.md](docs/TRUSTLENS_ARCHITECTURE.md) — target architecture mapped to implementation and deviations.
* [docs/SECURITY.md](docs/SECURITY.md) — threat model, implemented controls, audits and open risks.
* [docs/RETENTION.md](docs/RETENTION.md) — enforced retention policy, schedule and limitations.
* [docs/ENVIRONMENTS.md](docs/ENVIRONMENTS.md) — environment files, precedence, secrets and protected identifiers.
* [browser-extension/README.md](browser-extension/README.md) — MV3 permission model and user-triggered analysis flow.
* [mobile-app/README.md](mobile-app/README.md) / [mobile-app/PERMISSION_POLICY.md](mobile-app/PERMISSION_POLICY.md) — mobile plan and forbidden-access policy.
* [docs/BUSINESS.md](docs/BUSINESS.md) — segments, plan matrix from code, pricing guidance and commercial risks.
* [docs/LEGAL_DRAFTS.md](docs/LEGAL_DRAFTS.md) — non-lawyer drafts requiring mandatory counsel review.
* [docs/LAUNCH_READINESS.md](docs/LAUNCH_READINESS.md) — evidence-based go/no-go checklist.
* [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — configuration, container deployment, backups and troubleshooting.
* [docs/RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md) — Render Blueprint prerequisites, prompts, webhook setup and verification.
* [docs/TESTING.md](docs/TESTING.md) — exact commands, suite coverage and CI mapping.
* [docs/PRESENTATION_GUIDE.md](docs/PRESENTATION_GUIDE.md) — slide story, live demo script, architecture view and honest talking points.
* [frontend/src/components/ArchitectureScene3D.tsx](frontend/src/components/ArchitectureScene3D.tsx) — interactive 3D internal-architecture animation in the landing page.
