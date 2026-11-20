# TrustLens AI — Environment configuration

**Status:** implemented in Stage 8. Environment variables are the only supported way to configure secrets. No credential belongs in source control.

## 1. Templates and real files

| File | Tracked? | Purpose |
| --- | --- | --- |
| `.env.example` | Yes | Canonical backend/Compose template. Every optional integration is empty; start here. |
| `frontend/.env.example` | Yes | Frontend build-time template (`VITE_API_URL`, optional `VITE_APP_NAME`). |
| `.env` (root) | No, gitignored | Local backend/Compose values. The working copy currently contains Razorpay **test** billing variables only. |
| `frontend/.env` | No, gitignored | Local frontend build overrides, if needed. |
| `legacy-threat-intel/.env.backup` | No, gitignored | Historical artifact; never read by the application or Compose. Rotate anything that was ever real and delete it when possible. |
| `backups/` | No, gitignored | Logical backup output. Contains personal data; encrypt and restrict permissions. |

`scripts/secret_scan.py` runs in CI as a blocking check: it fails if a tracked file name starts with `.env` (except `.env.example`), if anything under `backups/` is tracked, or if tracked text contains common credential patterns or private-key blocks. Final local run: `status: ok`, 269 files scanned, no findings.

## 2. Precedence and scope

- `Settings` in `backend/app/core/config.py` reads environment variables first, then `../.env` and `.env` relative to the process working directory. It is cached with `lru_cache(maxsize=1)`, so changing a value requires a process restart.
- Compose loads the optional root `.env` through `env_file` and applies explicit service overrides (MongoDB/Redis URLs, DB name, model/data paths, Celery flags). Compose overrides win for those service processes.
- `VITE_API_URL` is baked into the frontend bundle at build time; changing it requires rebuilding the image. The Compose default is `/api/v1` so browser calls stay same-origin.
- Tests set `MONGODB_URI=mongomock://`, `CELERY_ENABLED=false`, `TASK_ALWAYS_EAGER=true` and `SEED_DEMO_DATA` explicitly before importing the app. They do not depend on a developer's local `.env`.
- The browser extension stores only the API base URL, access token and optional web-app URL in `chrome.storage.local` for the current browser profile. It reads no environment file and transmits the token only to the configured API origin after explicit user consent.
- The React Native app is a plan only. Its future design uses the OS keystore and environment-specific API base, with no environment file shipped in a release.

## 3. Production checklist

1. Copy templates to untracked `.env` files; fill only the values you intend to use.
2. Set `ENVIRONMENT=production` and a unique high-entropy `SECRET_KEY` (`openssl rand -hex 48`); the app refuses to start with the development default in production.
3. Set explicit `ALLOWED_HOSTS` and `CORS_ORIGINS`; remove localhost defaults and `*` allowed-host mode.
4. Set `SEED_DEMO_DATA=false` (or ensure strong non-default credentials); never expose demo/admin accounts.
5. Review `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_WINDOW_SECONDS`, `RETENTION_ENABLED`, `RETENTION_DAYS` and `AUDIT_RETENTION_DAYS`. See [RETENTION.md](RETENTION.md).
6. Configure only licensed/enabled providers; empty values honestly report `not_configured`. See [SECURITY.md](SECURITY.md) for webhook and secret-rotation procedures.
7. Terminate TLS at a reverse proxy, enable MongoDB/Redis authentication and network isolation, and monitor request IDs, `429`s and `5xx`s.
8. Keep CI secrets in the GitHub Actions secret store; the release workflow uses only the built-in `GITHUB_TOKEN` with `packages: write`.

## 4. Protected identifiers

The HireShield → TrustLens rebrand deliberately preserved identifiers whose change would break data or deployments: MongoDB database `hireshield`, Compose project/volumes `hireshield-ai`, Celery namespace `hireshield`, Render hosts/services `hireshield-api-wets.onrender.com`, `hireshield-web-j72o.onrender.com`, `hireshield-api`, `hireshield-web`, `hireshield-backend`, seeded account emails `demo@hireshield.io` / `admin@hireshield.io`, model-manifest provenance, CI artifact names and live FAQ URLs. Do not “rebrand” these in `.env` or deployment descriptors without a separate migration plan.
