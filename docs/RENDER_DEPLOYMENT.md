# HireShield AI — Render Deployment Guide

**Status: manifests prepared, nothing deployed.** The root [`render.yaml`](../render.yaml) describes the intended Render resources, but this workspace has no Render account/CLI access, no Git history, no domain and no production secrets. Do not describe HireShield AI as deployed until the checklist at the end passes.

Render will create these resources from the Blueprint:

| Resource | Type | Purpose |
| --- | --- | --- |
| `hireshield-redis` | Key Value (Redis-compatible) | Celery broker/result backend. Internal access only; `noeviction`; persistence on. |
| `hireshield-api` | Docker web service | FastAPI/Uvicorn on container port `8000`. Public HTTPS host. |
| `hireshield-worker` | Docker background worker | Celery worker for monitoring/analysis/email jobs. |
| `hireshield-beat` | Docker background worker | Celery Beat scheduler. |
| `hireshield-web` | Static site | React SPA built from `frontend/`, published from `frontend/dist`. |

Render does **not** host MongoDB in this Blueprint. You must provide an external MongoDB connection string (MongoDB Atlas is the usual choice).

> Cost note: `0.5c-512mb` is a paid compute plan for web/worker services, and the `256mb` Key Value instance is also paid. Static sites are free. Check current Render pricing before creating the Blueprint. Free web services sleep and are unsuitable for payment webhooks.

---

## 1. Prerequisites

1. **A Git repository.** Render deploys from Git, not from this local folder. The workspace is currently not a Git repository, so initialise one and push it to GitHub/GitLab/Bitbucket:

   ```powershell
   git init
   git add .
   git commit -m "Initial HireShield AI application"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```

   `.gitignore` excludes `.env`, `.env.*` (except `.env.example`), `.venv/`, `node_modules/` and build output. Verify with `git status` that no secret or local `.env` is staged.

2. **MongoDB Atlas or another managed MongoDB.** Create a cluster, database user and network access rule that permits Render egress (Atlas commonly uses `0.0.0.0/0` for managed-platform deployments; restrict further if your provider supports Render IP ranges). Copy the SRV connection string. The app uses `MONGODB_DB=hireshield` separately, so the URI may point at the cluster root.

3. **A Render account** with a workspace where the five resource names above are available. If a name is taken, rename it in `render.yaml` **and** update every reference to it.

4. **Optional credentials**, only if you want those features enabled at launch:
   - Razorpay key id, key secret and a webhook secret (test first; live only after the drill).
   - Cloudflare Turnstile site key and secret key for the production hostname.
   - SMTP credentials for verification, reset and alert emails.
   - Licensed threat-intelligence/registry keys. RDAP, DNS and TLS checks need no credentials.

No local `.env` value is read by Render. The Blueprint supplies runtime environment variables.

---

## 2. Key environment decisions in the Blueprint

- `SECRET_KEY` is generated **once** in the `hireshield-backend` environment group and shared by API, worker and beat. Do not replace it with the local development placeholder.
- `ENVIRONMENT=production`, `SEED_DEMO_DATA=false`, `CELERY_ENABLED=true`, `TASK_ALWAYS_EAGER=false`, `MODEL_DIR=/app/models`, `DATA_DIR=/app/data`.
- `MONGODB_URI` uses `sync: false`, so Render prompts for it. It is declared on API, worker and beat; enter the **same** Atlas URI each time.
- `REDIS_URL` is imported from the Key Value service via `fromService`, so no Redis password is hardcoded.
- `PORT=8000` matches the Uvicorn command. Render routes public traffic to that container port.
- `CORS_ORIGINS` defaults to `https://hireshield-web.onrender.com` and `ALLOWED_HOSTS` to `hireshield-api.onrender.com`. Update the environment group in the Blueprint if Render gives your services a suffix or you use custom domains.
- `VITE_API_URL` defaults to `https://hireshield-api.onrender.com/api/v1`. It is **baked into the JavaScript bundle at build time**. If the API host changes, edit that value and trigger a frontend rebuild; a dashboard-only change is not enough.
- Razorpay and Turnstile values also use `sync: false`. Leave them blank at creation to keep those integrations explicitly disabled; `/api/v1/system/config` will then report them as not configured.

> `sync: false` values are prompted only during the **initial** Blueprint creation. Later Blueprint syncs ignore them. To change a secret later, edit it in the Render dashboard or delete and recreate the environment variable deliberately.

---

## 3. Deploy from the Blueprint

1. Push the repository (including `render.yaml`) to your chosen Git host.
2. In Render, choose **New → Blueprint**.
3. Connect the repository and the branch to deploy. Accept the default Blueprint path `render.yaml`.
4. Choose a Blueprint/workspace name and region if prompted. Keep the resource names in the file consistent with your final hostnames.
5. Fill the prompted values:
   - `MONGODB_URI`: the Atlas connection string, three times (API, worker, beat).
   - `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`: leave blank for a no-billing deployment, or supply test values. Never use live keys for the first drill.
   - `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`: leave blank until a widget exists for the final hostname.
6. Click **Apply** / **Create Resources**. Render builds three Docker services from `backend/Dockerfile` and the static site from `frontend/`.
7. Watch the deploys. Expected commands in the logs:
   - API: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers`
   - Worker: `celery -A app.workers.celery_app:celery_app worker --loglevel=info --queues=celery --concurrency=2`
   - Beat: `celery -A app.workers.celery_app:celery_app beat --loglevel=info`

Render supplies managed TLS on the `onrender.com` hosts. No reverse-proxy container is needed for the static-site deployment because the browser calls the API host directly using the baked `VITE_API_URL`.

---

## 4. After the first deploy

### Fix hostnames if needed

Open the API service logs and the frontend URL. If Render appended a suffix:

1. Edit `envVarGroups[0].envVars` in `render.yaml`:
   - `CORS_ORIGINS` → the exact frontend HTTPS origin.
   - `ALLOWED_HOSTS` → the exact API hostname (no scheme).
2. Edit `VITE_API_URL` on `hireshield-web` → `https://<api-host>/api/v1`.
3. Commit, push and let Render redeploy. Alternatively make the equivalent changes in the dashboard, but then keep `render.yaml` in sync to avoid a later Blueprint sync overwriting them.

### Bootstrap an administrator

`SEED_DEMO_DATA=false` means **no demo or admin accounts are created**. Choose one controlled approach:

- Register your real admin email through the UI, then promote that document in MongoDB by setting `role: "admin"` (and normally `email_verified: true`); or
- Perform a one-time controlled seed with unique strong credentials, then disable seeding again. Never expose the development `admin@hireshield.io` / `AdminPass123!` pair.

Remove the temporary local `ops.admin@hireshield.io` verification account if any database is ever copied from this workspace.

### Configure Razorpay

1. In Razorpay test mode, open **Settings → Webhooks → Add Webhook**.
2. URL: `https://<api-host>/api/v1/billing/webhooks/razorpay` (with the Blueprint names, `https://hireshield-api.onrender.com/api/v1/billing/webhooks/razorpay`).
3. Secret: the same value as the API service's `RAZORPAY_WEBHOOK_SECRET`. Do not paste it into `render.yaml` or a chat.
4. Events: `payment.captured`, `order.paid`, `payment.failed`, `refund.created`. Optional: `subscription.charged`, `subscription.cancelled`.
5. Run a real test-mode purchase. Confirm that a successful browser checkout alone does **not** grant paid access, and that only the signed webhook moves the subscription to paid. Then exercise a failure and refund. See [RAZORPAY_SETUP.md](RAZORPAY_SETUP.md).
6. Only after the full drill passes, replace the test keys/secret in the Render dashboard, register the production webhook and repeat verification with a small live transaction. PAN/KYC remains inside Razorpay; this app never collects card, CVV, bank or PAN data.

### Optional integrations

Add SMTP or credentialed intelligence keys through the Render dashboard (or add new `sync: false` entries to each relevant service and redeploy). Empty values are correct for unconfigured integrations: the API reports them honestly rather than inventing results.

---

## 5. Verification checklist

Run these against the public URLs after each deploy:

- [ ] `GET https://<api-host>/health` returns a healthy JSON response; `database` is `connected` and `in_memory_fallback` is false.
- [ ] `GET https://<api-host>/api/v1/health` returns the API health payload.
- [ ] `GET https://<api-host>/api/v1/system/config` shows `environment: production`, correct billing mode and only the integrations you actually configured. `/docs` and `/openapi.json` are disabled.
- [ ] Open `https://<web-host>/`, sign in with the provisioned admin account, then deep-link to a route such as `/app/admin` and refresh: the SPA rewrite must serve `index.html`.
- [ ] The browser network tab shows API calls going to the exact `VITE_API_URL` host and no CORS/TrustedHost errors.
- [ ] Start an analysis and confirm Celery work is processed by `hireshield-worker`; check `hireshield-beat` logs for scheduled entries.
- [ ] Razorpay test purchase → signed webhook → paid subscription → refund/failure drill passes. An unsigned webhook returns `400`; a checkout callback never grants access.
- [ ] MongoDB Atlas has authentication enabled and a tested backup/restore. Key Value metrics, memory and connection limits are monitored.
- [ ] Custom domains, if used, are set on both services and reflected in `ALLOWED_HOSTS`, `CORS_ORIGINS` and `VITE_API_URL`.

---

## 6. Local validation before pushing

The Render CLI is not installed in this workspace, so Blueprint validation was **not** run here. On a machine with the CLI:

```bash
render blueprints validate render.yaml
```

You can also associate `render.yaml` with Render's JSON Schema (`https://render.com/schema/render.yaml.json`) in VS Code. Basic YAML parsing can be checked with Python's `yaml.safe_load`.

Always validate the rendered config after editing service names or environment references. See [DEPLOYMENT.md](DEPLOYMENT.md) for application-level configuration, backups and Compose deployment, and [LAUNCH_READINESS.md](LAUNCH_READINESS.md) for the remaining production go/no-go criteria. **A manifest is not a deployment.**
