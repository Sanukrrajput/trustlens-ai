# TrustLens AI — Render Free-Plan Deployment Guide

**Status: deployed on Render's Free plan.** The root [`render.yaml`](../render.yaml) declares only resources available on Render's Free plan: one free Docker web service for the API and one free static site for the frontend. This is an **evaluation deployment, not a production deployment**.

- API: <https://hireshield-api-wets.onrender.com>
- Frontend: <https://hireshield-web-j72o.onrender.com>
- Blueprint instance: `trustlens-ai` (`exs-dbvj2k8n74is739nq3h0`), synced from `Sanukrrajput/trustlens-ai@main`
- External datastore: MongoDB Atlas free M0; the URI is a Render secret and is not in Git, chat or this document.

Live verification: `/health`, `/api/v1/health` and `/api/v1/system/config` return expected production payloads; the database is connected and `in_memory_fallback` is false; `/docs` and `/openapi.json` return 404; the frontend deep-link path serves the SPA and calls the correct API host.

> Free-plan reality: the API container sleeps after roughly 15 minutes of inactivity and takes about a minute to wake on the next request. Render does not offer free background workers or cron jobs. Do not use this deployment for time-sensitive billing webhooks, scheduled monitoring or production traffic.

---

## 1. What the free Blueprint creates

| Resource | Type | Plan | Purpose |
| --- | --- | --- | --- |
| `hireshield-api` | Docker web service | `free` | FastAPI/Uvicorn on container port `8000`; public HTTPS host; health path `/health`. |
| `hireshield-web` | Static site | free | React SPA built from `frontend/`, published from `frontend/dist`. |

The following paid resources were **removed**: `trustlens-worker`, `trustlens-beat` and `trustlens-redis` (Key Value). MongoDB is not created by the Blueprint; an external MongoDB Atlas M0 cluster is used.

Free-plan runtime choices:

- `CELERY_ENABLED=false`
- `TASK_ALWAYS_EAGER=true`
- `SCHEDULER_ENABLED=false`

Consequences:

- Celery/Redis are disabled. Background work, if triggered, runs **in the web process** only.
- No periodic monitoring, scheduled reports or retry-after-restart queue exists.
- Tasks are lost if the service restarts while they are running.
- `/api/v1/system/config` reports Redis and scheduler status honestly.
- The free service is not suitable as a payment-webhook endpoint because of cold starts.

---

## 2. Prerequisites

1. **Git remote.** Already configured and pushed:

   ```powershell
   git remote -v
   git status --short
   git push origin main
   ```

   `.gitignore` excludes `.env`, `.env.*` except `.env.example`, `.venv/`, `node_modules/` and build output. Verify that no secret or local `.env` is staged.

2. **MongoDB Atlas.** A free M0 cluster, database user and network access rule exist. The connection string is entered only through Render's secret prompt and is never placed in `render.yaml`, Git or documentation.

3. **Render account and GitHub access.** The GitHub App should have access only to `Sanukrrajput/trustlens-ai`. Confirm the workspace shows **No card on file**; the free plan must not require payment.

4. **Optional credentials.** Leave Razorpay and Turnstile blank at first. With no keys, billing and bot-challenge integrations remain explicitly disabled and are reported as such.

No local `.env` value is read by Render. The Blueprint supplies runtime environment variables.

---

## 3. Key environment decisions in the Blueprint

- `SECRET_KEY` is generated once in the `hireshield-backend` environment group and used by the API. Do not replace it with the development placeholder.
- `ENVIRONMENT=production` and `SEED_DEMO_DATA=false`: no demo/admin accounts are seeded.
- `MONGODB_URI` uses `sync: false`, so Render prompts for it. Paste the Atlas URI into that prompt only.
- `PORT=8000` matches the Uvicorn command. Render routes public traffic to that container port.
- `CORS_ORIGINS` is set to `https://hireshield-web-j72o.onrender.com`; `ALLOWED_HOSTS` is set to `hireshield-api-wets.onrender.com`.
- `VITE_API_URL` is set to `https://hireshield-api-wets.onrender.com/api/v1`. It is **baked into the JavaScript bundle at build time**. If the API host changes, edit this value and trigger a frontend rebuild; a dashboard-only change is not enough.
- `HealthCheckTrustedHostMiddleware` exempts only `/health` from host validation, because platform health probes may send an internal IP or hostname in the `Host` header. Application routes remain host-allow-listed.
- Razorpay and Turnstile values use `sync: false`. Leave them blank at creation to keep those integrations disabled.
- `REDIS_URL` is absent. The backend falls back to in-memory Celery behaviour, which is safe only because it is paired with `CELERY_ENABLED=false` and eager tasks.

> `sync: false` values are prompted only during the **initial** Blueprint creation. Later Blueprint syncs ignore them. To change a secret later, edit it in the Render dashboard or deliberately delete and recreate the environment variable.

---

## 4. Deploy from the Blueprint

1. Push the updated repository (including the free-plan `render.yaml`) to `main`.
2. In Render, choose **New → Blueprint**.
3. Connect `Sanukrrajput/trustlens-ai`, branch `main`, Blueprint path `render.yaml`.
4. Choose a Blueprint/workspace name. Keep the service names in the file consistent with the final hostnames.
5. Confirm the parser shows only `hireshield-api` and `hireshield-web`, with the API plan as `free`. Do not continue if paid workers, Redis or a paid API plan still appear.
6. Fill the prompted values:
   - `MONGODB_URI`: the Atlas connection string. Paste it directly into the Render prompt; do not echo it into chat, a file or `render.yaml`.
   - `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`: leave blank.
   - `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`: leave blank.
7. Click **Apply** / **Create Resources**. Render builds one Docker image from `backend/Dockerfile` and the static site from `frontend/`.
8. Watch the deploys. Expected API command in the logs:

   ```text
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
   ```

   Expected frontend build command:

   ```text
   cd frontend && npm ci && npm run build
   ```

Render supplies managed TLS on the `onrender.com` hosts. No reverse-proxy container is needed because the browser calls the API host directly using the baked `VITE_API_URL`.

---

## 5. After the first deploy

### Fix hostnames if needed

Open the API service logs and the frontend URL. If Render appended a suffix:

1. Edit `envVarGroups[0].envVars` in `render.yaml`:
   - `CORS_ORIGINS` → the exact frontend HTTPS origin.
   - `ALLOWED_HOSTS` → the exact API hostname, with no scheme.
2. Edit `VITE_API_URL` on `hireshield-web` → `https://<api-host>/api/v1`.
3. Commit, push and let Render redeploy. Dashboard-only changes are acceptable for an urgent fix, but keep `render.yaml` in sync so a later Blueprint sync does not overwrite them.

### Bootstrap an administrator

`SEED_DEMO_DATA=false` means **no demo or admin accounts are created**. Register a real admin email through the UI, then promote that document in MongoDB by setting `role: "admin"` and normally `email_verified: true`.

Never expose the development `admin@hireshield.io` / `AdminPass123!` pair. Remove the temporary local `ops.admin@hireshield.io` verification account if any local database is ever copied.

### Billing and Turnstile remain disabled

No Razorpay keys are configured. `/api/v1/system/config` must report billing as unavailable/not configured, and checkout must fail honestly instead of inventing an order.

Turnstile activates only when **both** site and secret keys are present. With blank keys, login must report `not_configured` and not run a challenge.

Do not register a Razorpay webhook pointing at a free web service: cold starts can cause timeouts. If billing is enabled later, use a paid always-on API plan first, then follow [RAZORPAY_SETUP.md](RAZORPAY_SETUP.md).

---

## 6. Verification checklist

Run these against the public URLs after each deploy:

- [ ] `GET https://<api-host>/health` returns a healthy JSON response; `database` is `connected` and `in_memory_fallback` is false.
- [ ] `GET https://<api-host>/api/v1/health` returns the API health payload.
- [ ] `GET https://<api-host>/api/v1/system/config` shows `environment: production`, `celery_enabled: false`, `scheduler_enabled: false`, Redis not configured, and only the integrations actually configured.
- [ ] `/docs` and `/openapi.json` are disabled in production.
- [ ] Open `https://<web-host>/`, sign in with the provisioned admin account, then deep-link to `/app/admin` and refresh: the SPA rewrite must serve `index.html`.
- [ ] Browser network tab shows API calls going to the exact `VITE_API_URL` host and no CORS/TrustedHost errors.
- [ ] A first request after idle succeeds after the short cold-start delay.
- [ ] No worker or beat services exist in the Render dashboard; no paid resources appear on the bill.
- [ ] MongoDB Atlas authentication is enabled and the IP access rule is as narrow as Render's dynamic egress allows.

Do **not** expect scheduled monitoring, background retries or payment webhook delivery on this free deployment.

---

## 7. Local validation before pushing

Render CLI validation is optional:

```bash
render blueprints validate render.yaml
```

This project also checks YAML parsing locally:

```powershell
python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('render.yaml').read_text(encoding='utf-8')); print('render.yaml OK')"
```

Run the secret guard and full test suite before every deployment change. See [DEPLOYMENT.md](DEPLOYMENT.md) for application-level configuration and [LAUNCH_READINESS.md](LAUNCH_READINESS.md) for the remaining production go/no-go criteria. **A manifest or a successful free deployment is not a production launch.**
