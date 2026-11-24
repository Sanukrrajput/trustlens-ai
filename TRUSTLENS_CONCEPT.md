# TrustLens AI — Canonical Product Concept

**Status:** Authoritative. This record overrides any older copy that frames the product as a job-fraud-only tool.

## One-line definition

TrustLens AI is an **evidence-led verification lens for any online offer, advert, message, link or screenshot**. It tells a person what was observed, what was checked, what could not be checked, which signals drove the assessment, and what to do next.

## What makes TrustLens distinct

HireShield AI was a recruitment-fraud checker. TrustLens keeps that capability as **one offer category**, but the product itself is broader:

| HireShield framing (retired) | TrustLens framing (active) |
| --- | --- |
| “Verify before you apply” | “Verify before you act” |
| Job posts and recruiter messages only | Offers, adverts, giveaways, scholarships, investments, promotions, recruitment, impersonation, links and documents |
| Employer/recruiter legitimacy | Claim, brand/campaign authorisation, sender, domain, payment and data-request evidence |
| A risk verdict | An explainable evidence report with missing information and next steps |

## Non-negotiable product rules

1. Absence of a scam record is **not** evidence of legitimacy.
2. A score is decision support, **not** a calibrated probability of fraud.
3. Missing evidence is reported as missing; checks that did not run are never shown as clean results.
4. External lookups are consent-gated and report `not_configured` / `not_attempted` honestly.
5. Submitted content and fetched pages are untrusted input.
6. Recruitment is a **supported special case**, never the default identity of the product.
7. Stable infrastructure identifiers inherited from the baseline (`hireshield` DB name, Compose project, Render hosts, seeded emails, Celery namespace, CI tags) are compatibility keys, **not** product branding. They must not appear in user-facing copy.

## User-facing language rules

- Default wording: **offer, advert, message, link, screenshot, claim, brand, sender**.
- Use “recruitment”, “job posting” or “recruiter” only inside the recruitment category or when describing the legacy model/data scope.
- Lead every primary CTA with a generic action: “Check an offer”, “Verify a link”, “Start a free investigation”.
- Never imply that a verified company automatically verifies a specific offer, campaign or sender.

## Implementation note

This concept is enforced by the active copy in `frontend/src/`, the API config identity `app_name=TrustLens AI`, and the scoped model documentation in `docs/ML.md`. Historical documents may mention the HireShield baseline only as implementation history; they are not the product definition.
