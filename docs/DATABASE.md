# TrustLens AI — Database

Scope: MongoDB persistence implemented in `backend/app/db/mongo.py` and `backend/app/db/repositories.py`, plus the collections actually written by services, routes and workers. This document does not cover `legacy-threat-intel/`.

## 1. Connection and bootstrap

| Setting | Default | Compose value | Source |
| --- | --- | --- | --- |
| `MONGODB_URI` | `mongodb://localhost:27017` | `mongodb://mongodb:27017` | `backend/app/core/config.py`, `docker-compose.yml` |
| `MONGODB_DB` | `trustlens` | `${MONGODB_DB:-trustlens}` | same |
| `MONGODB_URI=mongomock://...` | in-memory test/dev mode | not used in Compose | `backend/app/db/mongo.py` |

`MongoDBService(settings)` creates a `MongoClient` with `serverSelectionTimeoutMS=5000`, `maxPoolSize=20` and `tz_aware=True`. `connect()` forces an early `admin.command("ping")` so failures are observable at startup. `setup()` then:

1. Creates any of the 28 declared `COLLECTIONS` that do not exist.
2. Applies `$jsonSchema` validators with `validationLevel: moderate` to **new** `users`, `fraud_analyses`, `notifications` and `audit_logs` collections. Validators are skipped for mongomock/injected clients; failures are logged, not fatal.
3. Calls `create_indexes()` for the 16 collections with declared indexes; failures are logged as warnings.

`MongoDBService.collection(name)` rejects any name outside `COLLECTIONS` with `KeyError`. All application access is centralised in `Repositories` (`backend/app/db/repositories.py:373`); `public()` converts `_id` to `id`, `BaseRepository.insert()` sets `created_at`, and `update()` sets `updated_at` while removing `_id`/`id` from changes. The admin config endpoint uses `settings.public_dict()`, not database state.

## 2. Collections

### 2.1 Collections in active use

| Collection | Repository / accessor | Written by | Indexes / TTL declared |
| --- | --- | --- | --- |
| `users` | `UserRepository` | Registration, demo/admin seeding, verification, role/active changes, preferences | `uniq_email`, `created_at_desc`; validator |
| `subscriptions` | `SubscriptionRepository` | Registration default plan, plan service, verified webhooks, cancel flag, scan increments | `uniq_user_sub` |
| `payments` | `PaymentRepository` | HMAC-verified webhook events with raw event payload | `uniq_payment`, `uniq_event` (both sparse unique) |
| `fraud_analyses` | `AnalysisRepository` | Analysis lifecycle (`pending` → `completed`/`failed`), history, stats | 6 indexes incl. idempotency + 365-day TTL; validator |
| `risk_indicators` | `GenericRepository` | One document per indicator on every analysis | none |
| `notifications` | `NotificationRepository` | Deduped high-risk and monitoring alerts; read state | `user_unread`, `uniq_dedupe`, 180-day TTL; validator |
| `monitoring_tasks` | `MonitoringRepository` | User CRUD; scheduler writes `last_run_at`/`last_status` | `user_created` |
| `companies` | `CompanyRepository` | `CompanyVerifier.upsert` by name fingerprint; company detail route | `uniq_company_fp`, `domain` |
| `domain_intelligence` | `DomainRepository` | `DomainAnalyser` cache/refresh by domain | `uniq_domain`, 30-day cache TTL |
| `job_listings` | `GenericRepository` | `run_monitoring` upserts by fingerprint; anomaly engine counts repeats | `uniq_listing_fp`, `published_desc` |
| `api_usage` | `ApiUsageRepository` | HTTP middleware increments per user + UTC hour bucket | `uniq_usage_bucket` |
| `audit_logs` | `AuditRepository` | Auth, monitoring, company, billing and admin actions | `actor_created`, 730-day TTL; validator |
| `plans` | `PlanRepository` | Five seeded plans; admin `PATCH /admin/plans/{code}` | none |
| `task_status` | `TaskStatusRepository` | Celery task start/complete/fail status | `uniq_task`, 7-day TTL |
| `reports` | `ReportRepository` | Cached base64 PDF and generation timestamp per analysis | `uniq_analysis_report` |
| `user_reports` | `UserReportRepository` | Corrections and community claims with dedupe keys, reputation snapshots, moderation states and review metadata | `analysis_user`, `uniq_user_report_dedupe`, `report_duplicate_group`, `entity_moderation`; validator |
| `token_blacklist` | `repos.blacklist` (`GenericRepository`) | Logout JWT `jti`; also queried by fingerprint in anomaly engine | none |
| `model_registry` | `ModelRepository` | Training registers versions; admin reads active/all | `uniq_model_version` |
| `platform_settings` | Direct `repos.mongo.db[...]` | `analytics_snapshot` from `aggregate_analytics` | none |
| `health_checks` | Direct `repos.mongo.db[...]` | Periodic `health_check` results | none |

### 2.2 Declared but unused by current application code

These names are created by `setup()`; no write path was found in `backend/app/`:

| Collection | Note |
| --- | --- |
| `organizations`, `recruiters` | Reserved for future tenant/entity modelling. |
| `url_scans`, `message_scans`, `document_scans` | Repository wrappers exist, but analysis results live in `fraud_analyses` with nested `url_intelligence`/`message_intelligence`. |
| `model_evaluations` | No current writer; training writes artifacts to disk and `model_registry`. |
| `processed_events` | Has a unique `event_id` index, but webhook idempotency is implemented via `payments.provider_event_id`. |
| `password_resets` | Reset tokens are stateless JWTs; no token document is stored. |

## 3. Indexes

Exact definitions from `backend/app/db/mongo.py:92–155`:

| Collection | Index name | Keys / options |
| --- | --- | --- |
| `users` | `uniq_email` | `{email: 1}` unique |
| `users` | `created_at_desc` | `{created_at: -1}` |
| `fraud_analyses` | `user_created` | `{user_id: 1, created_at: -1}` |
| `fraud_analyses` | `risk_score` | `{risk.score: -1}` |
| `fraud_analyses` | `analysis_type` | `{analysis_type: 1}` |
| `fraud_analyses` | `company_fp` | `{extracted.company_fingerprint: 1}` |
| `fraud_analyses` | `uniq_idempotency` | `{client_request_id: 1, user_id: 1}` unique, sparse |
| `fraud_analyses` | `analysis_ttl` | `{created_at: 1}`, `expireAfterSeconds=31536000` (365 days) |
| `notifications` | `user_unread` | `{user_id: 1, read: 1, created_at: -1}` |
| `notifications` | `uniq_dedupe` | `{dedupe_key: 1}` unique, sparse |
| `notifications` | `notification_ttl` | `{created_at: 1}`, `expireAfterSeconds=15552000` (180 days) |
| `monitoring_tasks` | `user_created` | `{user_id: 1, created_at: -1}` |
| `domain_intelligence` | `uniq_domain` | `{domain: 1}` unique |
| `domain_intelligence` | `cache_ttl` | `{checked_at: 1}`, `expireAfterSeconds=2592000` (30 days) |
| `companies` | `uniq_company_fp` | `{name_fingerprint: 1}` unique |
| `companies` | `domain` | `{domain: 1}` |
| `job_listings` | `uniq_listing_fp` | `{fingerprint: 1}` unique |
| `job_listings` | `published_desc` | `{published_at: -1}` |
| `subscriptions` | `uniq_user_sub` | `{user_id: 1}` unique |
| `payments` | `uniq_payment` | `{provider_payment_id: 1}` unique, sparse |
| `payments` | `uniq_event` | `{provider_event_id: 1}` unique, sparse |
| `user_reports` | `analysis_user` | `{analysis_id: 1, user_id: 1}` |
| `user_reports` | `uniq_user_report_dedupe` | `{dedupe_key: 1}` unique, sparse — one report per reporter/entity/claim |
| `user_reports` | `report_duplicate_group` | `{duplicate_group_key: 1}` — groups claims for independent-reporter counts |
| `user_reports` | `entity_moderation` | `{entity_key: 1, moderation_state: 1}` — community corroboration lookup |
| `api_usage` | `uniq_usage_bucket` | `{user_id: 1, bucket: 1}` unique |
| `audit_logs` | `actor_created` | `{actor_id: 1, created_at: -1}` |
| `audit_logs` | `audit_ttl` | `{created_at: 1}`, `expireAfterSeconds=63072000` (730 days) |
| `model_registry` | `uniq_model_version` | `{model_name: 1, version: 1}` unique |
| `task_status` | `uniq_task` | `{task_id: 1}` unique |
| `task_status` | `task_ttl` | `{created_at: 1}`, `expireAfterSeconds=604800` (7 days) |
| `processed_events` | `uniq_event` | `{event_id: 1}` unique |
| `reports` | `uniq_analysis_report` | `{analysis_id: 1}` unique |

Validators require:

| Collection | Required fields |
| --- | --- |
| `users` | `email`, `password_hash`, `role`, `created_at`; role enum `user/student/staff/admin/owner` |
| `fraud_analyses` | `user_id`, `analysis_type`, `status`, `created_at`, `risk` (object) |
| `notifications` | `user_id`, `kind`, `title`, `created_at` |
| `audit_logs` | `actor_id`, `action`, `created_at` |
| `user_reports` | `analysis_id`, `user_id`, `category`, `report_type`, `status`, `moderation_state`, `created_at`; `category` enum `correction/community`, `moderation_state` enum `pending/verified/corroborated/false_report/dismissed` |

## 4. Retention and data lifecycle

- MongoDB TTL indexes perform asynchronous deletion via the server's TTL monitor; expiry is not instantaneous and depends on mongod running.
- TTL seconds in `mongo.py` remain **hard-coded** (analyses 365 days, notifications 180, domain cache 30, audit logs 730, task status 7) and are now an asynchronous safety net only.
- `RETENTION_DAYS` and `AUDIT_RETENTION_DAYS` are authoritative for the Stage 8 purge in `backend/app/services/retention_service.py`; it also covers `risk_indicators`, `reports`, `user_reports`, `health_checks`, `signin_events` and `api_usage`, with shorter caps for notifications/support chats/domain cache/task status. See [RETENTION.md](RETENTION.md).
- No cascade is implemented: deleting a `fraud_analyses` document does not remove related documents by reference. The purge treats each collection independently under its own policy.
- Idempotency and dedupe are enforced by unique indexes: `(client_request_id, user_id)` for analyses, `dedupe_key` for notifications, `provider_event_id` for webhook payments, `(user_id, bucket)` for API usage, and `dedupe_key` (reporter + entity + normalised claim) for `user_reports`. Duplicate reports reuse the original document; different reporters on the same claim remain distinct.

## 5. Failure and fallback behaviour

- **Startup:** the API lifespan calls `mongo.connect()` and `mongo.setup()`. In `production`/`prod`, an exception is re-raised and startup fails (fail closed). In other environments, the service is replaced with `mongomock://`, `app.state.in_memory_fallback = True`, and startup continues with a warning (`backend/app/main.py:161–178`).
- **Visibility:** `/health` and `/api/v1/health` report `database: connected|unavailable`, `in_memory_fallback`, and status `ok|degraded`. `/api/v1/health` also reports Redis broker status (`backend/app/api/routes/system.py`).
- **Limitations of fallback:** data is process-local and lost on restart; it is for local development/tests only. Injected/mongomock clients skip JSON-schema validators.
- **Runtime errors:** `PyMongoError` is handled globally as HTTP 503 with `{"detail": "database temporarily unavailable"}`; missing repositories yield HTTP 503 `database not ready`.
- **Workers:** `worker_context()` connects with the configured URI and does not fall back to mongomock, so a broken database stops scheduled work rather than writing to an ephemeral store.

## 6. Backup and restore (MongoDB)

All commands below target the local Compose database name `trustlens`; substitute your `MONGODB_DB` if changed.

### Backup

```bash
# Consistent offline-style dump from the Compose MongoDB container
docker compose exec mongodb mongodump --db trustlens --out /tmp/trustlens-backup
docker compose cp mongodb:/tmp/trustlens-backup ./backup/trustlens-backup

# Alternative when mongod is reachable from the host
mongodump --uri "mongodb://localhost:27017/trustlens" --out ./backup
```

For a live production replica set, prefer `mongodump --uri "mongodb://.../trustlens?replicaSet=rs0" --oplog --out ./backup` for a point-in-time-consistent snapshot. The bundled Compose MongoDB is a standalone instance with no oplog-based consistency guarantee.

### Restore

```bash
# Pause writers first (recommended)
docker compose stop api worker beat

docker compose cp ./backup/trustlens-backup mongodb:/tmp/trustlens-backup
docker compose exec mongodb mongorestore --db trustlens --drop /tmp/trustlens-backup/trustlens

docker compose start api worker beat
```

`--drop` overwrites existing collections; omit it to merge. After restoring into an empty database, restart/start the API or worker once: `MongoDBService.setup()` recreates missing collections and indexes. JSON-schema validators are applied only when a collection is created, so a restored collection keeps its original validation options. Verify with:

```bash
curl -fsS http://localhost:${API_PORT:-8000}/health
docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("trustlens").getCollectionNames().length'
```

Include `mongodb_data` in disaster-recovery planning; it is the named Compose volume holding the database files. Redis holds only broker/result state and is not part of the durable business-data backup.
