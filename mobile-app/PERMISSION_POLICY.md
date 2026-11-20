# Mobile permission and data-access policy

This policy applies to any future TrustLens AI React Native implementation. It is written before the code so that capability creep is visible in review.

## Allowed

| Capability | Scope | Condition |
| --- | --- | --- |
| Android Share Intent `text/plain` | One user-selected text item | Submitted only after the user taps Verify |
| Android Share Intent `image/*` | One user-selected image | MIME/size checked locally; submitted only after Verify |
| Photo-library single-image picker | One image chosen in the app | No bulk enumeration or background reads |
| Clipboard paste | Text the user pastes into the app | No background clipboard polling |
| Secure token storage | OS keystore / Keychain | Token never logged or sent except to the configured API origin |
| System-browser login | Auth flow only | No in-app credential harvesting |

## Explicitly forbidden

The implementation must **not** include, request or emulate:

- `BIND_NOTIFICATION_LISTENER_SERVICE` or any notification capture.
- An accessibility service (`AccessibilityService`) or any overlay that reads another app's screen.
- Background screenshot capture, screen recording, or periodic media-library scans.
- `READ_SMS`, `READ_CONTACTS`, `READ_CALL_LOG`, `ACCESS_FINE_LOCATION`, `READ_PHONE_STATE`.
- Broad `READ_EXTERNAL_STORAGE`; use the scoped single-item picker instead.
- Message-app scraping, chat database access, or reading another app's files.
- `RECEIVE_BOOT_COMPLETED`, background services or periodic sync that analyses content.
- Silent forwarding of shared content to analytics, advertising or a second backend.
- Any local "fraud verdict" produced without the server's explainable result.

## Data handling

- Shared content is held in memory until Verify or Cancel, then discarded from the queue.
- Any local result cache is opt-in, short-lived and clearable from Settings.
- The app sends only the selected item, the chosen offer category (default `other`), `consent_external_lookups: false`, and an idempotency key to the configured API.
- Request/response bodies containing user content are never written to application logs.
- Screenshots and user-supplied adverts are treated as untrusted evidence, never as proof of campaign authorisation.

## Review gate

A pull request that adds any permission not listed under **Allowed** must include a written justification, a data-flow diagram and an explicit owner approval. A PR that adds any item from **Explicitly forbidden** is rejected. The acceptance checklist in [README.md](README.md) must be checked before release.
