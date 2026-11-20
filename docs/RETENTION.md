# TrustLens AI — Retention policy and enforcement

**Status:** implemented in Stage 8. This document describes the behaviour that actually runs, not just the configured numbers.

## 1. Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `RETENTION_ENABLED` | `true` | Master switch. When `false`, the service returns `status: "disabled"` and deletes nothing. |
| `RETENTION_DAYS` | `365` | Default maximum age for analysis, report, monitoring, notification, sign-in, health, usage and support data. |
| `AUDIT_RETENTION_DAYS` | `730` | Maximum age for `audit_logs`. |
| `RATE_LIMIT_*` | — | Unrelated to retention; see [API.md](API.md). |

The settings validator rejects non-positive retention values at startup. Values are read by `Settings` from the environment/root `.env`, not from the frontend.

## 2. Effective policy

`backend/app/services/retention_service.py` defines `RETENTION_RULES` as `(collection, timestamp field, settings field, optional shorter cap)`:

| Collection | Timestamp field | Effective period |
| --- | --- | --- |
| `fraud_analyses` | `created_at` | `RETENTION_DAYS` |
| `risk_indicators` | `created_at` | `RETENTION_DAYS` |
| `reports` | `created_at` | `RETENTION_DAYS` |
| `user_reports` | `created_at` | `RETENTION_DAYS` |
| `notifications` | `created_at` | `min(RETENTION_DAYS, 180)` |
| `monitoring_tasks` | `created_at` | `RETENTION_DAYS` |
| `audit_logs` | `created_at` | `AUDIT_RETENTION_DAYS` |
| `health_checks` | `created_at` | `RETENTION_DAYS` |
| `signin_events` | `created_at` | `RETENTION_DAYS` |
| `support_messages` | `created_at` | `min(RETENTION_DAYS, 30)` |
| `domain_intelligence` | `checked_at` | `min(RETENTION_DAYS, 30)` |
| `task_status` | `updated_at` | `min(RETENTION_DAYS, 7)` |
| `api_usage` | `updated_at` | `RETENTION_DAYS` |

Collections not listed here are not purged by this service. `payments` intentionally retains provider event/idempotency records; legal counsel must decide its final schedule before real billing data is processed.

## 3. What runs

- `enforce_retention(repos, settings)` deletes only documents where the collection's timestamp field is **strictly older** than `now - effective_days`. A document without that field is never selected.
- Each enabled run returns `{status, deleted: {collection: count}, total_deleted, executed_at, policy_days, limitations}` and writes one `system.retention_enforced` audit event with that summary.
- `backend/app/workers/tasks.py::cleanup_retention` uses the same service, writes Celery task status, and skips when `SCHEDULER_ENABLED=false` or `RETENTION_ENABLED=false`.
- `backend/app/workers/celery_app.py` schedules `enforce-data-retention` daily at 03:00 UTC.
- Admin/owner users can dispatch it immediately with `POST /api/v1/system/tasks/retention`, which returns `TriggerOut` (`queued` or `failed`). The purge itself still happens in the worker context.

MongoDB TTL indexes in `backend/app/db/mongo.py` remain an **asynchronous safety net** with fixed seconds (for example analyses 365 days, audit logs 730 days). They are not derived from the settings and must not be used as evidence that a shortened configuration has taken effect; the service is the authoritative enforcement path.

## 4. Limitations and operator duties

- This is not self-service data export/deletion; data-subject requests still need an operational process.
- A disabled job, a stopped Celery beat or a failed worker means retention is not enforced. Monitor task status and the audit event.
- Deletions are permanent from the application's viewpoint; take a verified backup before changing periods downward. See [DEPLOYMENT.md](DEPLOYMENT.md#backups-and-restore).
- `RETENTION_DAYS=365` and `AUDIT_RETENTION_DAYS=730` in this repository are engineering defaults, **not** a legally approved schedule. Replace them with the reviewed `[RETENTION SCHEDULE]` from [LEGAL_DRAFTS.md](LEGAL_DRAFTS.md) before processing real user data.
- A backup is not automatically encrypted by `scripts/backup_tool.py`; the operator must restrict access and encrypt at rest.

## 5. Verification

`backend/tests/test_hardening.py::test_retention_purge_respects_configuration` inserts expired and recent documents into `fraud_analyses` and `audit_logs`, verifies that only the expired documents are removed, and verifies that `RETENTION_ENABLED=false` deletes nothing. Final suite result: **111 backend tests passed**.
