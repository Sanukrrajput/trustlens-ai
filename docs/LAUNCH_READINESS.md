# HireShield AI — Launch Readiness

**Evidence date:** 19 November 2026
**Current decision:** **NO-GO for production launch.** **Conditional GO for local demo, internal evaluation and non-production pilots**, provided outputs are treated as advisory and the demo credentials are never exposed outside a controlled environment.

This assessment is based only on files in this repository and checks executed in this working tree. No live production deployment, external API credentials, payment provider, legal approval or security audit is evidenced. A [Render Blueprint](../render.yaml) and [deployment guide](RENDER_DEPLOYMENT.md) were prepared on 19 November 2026, but they are manifests only; no cloud resources were created. A local Git root commit (`d0724e9`) exists; there is no remote or push.

---

## 1. Go / no-go summary

| Question | Answer | Evidence |
| --- | --- | --- |
| Does the product work locally? | **Yes** | Backend 64 tests pass; frontend 23 tests pass; frontend build passes; Compose configuration validates. |
| Is the codebase deployable as containers? | **Partially** | Dockerfiles, nginx config, Compose and a Render Blueprint exist; CI builds images. Local image builds were blocked because the Docker daemon was not running, and the Blueprint has not been applied to Render. |
| Are production secrets configured? | **No** | A local `.env` holds Razorpay **test** keys and a generated webhook secret, but `SECRET_KEY` is still the development placeholder and no production secret store/host/TLS config exists. The Render Blueprint generates a strong `SECRET_KEY` and prompts for other secrets when applied; production startup correctly rejects the weak default. |
| Are external intelligence providers configured? | **No** | All credentialed provider flags are `false`; RDAP/DNS/TLS are on by default without keys. |
| Is live billing configured? | **No** | Razorpay **test** keys are configured locally: `/system/config` reports `razorpay=true`, `mode=test`, `webhook=true`, and a real test order was created. The generated webhook secret is not yet registered in the Razorpay dashboard, no test purchase → webhook → subscription drill has run, and no live keys exist. See [RAZORPAY_SETUP.md](RAZORPAY_SETUP.md). |
| Are legal documents approved? | **No** | `docs/LEGAL_DRAFTS.md` is explicitly a non-lawyer draft requiring counsel review. |
| Are security and operational controls production-grade? | **No** | In-process rate limit, development defaults, no TLS/host allow-list configuration, no retention job, no backup/DR or incident process evidenced. |
| Is there a release history? | **Partial** | Local root commit `d0724e9` exists on `main`; no Git remote, push, tags or protected branch. |

---

## 2. Evidence-based checklist

Legend: **PASS** = verified in this workspace; **PARTIAL** = implemented but incomplete or unconfigured; **FAIL** = missing/blocked for production; **NOT VERIFIED** = no local evidence.

| Area | Requirement | Status | Evidence / gap | Required action |
| --- | --- | --- | --- | --- |
| Core API | Product endpoints under `/api/v1` | **PASS** | Auth, analysis, company, monitoring, reports, notifications, billing, admin and system routers registered in `app/main.py`. | None for functionality. |
| Explainability | Score with evidence, coverage, limitations | **PASS** | Six-component risk engine, category bands, `inconclusive` flag, sources attempted/succeeded in results. | Validate interpretation with users. |
| Backend tests | Automated suite passes | **PASS** | `64 passed` via `pytest backend/tests -q --tb=line`. | Keep in CI on every change. |
| Frontend tests / build | Tests and production build pass | **PASS** | `23 passed` in 6 files; `npm run build` passes. | Keep in CI on every change. |
| Compose config | Valid Compose definition | **PASS** | `docker compose config --quiet` passes. | Re-run after any Compose edit. |
| Container images | Both images build | **NOT VERIFIED** | Docker daemon unavailable locally; CI workflow has build steps. | Run both `docker build` commands on a machine with Docker, then deploy those exact tags. |
| Production secret | Strong `SECRET_KEY` | **FAIL** | The local `.env` only sets Razorpay test billing variables; `SECRET_KEY` is still the dev placeholder, which production validation rejects by design. | Set a unique high-entropy key before starting in production. |
| Demo accounts | No predictable accounts in production | **PARTIAL** | Auto-disable triggers with weak defaults, but `SEED_DEMO_DATA=true` is the default and must be explicitly managed. | Set `SEED_DEMO_DATA=false`, rotate/remove demo data before launch. |
| Hosts / CORS / TLS | Restricted hosts, production origins, TLS | **FAIL** | `ALLOWED_HOSTS=*` default; CORS limited to localhost dev origins; HSTS added only when production; no TLS termination configured in repo. | Set production hosts/origins and terminate TLS at the ingress/reverse proxy. |
| Rate limiting | Distributed, configurable abuse control | **PARTIAL** | In-process `SlidingWindowRateLimiter(limit=120)` on analysis endpoints; `RATE_LIMIT_PER_MINUTE` setting exists but is not used by the dependency. | Implement shared (Redis-backed) rate limiting and apply to auth/billing where appropriate. |
| Data retention | Enforced retention and deletion | **FAIL** | `RETENTION_DAYS`/`AUDIT_RETENTION_DAYS` exist in config; no purge job found; no self-service export/delete endpoints. | Implement enforcement and a documented data-subject process before processing real user data. |
| Legal | Reviewed Terms/Privacy/DPA/AUP/cookies/disclaimers | **FAIL** | Drafts only; jurisdiction and controller placeholders unresolved. | Qualified counsel review and sign-off; publish approved versions. |
| Billing | Live provider + verified webhooks | **FAIL** | Razorpay test keys are configured and a real test order was created; browser checkout, order notes, amount checks and signed webhook logic are implemented and covered by local tests. A locally signed event was verified against the real secret and recorded as `ignored`. The webhook secret is not registered in the dashboard, no signed **activation** drill has run, and no live keys exist. | Register the webhook URL/secret and events in Razorpay; run the test-mode purchase → webhook → subscription → refund drill via [RAZORPAY_SETUP.md](RAZORPAY_SETUP.md); then obtain live keys. |
| External intelligence | Commercial reputation and registry sources | **FAIL** | RDAP/DNS/TLS on; VirusTotal/Safe Browsing/Web Risk/MCA unconfigured. Safe Browsing v4 is non-commercial; MCA has no official public API. | License Web Risk and a licensed registry intermediary; configure keys and consent; record quotas/terms. |
| Notifications | Email and SMS delivery | **PARTIAL** | In-app works; SMTP/SMS skipped when unconfigured. | Configure providers if contractual alerts are promised; otherwise disclose in-app-only. |
| ML governance | Approved artifacts only; audited rejections | **PASS** | Manifest gates loading; rejected models not active; rule fallbacks are labelled. | Add production precision/drift monitoring and non-English evaluation if needed. |
| Observability | Health and audit signals | **PARTIAL** | `/health`, `/api/v1/health`, `/system/config`, audit log, task status endpoints exist. No alerting, metrics dashboard or queue-depth monitoring evidenced. | Add monitoring/alerting and dashboards before launch. |
| Backups / DR | Tested restore | **FAIL** | Deployment doc describes options; no executed restore drill evidenced. | Provision managed backups and perform a documented restore test. |
| Security assurance | Pen test / threat model / dependency scanning | **NOT VERIFIED** | No report or scan output in repository; CI has no dependency audit step. | Complete security review and add dependency scanning to CI. |
| Release process | Git history and versioned releases | **FAIL** | No `.git`; no commits; container-release workflow exists but has not run here. | Initialise git, commit baseline, protect branches, publish tagged images. |
| Legacy separation | Old SOC app not active | **PASS** | `legacy-threat-intel/` preserved; no active code/Compose references. | Keep archived; do not deploy or describe as active product. |

---

## 3. Configured vs unconfigured services

Runtime flags are derived from `app/api/routes/system.py::_integration_flags` and configuration defaults. With the current local `.env` (Razorpay test keys only, no production secrets), the observed values are:

| Service flag | Current value | Meaning |
| --- | --- | --- |
| `rdap` | **true** | RDAP enabled by default, no credential required. |
| `dns` | **true** | DNS lookups enabled by default, no credential required. |
| `tls` | **true** | TLS certificate inspection enabled by default, no credential required. |
| `virustotal` | **false** | `VIRUSTOTAL_API_KEY` empty; no reputation lookup performed. |
| `google_safe_browsing` | **false** | Key empty; Safe Browsing v4 is non-commercial and should not be used for commercial launch. |
| `google_web_risk` | **false** | Key empty; Web Risk v1 is the commercial alternative. |
| `mca_registry` | **false** | `MCA_API_URL`/`MCA_API_KEY` empty; MCA has no official public API, so a licensed intermediary is required. |
| `smtp` | **false** | `SMTP_HOST` empty; email delivery skipped. |
| `sms` | **false** | `SMS_PROVIDER_URL` empty; SMS delivery skipped. |
| `razorpay` | **true** | Local `.env` contains `rzp_test_...` keys; verified via `/system/config` (`mode=test`) and a real test order. Not live. |
| `stripe` | **false** | Secret key empty; checkout returns `503`. |
| `approved_job_sources` | **false** | `JOB_SOURCE_URLS` empty; monitoring will not fetch arbitrary job sites. |
| `cloudflare_turnstile` | **false** | Site/secret keys empty; login reports `not_configured` and does not run a challenge. Configure keys before launch. |

Related feature flags from `/system/config` after the local test-key configuration: `external_lookups_require_consent: true`, `corporate_registry_requires_separate_consent: true`, `webhook_only_payment_activation: true`, `billing_enabled: true`, `razorpay_webhook_secret_configured: true` (dashboard registration still pending), `remembered_sign_ins: true`, `demo_mode: true` (development environment).

**Datastore note:** the local `.env` contains only billing variables and no production datastore is provisioned. Redis was unreachable at `localhost:6379` during verification; a local MongoDB listener answered a ping at `localhost:27017`, but there is no evidence of authentication, backup, retention enforcement or production sizing. Treat both as incidental local state, not launch infrastructure. The in-memory fallback is development-only; production startup fails if MongoDB is unavailable.

---

## 4. Model limitations to disclose

| Item | Evidence | Launch implication |
| --- | --- | --- |
| Approved models | `job_tfidf_logreg` and `job_tfidf_linearsvc`, version `v20261118T181617Z-f6e8b1`, from EMSCAD. | Only job text has approved trained models. |
| Metrics | ROC-AUC 0.9891 / 0.9914; recall 0.9574 / 0.9645; precision 0.375 / 0.4595; PR-AUC 0.8772 / 0.9026. | High ranking performance does not imply low false-positive risk. Avoid accuracy-only marketing claims. |
| Language / modality | English-language EMSCAD text; no independent employer/domain/sender verification. | Non-English and obfuscated content is unvalidated. |
| Rejected models | `message_tfidf_logreg` (synthetic, 8 rows), `anomaly_iforest`, `anomaly_supervised` all `approved: false`, `active: false`. | Message and anomaly scoring use labelled rule fallbacks; do not quote their metrics as production KPIs. |
| Probability semantics | LinearSVC decision margin is sigmoid-mapped; `confidence` is margin/evidence strength and is not used as the risk score. | UI, docs and support must not describe these as calibrated fraud probabilities. |
| Drift monitoring | No production monitoring or retraining trigger evidenced. | Add precision/recall and feature-drift tracking before scaling. |

---

## 5. Security blockers

1. **Development secret and environment defaults.** `SECRET_KEY` is a placeholder and `ENVIRONMENT=development` by default. Production validation exists but no production values are configured.
2. **Predictable seeded accounts.** Demo/admin credentials are documented for local use; auto-disable is a safeguard, not a substitute for explicit removal.
3. **Open host policy.** `ALLOWED_HOSTS=*` means TrustedHost middleware is not installed; CORS origins are localhost-only development values.
4. **TLS not owned by the app.** HSTS is added only in production; TLS termination, certificate management and proxy trust must be configured at deployment. `--proxy-headers` is used by the API container, so proxy configuration must be correct.
5. **In-process rate limiting.** Hard-coded 120/minute per client+path in one process; not effective across multiple API workers. The configured `RATE_LIMIT_PER_MINUTE` value is unused by the dependency.
6. **No security assurance evidence.** No dependency audit, penetration test, threat model or secret-scanning output is present.
7. **Unbounded retention.** Retention periods are declared but not enforced; audit and assessment data would accumulate.
8. **No data-subject tooling.** No self-service export/deletion; manual processes are undocumented and legal drafts flag this gap.

---

## 6. Operational blockers

1. No production MongoDB/Redis, authentication, backup or restore drill.
2. No TLS/ingress configuration, production host names or CORS policy.
3. Container images not built locally; no image scanning or pinned release tags deployed.
4. No external reputation/registry licenses; many assessments would remain inconclusive.
5. No email/SMS providers; alerting claims must be limited to in-app.
6. No payment provider, webhook endpoint registration, reconciliation or refund process.
7. No alerting on health, queue depth, failed webhooks or model load failures.
8. No reviewer workflow with SLA for correction reports.
9. No incident response, on-call ownership or DR runbook.
10. No git repository, commits, tags or rollback record.

---

## 7. Exact steps to reach production readiness

1. **Establish source control.** Initialise git at the workspace root, add a `.gitignore`-respecting baseline, commit, create a protected `main` branch and tag a release candidate. Confirm the legacy directory is intentionally archived and not shipped.
2. **Create production environment file.** Copy `.env.example` to `.env` on the server only. Set `ENVIRONMENT=production`; generate `SECRET_KEY` with `openssl rand -hex 48`; set `SEED_DEMO_DATA=false`, production `ALLOWED_HOSTS` and `CORS_ORIGINS`, strong MongoDB credentials, and explicit model/data paths. Never commit `.env`.
3. **Provision infrastructure.** Deploy MongoDB with authentication, TLS and automated backups; deploy Redis with persistence; size API/worker/beat processes; run `docker compose config --quiet` and build both images from the tagged commit on a Docker-capable host.
4. **Terminate TLS and lock the boundary.** Put the API/frontend behind a trusted TLS reverse proxy or ingress, forward correct `X-Forwarded-*` headers, enforce HTTPS/HSTS, and remove wildcard host allowance.
5. **Complete the code-level production fixes.** Replace the in-process limiter with Redis-backed limits keyed by user/IP; implement retention purge jobs for analyses/audits; add export/deletion or a documented, staffed manual process; implement or remove the enterprise “API access” promise.
6. **Configure integrations lawfully.** Choose Web Risk for commercial URL reputation; license a corporate-registry intermediary with consent; configure VirusTotal only within its terms; add SMTP/SMS if promised; record provider quotas, costs and subprocessors.
7. **Configure billing end to end.** Razorpay **test** keys and a webhook secret are already in the local `.env`; register that secret and the `/api/v1/billing/webhooks/razorpay` URL/events in the Razorpay test dashboard, then complete test-mode checkout → verified webhook → subscription → cancellation → refund/reconciliation drills. For production, replace with live keys/secret. Confirm no frontend callback grants access.
8. **Obtain legal approval.** Have counsel finalise all documents in `docs/LEGAL_DRAFTS.md`, fill jurisdiction/entity/contact placeholders, approve DPA/subprocessor terms, retention schedule, acceptable use, disclaimers and correction/takedown workflow. Verify deployed behaviour matches the approved text.
9. **Prove observability and recovery.** Add metrics/alerts for `/health`, database status, broker connectivity, queue depth, failed webhooks, model-load errors and external provider errors. Perform a documented MongoDB restore drill and an application rollback drill.
10. **Security and quality sign-off.** Run dependency scanning, a security review/penetration test, load testing and the full CI suite (`compileall`, 64 backend tests, training smoke test, frontend build, 23 frontend tests across 6 files, both container builds). Document findings and remediation.
11. **Production smoke test.** Verify `GET /health`, `GET /api/v1/system/config` flags, login with non-demo accounts, one analysis of each type, PDF download, correction submission, admin RBAC denial for non-admin users, and a signed test webhook. Confirm `/docs` and `/openapi.json` are disabled in production.
12. **Record the go/no-go decision.** Capture evidence, named approvers, residual risks and version/tag in a signed launch record. Only then consider changing this document’s decision.

---

## 8. Re-verification commands

```powershell
# Repository root
.\.venv\Scripts\python.exe -m compileall -q backend/app backend/scripts
.\.venv\Scripts\python.exe -m pytest backend/tests -q --tb=line
docker compose config --quiet

# Container builds (requires a running Docker daemon)
docker build --file backend/Dockerfile --tag hireshield-api:rc backend
docker build --file frontend/Dockerfile --tag hireshield-frontend:rc frontend

# Frontend
cd frontend
npm ci
npm run build
npm run test -- --run
```

Expected local results at this snapshot: compile and tests pass (64 backend), build passes, 23 frontend tests across 6 files, Compose config passes; container builds remain unverified locally. Re-run all checks after every change that affects launch criteria.
