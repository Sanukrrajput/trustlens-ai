# TrustLens AI — Derived Execution Plan

This document converts the TrustLens AI master specification into an executable, staged plan for **this repository**. It is derived from the specification body (sections 3–14) because the supplied prompt ended at "STAGE 1: Architecture".

> **Concept correction:** the engineering decision to rebrand and extend the HireShield baseline in place does not define the product. [TRUSTLENS_CONCEPT.md](../TRUSTLENS_CONCEPT.md) is the authoritative definition. User-facing copy must be offer-first; recruitment is one supported category, not the product's identity.

## Decisions taken with the project owner

| Decision | Choice | Consequence |
| --- | --- | --- |
| Repository relationship | **Rebrand and extend in place** | The working, tested HireShield AI application is the baseline. No second disconnected codebase is created. |
| Persistence | **Keep MongoDB** | The specification's SQLAlchemy/SQLite/PostgreSQL requirement is a documented deviation. Repositories, indexes, validators and 73 passing backend tests are preserved. |
| Planning | **Derive stages from the specification body** | Stages below are derived from product platforms, architecture layers, engines, API, security, ML, community and DevOps sections. |

## Baseline evidence (verified in this working tree)

| Check | Result |
| --- | --- |
| `python -m pytest backend/tests -q --tb=line` | **111 passed** after Stage 8 (73 at baseline; 101 after Stage 5) |
| `npm run test -- --run` (frontend) | **29 passed**, 7 files (27 at baseline) |
| `npm test` (browser extension) | **6 passed** after Stage 7 |
| `npm run build` (frontend) | **Passed** (`tsc --noEmit && vite build`) |
| Git working tree | Clean after the Stage 1–8 commit and the dependency-remediation follow-up; no push or deployment has been made |

The existing product already provides: FastAPI + `/api/v1`, Argon2id auth with JWT rotation/revocation, RBAC with ownership checks, a five-category explainable risk engine, SSRF-resistant URL fetching, RDAP/DNS/TLS lookups with consent gates, manifest-gated local ML models with honest rule fallbacks, Mongo repositories with validators and indexes, PDF/JSON reports, correction feedback, monitoring with in-app notifications, admin APIs, structured audit logging, Docker Compose, CI workflows and a free-tier Render evaluation deployment.

## Target product shape

TrustLens AI is an **online offer verification and fraud-intelligence platform**. A user submits a URL, a message/offer text, or a screenshot; the platform returns an evidence-backed assessment that states what was observed, what was checked, what could not be checked, which signals drove the score, and what the user should do next. It never claims that absence of a scam record proves legitimacy, and it never presents a score as a calibrated probability of fraud.

Scope broadening: recruitment fraud remains a supported special case, but the primary domain becomes **generic offers** — advertisements, discounts, giveaways, scholarships, investments, promotions, recruitment and impersonation attempts across social platforms, messaging apps, websites and email.

---

## Stage 1 — Architecture (done)

**Deliverables**

1. Evidence-based target architecture document mapping every specification layer to the current implementation.
2. Explicit deviation register (MongoDB retained; billing exists but is out of specification scope; legacy SOC code out of scope).
3. This staged plan with acceptance criteria.

**Acceptance:** `docs/TRUSTLENS_ARCHITECTURE.md` and this plan published; no working functionality removed; baseline tests still green.

## Stage 2 — Rebrand and trust surface (done)

**Scope:** replace user-facing product identity with TrustLens AI across API defaults, SPA assets/copy, reports, configuration templates, documentation and deployment descriptors. Preserve infrastructure identifiers whose change would break data or deployments (database name, live Render hostnames, git remote, seeded account emails) until a separate migration is planned.

**Acceptance met:** user-facing identity is TrustLens AI; protected infrastructure identifiers (MongoDB DB name, Compose project/volumes, Celery namespace, Render hosts/services, seeded account emails, model manifest provenance, CI artifact names, live FAQ URLs) were explicitly preserved by `scripts/rebrand_trustlens.py`. Existing tests updated and passing; production build passes; `docker compose config --quiet` passes. Historical references in `README.md`, deployment docs and the two TrustLens planning documents intentionally retain old infrastructure names.

## Stage 3 — Generic offer verification in the web application (done)

**Scope:** introduce offer-type-aware analysis (advertisement / giveaway / scholarship / investment / recruitment / promotion / other) while keeping `/analysis/job` as a backwards-compatible alias. Generalise labels, validation copy, entity extraction prompts where safe, and report explanations. Keep job-specific ML models but describe them accurately as recruitment-text models rather than general offer models.

**Acceptance met:** `POST /api/v1/analysis/offer` accepts an offer category and returns a structured report; `/analysis/job` remains unchanged for existing clients; the frontend workspace has a working "Offer" tab; offer scoring uses a named `offer_rule_fallback` because no general-offer model is approved; category-aware indicators and campaign-authorisation uncertainty are asserted by tests. No fabricated detection results.

## Stage 4 — Intelligence engines (done)

**Scope met:** three independent engines were added and wired into `AnalysisService` without becoming hard dependencies:

- **Image/OCR** (`backend/app/intelligence/image/ocr.py`): validates image bytes, caps dimensions, delegates to optional local `pytesseract` only when a real `tesseract` binary exists, extracts phone/email/URL/payment/credential observations, and reports `not_configured` with explicit "image does not prove authenticity" limitations when OCR is unavailable. Document uploads now carry `image_intelligence`; an invalid image is `invalid_image`, never a clean result.
- **Brand/campaign** (`backend/app/intelligence/brand_verification/`): reports `verified_company`, `verified_official_campaign`, `unverified_advertisement`, `suspected_impersonation` or `not_attempted`. Registry confirmation never implies campaign authorisation; only independently sourced campaign evidence can produce `verified_official_campaign`. User-supplied screenshots and adverts are explicitly excluded.
- **Threat indicators** (`backend/app/intelligence/threat_indicators/`): MongoDB `threat_indicators` and `threat_sources` collections, value normalisation, source-aware deduplication, observed/expiry timestamps, TTL index, admin source registry, direct JSON import, and optional SSRF-safe public JSON feed refresh. No feed is configured by default; unavailable feeds report `not_configured`/`not_attempted`, and absence of a match never establishes legitimacy.

**Acceptance met:** each engine has isolated unit tests; their results appear in `AnalysisResult` (`image_intelligence`, `brand_intelligence`, `threat_intelligence`) and PDF reports; all indicators pass through canonical deduplication; backend **97 passed**, frontend **29 passed**, `npm run build` and `docker compose config --quiet` pass.

## Stage 5 — Risk engine and report alignment (done)

**Scope met:** the risk engine now scores five signal categories — `content` 30%, `url` 25%, `brand` 25%, `threat` 10% and `community` 10% — with renormalisation over available categories retained. Indicators carry a `signal_category`; overlapping sub-signals inside one category use the strongest observation rather than double-counting. Empty/no-match threat, brand and history checks remain in `unavailable_signals` and never become clean zero-risk evidence. `RISK_WEIGHT_*` and `RISK_BAND_*_MAX` are configurable and documented; legacy six-weight variables are removed from the contract.

**Acceptance met:** deterministic tests cover the default split, custom weights/renormalisation, configurable bands, empty-threat honesty and structured fields. Every completed `AnalysisResult` now carries `evidence_sources` (status, attempted and observed timestamps, engine detail), `evidence_collected_at`, `missing_evidence`, `technical_limitations`, `risk.recommended_actions`, `risk.confidence`, `risk.uncertainty`, `risk.signal_weights` and `risk.unavailable_signals`; PDF and SPA reports render them. Model outputs are labelled "uncalibrated risk score" in the UI/PDF rather than as fraud probabilities. Backend **101 passed**, frontend **29 passed**, `npm run build` and `docker compose config --quiet` pass.

## Stage 6 — Community and moderation (done)

**Scope met:** corrections and community allegations are now distinct categories. `POST /api/v1/reports/feedback` stores `category="correction"`; `POST /api/v1/reports/community` stores `category="community"` with claim types `missed_fraud`, `impersonation`, `unauthorized_campaign` and `other`. Every report carries a pseudonymous `entity_key`, a normalised `claim_key`, a reporter/entity/claim `dedupe_key` and a `duplicate_group_key`; resubmissions return the original report with `duplicate=true`, while different reporters remain distinct so they can corroborate the same claim. Reporter reputation is a transparent, bounded snapshot (neutral 0.5 baseline, clamped to 0.05–0.95) derived from moderation outcomes and stored with each report. Moderators move reports through `pending`, `verified`, `corroborated`, `false_report` and `dismissed` states; false reports require a reason, legacy `reviewed` maps to `pending` and is never treated as verification, and every decision writes both a generic audit event and the state-specific action.

**Honesty gate:** only moderator-verified community reports from at least two distinct reporters create a `community_independently_corroborated` indicator. A single report produces no community indicator, cannot change the entity's risk classification and never becomes clean evidence. The indicator is `suspicious`, `independently_verified=false` and explicitly labelled as decision support that is not proof of fraud. False and dismissed reports are excluded; insufficient or absent community coverage stays in `missing_evidence` rather than being counted as a clean result.

**Acceptance met:** backend tests assert the correction/community distinction, duplicate detection, analysis ownership, single-report non-reclassification, two-reporter corroboration, false-report handling, reputation decay, audit metadata and RBAC. Backend **105 passed**, frontend **29 passed**, `npm run build` and `docker compose config --quiet` pass.

## Stage 7 — Extension and mobile plan (done)

**Scope met:** `browser-extension/` adds a Chrome Manifest V3 popup that analyses **only the active page** after the user clicks **Analyse this page**. Install-time permissions are exactly `activeTab`, `scripting` and `storage`; there is no service worker, content script, history/webNavigation/alarms/cookies access or telemetry. The host permission for the configured API origin is requested at click time and can be denied before any page text is sent. The popup reads at most 20,000 characters of visible text, disables external lookups, generates a fresh idempotency key, renders all untrusted text with `textContent`, and labels the score as uncalibrated with a count of missing checks. Page text is never written to extension storage. `mobile-app/README.md` and `mobile-app/PERMISSION_POLICY.md` define a future React Native single-item Share Intent/screenshot/message flow and explicitly forbid notification-listener, accessibility, background-capture and cross-app access.

**Acceptance met:** six extension contract tests pass. They assert the exact permission set, absence of background/automatic hooks, explicit-click wiring, serialisable self-contained extraction, bounded untrusted text and honest failure when a page is unavailable. Mobile is deliberately a plan, not a shipped application.

## Stage 8 — Security, DevOps and validation (done)

**Scope met:** dependency and secret checks were added to CI; `scripts/secret_scan.py` scans tracked files and fails on tracked `.env`/backup files or credential patterns. Rate limits are driven by `RATE_LIMIT_PER_MINUTE` and `RATE_LIMIT_WINDOW_SECONDS` with a `Retry-After` header; `X-Request-ID` is accepted only when it is a short opaque token, otherwise generated, echoed, exposed to CORS and attached to structured `ctx_*` logs. `RETENTION_DAYS`/`AUDIT_RETENTION_DAYS` are now enforced by `backend/app/services/retention_service.py`, a Celery beat task and an admin-only `POST /system/tasks/retention` trigger; MongoDB TTL indexes remain an asynchronous safety net. `scripts/backup_tool.py` provides JSONL logical backup, checksum verification and restore that refuses without `--confirm`. `.gitignore` excludes `backups/`; Dependabot configs cover pip, npm and GitHub Actions.

**Acceptance met:** backend **111 passed**, frontend **29 passed** across 7 files, extension **6 passed**, frontend production build passed, `docker compose config --quiet` passed, `python -m compileall` passed, `ruff check` passed, `python scripts/secret_scan.py` reported `status: ok` over 299 tracked files with no tracked env/backup files, `pip check` and `npm ls --omit=dev` reported consistent dependency trees. A follow-up remediation replaced vulnerable `python-jose`/`ecdsa` with `PyJWT` and upgraded React Router, Vite and Vitest; both `pip-audit` and the full `npm audit` now report **0 vulnerabilities** and are blocking CI checks. No secrets, databases, uploads or private datasets are committed; no push or deployment has been made.

---

## Standing engineering rules

1. No fake integrations, fabricated statistics, hardcoded detection outcomes or inert buttons.
2. Every external provider reports `not_configured` or `not_attempted` when unavailable — never simulated.
3. All submitted content is untrusted input; structured validation and schema checks are mandatory.
4. Missing evidence is never treated as a clean result.
5. Every change is verified with the backend suite, frontend suite and production build before being reported as done.
