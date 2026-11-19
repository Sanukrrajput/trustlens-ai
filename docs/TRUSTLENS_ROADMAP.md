# TrustLens AI — Derived Execution Plan

This document converts the TrustLens AI master specification into an executable, staged plan for **this repository**. It is derived from the specification body (sections 3–14) because the supplied prompt ended at "STAGE 1: Architecture".

## Decisions taken with the project owner

| Decision | Choice | Consequence |
| --- | --- | --- |
| Repository relationship | **Rebrand and extend in place** | The working, tested HireShield AI application is the baseline. No second disconnected codebase is created. |
| Persistence | **Keep MongoDB** | The specification's SQLAlchemy/SQLite/PostgreSQL requirement is a documented deviation. Repositories, indexes, validators and 73 passing backend tests are preserved. |
| Planning | **Derive stages from the specification body** | Stages below are derived from product platforms, architecture layers, engines, API, security, ML, community and DevOps sections. |

## Baseline evidence (verified in this working tree)

| Check | Result |
| --- | --- |
| `python -m pytest backend/tests -q --tb=line` | **73 passed** |
| `npm run test -- --run` (frontend) | **27 passed**, 7 files |
| `npm run build` (frontend) | **Passed** (`tsc --noEmit && vite build`) |
| Git working tree | Clean at start of work |

The existing product already provides: FastAPI + `/api/v1`, Argon2id auth with JWT rotation/revocation, RBAC with ownership checks, a six-component explainable risk engine, SSRF-resistant URL fetching, RDAP/DNS/TLS lookups with consent gates, manifest-gated local ML models with honest rule fallbacks, Mongo repositories with validators and indexes, PDF/JSON reports, correction feedback, monitoring with in-app notifications, admin APIs, structured audit logging, Docker Compose, CI workflows and a free-tier Render evaluation deployment.

## Target product shape

TrustLens AI is an **online offer verification and fraud-intelligence platform**. A user submits a URL, a message/offer text, or a screenshot; the platform returns an evidence-backed assessment that states what was observed, what was checked, what could not be checked, which signals drove the score, and what the user should do next. It never claims that absence of a scam record proves legitimacy, and it never presents a score as a calibrated probability of fraud.

Scope broadening: recruitment fraud remains a supported special case, but the primary domain becomes **generic offers** — advertisements, discounts, giveaways, scholarships, investments, promotions, recruitment and impersonation attempts across social platforms, messaging apps, websites and email.

---

## Stage 1 — Architecture (in progress)

**Deliverables**

1. Evidence-based target architecture document mapping every specification layer to the current implementation.
2. Explicit deviation register (MongoDB retained; billing exists but is out of specification scope; legacy SOC code out of scope).
3. This staged plan with acceptance criteria.

**Acceptance:** architecture document reviewed; no working functionality removed; baseline tests still green.

## Stage 2 — Rebrand and trust surface

**Scope:** replace user-facing product identity with TrustLens AI across API defaults, SPA assets/copy, reports, configuration templates, documentation and deployment descriptors. Preserve infrastructure identifiers whose change would break data or deployments (database name, live Render hostnames, git remote, seeded account emails) until a separate migration is planned.

**Acceptance:** no user-facing "HireShield" branding remains; existing tests updated and passing; production build passes; deployment descriptors remain valid (`docker compose config --quiet`).

## Stage 3 — Generic offer verification in the web application

**Scope:** introduce offer-type-aware analysis (advertisement / giveaway / scholarship / investment / recruitment / promotion / other) while keeping `/analysis/job` as a backwards-compatible alias. Generalise labels, validation copy, entity extraction prompts where safe, and report explanations. Keep job-specific ML models but describe them accurately as recruitment-text models rather than general offer models.

**Acceptance:** new offer endpoints or aliases work end to end; old clients continue to function; regression tests for both paths; no fabricated detection results.

## Stage 4 — Intelligence engines

**Scope:** add the independent engines the specification requires and that are absent today:

- Image/OCR engine using an open-source OCR path with safe image handling, text/phone/URL/email/payment extraction, and explicit "image does not prove authenticity" framing.
- Brand and official-campaign verification engine with separate states for verified entity, verified official campaign, unverified advertisement and suspected impersonation.
- Threat-intelligence indicator store with normalisation, deduplication, source registry, timestamps, expiry and optional public-feed imports.

**Acceptance:** each engine is independently testable, reports `not_configured`/`not_attempted` honestly, and cannot become a hard dependency of the web application.

## Stage 5 — Risk engine and report alignment

**Scope:** align signal categories and weights with the specification's initial 30/25/25/10/10 split, with availability-based renormalisation retained. Extend the structured report to carry evidence sources, timestamps, confidence/uncertainty, missing information and recommended actions. Keep calibrated-probability language out of the product.

**Acceptance:** deterministic risk-engine tests; score bands and weights configurable and documented; every report contains the required structured fields.

## Stage 6 — Community and moderation

**Scope:** differentiate community reports from corrections, add duplicate detection, reputation-aware weighting, moderator verification states and false-report handling. Never classify a business as fraudulent from a single report.

**Acceptance:** one user report cannot by itself change an entity's risk classification; moderation actions are audited; ownership and RBAC tests pass.

## Stage 7 — Extension and mobile plan

**Scope:** after the web application is complete, add a Chrome Manifest V3 extension with user-triggered current-page analysis, minimal permissions and no silent history collection; add a React Native implementation plan covering Android Share Intent, screenshots and messages, with no monitoring of other applications.

**Acceptance:** extension performs only user-triggered analysis; permissions are minimal; mobile plan explicitly forbids unauthorised access.

## Stage 8 — Security, DevOps and validation

**Scope:** dependency scanning, secret hygiene, retention enforcement, configurable rate limiting, structured logging with request IDs, backup/restore drill, separate environment configuration, and full test/build/container verification.

**Acceptance:** full test suite green; security checks documented with real commands and results; no secrets, databases, uploads or private datasets committed.

---

## Standing engineering rules

1. No fake integrations, fabricated statistics, hardcoded detection outcomes or inert buttons.
2. Every external provider reports `not_configured` or `not_attempted` when unavailable — never simulated.
3. All submitted content is untrusted input; structured validation and schema checks are mandatory.
4. Missing evidence is never treated as a clean result.
5. Every change is verified with the backend suite, frontend suite and production build before being reported as done.
