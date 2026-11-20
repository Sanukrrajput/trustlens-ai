# TrustLens AI browser extension (Chrome Manifest V3)

A deliberately small client for checking **the page you are currently viewing**. It has no background service worker, no content scripts and no history access. Analysis happens **only** when you click **Analyse this page**.

## Install for local development

1. Run the API (`docker compose up -d api` or the local FastAPI server) and sign in to the web app to obtain an access token.
2. Open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked** and select this directory.
3. Open the extension, expand **Connection settings**, and set:
   - **API base URL** — e.g. `http://localhost:8000/api/v1`
   - **Access token** — your own bearer access token from the web app
   - **Web app URL** *(optional)* — enables the "Open full report" link
4. Click **Analyse this page**. Chrome asks once to allow requests to your configured API origin; deny and nothing is sent.

## Permissions and why they exist

| Permission | Why it is needed | What it does **not** allow |
| --- | --- | --- |
| `activeTab` | Read and inject into the one tab the user is on when they click the action | No access to other tabs, no tab tracking |
| `scripting` | Inject a one-shot extractor into that tab on click | No persistent content script, no network interception |
| `storage` | Keep the API base URL, token and optional web URL in this browser profile | No sync to other devices, no page-content storage |
| `optional_host_permissions` | Request access to the configured API origin after an explicit click | Nothing is granted at install time; no arbitrary hosts are contacted |

There is no `history`, `tabs`, `webNavigation`, `cookies`, `alarms`, `background` or `content_scripts` entry. `manifest.json` pins a strict CSP (`script-src 'self'`) and the popup renders all remote and page-derived text with `textContent`, never `innerHTML`.

## What happens on a click

1. The popup reads the active tab's `id` and `url` (allowed by `activeTab` for that gesture).
2. It requests access to the API origin; if denied, it stops before reading any page text.
3. A self-contained extractor reads `document.title`, the meta description and up to 20,000 characters of visible text from **that page only**. Form values, cookies, stored data, other tabs and browsing history are never read.
4. It POSTs to `/api/v1/analysis/offer` with `offer_category: "other"` and `consent_external_lookups: false`. A fresh `client_request_id` is generated for idempotency.
5. The response is rendered in the popup. The score is labelled **uncalibrated risk score**, missing checks are counted, and no absence of evidence is presented as legitimacy.

Page text is held only in the popup's memory for that session. It is not written to extension storage or to any third party. Closing the popup discards it.

## Limits and privacy notes

- The extension uses your own account token; plan limits, authentication and server-side rate limits still apply.
- External lookups are never enabled from the extension. If you want them, run the analysis in the web app with explicit consent.
- A short page (<20 characters of visible text) is rejected before any request is sent.
- If the API origin does not allow the `chrome-extension://` origin via CORS, the request will fail with a visible error; configure `CORS_ORIGINS` on your own deployment rather than weakening the extension.
- No telemetry, analytics, crash reporting or remote configuration is included.
- Risk output is decision support only and is never proof of fraud or of legitimacy.

## Verification

```
cd browser-extension
npm test
```

The six tests assert the minimal permission set, absence of background/automatic hooks, explicit-click wiring, self-contained extraction, bounded/untrusted text handling and honest failure when a page is unavailable. They are static/runtime contract tests, not browser-integration tests; load the unpacked extension for interactive verification.
