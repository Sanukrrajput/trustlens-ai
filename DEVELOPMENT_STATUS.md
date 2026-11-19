# HireShield AI — Development Status

**Snapshot date:** 18 November 2026
**Overall assessment:** functional, tested prototype with deployable scaffolding. **Not fully launch-ready.** Local/demo operation is supported; production launch is blocked by configuration, security, legal, integration and operational gaps listed below.

All statements below are derived from files in this repository or from commands executed in this working tree. Nothing here should be read as evidence of a live production deployment.

---

## 1. Staged status

| Stage | Status | Evidence / boundary |
| --- | --- | --- |
| Product definition and UI/UX | **Done** | Landing, auth, dashboard, scanner, report, company intelligence, monitoring, billing, admin and legal draft pages exist in `frontend/src/pages/`. Terms/privacy consent is required at registration. |
| Core API and persistence | **Done** | FastAPI app with `/api/v1` routers for auth, analysis, company, monitoring, reports, notifications, billing, admin and system. MongoDB repositories plus a development-only `mongomock` fallback. |
| Explainable risk engine | **Done** | Six-component weighted scoring, availability-based renormalisation, evidence boosts, inconclusive handling and category bands in `backend/app/core/risk_engine.py`. |
| Intelligence modules | **Done (with limitations)** | Extraction, rules, message analysis, SSRF-protected URL fetch, RDAP/DNS/TLS, optional threat feeds, company verification with separate consent, and historical/anomaly checks. Unconfigured sources report honest statuses. |
| ML training and governance | **Done (partial capability)** | Manifest-gated approval, EMSCAD corpus training, metrics and threshold selection, rejected-model audit trail, rule fallbacks. Only two job-text models are approved; message/anomaly models are not. |
| Reports and feedback | **Done (basic)** | PDF generation, JSON report view, admin CSV export, correction reports stored as `pending_review`. No SLA, reviewer queue UI or export/deletion self-service was found. |
| Frontend tests and build | **Done** | 23 Vitest tests pass across 6 files; `npm run build` passes. |
| Backend tests | **Done** | 64 pytest tests pass across 3 files. |
| Container and CI scaffolding | **Done (partially verified)** | Dockerfiles, nginx config, Compose file, ignore files and two GitHub Actions workflows exist. `docker compose config --quiet` passed; image builds were blocked locally by an unavailable Docker daemon and are CI-verified. |
| Billing integration | **Partial** | Checkout creation, browser Checkout.js wrapper and HMAC-verified webhook state transitions are implemented and unit/integration tested. A local `.env` holds Razorpay **test** keys and a generated webhook secret; `/system/config` reports them and a real test order was created. Dashboard webhook registration and the signed webhook → subscription drill are still pending; no live keys. Free/enterprise plans have zero price and correctly do not open online checkout. |
| External intelligence integrations | **Partial** | RDAP/DNS/TLS are enabled without credentials; all credentialed feeds (VirusTotal, Safe Browsing/Web Risk, MCA intermediary) are unconfigured. |
| Notifications | **Partial** | In-app notifications work; SMTP and SMS are unconfigured, so email/SMS delivery is skipped. |
| Security hardening | **Partial** | Argon2, JWT rotate/revoke, RBAC, upload validation, SSRF protections, audit log and security headers exist. Production secret validation exists, but current defaults, in-process rate limiting and missing host/TLS/secret operational configuration block launch. |
| Legal and compliance | **Not done** | Draft Terms, Privacy, DPA, Acceptable Use, cookie/consent and takedown sections exist in `docs/LEGAL_DRAFTS.md` and draft UI pages, but have not been reviewed by qualified counsel. No signed DPA/process inventory/retention enforcement. |
| Production operations | **Not done** | No provisioned production database/broker, TLS termination, backup/restore drill, alerting, runbook ownership, rate-limit architecture, or release history. Workspace is not a git repository and no commits exist. |

---

## 2. Precise verification results

Executed in this working tree:

| Check | Command | Result |
| --- | --- | --- |
| Backend suite | `.\.venv\Scripts\python.exe -m pytest backend/tests -q --tb=line` | **64 passed**, 488 warnings in 20.61 s. Warnings are deprecation notices from Starlette/httpx, pytest-asyncio and mongomock. |
| Frontend suite | `npm run test -- --run` (in `frontend/`) | **23 passed** across **6 test files**: `validation.test.ts` (6), `auth.test.tsx` (8), `analysis.test.tsx` (4), `admin.test.tsx` (2), `razorpay.test.ts` (2), `billing.test.tsx` (1). React Router future-flag warnings were emitted, not failures. |
| Frontend build | `npm run build` | **Passed**: `tsc --noEmit && vite build`, 2217 modules transformed, `dist/` emitted in 5.81 s. |
| Compose configuration | `docker compose config --quiet` | **Passed** (per `docs/TESTING.md`; no Docker daemon required for this check). |
| Container image builds | `docker build --file backend/Dockerfile ...` / `frontend/Dockerfile` | **Not verified locally** — Docker daemon (`npipe:////./pipe/dockerDesktopLinuxEngine`) was not running. CI workflow performs both builds. |

Backend suite composition: `test_api.py` (auth lifecycle, remembered sign-ins/device recognition, sign-in activity ownership, new-device notification, Turnstile enforcement and fail-closed provider outage, analysis/report/feedback flow, consent behaviour, plan/checkout configuration failure, signed webhook activation, RBAC, company/monitoring CRUD and notifications), `test_ml.py` (data validation, synthetic-data honesty, features, metrics, inference contract, fallback behaviour, manifest gating, risk behaviour, training approval rules), `test_intelligence.py` (extraction, message analysis, SSRF cases, unconfigured-source honesty, lookalike heuristics, rule indicators, consent gates, limited anomaly mode).

CI additionally runs `python -m compileall -q backend/app backend/scripts` and a model-training smoke test writing to a temporary model directory.

---

## 3. Active model manifest

Manifest: `backend/models/model_manifest.json`
Training version: `v20261118T181617Z-f6e8b1`
Generated: `2026-11-18T18:18:17+00:00`
Corpus: `emscad_v1` (University of the Aegean EMSCAD, CC0-origin Kaggle mirror; 17,880 raw rows, 2,180 duplicates removed, 14,993 negative / 707 positive, 3,140 evaluation rows).

| Family | Approved | Active | Implementation | Precision | Recall | ROC-AUC | PR-AUC | F1 | Threshold |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `job_tfidf_logreg` | Yes | Yes | scikit-learn TF-IDF + LogisticRegression | 0.3750 | 0.9574 | 0.9891 | 0.8772 | 0.5389 | 0.2793 |
| `job_tfidf_linearsvc` | Yes | Yes | scikit-learn TF-IDF + LinearSVC (sigmoid-mapped decision score) | 0.4595 | 0.9645 | 0.9914 | 0.9026 | 0.6224 | 0.3670 |

Both approved models are text-only, trained on English-language EMSCAD text, and carry the manifest limitation that they do not independently verify an employer, domain or sender. The LinearSVC score is a ranking score, **not** a calibrated probability. `confidence` is a margin/evidence-strength indicator and is explicitly not used as the risk score.

### Rejected / non-active artifacts

| Family | Approved | Active | Corpus | ROC-AUC | Recall | Why it matters |
| --- | --- | --- | --- | ---: | ---: | --- |
| `message_tfidf_logreg` | No | No | 8 hand-authored synthetic messages | 0.8667 | 0.6000 | Small synthetic corpus; manifest explicitly forbids presenting these metrics as production KPIs. |
| `anomaly_iforest` | No | No | EMSCAD text; contextual fields absent | 0.7251 | 0.1773 | Poor detection; contextual features were neutral zeroes in training. |
| `anomaly_supervised` | No | No | EMSCAD text; XGBoost | 0.8468 | 0.3404 | Insufficient recall/precision; same contextual-feature limitation. |

The runtime loads only `approved: true` artifacts. When none is available or load fails, it returns a named `*_rule_fallback` prediction with explicit limitations; risk scoring discounts rule fallbacks to 0.45 trust. Job text uses approved models; message and anomaly scoring currently use honest rule fallbacks.

---

## 4. Service readiness

| Service / capability | Current state | Evidence |
| --- | --- | --- |
| MongoDB | **Not provisioned for production.** A local listener answered `ping` at `localhost:27017` during verification, but the root `.env` only holds Razorpay test billing variables; there are no production DB credentials, backup, alerting or retention enforcement. App startup fails in production if MongoDB is unavailable. | `app/main.py` lifespan; `app/core/config.py`; local `pymongo` ping. |
| Redis / Celery broker | **Unavailable locally** — connection to `localhost:6379` timed out. Celery uses eager in-process execution when no broker is available; Compose defines `redis:7.4-alpine`. | `app/workers/celery_app.py`; local Redis ping; `docker-compose.yml`. |
| In-memory fallback | **Development only.** API health reports `degraded` and `in_memory_fallback: true`; production re-raises connection failures. | `app/main.py`, `system.py` health endpoints. |
| External API credentials | **Only Razorpay test keys are configured locally.** A root `.env` exists with `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` and `PAYMENT_CURRENCY=INR`; all other credential fields default to empty and `system/config` reports `false`. Never commit `.env`. | `.env.example`, `app/core/config.py`, `app/api/routes/system.py`. |
| RDAP / DNS / TLS | **Enabled by default**, no credentials required. | `RDAP_ENABLED`, `DNS_ENABLED`, `TLS_ENABLED` defaults. |
| VirusTotal / Safe Browsing / Web Risk / MCA registry | **Unconfigured** and reported as `not_configured`. Safe Browsing v4 is non-commercial; use Web Risk for commercial deployment. MCA requires a licensed intermediary and separate consent. | Config defaults; `domain_analysis/analyser.py`; `company_verification/verifier.py`. |
| SMTP / SMS | **Unconfigured**; in-app notifications still work. | `notification_service.py`; config defaults. |
| Razorpay / Stripe | Razorpay **test mode configured locally** (`mode=test`, real test order created); webhook secret generated but not registered in dashboard, so no signed activation drill yet. Stripe remains unconfigured and returns `503`. Only verified webhooks activate plans. | `billing/payments.py`, `routes/billing.py`, `docs/RAZORPAY_SETUP.md`. |
| Approved job sources | **None configured** (`JOB_SOURCE_URLS` empty); monitoring will not fetch arbitrary sites. | Config; `system/config` flag. |
| Demo/admin accounts | Seeded in development with documented weak defaults; auto-disabled in production when those weak defaults remain. Must be explicitly removed/rotated before launch. | `app/main.py::_seed_accounts`, `config.py` validator. |
| Git / release provenance | **Workspace is not a git repository; no commits made.** | `.git` absent at workspace root. |

---

## 5. Known limitations

1. **Not launch-ready:** no production environment, secrets, TLS termination, host allow-list, or signed release history.
2. **Model scope:** only two English text-only job models are approved; precision is modest (0.375 / 0.459) despite high ROC-AUC, so false positives are plausible. Message/anomaly outputs are rule fallbacks.
3. **No calibrated probabilities:** sigmoid-mapped scores and model `confidence` must not be presented as fraud likelihood.
4. **Coverage-dependent results:** low evidence coverage yields `inconclusive`; missing sources are not “clean” results.
5. **Rate limiting is in-process and hard-coded:** `enforce_rate_limit` uses a module-level `SlidingWindowRateLimiter(limit=120)` rather than `settings.rate_limit_per_minute`, and is applied to analysis endpoints only. It will not be consistent across multiple workers.
6. **Retention settings are declarative only:** `RETENTION_DAYS=365` and `AUDIT_RETENTION_DAYS=730` exist in config, but no purge/retention job was found.
7. **Data-subject tooling gaps:** no self-service export or deletion endpoints; corrections are stored for review without a promised response time.
8. **Billing not proven live:** no provider credentials, webhook endpoint deployment, refund/chargeback runbook or reconciliation process.
9. **Notifications limited:** no email/SMS delivery until SMTP/SMS configured; monitoring depends on allow-listed job sources.
10. **Local verification gaps:** container image builds blocked locally; no load test, penetration test, DR drill or production smoke test.
11. **Legacy code:** `legacy-threat-intel/` is preserved historical SOC code and is not active; it is not referenced by the application or Compose setup.
12. **Legal drafts unreviewed:** see `docs/LEGAL_DRAFTS.md`; counsel review is mandatory.

---

## 6. Next steps (priority order)

1. **Security and production configuration:** set `ENVIRONMENT=production`, a high-entropy `SECRET_KEY`, explicit `SEED_DEMO_DATA=false`, production `ALLOWED_HOSTS`/`CORS_ORIGINS`, TLS termination, and remove demo data. Review the hard-coded rate limiter for multi-worker deployment.
2. **Provision real infrastructure:** managed MongoDB with authentication/backups, Redis broker with monitoring, Celery worker/beat observability, alerting on `/health` and queue depth, and a tested restore procedure.
3. **Complete integrations under licence:** choose Web Risk over Safe Browsing for commercial use; license an MCA intermediary; configure VirusTotal, SMTP/SMS and payment credentials; register and verify webhook endpoints; document quotas and costs.
4. **Legal and privacy review:** qualified counsel to finalise Terms, Privacy, DPA, Acceptable Use, cookie/consent and takedown/correction workflows; build a data inventory and enforce retention; define jurisdiction and data-controller placeholders.
5. **Model governance:** monitor precision/false positives in production, add non-English evaluation if those markets are targeted, keep rejected models out of the active path, and re-run the training smoke test on every model change.
6. **Commercial validation:** confirm the seeded plan prices and limits with real customers, instrument conversion/churn/cost-per-scan, and explicitly implement or remove any plan feature strings not yet backed by code (for example enterprise “API access”).
7. **Release engineering:** initialise git, commit a clean baseline, protect branches, run `container-release.yml`, verify both images, and record a versioned rollback procedure.
8. **Operational readiness:** security review/pen test, load test, incident runbook, support/correction reviewer workflow, and a documented go/no-go sign-off.
