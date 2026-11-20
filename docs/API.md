# TrustLens AI — API Reference

Scope: every route registered by `backend/app/main.py` and the route modules under `backend/app/api/routes/`. All paths below are relative to the API prefix `/api/v1` unless explicitly marked as a root path. Request/response models are defined in `backend/app/schemas.py`.

**Local environment:** the untracked root `.env` contains Razorpay **test** billing variables only; committed templates leave every credential empty. All non-billing credentials therefore default to empty strings, `/system/config` reports those integrations as unavailable/unconfigured, and no simulated intelligence results are returned.

## 1. Conventions

| Item | Behaviour |
| --- | --- |
| Base URL | `/api/v1`; root metadata `GET /` and real process health `GET /health` are outside the prefix. In Compose, nginx also serves a static `GET /health`. |
| Authentication | `Authorization: Bearer <access_token>` for protected routes. Tokens are HS256 JWTs with `type`, `sub`, `jti`, 30-minute access / 14-day refresh expiry (`backend/app/core/security.py`). |
| Roles | `user = student < staff < admin < owner`; `require_admin` accepts admin or owner. Ownership is checked separately on analyses, reports and monitoring tasks. |
| Content type | JSON for all bodies except `POST /analysis/document` (`multipart/form-data`) and provider webhooks (raw body). |
| Error shape | `{"detail": "..."}`; validation errors use `{"detail": [{"loc": [...], "msg": "..."}]}` (HTTP 422). |
| Rate limiting | Selected routes: `RATE_LIMIT_PER_MINUTE` (default 120) requests / client IP / path / `RATE_LIMIT_WINDOW_SECONDS` (default 60), in-process sliding window; `429` includes `Retry-After` (`backend/app/api/deps.py`). |
| Request IDs | Every response carries `X-Request-ID`. A caller-supplied value is accepted only when it is 8–64 alphanumeric characters; otherwise the server generates a 32-character hex id. The same id is written to `ctx_request_id` structured logs. |
| Usage accounting | Middleware records one `api_usage` increment per authenticated `/api/*` request per user per UTC hour, excluding `/api/v1/auth/refresh`. |
| Docs | `/docs` and `/openapi.json` exist only when `ENVIRONMENT != production`; ReDoc is disabled. |
| Security headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `X-Request-ID`, CSP on every response; HSTS in production. |

## 2. Public endpoints (no access token)

| Method | Path | Purpose | Request / response | Notes |
| --- | --- | --- | --- | --- |
| `GET` | `/` | Service metadata | `{service, version, docs, api, status}` | Root, outside `/api/v1` (`main.py:299`). |
| `GET` | `/health` | Real API + MongoDB health | `{status, version, environment, database, in_memory_fallback, started_at}` | Root, outside prefix (`main.py:310`). |
| `GET` | `/health` | Versioned health with Redis status | `{status, version, environment, timestamp, database, broker, configured, in_memory_fallback, ...}` | `/api/v1/health` from `system.py`; use this through nginx. |
| `GET` | `/system/config` | Non-secret capabilities | `{app_name, version, environment, integrations, features, upload, support_note}` | Unconfigured providers are `false`. |
| `POST` | `/support/chat` | Docs-backed support answers | `SupportChatRequest` → `SupportChatReply` | Curated FAQ matcher, not a generative model. Body requires `message` and a random `session_id` (8–64 URL-safe characters). Both question and answer are stored in `support_messages`; unmatched questions get `grounded: false` and suggestions. Rate limited; no external model/provider calls. |
| `GET` | `/support/chat` | Saved conversation | `session_id` query → `list[SupportChatMessage]` | Returns up to 100 stored messages for that session in chronological order. Rate limited. Anyone holding the session ID can read it, so keep it browser-local. |
| `DELETE` | `/support/chat` | Clear saved conversation | `session_id` query → `{status, session_id, deleted}` | Removes every stored message for that session. Rate limited. Messages also expire after 30 days via TTL index. |
| `POST` | `/auth/register` | Create account | `UserRegister` → `UserOut`, **201** | Requires `consent_privacy` and `consent_terms`; email must be new (409); creates free subscription; sends verification email if SMTP configured. Rate limited. |
| `POST` | `/auth/login` | Obtain tokens | `UserLogin` → `TokenPair` | 401 invalid credentials; 403 disabled account. Optional `access_mode` (`user`/`admin`) is checked against the **verified account role** — a normal account cannot sign in as admin and an admin cannot sign in as a normal user (403). Other optional fields: `device_id`, `remember_device`, `turnstile_token`. Returns `previous_signin`, `new_device`, `verification`. With Turnstile configured, a missing/invalid token returns 400. Rate limited. |
| `GET` | `/auth/security-config` | Public login verification capabilities | `LoginSecurityOut` | `{enabled, site_key, provider, status, note}`; `status=not_configured` when keys are absent. |
| `POST` | `/auth/refresh` | Rotate tokens | `RefreshRequest` → `TokenPair` | Body refresh token; 401 on invalid/expired type or unavailable user. Excluded from usage counting. |
| `POST` | `/auth/verify-email` | Confirm email | `VerifyEmailRequest` → `{"status":"verified"}` | 400 invalid token, 404 user missing. |
| `POST` | `/auth/forgot-password` | Request reset link | `ForgotPasswordRequest` → `{"status":"accepted"}` | Always accepted; email only sent when SMTP configured. Rate limited. |
| `POST` | `/auth/reset-password` | Set new password | `ResetPasswordRequest` → `{"status":"updated"}` | 400 invalid token, 404 user missing. |
| `GET` | `/billing/plans` | Active plan catalogue | `list[PlanOut]` | Prices from seeded/admin-edited `plans` collection. |
| `POST` | `/billing/webhooks/{provider}` | Payment provider event | raw JSON → `{status, event_id, subscription_status\|...}` | Public but **signature required**; `provider` is `razorpay` or `stripe`, otherwise 404. See §7. |

## 3. Authenticated endpoints

All routes in this section require a valid access token (`get_current_user`). Ownership is enforced where noted; admin bypass is explicit in code.

### 3.1 Authentication / account

| Method | Path | Purpose | Response | Evidence |
| --- | --- | --- | --- | --- |
| `GET` | `/auth/me` | Current user | `UserOut` | `auth.py:157` |
| `GET` | `/auth/signin-activity` | Recent sign-ins | `list[SigninEventOut]` | Own events only, newest first, `limit` 1–50; includes device label, masked IP, Cloudflare country header when present, device recognition and verification status. |
| `POST` | `/auth/logout` | Revoke current access token | `{"status":"logged_out"}` | Adds JWT `jti` to `token_blacklist`; audit `user.logout`. |
| `POST` | `/auth/resend-verification` | Resend verification email | `{"status":"accepted"}` | Uses first configured CORS origin as link base. |

### 3.2 Analysis

| Method | Path | Purpose | Request | Response |
| --- | --- | --- | --- | --- |
| `POST` | `/analysis/offer` | Analyse a generic online offer with category | `OfferAnalysisRequest` | `AnalysisResult` |
| `POST` | `/analysis/job` | Analyse a recruitment posting (compatible alias) | `JobAnalysisRequest` | `AnalysisResult` |
| `POST` | `/analysis/message` | Analyse a recruiter message | `MessageAnalysisRequest` | `AnalysisResult` |
| `POST` | `/analysis/url` | Analyse a URL | `UrlAnalysisRequest` | `AnalysisResult` |
| `POST` | `/analysis/document` | Analyse PDF/image/text upload | multipart: `file`, `consent_external_lookups`, optional `client_request_id` | `AnalysisResult` |
| `GET` | `/analysis` | List own analyses | query: `page`, `page_size` (1–100), `analysis_type` | `Paginated[AnalysisListItem]` |
| `GET` | `/analysis/{analysis_id}` | Fetch one result or task state | path id | `AnalysisResult \| TaskStatusOut` |

Notes from `backend/app/api/routes/analysis.py`:

- All four submission routes use `enforce_rate_limit` and convert `PermissionError` from `PlanService.can_scan()` into **402** (plan inactive or scan limit reached).
- Document uploads validate size (10 MB), declared MIME, magic bytes and filename before parsing; invalid uploads produce **400**. Image uploads are handled by the optional local OCR engine: it reports `not_configured` when no `tesseract` binary is installed and never treats an image as proof of authenticity.
- Every analysis result now includes `image_intelligence` (only for image uploads), `brand_intelligence` and `threat_intelligence`. Brand states are `verified_company`, `verified_official_campaign`, `unverified_advertisement`, `suspected_impersonation` and `not_attempted`; no campaign is verified without independent evidence.
- `GET /analysis` rejects `page < 1` or `page_size` outside 1–100 with **400**.
- `GET /analysis/{id}` returns 404 for a missing analysis and enforces owner/`admin`/`owner` access when an analysis document exists. If no analysis exists but a `task_status` document does, it returns a `TaskStatusOut` (task polling path).

### 3.3 Company intelligence and monitoring

| Method | Path | Purpose | Request | Response |
| --- | --- | --- | --- | --- |
| `POST` | `/company/verify` | Consent-gated company corroboration | `CompanyVerifyRequest` | raw result dict (`json_safe`) |
| `GET` | `/company/{company_id}` | Stored company + up to 20 prior investigations | path id | dict; 404 if not found |
| `GET` | `/monitoring` | List own monitoring tasks | — | `list[MonitoringTaskOut]` (max 200 by repository) |
| `POST` | `/monitoring` | Create task | `MonitoringTaskCreate` | `MonitoringTaskOut`, **201**; 400 if no company/title/keyword |
| `DELETE` | `/monitoring/{monitor_id}` | Delete own task | path id | `{"status":"deleted"}`; 404 when not owned |

`GET /company/{id}` is authenticated but has no per-user ownership filter (`company.py:38–60`). Company verification writes an audit event `company.verify`.

### 3.4 Reports and feedback

| Method | Path | Purpose | Response / notes |
| --- | --- | --- | --- |
| `POST` | `/reports/feedback` | Submit a correction to one assessment | `UserReportCreate` → `UserReportOut` with `category: correction`, `moderation_state: pending`, `status: pending_review`; requires ownership of the analysis. Corrections never become community evidence. |
| `POST` | `/reports/community` | Submit a community allegation about the entity | `CommunityReportCreate` → `UserReportOut` with `category: community`, `moderation_state: pending`; requires ownership of the analysis. |
| `GET` | `/reports/{analysis_id}` | Report metadata | `{analysis_id, report_id, generated_at, risk, status:"available"}`; ownership/admin bypass. |
| `GET` | `/reports/{analysis_id}/pdf` | Download PDF | `application/pdf` with `Content-Disposition`; generated and cached in `reports` if absent. |
| `GET` | `/reports/export/analyses.csv` | Export analyses | **Admin-only**; `text/csv`, up to 5,000 analyses. Registered before the dynamic `/{analysis_id}` route. |

Ownership failures for reports return **403** `not permitted`; missing analyses return **404**. Both report routes hash the claim text to a `claim_key`, derive a stable pseudonymous `entity_key` from the analysis fingerprint/domain, and enforce a unique `dedupe_key` of reporter + entity + claim. Re-submitting the same claim returns the original document with `duplicate=true` and an updated `duplicate_count`; a different reporter submitting the same claim creates a distinct report in the same `duplicate_group_key`. `UserReportOut` also exposes `category`, `moderation_state`, `entity_key`, `claim_key`, `dedupe_key`, `duplicate_group_key`, `duplicate_of`, `duplicate`, `reporter_reputation` (`score`, `basis`, `computed_at`), `reviewed_by`, `reviewed_at`, `review_notes`, `is_false_report`, `false_report_reason`, `evidence_url` and `updated_at`. Reporter reputation starts neutral at 0.5, is bounded to 0.05–0.95, and is a weighting input only — never proof that a claim is true.

### 3.5 Notifications

| Method | Path | Purpose | Request | Response |
| --- | --- | --- | --- | --- |
| `GET` | `/notifications` | Paginated inbox | `page`, `page_size` (1–100), `unread_only` | `Paginated[NotificationOut]` |
| `PATCH` | `/notifications/{notification_id}/read` | Mark read | path id | `NotificationOut`; 404 if not owned/found |
| `PUT` | `/notifications/preferences` | Merge alert preferences | `PreferencesIn` (`email_alerts`, `in_app_alerts`, `sms_alerts`, extra allowed) | `{"status":"updated","preferences":{...}}` |

### 3.6 Billing (authenticated)

| Method | Path | Purpose | Request | Response |
| --- | --- | --- | --- | --- |
| `GET` | `/billing/subscription` | Current subscription + usage | — | `SubscriptionOut` |
| `POST` | `/billing/checkout` | Create provider checkout | `CheckoutRequest` | `CheckoutOut`; **503** if provider unconfigured; **502** on provider/network failure |
| `POST` | `/billing/subscription/cancel` | Set cancellation flag | `{"cancel_at_period_end": true}` | `SubscriptionOut` — does **not** change billing status |

`success_url`/`cancel_url` must be absolute `http(s)` URLs whose netloc is in `CORS_ORIGINS`; otherwise **400**. A frontend success callback never activates a plan.

## 4. Admin-only endpoints

Every route below depends on `require_admin` (`backend/app/api/deps.py:92`). A non-admin receives **403** `insufficient permissions`.

| Method | Path | Purpose | Response / notes |
| --- | --- | --- | --- |
| `GET` | `/admin/dashboard` | Platform counts, distributions, 24h API usage | `total_users`, `total_analyses`, `high_risk_count`, `inconclusive_count`, `api_requests_24h`, `scans_by_type`, `risk_distribution`, `daily_scans`, `generated_at` |
| `GET` | `/admin/users` | Paginated users minus password hash/consent | `{items,total,page,page_size}` with subscription summary |
| `POST` | `/admin/users` | Create user/staff/admin account | `AdminUserCreate` (`email`, `password` 10–128 chars, `full_name`, optional `organisation`, `role`) → `UserOut`, **201**; 409 duplicate email, 400 `owner`/unknown role, 403 above own role. Free subscription, unverified email, verification email attempt when SMTP configured, and `admin.user_created` audit event. |
| `PATCH` | `/admin/users/{user_id}/role` | Change role | `{"status":"updated",...}`; unknown role 400; cannot grant above own role (403) |
| `PATCH` | `/admin/users/{user_id}/active` | Enable/disable user | 404 missing; 403 if disabling an `owner` |
| `GET` | `/admin/audit-logs` | Paginated audit trail | optional `action` regex filter (case-insensitive) |
| `GET` | `/admin/models` | Model versions and active flags | `{items, active}` |
| `GET` | `/admin/reports` | User reports and community claims (max 200) | `{items,total}` |
| `PATCH` | `/admin/reports/{report_id}` | Apply a moderation decision | `ReportReview`: `moderation_state` (`pending\|verified\|corroborated\|false_report\|dismissed`) or legacy `status` (`reviewed\|dismissed\|actioned`), optional `review_notes` and `false_report_reason`; at least one decision field required. Writes `admin.report_reviewed` plus the state-specific `admin.report_*` audit action with previous/new state metadata. |
| `GET` | `/admin/plans` | All plans sorted by monthly price | `{items}` |
| `PATCH` | `/admin/plans/{code}` | Edit plan fields | `PlanChange`; 404 missing, 400 when no changes |
| `GET` | `/admin/config` | Non-secret settings | `Settings.public_dict()` with secrets masked as `***configured***` |
| `GET` | `/admin/tasks` | 50 most recently updated Celery task statuses | `{items}` |
| `GET` | `/system/tasks/{task_id}` | One task status | `TaskStatusOut`; unknown id → `status: "unknown"` |
| `POST` | `/system/tasks/monitoring` | Trigger `run_monitoring` | `TriggerOut` (`task_id`, `status`, `task_name`) |
| `POST` | `/system/tasks/domain-refresh` | Trigger `refresh_domain_intelligence` | `TriggerOut` |
| `POST` | `/system/tasks/analytics` | Trigger `aggregate_analytics` | `TriggerOut` |
| `POST` | `/system/tasks/health-check` | Trigger `health_check` | `TriggerOut` |
| `POST` | `/system/tasks/retention` | Trigger the configured retention purge immediately | `TriggerOut`; dispatch queues `app.workers.tasks.cleanup_retention`, which honours `RETENTION_ENABLED` and `SCHEDULER_ENABLED` |
| `GET` | `/threat-intelligence/sources` | Source registry with `configured`/`not_configured`/`disabled` states | `{sources: [...]}` |
| `POST` | `/threat-intelligence/sources` | Register an optional public JSON feed; URL structure is SSRF-validated | `ThreatSourceRegister` → public source record; **400** for unsafe URLs |
| `POST` | `/threat-intelligence/sources/{source_id}/refresh` | SSRF-safe fetch and import of a configured feed | `{status, ingested, limitations}`; `not_configured` when no URL exists |
| `POST` | `/threat-intelligence/import` | Import structured indicators directly | `ThreatImport` (max 1000 items) → `{status, ingested, skipped}` |
| `GET` | `/threat-intelligence/indicators` | Inspect deduplicated stored indicators | `{total, items}`; `limit` 1–200 |

Moderation details: invalid state transitions return **409** `invalid moderation transition: <from> -> <to>`; `false_report` without a non-empty `false_report_reason` returns **400**; legacy `status="reviewed"` maps to `moderation_state="pending"` and is deliberately not treated as verification. Allowed transitions are `pending → pending|verified|corroborated|false_report|dismissed`, `verified → verified|corroborated|false_report|dismissed`, `corroborated → corroborated|false_report|dismissed`, `false_report → false_report|pending`, and `dismissed → dismissed|pending|verified`. Only `verified` or `corroborated` **community** reports from at least two distinct reporters produce a `community_independently_corroborated` indicator; a single report cannot change a risk classification. Non-admins (including report owners) receive **403** from the moderation route.

`TriggerOut` status is `queued` on successful dispatch; dispatch failures are returned as status `failed` with an `error` string rather than raising.

## 5. Important request/response shapes

Source: `backend/app/schemas.py` (class names below).

| Model | Fields relevant to clients |
| --- | --- |
| `UserRegister` | `email`, `password` (10–128 chars), `full_name`, optional `organisation`, `consent_privacy=true`, `consent_terms=true` |
| `TokenPair` | `access_token`, `refresh_token`, `token_type="bearer"`, `expires_in` (seconds) |
| `UserOut` | `id`, `email`, `full_name`, `role`, `organisation`, `email_verified`, `created_at`, `preferences` |
| `JobAnalysisRequest` | `text` (20–200k), optional `company_name`, `job_title`, `recruiter_email`, `source_url`, `consent_external_lookups=false`, `client_request_id` |
| `MessageAnalysisRequest` | `text` (5–100k), `channel` (`email\|sms\|whatsapp\|unknown`), optional `sender`, `consent_external_lookups`, `client_request_id` |
| `UrlAnalysisRequest` | `url` (5–2048), `consent_external_lookups`, `client_request_id` |
| `CompanyVerifyRequest` | `company_name`, optional `website_url`, `corporate_id`, two independent consent flags |
| `OfferAnalysisRequest` | `text` (20–200k), `offer_category` (`advertisement\|giveaway\|scholarship\|investment\|recruitment\|promotion\|other`), optional `company_name`, `source_url`, `consent_external_lookups`, `consent_corporate_registry_lookup`, `client_request_id` |
| `AnalysisResult` | `id`, `analysis_type`, `offer_category`, `status`, `user_id`, `created_at`, `completed_at`, redacted `input_preview`, `extracted`, `model_predictions`, `domain_intelligence`, `company_intelligence`, `message_intelligence`, `historical_intelligence`, `image_intelligence`, `brand_intelligence`, `threat_intelligence`, `community_intelligence`, `indicators`, `evidence_sources`, `evidence_collected_at`, `missing_evidence`, `technical_limitations`, `risk`, `sources_attempted`, `sources_succeeded`, `report_id` |
| `RiskAssessment` | `score` (0–100), `category`, `inconclusive`, `summary`, `evidence_summary`, `recommended_actions`, `confidence`, `uncertainty`, `data_coverage`, `weights_version`, `signal_weights`, `unavailable_signals`, `component_scores` |
| `EvidenceSource` | `name`, `status`, `attempted_at`, `observed_at`, optional `detail` — one honest record per checked source |
| `EvidenceIndicator` | `name`, `status` (confirmed_malicious → supportive), `severity`/`confidence` 0–1, `description`, `source`, optional `reference_url`, `observed_at`, `independently_verified`, optional `expires_at`, `weight`, `signal_category` (`content\|url\|brand\|threat\|community\|coverage`) |
| `ModelPrediction` | `model_name`, `model_version`, `prediction`, `fraud_probability` (legacy field name; display as an **uncalibrated model risk score**, never as a fraud probability), `confidence`, `contributing_features`, `limitations` |
| `AnalysisListItem` / `Paginated[T]` | list items plus `total`, `page`, `page_size`, `pages` |
| `TaskStatusOut` | `task_id`, `status`, optional `result`, `error` |
| `MonitoringTaskCreate` / `Out` | `name`, `company_names`, `job_titles`, `source_urls`, `keywords`, `enabled`, `notify_email`, `notify_in_app`; `Out` adds `user_id`, `created_at`, `last_run_at`, `last_status` |
| `NotificationOut` | `id`, `user_id`, `kind`, `title`, `body`, `severity`, `read`, `created_at`, optional `analysis_id` |
| `PlanOut` | `code`, `name`, `description`, `price_monthly_paise`, `price_yearly_paise`, `currency`, `scan_limit`, `features`, `active`, `popular` |
| `CheckoutRequest` | `plan_code`, `interval` (`monthly\|yearly`), `provider` (`razorpay\|stripe`), optional `success_url`, `cancel_url` |
| `CheckoutOut` | `provider`, `checkout_id` (Razorpay order id), optional `key_id` (public Razorpay key), optional `checkout_url` (Stripe), `amount`, `currency`, optional `name`, `description`, `mode` (`test\|live\|unknown`) |
| `SubscriptionOut` | `id`, `user_id`, `plan_code`, `status`, `interval`, `provider`, `current_period_end`, `scans_used`, `scan_limit`, `cancel_at_period_end` |
| `UserReportCreate` | Correction input: `analysis_id`, `report_type` (`false_positive\|missed_fraud\|identity_correction\|other`), `details` (10–5000 chars), optional `evidence_url` |
| `CommunityReportCreate` | Community input: `analysis_id`, `claim_type` (`missed_fraud\|impersonation\|unauthorized_campaign\|other`), `details` (10–5000 chars), optional `evidence_url` |
| `UserReportOut` | `id`, `analysis_id`, `user_id`, `category` (`correction\|community`), `report_type`, `details`, `status`, `moderation_state`, `entity_key`, `claim_key`, `dedupe_key`, `duplicate_group_key`, `duplicate_of`, `duplicate_count`, `duplicate`, `reporter_reputation`, `reviewed_by`, `reviewed_at`, `review_notes`, `is_false_report`, `false_report_reason`, `evidence_url`, `created_at`, `updated_at` |
| `ReporterReputation` | `score` (0–1), `basis` (counts by moderation state), `computed_at` |
| `ReportReview` | Admin moderation input: `status` or `moderation_state` (one required), optional `review_notes`, `false_report_reason` |
| `community_intelligence` | `status` (`no_stable_entity\|insufficient_independent_reports\|corroborated`), `entity_key`, `supporting_reports`, `independent_reporters`, `average_reputation`, `weighted_support`, `moderation_states`, `indicators`, `limitations` |
| `ThreatSourceRegister` | `source_id`, `name`, `kind` (`public_json_feed\|import`), optional `url`, `enabled`, `description` |
| `ThreatIndicatorIn` / `ThreatImport` | `kind` (`domain\|url\|email\|phone\|brand\|ip\|fingerprint\|generic`), `value`, `status`, `severity`, `confidence`, `description`, optional `reference_url`/`source_url`, `independently_verified`, `ttl_days`; import wraps up to 1000 indicators |

The five signal categories and the default specification weights are `content` 30%, `url` 25%, `brand` 25%, `threat` 10% and `community` 10%. Weights and score-band bounds are environment-configurable (`RISK_WEIGHT_*`, `RISK_BAND_*_MAX`) and normalised at runtime; `weights_version` records the exact weights and bands used. Default bands are `0–19 Low observed risk`, `20–39 Limited warning signals`, `40–59 Moderate risk`, `60–79 High risk`, `80–100 Critical risk indicators`. Low evidence coverage forces `inconclusive=true`; an empty or no-match threat/brand/history lookup remains in `unavailable_signals` and is never counted as a clean result. A low score is never a safety guarantee or a calibrated fraud probability.

## 6. Error conventions and rate limits

| Status | Typical causes |
| --- | --- |
| 400 | Invalid pagination, upload validation, invalid email/reset token, disallowed redirect URL, malformed monitoring task, missing plan changes, moderation decision with no state, `false_report` without a reason |
| 401 | Missing/malformed bearer header, invalid/expired token, wrong token type, revoked `jti`, unavailable user |
| 402 | `PlanService.can_scan()` denied: subscription not active or scan limit reached (analysis routes) |
| 403 | Insufficient role, non-owned analysis/report, disabled account at login, role escalation attempt, owner disable attempt |
| 404 | Unknown analysis/company/monitor/notification/report/user, unknown webhook provider, plan not found |
| 409 | Email already registered, invalid moderation state transition |
| 422 | Pydantic validation failure; `detail` is a list of `{loc, msg}` |
| 429 | Rate limit exceeded on rate-limited routes |
| 500 | Generic unhandled error (`internal server error`) or webhook processing failure |
| 502 | Payment provider temporarily unavailable |
| 503 | Database not ready, `PyMongoError`, or `PaymentConfigurationError` (integration not configured) |

Rate-limited routes (`enforce_rate_limit` dependency): `POST /auth/register`, `POST /auth/login`, `POST /auth/forgot-password`, `POST /analysis/{job,message,url,document}`, and `GET/DELETE /support/chat`. The limiter key is `<client host>:<path>`, so the same client has an independent window per route. The policy comes from `RATE_LIMIT_PER_MINUTE` and `RATE_LIMIT_WINDOW_SECONDS`; a `429` response includes `Retry-After` equal to the window. The limiter is in-process: restart resets it and multiple API replicas do not share counters.

## 7. Webhook contract

`POST /api/v1/billing/webhooks/{provider}` is the only path that can change paid entitlement. Evidence: `backend/app/api/routes/billing.py` and `backend/app/billing/payments.py` (`PaymentService.verify_webhook` / `handle_verified_event`).

| Provider | Signature source | Verification |
| --- | --- | --- |
| `razorpay` | `x-razorpay-signature` | HMAC-SHA256 of the **raw body** with `RAZORPAY_WEBHOOK_SECRET`, compared with `hmac.compare_digest` |
| `stripe` | `stripe-signature` | Parse `t=`/`v1=` parts, HMAC-SHA256 of `t + "." + raw body` with `STRIPE_WEBHOOK_SECRET`, accept any matching `v1`, reject timestamps more than 300 seconds old |

Flow and semantics:

1. Missing secret or signature → **400** `invalid webhook`. Unknown provider → **404**.
2. Event id is taken from `id` or `event_id`; missing id → 400. If `payments.provider_event_id` already exists, response is `{"status":"already_processed","event_id":...}` and no second state change occurs.
3. Event type comes from `event` or `type`. Activation allowlist: `payment.captured`, `order.paid`, `subscription.charged`, `checkout.session.completed`, `invoice.payment_succeeded`. Negative events `payment.failed`, `subscription.cancelled`, `customer.subscription.deleted`, `charge.refunded`, `refund.created` map to `cancelled`/`refunded`. All other verified events are recorded as `ignored` and never change entitlement.
4. `user_id` comes from Razorpay `notes` (order, payment, subscription or refund entity — order notes are checked first) or Stripe `metadata`/`client_reference_id`; `plan_code` and `interval` default to `professional`/`monthly` when absent.
5. For activation events, the event amount and currency are compared with the configured plan for the selected interval. Mismatches are recorded as `amount_mismatch`/`currency_mismatch` and do not change subscription state.
6. On an allowed event with a user id, the subscription is upserted with `status`, `provider`, `plan_code`, `scan_limit`, `current_period_end` (now + 30 or + 365 days), `scans_used = 0` and `cancel_at_period_end`; the full verified event is appended to `payments`.
7. Successful response: `{"status":"processed","event_id":...,"subscription_status":...}` for state-changing events, or `ignored`/`amount_mismatch`/`currency_mismatch` for non-activating events. An audit event `billing.webhook_processed` is recorded.

Checkout is separate: `POST /billing/checkout` creates a provider order/session. Razorpay requires `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` and returns an order `checkout_id`, public `key_id`, display `name`/`description`, `mode`, amount and currency. The frontend loads the official Razorpay Checkout script and opens it with the server-created order id; its handler is display-only. Stripe requires `STRIPE_SECRET_KEY` and returns `checkout_url`. Both fail with 503 when unconfigured. The frontend `?checkout=success` / `?checkout=cancelled` redirect is display-only. See [RAZORPAY_SETUP.md](RAZORPAY_SETUP.md).

## 8. Minimal examples

```bash
# Public capability check
curl -s http://localhost:8000/api/v1/system/config

# Login, then submit a message with no external consent
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@hireshield.io","password":"DemoPass123!"}' | jq -r .access_token)

curl -s -X POST http://localhost:8000/api/v1/analysis/message \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"text":"Pay a registration fee and share your OTP to get this job.","channel":"whatsapp","consent_external_lookups":false}'
```

The demo credentials above are development seed values from `backend/app/core/config.py`; production seeding is disabled when weak defaults are present. Do not treat them as configured production accounts.

## 9. Verification

Endpoint inventory and shapes were checked against the route decorators and Pydantic models in the files cited above. Final verification: backend **111 passed** (`python -m pytest backend/tests -q --tb=line`), frontend **29 passed** across 7 files (`npm run test -- --run`), browser extension **6 passed** (`npm test`), `npm run build` and `docker compose config --quiet` succeeded, Ruff/compileall/secret scan passed. Both `npm audit --json` and `pip-audit --format json` reported 0 vulnerabilities and are blocking CI checks; see [SECURITY.md](SECURITY.md). No live provider keys, OCR binary or signed webhook activation drill were used; the free evaluation deployment reports billing, Turnstile and credentialed intelligence providers as disabled or unconfigured through `/api/v1/system/config`.
