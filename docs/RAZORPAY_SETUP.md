# Razorpay setup for plans and billing

This guide configures Razorpay for the TrustLens AI plan catalogue, browser checkout and signed webhook activation. It does not require any source-code changes: all behaviour is driven by environment variables and the admin-editable `plans` collection.

> **PAN / KYC note:** PAN, GST, bank settlement and merchant KYC details are configured in your Razorpay dashboard, not in this application. TrustLens never accepts or stores card numbers, CVV, bank details or PAN. If you meant Razorpay merchant PAN verification, complete it in Razorpay → Settings → Account & KYC before going live.

## Current local status (this workspace)

- A root `.env` contains a Razorpay **test** key pair imported from `C:\Users\LENOVO\Downloads\rzp-key.csv`, a locally generated `RAZORPAY_WEBHOOK_SECRET`, and `PAYMENT_CURRENCY=INR`. Never commit it.
- The Razorpay account id `acc_SJwl6TxN6lCfva` was supplied but is not used by this integration; only key id/secret and webhook secret are required.
- Verified after restart: `GET /api/v1/system/config` reports `integrations.razorpay=true`, `billing.razorpay_mode=test`, `billing.razorpay_webhook=true` and `features.billing_enabled=true`.
- A real test order was created via `POST /api/v1/billing/checkout` (professional monthly, 29900 paise, INR). No payment was completed and no entitlement changed.
- A locally signed webhook using the configured secret was accepted and recorded as `ignored` (see §5 smoke test), proving HMAC verification works with the real secret.
- **Still pending:** copy the webhook secret from `.env` into Razorpay → Settings → Webhooks, register the URL and event list below, then run the full signed purchase → subscription drill in §5. No live keys are configured.

## 1. Create keys

1. Sign in to Razorpay and use **Test mode** first.
2. Go to **Settings → API Keys** and generate a test key pair.
3. Copy the **Key ID** (`rzp_test_...`) and **Key Secret**. Treat the secret as a password.
4. Go to **Settings → Webhooks → Add Webhook**.
5. Set the webhook URL to the public API path:

   ```text
   https://<your-api-host>/api/v1/billing/webhooks/razorpay
   ```

   For local development, expose port 8000 through a trusted tunnel (for example ngrok) and use that HTTPS URL.

6. Create a **webhook secret** and copy it. This is different from the API Key Secret.
7. Subscribe at least to:

   | Event | Purpose |
   | --- | --- |
   | `payment.captured` | Activates a paid subscription |
   | `order.paid` | Backup activation event |
   | `payment.failed` | Records a failed payment |
   | `refund.created` | Records a refund |

   Optional when using Razorpay Subscriptions rather than one-time orders: `subscription.charged`, `subscription.cancelled`.

## 2. Configure the environment

Copy `.env.example` to `.env` at the repository root, then fill only the billing block:

```dotenv
RAZORPAY_KEY_ID=rzp_test_replace_me
RAZORPAY_KEY_SECRET=replace_me_with_test_key_secret
RAZORPAY_WEBHOOK_SECRET=replace_me_with_webhook_secret
PAYMENT_CURRENCY=INR
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

Never commit `.env`. `RAZORPAY_KEY_ID` is a public, browser-visible identifier; `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` must remain server-side only.

Restart the API after changing these values. The frontend does not need a Razorpay environment variable: the server returns the public key id with each checkout response.

## 3. Confirm runtime configuration

```bash
curl -s http://localhost:8000/api/v1/system/config | jq '.integrations, .billing, .features.billing_enabled'
```

Expected with test keys:

```json
{
  "razorpay": true,
  "billing": {
    "razorpay": true,
    "razorpay_mode": "test",
    "razorpay_webhook": true,
    "stripe": false,
    "stripe_webhook": false,
    "currency": "INR"
  },
  "billing_enabled": true
}
```

If keys are missing, checkout returns `503 not configured` and the UI reports the real error. No payment is simulated.

## 4. Set plan prices

Plans are seeded once into MongoDB and then edited through the admin API. Prices are in the smallest currency unit (paise for INR).

```bash
TOKEN="<admin access token>"
curl -X PATCH http://localhost:8000/api/v1/admin/plans/professional \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"price_monthly_paise":29900,"price_yearly_paise":299000,"active":true}'
```

`free` and `enterprise` default to price `0`, so they intentionally do not open a paid checkout. The amount in the signed webhook must match the plan price for the chosen interval; mismatches are recorded and do not change subscription state.

## 5. Test the full flow

1. Sign in as a normal user and open **Plans & billing**.
2. Choose monthly or yearly, then choose a paid plan.
3. The API creates a Razorpay **order** on the server; the browser opens the official Razorpay Checkout script with that order id.
4. Pay with a Razorpay test card. The page shows **Awaiting webhook** and the payment/order ids. This screen does **not** grant access.
5. Confirm the webhook was delivered in Razorpay → Webhooks → Attempts.
6. Refresh `/billing/subscription` or click **Refresh subscription status** in the UI. Only after the signed webhook is verified should `plan_code`, `provider: razorpay` and the new scan limit appear.
7. In Razorpay, issue a test refund and confirm the `refund.created` webhook is recorded without reactivating the account.

A local signed-event smoke test is also available:

```powershell
$line = Get-Content -LiteralPath '.env' | Where-Object { $_ -like 'RAZORPAY_WEBHOOK_SECRET=*' } | Select-Object -First 1
$secret = $line.Split('=', 2)[1].Trim()
$eventId = 'evt_local_smoke_' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$body = '{"id":"' + $eventId + '","event":"payment.captured","payload":{}}'
$hash = [Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($secret)).ComputeHash([Text.Encoding]::UTF8.GetBytes($body))
$sig = [BitConverter]::ToString($hash).Replace('-', '').ToLowerInvariant()
Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/billing/webhooks/razorpay' -Method Post -ContentType 'application/json' -Headers @{ 'X-Razorpay-Signature' = $sig } -Body $body
```

This payload has no user notes, so it is recorded as ignored; it proves signature verification without changing entitlement. Verified locally against the generated secret: `{"status":"ignored","event_id":"evt_local_smoke_...","subscription_status":"ignored"}`.

## 6. Go live

1. Complete Razorpay merchant KYC, settlement and tax configuration in the Razorpay dashboard.
2. Generate **live** keys and a separate live webhook secret.
3. Register the live webhook URL with the live event list.
4. Replace the test values in the production secret store, set `ENVIRONMENT=production`, strong `SECRET_KEY`, explicit `CORS_ORIGINS` and `ALLOWED_HOSTS`.
5. Run one low-value live purchase, verify activation, then verify cancellation/refund handling.
6. Reconcile Razorpay payments against the `payments` collection and keep `raw_event` payloads for audit.

## Security behaviour

- Webhook authenticity: HMAC-SHA256 of the **raw** request body with `RAZORPAY_WEBHOOK_SECRET`, compared using `hmac.compare_digest`.
- Idempotency: provider event ids are unique; replays return `already_processed`.
- Activation allowlist: only `payment.captured`, `order.paid`, `subscription.charged`, `checkout.session.completed` and `invoice.payment_succeeded` can activate. Unknown events are ignored.
- Amount and currency are checked against the configured plan; mismatches never activate a subscription.
- Browser success/cancel URLs and the checkout response are display-only and can never grant paid access.

See [API.md](API.md) §7 for the webhook contract and [DEPLOYMENT.md](DEPLOYMENT.md) for production environment handling.
