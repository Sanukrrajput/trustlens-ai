# TrustLens AI mobile implementation plan (React Native)

**Status: plan only — no mobile application is implemented in this repository.** This document defines the boundary a future implementation must respect. The web application and its API remain the source of truth; this plan does not create a second intelligence engine.

## Product shape

A React Native (TypeScript) client for Android and iOS that lets a user **explicitly share** one item for verification:

| Entry point | User action | Data sent |
| --- | --- | --- |
| Android Share Intent (`ACTION_SEND`, `text/plain`) | User selects TrustLens in the share sheet for a message, advert or offer text | The shared text only |
| Android Share Intent (`ACTION_SEND`, `image/*`) | User shares a screenshot or photo | That single image only |
| In-app "Choose screenshot" | User picks one image from the photo library | That single image only |
| In-app paste | User pastes message text | The pasted text only |

No entry point reads another application's data without the user's deliberate share action.

## Hard prohibitions

See [PERMISSION_POLICY.md](PERMISSION_POLICY.md). In short: no notification-listener service, no accessibility service, no background screenshot capture, no contact/location access, no bulk media-library scanning, no message-app scraping, no silent monitoring, no background analysis and no geofencing.

## Architecture

```
Share Intent / in-app picker
        ↓  (explicit user action only)
Local validation + size/type checks
        ↓
Secure token from OS keystore
        ↓
POST /api/v1/analysis/offer  (text)  or  /api/v1/analysis/document (single image)
        ↓
Explainable JSON result → local rendering (score, indicators, missing evidence)
        ↓
Optional deep link to the web-app report for the full audit trail
```

The mobile client must not implement its own risk model, threat feed, campaign verification or reputation logic. It consumes the same validated API contract as the web and extension clients and displays the same honesty caveats: uncalibrated score, no proof of fraud, absence of a match is not legitimacy.

## Implementation phases

1. **Scaffold** — RN TypeScript app, environment-specific API base, OS keystore-backed token storage, login via the system browser (`ASWebAuthenticationSession` / Chrome Custom Tabs). No share receiver yet.
2. **Share Intent receiver** — Android intent filters for `text/plain` and single `image/*`; an in-app queue with exactly one item at a time; explicit "Verify" button; no automatic submission on receive.
3. **Single-image flow** — MIME/magic-byte and size validation on device; upload to `/analysis/document`; show a clear `not_configured` state when OCR is unavailable; never claim a screenshot proves authenticity.
4. **Text/message flow** — 20–200,000 character validation; `/analysis/offer` with `offer_category: "other"` and `consent_external_lookups: false`; a separate, unchecked-by-default consent toggle if external lookups are ever exposed.
5. **Report rendering** — risk category, uncalibrated score, indicator list, `missing_evidence`, `technical_limitations`, deep link to web report. No charts implying calibrated probability.
6. **Hardening** — certificate pinning for the configured production host, local result cache with short TTL and user-clearable history, accessibility review, crash-free local error states, abuse/rate-limit handling.
7. **Acceptance** — permission audit, data-flow review and the tests below; publish only after the web app and Stage 8 controls are green.

## Acceptance checklist for the future implementation

- Granting no "dangerous" Android permission still allows the full user-shared flow.
- No `RECEIVE_BOOT_COMPLETED`, `READ_SMS`, `READ_CONTACTS`, `ACCESS_FINE_LOCATION`, `READ_EXTERNAL_STORAGE` (broad), `BIND_NOTIFICATION_LISTENER_SERVICE` or accessibility service declaration exists in the built manifest.
- A share arrives but nothing is transmitted until the user taps Verify.
- Only the shared item appears in the request body; no other messages, photos or app data are included.
- Denying network access or having an unconfigured backend produces an explicit error, never a fabricated result.
- The rendered score is labelled uncalibrated and an empty threat/brand lookup is shown as unavailable, not clean.
- The app has no background scheduler, no silent refresh and no telemetry.

## Verification commands (once implemented)

```
npm test                 # unit + share-intent contract tests
npm run build            # TypeScript + release bundle
./gradlew lint           # Android manifest permission audit
```

Until those commands exist in code, this document is the plan and must not be presented as a delivered application.
