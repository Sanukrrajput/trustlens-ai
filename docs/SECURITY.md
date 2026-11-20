# TrustLens AI — Security Documentation

This document describes the security posture that is actually implemented in this repository. It is based on code and configuration inspection, not on a live deployment assessment. A local root `.env` exists with Razorpay **test** keys, a generated webhook secret and `PAYMENT_CURRENCY=INR`; it must never be committed. `.env.example`, `frontend/.env.example` and the unused `legacy-threat-intel/.env.backup` are templates/archives. No external intelligence or SMTP/SMS credentials are configured, and no live payment keys exist.

## Scope and trust boundaries

| Boundary | Traffic | Notes |
| --- | --- | --- |
| Browser → API | JSON/multipart over HTTP(S) | CORS and bearer tokens are configured. TLS must be terminated by a reverse proxy; the bundled nginx service listens on plain HTTP. |
| API → MongoDB/Redis | Persistence, broker, result backend | Compose uses internal services without authentication. Production must isolate and authenticate them. |
| API → external web sources | Safe URL fetch, RDAP, DNS, TLS probes, optional threat feeds | URL fetching is consent-gated and SSRF-resistant, but egress controls are still required. |
| Payment provider → API webhook | Razorpay/Stripe signed events | Raw body HMAC verification is implemented; this is the only path that activates paid access. |
| Admin user → API | Plan, user, report and task management | RBAC with `require_admin` on admin-facing routes. |

## Threat model

| Adversary / scenario | Primary concern | Implemented mitigation | Remaining gap |
| --- | --- | --- | --- |
| Unauthenticated internet user | Access to analyses, admin data or expensive endpoints | Bearer-token authentication on analysis/admin/report routes; rate-limited login/register/forgot-password and analysis endpoints | In-process limiter is not shared across workers; no WAF |
| Malicious registered user | Enumerate other users' analyses or escalate role | User-scoped repository queries, active-user check, role hierarchy, `require_admin` | No per-object authorization test suite beyond admin RBAC tests |
| Stolen access token | Impersonation until expiry | Short `access` token lifetime (`30` minutes by default), `jti`, logout blacklist | Logout blacklists only the access-token `jti`; refresh tokens remain valid until expiry |
| Malicious file upload | Code execution, path traversal, resource exhaustion | MIME allowlist, magic-byte checks, filename sanitisation, size cap, no execution of file content | No antivirus/malware scanning |
| Malicious URL / SSRF | Access to localhost, metadata services or internal networks | `SafeURLFetcher` scheme/host/port/DNS checks, IP pinning, manual redirects, text-only MIME allowlist, byte cap | Egress firewall still required; unconfigured providers remain unavailable |
| Forged payment event / replay | Unauthorised paid access | HMAC verification on raw body, Stripe timestamp tolerance, event-ID idempotency, webhook-only activation | Razorpay verification has no timestamp window; protect the webhook endpoint and rotate secrets |
| Over-privileged or compromised admin | Data exposure, destructive configuration changes | Role hierarchy and audit entries for role/user/plan/report changes | No separate approval workflow or immutable audit store |
| Provider compromise or malicious content | False intelligence, harmful payloads | Provenance fields, confidence values, limitations, consent gates, text-only fetch | External data is not independently trustworthy; registry provider quality varies |
| Secret leakage in logs/API | Credential disclosure | Environment-only secrets, admin config masking, capability flags on `/system/config`, generic error responses | No secret-scanning tool is configured in this repository |

## Implemented controls

| Control | Implementation | File references |
| --- | --- | --- |
| Environment-driven secrets | `Settings` reads only environment variables / `.env`; external keys default to empty and mean “not configured”. | `backend/app/core/config.py`, `.env.example` |
| Secret masking | `Settings.public_dict()` replaces known secret values with `***configured***`; `/api/v1/system/config` exposes capability flags only. | `backend/app/core/config.py`, `backend/app/api/routes/admin.py`, `backend/app/api/routes/system.py` |
| Production secret validation | `ENVIRONMENT=production` with the development `SECRET_KEY` raises `SECRET_KEY must be set to a strong random value in production`. | `backend/app/core/config.py` |
| Demo-account fail-closed | Production seeding is disabled automatically when default weak demo/admin passwords or the development secret are present. | `backend/app/core/config.py`, `backend/app/main.py` |
| Password hashing | Argon2 with `time_cost=3`, `memory_cost=65536`, `parallelism=2`. | `backend/app/core/security.py` |
| Tokens | HS256 JWTs with `sub`, `type`, `iat`, `exp` and `jti`; distinct `access`, `refresh`, `verify_email` and `password_reset` types; `decode_token()` enforces expected type. | `backend/app/core/security.py`, `backend/app/api/routes/auth.py` |
| Token revocation | Logout inserts the access-token `jti` into a blacklist checked by `get_current_user()`. | `backend/app/api/routes/auth.py`, `backend/app/api/deps.py` |
| Authorization | Role hierarchy `user`/`student` < `staff` < `admin` < `owner`; `require_admin` on admin, report-review and system-task routes. | `backend/app/core/security.py`, `backend/app/api/deps.py`, `backend/app/api/routes/admin.py`, `backend/app/api/routes/reports.py`, `backend/app/api/routes/system.py` |
| Configurable rate limiting | In-process sliding-window limiter applied to register, login, forgot-password, analysis and support-chat routes. `RATE_LIMIT_PER_MINUTE` and `RATE_LIMIT_WINDOW_SECONDS` control the policy; rejected requests receive `429` with `Retry-After` and a structured `ctx_request_id` log. It is still per-process, not shared between replicas. | `backend/app/core/security.py`, `backend/app/api/deps.py`, `backend/app/api/routes/auth.py`, `backend/app/api/routes/analysis.py`, `backend/app/api/routes/support.py`, `.env.example` |
| Login verification | Cloudflare Turnstile `siteverify` is called server-side when both keys are configured; missing/invalid/unavailable tokens deny login. Without keys the endpoint reports `not_configured`; no challenge is simulated. The site key is public; the secret is masked in admin config. | `backend/app/services/turnstile_service.py`, `backend/app/core/config.py`, `backend/app/api/routes/auth.py`, `frontend/src/components/Turnstile.tsx` |
| Remembered sign-ins | Successful sign-ins are persisted with device label, masked IP and Cloudflare country header; only a keyed hash of a random browser id is stored. Unrecognised devices raise a notification and optional email. Activity is owner-only. | `backend/app/services/login_security.py`, `backend/app/db/repositories.py`, `backend/app/api/routes/auth.py`, `frontend/src/pages/SettingsPage.tsx` |
| Upload validation | Non-empty, max `MAX_UPLOAD_MB` (default 10), declared MIME allowlist, magic-byte checks, WebP `RIFF`/`WEBP` verification, filename sanitisation. | `backend/app/core/security.py`, `backend/app/api/routes/analysis.py` |
| Safe document handling | PDF text extraction, OCR and plain-text decoding only; no execution of uploaded content; extraction limitations are surfaced. | `backend/app/services/analysis_service.py` |
| Preview redaction | Analysis previews redact e-mail addresses, Indian-style phone numbers and URLs; identifiers are stored as SHA-256 hashes. | `backend/app/services/analysis_service.py`, `backend/app/core/security.py` |
| SSRF resistance | HTTP(S) only, no userinfo, hostname/allowlist/port checks, blocks local/internal/metadata and ambiguous numeric hosts, validates every DNS answer, pins the connection IP with original Host/SNI, manual redirects with limit, TLS 1.2 minimum, text-only MIME allowlist and `262,144`-byte fetch cap. | `backend/app/intelligence/url_scanning/safe_fetch.py` |
| Consent gates | External URL/domain/company lookups require `consent_external_lookups`; corporate registry lookup requires separate consent in the company endpoint. | `backend/app/services/analysis_service.py`, `backend/app/api/routes/company.py`, `backend/app/schemas.py`, `backend/app/intelligence/company_verification/verifier.py` |
| Webhook verification | Provider allowlist, HMAC over raw body (`x-razorpay-signature` / `stripe-signature`), Stripe timestamp tolerance of 300 seconds, event-ID idempotency, audit entry. | `backend/app/api/routes/billing.py`, `backend/app/billing/payments.py` |
| Payment activation integrity | Frontend success/cancel redirects and Razorpay checkout handler never grant access; only verified webhooks mutate subscriptions. Activation uses an event allowlist plus amount/currency checks; unconfigured checkout returns `503`, provider/network failures return generic `502`. | `backend/app/api/routes/billing.py`, `backend/app/billing/payments.py`, `frontend/src/lib/razorpay.ts`, `backend/app/main.py` |
| Redirect safety | Checkout redirect URLs must be absolute HTTP(S) and match the host of a configured CORS origin. | `backend/app/api/routes/billing.py` |
| Host/CORS controls | `TrustedHostMiddleware` when allowed hosts do not contain `*`; `CORSMiddleware` with explicit origins, credentials and method/header lists. | `backend/app/main.py` |
| Security headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, restrictive `Content-Security-Policy`; HSTS in production. | `backend/app/main.py` |
| Production documentation | `/docs` and `/openapi.json` are disabled when environment is production. | `backend/app/main.py` |
| Datastore fail-closed | MongoDB failure falls back to `mongomock` only outside production; production re-raises and startup fails. | `backend/app/main.py` |
| Error hygiene | Validation errors return structured `422`; database errors return generic `503`; unhandled errors return generic `500` and are logged server-side. | `backend/app/main.py` |
| Audit trail | Selected security-relevant events are logged: registration, login/logout, email/password reset, admin changes, billing/checkout/webhook, monitoring, company verification, moderation and retention enforcement. | `backend/app/api/routes/auth.py`, `backend/app/api/routes/admin.py`, `backend/app/api/routes/billing.py`, `backend/app/api/routes/company.py`, `backend/app/api/routes/monitoring.py`, `backend/app/services/retention_service.py` |
| Request correlation | `X-Request-ID` is generated (or accepted only as a 8–64 character alphanumeric token), echoed on every response, exposed to CORS, and copied into structured `ctx_*` fields on request logs and error logs. Security headers are applied in a `finally` block so errors do not bypass them. | `backend/app/main.py`, `backend/app/core/logging_conf.py` |
| Retention enforcement | `RETENTION_DAYS` and `AUDIT_RETENTION_DAYS` drive real deletions, with shorter caps for notifications (180 days), support chats (30), domain cache (30) and task status (7). A nightly Celery task and an admin-only trigger run the same service; each run writes an audit event. | `backend/app/services/retention_service.py`, `backend/app/workers/tasks.py`, `backend/app/workers/celery_app.py`, `backend/app/api/routes/system.py`, `docs/RETENTION.md` |
| Backup/restore drill | JSONL logical backups include per-collection SHA-256 manifests; `verify` checks hashes and counts; `restore` refuses without `--confirm`. Backups are gitignored and contain personal data, so operator-side encryption and permissions are required. | `scripts/backup_tool.py`, `.gitignore`, `docs/DEPLOYMENT.md` |
| Secret hygiene | `scripts/secret_scan.py` runs in CI as a blocking check over tracked files, rejecting tracked `.env`/backup files and common credential patterns. | `scripts/secret_scan.py`, `.github/workflows/ci.yml` |
| Dependency auditing | CI installs `pip-audit` and runs `npm audit --omit=dev --audit-level=high`, uploading JSON reports as artifacts. `pip check` and `npm ls --omit=dev` are also enforced. Dependabot opens weekly pip/npm and monthly Actions updates. | `.github/workflows/ci.yml`, `.github/dependabot.yml` |

## Secret management

- Copy `.env.example` to `.env`, edit locally and never commit it. `.gitignore` excludes `.env` and `.env.*` except `.env.example`.
- Generate the production signing key with `openssl rand -hex 48`. Set `ENVIRONMENT=production` in the same change.
- Keep external keys empty unless that provider is intentionally enabled. Empty values are reported honestly as `not_configured` / unavailable instead of simulated.
- `GET /api/v1/system/config` returns booleans such as `integrations.razorpay` and `features.billing_enabled`, never key material.
- `GET /api/v1/admin/config` uses `Settings.public_dict()`, which masks `secret_key`, provider API keys, SMTP/SMS keys and payment secrets.
- Rotate secrets deliberately:
  - `SECRET_KEY`: rotating invalidates all existing signed tokens, including refresh tokens.
  - `RAZORPAY_WEBHOOK_SECRET` / `STRIPE_WEBHOOK_SECRET`: coordinate rotation with the provider dashboard and expect a short overlap window.
  - External API keys: rotate at the provider; the application reads configuration at startup.
- The legacy `legacy-threat-intel/.env.backup` is not read by the application or Compose. Treat it as historical material, remove it from deployment images, and rotate anything in it that was ever real.
- Provider webhook events are stored in the `payments` collection including `raw_event`; apply database access controls and retention to that collection.

## Webhook verification procedure

1. Only `POST /api/v1/billing/webhooks/razorpay` and `/stripe` are accepted; other providers return `404`.
2. The route reads the **raw request body** before parsing. Re-serialising JSON would invalidate the signature.
3. For Razorpay, the backend computes HMAC-SHA256 of the raw body with `RAZORPAY_WEBHOOK_SECRET` and compares it with `x-razorpay-signature` using `hmac.compare_digest`.
4. For Stripe, the backend parses `stripe-signature`, verifies a `v1` HMAC over `timestamp.raw_body` with `STRIPE_WEBHOOK_SECRET`, and rejects timestamps more than 300 seconds from server time.
5. Invalid signatures or missing secrets return HTTP `400 invalid webhook`; no state is changed.
6. Verified events must contain an event ID. Previously processed IDs return `already_processed`.
7. Only verified events call `handle_verified_event()`, which upserts subscription state and records the payment event.
8. Checkout success/cancel URLs and the browser billing page have no activation authority. A user cannot self-grant paid access by navigating to a success URL.

## Consent and privacy notes

- Registration requires explicit `consent_privacy` and `consent_terms`; the schema validator rejects false values.
- `consent_external_lookups` defaults to `false` on job, message, URL, document and company requests. Without it, URL/domain/company intelligence is marked `not_attempted` and a limitation is added.
- `/api/v1/company/verify` accepts a separate `consent_corporate_registry_lookup`; `CompanyVerifier._registry()` returns `not_attempted` when registry consent is absent and `not_configured` when no licensed provider is configured.
- In the general analysis flow, `AnalysisService` currently passes `consent_registry` from `payload.get("consent_registry")`, which is not a field in the checked-in analysis schemas. The separate `/company/verify` route is therefore the reliable path for explicit registry consent today.
- Analysis records store a redacted `input_preview` and an `input_sha256`, not the full submitted text in the result document. Extracted entities, rule indicators, model outputs and external body previews are persisted.
- `contact_fingerprint()` produces a SHA-256 pseudonymous fingerprint for company/contact correlation; it is not reversible but is still personal data when derived from identifiable input.
- `RETENTION_DAYS` and `AUDIT_RETENTION_DAYS` are now enforced (`365` and `730` by default) by the scheduled/admin-triggered purge described in [RETENTION.md](RETENTION.md). Documents lacking the policy timestamp field are not deleted, and MongoDB TTL indexes remain a separate asynchronous safety net. Self-service export/deletion is still absent.
- Google Safe Browsing v4 is documented in source as non-commercial. Commercial deployments should use Google Web Risk and confirm licensing.
- MCA has no official public API in this integration; registry verification requires a licensed/bulk provider configured through `MCA_API_URL` and `MCA_API_KEY`.

## Deployment hardening checklist

- [ ] Set `ENVIRONMENT=production` and a unique high-entropy `SECRET_KEY`.
- [ ] Set `ALLOWED_HOSTS` to exact external hostname(s); avoid `*`.
- [ ] Set `CORS_ORIGINS` to exact frontend origins; remove localhost defaults.
- [ ] Terminate TLS at a trusted reverse proxy; the bundled nginx listens on port `80` only.
- [ ] Preserve `Host`, `X-Forwarded-Proto`, `X-Forwarded-Host` and `X-Forwarded-For`; Uvicorn runs with `--proxy-headers`.
- [ ] Enable authentication and network isolation for MongoDB and Redis. The Compose file does not.
- [ ] Do not publish MongoDB or Redis ports to the host; restrict access to the Compose network.
- [ ] Disable or remove demo/admin accounts. Production auto-disable only covers known weak defaults; strong explicit demo passwords would still seed.
- [ ] Configure only the external providers you intend to use; leave the rest empty.
- [ ] Confirm commercial licensing before enabling Google Safe Browsing; use Web Risk or another licensed source for commercial use.
- [ ] Use a licensed corporate registry provider for MCA data and keep separate registry consent enabled.
- [ ] Configure Razorpay/Stripe secrets and webhook URLs in the provider dashboard; test invalid and replayed webhook rejection.
- [ ] Add a shared, distributed rate limiter at the proxy or gateway; the built-in configurable limiter is per-process.
- [ ] Add outbound egress allowlisting/firewalling for the API and worker containers.
- [ ] Add antivirus/CDR scanning for uploads if user documents are accepted in production.
- [ ] Feed `X-Request-ID` and the `ctx_*` JSON log fields into centralized logging/alerting for auth failures, `429`s, `5xx`s, webhook rejections and database failures.
- [ ] Set `RETENTION_ENABLED=true`, review [RETENTION.md](RETENTION.md) against the legally approved schedule, and confirm the nightly beat task is running.
- [ ] Back up MongoDB with `scripts/backup_tool.py` (or the documented volume snapshots) before upgrades, verify the manifest, and perform a restore drill into a scratch database.
- [ ] Verify `/docs` and `/openapi.json` return `404` in production.
- [ ] Restrict admin routes at the proxy as defence in depth, even though `require_admin` is implemented.
- [ ] Review model manifest approvals before deploying a retrained image; model files are baked into the backend image.

## Incident response notes

These are operator notes, not an automated playbook.

1. **Contain**
   - Disable the affected account with the admin user-active control.
   - Block the source IP at the proxy if abuse is observed.
   - If webhooks are abused, pause the provider webhook endpoint or rotate its signing secret with the provider.
   - Stop the stack if datastore compromise is suspected and preserve volumes for forensic imaging.

2. **Rotate**
   - Rotate `SECRET_KEY` to invalidate all signed sessions. This is broader than per-token logout blacklisting.
   - Rotate affected provider API keys, SMTP/SMS credentials and payment webhook secrets.
   - Remove stale values from `.env`, deployment secret stores and the unused legacy backup file.

3. **Investigate**
   - Query the `audit_logs` collection for `user.login`, `user.logout`, `admin.*`, `billing.*`, `company.verify` and monitoring events.
   - Review `fraud_analyses` and analysis records for manipulated submissions or unexpected scoring outcomes.
   - Query the `payments` collection for suspicious `provider_event_id`, `raw_event` and subscription changes.
   - Review `GET /health`, API logs and proxy logs for database fallback, error spikes and unusual request paths.
   - For upload or URL abuse, review analysis records, `sources_attempted`/`sources_succeeded` and outbound proxy/firewall logs.

4. **Recover**
   - Restore from a known-good MongoDB backup only for corruption or confirmed tampering; otherwise keep existing data.
   - Reissue paid subscription state through verified provider events or a reviewed admin correction.
   - Redeploy with clean secrets and verify `/health`, RBAC and webhook rejection with negative tests.

5. **Review**
   - Record root cause, affected data, detection gap and follow-up actions.
   - Apply organizational breach-notification and privacy policies; this repository does not implement notification automation.

## Stage 8 verification evidence (20 November 2026)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `.\.venv\Scripts\python.exe -m pytest backend/tests -q --tb=line` | **111 passed** (deprecation-warning noise only) |
| Frontend tests | `npm run test -- --run` in `frontend/` | **29 passed** across 7 files |
| Frontend build | `npm run build` | **Passed** (`tsc --noEmit && vite build`) |
| Extension contract | `npm test` in `browser-extension/` | **6 passed** |
| Lint / compile / config | `ruff check backend/app backend/tests backend/scripts scripts`, `compileall`, `docker compose config --quiet` | **Passed** |
| Secret hygiene | `python scripts/secret_scan.py` | `status: ok`, 269 tracked files scanned, no findings, no tracked `.env` or backups |
| Dependency consistency | `python -m pip check`, `npm ls --omit=dev` | **Passed** (no broken requirements; valid production tree) |
| Python dependency audit | `python -m pip_audit --requirement backend/requirements.txt --format json` | **3 findings in 2 packages** (below); CI job is report-only and uploads JSON |
| JavaScript dependency audit | `npm audit --omit=dev --audit-level=high --json` in `frontend/` | Exit **0**: 0 high/critical, 2 moderate React Router advisories, 49 production dependencies |

Open Python advisories: `python-jose==3.5.0` (`PYSEC-2026-4298` / `CVE-2026-85394`) and its transitive `ecdsa==0.19.2` (`PYSEC-2026-1325` / `CVE-2024-23342`, reported twice). `pip-audit` reports no fixed versions. Mitigations already in place: `decode_token()` pins `algorithms=[settings.jwt_algorithm]` (HS256 with a symmetric secret by default), so the unauthenticated-algorithm and DER-public-key confusion path is not reachable through this application; the ecdsa Minerva issue affects signing/key generation/ECDH, while this service neither signs ECDSA tokens nor exposes an ECDSA verification path. The moderate npm advisories affect `react-router`/`react-router-dom` 6.x (open redirect via backslash and SSR hydration constructor injection); the app is a client-only SPA without SSR hydration, and remediation requires a semver-major upgrade to 7.x. These are documented as open risks, not simulated or suppressed.

## Current limitations

- The local `.env` contains only Razorpay test billing variables; `.env.example` leaves all integrations empty, so every other provider is unavailable by default. The generated webhook secret is not yet registered in the Razorpay dashboard.
- Redis was unreachable locally; a local MongoDB listener answered `ping`, but there is no evidence of authentication, backup or production provisioning. Local development can use the `mongomock` fallback and eager/in-memory Celery; production fails closed instead.
- No TLS-terminating proxy, WAF, antivirus scanner, distributed rate limiter or SIEM is included.
- Compose does not enable MongoDB or Redis authentication, TLS or a separate reverse proxy.
- The in-process rate limiter is now configurable but remains per-process; multiple API replicas do not share counters. A reverse-proxy/gateway limiter is still required for production.
- Logout blacklists only the access-token `jti`; refresh tokens are not blacklisted or versioned.
- Admin role assignment is powerful and not gated by a second approver.
- The audit trail covers selected events only, is stored in MongoDB, and is not tamper-evident or exported.
- Upload validation checks size and declared content shape but does not detect malware or polyglot files beyond magic bytes.
- Safe URL fetching reduces SSRF risk but does not replace network egress controls. It fetches only text-like MIME types and truncates bodies at `262,144` bytes by default.
- Razorpay webhook verification has no timestamp window; Stripe does. Event-ID idempotency reduces replay impact but does not replace provider-side controls.
- The general analysis flow does not consume a `consent_registry` field from its schemas; use `/api/v1/company/verify` for separate registry consent.
- External intelligence is only as reliable as its source. Unconfigured providers report `not_configured`, and registry absence does not prove a company does not exist.
- Billing has Razorpay **test** credentials in the local (uncommitted) `.env`; Stripe remains unconfigured and returns `503 not configured`. A generated webhook secret exists but is not yet registered in the Razorpay dashboard, so no live signed activation has been exercised. Never treat test keys as production credentials.
- SMTP/SMS settings are empty, so high-risk notifications are not delivered in the default configuration.
- Retention is enforced for documents that carry the policy timestamp field; documents lacking that field are intentionally left alone, so collection-specific review is still needed.
- `pip-audit` reports advisories in `python-jose`/`ecdsa` with no published fix versions; npm reports two moderate React Router advisories. See the verification evidence above for mitigations and upgrade path.
- There is no evidence of a penetration test, formal security certification, or completed privacy/legal review in this repository.
- HSTS is emitted as a response header in production, but the shipped nginx service serves plain HTTP; TLS remains an operator responsibility.
- The restrictive `Content-Security-Policy` is emitted by the API middleware; any richer browser UI served from the API origin must be reviewed against it.
