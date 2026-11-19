# HireShield AI — Commercial Brief

**Status:** product and commercial planning draft, based strictly on the current code and seeded configuration.
**Evidence date:** 18 November 2026. No external API credentials, payment providers or production deployment are configured.

---

## 1. Product in one paragraph

HireShield AI is a commercial SaaS platform that screens recruitment content (job posts, messages, URLs and documents) and companies for fraud indicators. It returns an explainable 0–100 risk band, the evidence behind it, the sources attempted and succeeded, explicit limitations, and a downloadable report. External corroboration is consent-gated; unconfigured providers are reported as unavailable rather than simulated. Risk scores are decision support, not determinations of legitimacy.

---

## 2. Target segments

| Segment | Buyer / user | Evidence-backed need | Product fit in current code |
| --- | --- | --- | --- |
| Individual job seekers | Self-serve users on `free`, `student`, `professional` | Screen suspicious postings and recruiter messages before paying fees or sharing documents. | Job/message/URL/document analysis, risk bands, recommended actions, PDF reports. |
| Students and recent graduates | Students, career cells, individual students | Affordable protection during high-volume applications. | `student` plan with higher scan limits, PDF reports, job monitoring and email alerts. Email delivery requires SMTP configuration. |
| Recruiters and employers | Fraud/risk teams, talent leaders | Protect brand and candidates from impersonation and fake postings. | Company verification, domain intelligence, monitoring, historical/anomaly checks, admin analytics. |
| Universities and placement cells | Institutional buyers, staff administrators | Verify employers and protect students at scale. | `university` plan features: organisation accounts, bulk verification, staff accounts, institutional reports, centralised monitoring. |
| Enterprises / platforms | Security, trust & safety, compliance teams | Organisation-wide monitoring and custom deployment. | `enterprise` plan lists custom limits, API access, organisation-wide monitoring, role-based administration and custom reporting. **Gap:** no separate API-key/API-product implementation was found; REST endpoints exist but “API access” is currently a plan descriptor, not a distinct shipped feature. |
| Partners / channels | Job boards, placement platforms, licensed data providers | Add fraud screening to existing workflows. | Webhook-only billing model and admin-configurable plans support partner packaging; no partner portal or reseller API exists yet. |

---

## 3. Value propositions

1. **Explainability over black boxes.** Six weighted components, named indicators, source provenance and an explicit `inconclusive` state. Missing evidence is never reported as a clean domain or company.
2. **Consent-first corroboration.** `consent_external_lookups` gates external URL/domain/company work; `consent_corporate_registry_lookup` is a separate gate on company verification. Sources attempted and succeeded are recorded in the report.
3. **Evidence-backed deliverables.** JSON and PDF reports with risk, indicators, model predictions, limitations, recommended actions and missing evidence; CSV export for administrators.
4. **Operational honesty.** Unconfigured integrations return `not_configured`; checkout without provider configuration returns `503`; paid access only follows verified webhooks.
5. **Deployable architecture.** Docker Compose stack, CI checks, model manifest governance and admin controls reduce the engineering lift for institutional deployments.

---

## 4. Plan matrix (from `backend/app/services/plan_service.py`)

Plans are seeded into MongoDB by `PlanService.default_plans()` when absent, then editable via the plans collection / `PATCH /api/v1/admin/plans/{code}`. Amounts are stored in **paise**; currency comes from `PAYMENT_CURRENCY` and defaults to **INR**.

| Code | Name | Description | Monthly (paise / INR) | Yearly (paise / INR) | Scan limit | Features | Active | Popular |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| `free` | Free | Basic screening for individual job seekers. | 0 / ₹0 | 0 / ₹0 | 10 | Basic job analysis; Basic message analysis; Standard risk report | Yes | No |
| `student` | Student | Affordable protection for students and recent graduates. | 9,900 / ₹99 | 99,000 / ₹990 | 100 | Higher scan limits; PDF reports; Job monitoring; Email alerts | Yes | Yes |
| `professional` | Professional | Advanced investigation for active job seekers and recruiters. | 29,900 / ₹299 | 299,000 / ₹2,990 | 500 | Advanced domain intelligence; Detailed reports; Multiple monitored companies; Advanced analytics | Yes | No |
| `university` | University | Placement-cell and institutional verification workspace. | 99,900 / ₹999 | 999,000 / ₹9,990 | 5,000 | Organization accounts; Bulk verification; Staff accounts; Institutional reports; Centralized monitoring | Yes | No |
| `enterprise` | Enterprise | Custom deployment, API access and organisation-wide monitoring. | 0 / ₹0 | 0 / ₹0 | 100,000 | Custom limits; API access; Organization-wide monitoring; Role-based administration; Custom reporting | Yes | No |

Scan limits are also configurable through `FREE_SCAN_LIMIT`, `STUDENT_SCAN_LIMIT`, `PROFESSIONAL_SCAN_LIMIT`, `UNIVERSITY_SCAN_LIMIT` and `ENTERPRISE_SCAN_LIMIT` (defaults `10 / 100 / 500 / 5000 / 100000`). `PlanService.can_scan()` denies scans once usage reaches the limit; `consume_scan()` increments usage after a completed analysis.

**Billing behaviour that affects packaging:**

* `PaymentService.create_checkout()` rejects plans with amount `<= 0`, so `free` and `enterprise` do not open an online checkout; enterprise pricing is effectively sales-negotiated/offline.
* Checkout is available for `razorpay` or `stripe` only when configured; otherwise the API returns `503 not configured`.
* With Razorpay configured, the browser opens the official Checkout script using a server-created order; no paid access is granted from the checkout handler or success/cancel redirects, only HMAC-verified webhooks update subscriptions.
* Prices are **seed defaults present in code, not market-validated price points**. They can be changed by an administrator without a code release.

---

## 5. Pricing guidance (recommendations, not implemented behaviour)

The code contains prices, so the following is guidance on how to use them commercially:

* Keep `free` as an acquisition tier with a hard 10-scan limit; it is adequate for a first suspicious posting but not for ongoing monitoring.
* Position `student` as the high-volume self-serve tier (₹99 monthly / ₹990 yearly seeded); it is the only plan flagged `popular` in code.
* Position `professional` for active job seekers and recruiters (₹299 monthly / ₹2,990 yearly seeded) and gate it on advanced domain intelligence and monitoring depth.
* Treat `university` (₹999 monthly / ₹9,990 yearly seeded) as an institutional landing tier with seat/staff and reporting value, not merely a scan bundle.
* Keep `enterprise` at zero online price and sell it through contracts; scope custom deployment, organisation-wide monitoring and any API access explicitly in the agreement.
* Validate annual pricing, taxes, refund policy, currency support and provider fees before launch; the code stores amounts only and contains no tax or discount engine.
* Before charging, configure the provider and webhook secrets, verify webhook delivery, and reconcile plan changes against the `payments` collection. For Razorpay, follow [RAZORPAY_SETUP.md](RAZORPAY_SETUP.md); merchant PAN/KYC and tax settings remain in the Razorpay dashboard.

---

## 6. Go-to-market motion (recommendations)

1. **Self-serve / PLG:** landing page → free account → first job or message scan → PDF report → upgrade prompt at the 10-scan limit. The current UI already exposes plans, checkout and subscription state.
2. **Campus and university channel:** pilot with placement cells using the `university` plan feature set (staff accounts, bulk verification, centralised monitoring). Require counsel-reviewed data-sharing terms and consent flows before handling student data.
3. **Employer / recruiter channel:** sell brand-protection and candidate-assurance workflows around company verification and monitoring; emphasise that outputs are advisory and require human review.
4. **Job-board and marketplace partnerships:** propose embedded screening using allow-listed job sources; note that no partner API or embed widget has been implemented.
5. **Licensed data partners:** contract a corporate-registry intermediary (MCA has no official public API) and a commercial URL reputation source (Google Web Risk rather than non-commercial Safe Browsing v4 for commercial use).
6. **Content and trust:** publish explainers on recruitment-fraud patterns, consent and report interpretation. Avoid claims of guaranteed detection; use the manifest's actual metrics only with their limitations.

No customer acquisition activity, conversion tracking or partner agreements are evidenced in this repository.

---

## 7. Unit economics inputs

Known from code/configuration:

| Input | Current value / behaviour |
| --- | --- |
| Plan prices | Seeded values in the plan matrix above; admin-editable; INR default. |
| Scan entitlement | 10 / 100 / 500 / 5,000 / 100,000 per plan; enforced on completed analyses. |
| Model inference | Local `joblib` artifacts; no per-call paid model API in the approved path. |
| External lookups | RDAP/DNS/TLS free-by-configuration; VirusTotal/Web Risk/MCA/registry fees are provider- and quota-dependent and currently unconfigured. |
| Storage | MongoDB documents, reports (PDF stored as base64), audit and payment events; `RETENTION_DAYS=365`, `AUDIT_RETENTION_DAYS=730` are configured but no purge job was found. |
| Delivery | Email/SMS skipped unless SMTP/SMS providers are configured. |
| Payment fees | Provider-dependent; not modelled in code. |

Missing inputs required before a credible unit-economics model:

* gross margin per paid scan after external lookup and infrastructure cost;
* infrastructure cost per active user and per 1,000 scans (Mongo, Redis, workers, bandwidth);
* CAC by channel, free→paid conversion, monthly churn, annual prepay mix;
* support and manual correction-review cost per report;
* refund/chargeback rate and provider fee schedule;
* partner/revenue-share terms and licensed data quotas;
* security/compliance cost allocation and institutional deployment effort.

Use the simple model: `contribution per account = realised plan revenue − (scans × variable cost per scan) − support/compliance allocation − payment fees`, then divide CAC by contribution to estimate payback. Do not populate it with invented cost assumptions.

---

## 8. Compliance considerations

* **Consent and disclosure:** two explicit consent flags exist; privacy/terms consent is mandatory at registration. Draft policy pages disclose processing, external lookups, retention, security and correction requests but require counsel review.
* **Purpose limitation:** the service is fraud-risk decision support. Draft terms prohibit automated employment decisions about individuals, harassment and discriminatory use; this must be enforced in customer contracts and product controls.
* **Data protection:** account data, submitted content, extracted entities, reports, monitoring rules, notifications, billing state and correction reports are processed. No self-service export/deletion endpoints exist; retention values are not yet enforced by a job. Confirm controller/processor roles, cross-border transfers and data-subject request handling under applicable law (for example India DPDP and/or GDPR depending on market).
* **Provider terms:** Safe Browsing v4 is non-commercial; commercial launch should use Web Risk. MCA has no official public API; use a licensed intermediary with the required consent. Document each provider's retention and redistribution terms.
* **Billing compliance:** card data is not stored by the app; provider checkout and verified webhooks handle payment state. Taxes, invoicing, refunds and cancellation disclosure need implementable policy and provider configuration.
* **Claims and liability:** avoid “detects all fraud” language. Approved models are English-language and text-only; high ROC-AUC coexists with modest precision. Draft disclaimers and limitation-of-liability clauses require counsel review.

---

## 9. Sales and partner motion

| Motion | Current enablers | Requirements before sale |
| --- | --- | --- |
| Self-serve subscription | Plans, live Razorpay/Stripe checkout integration, scan limits, subscription API. | Configure Razorpay/Stripe credentials, webhook endpoint, tax/refund policy, production secrets and monitoring. |
| University / institution | University plan features, RBAC, monitoring, admin dashboard. | Signed DPA, consent architecture review, data residency/retention decisions, staff onboarding, support SLA. |
| Enterprise custom | Enterprise plan descriptor, Compose deployment, audit/config admin endpoints. | Define and implement “API access” deliverable, SSO/host allow-list/TLS, deployment runbook, security review, contract SLA. |
| Data/registry partner | `MCA_API_URL`/`MCA_API_KEY` integration point and separate consent gate. | Licensed intermediary contract, lawful basis/consent design, quota and cost model. |
| Job-board/channel | Allow-listed job source configuration and monitoring tasks. | Partner API/embed work, source agreements, abuse controls and attribution. |

---

## 10. Key commercial risks

1. **Trust risk from false positives/negatives:** approved job models have 0.375 / 0.459 precision; message/anomaly outputs are rule fallbacks. Overstating accuracy would damage credibility.
2. **Coverage risk:** without configured external feeds, many assessments are inconclusive; customer value depends on licenses for commercial threat and registry data.
3. **Legal/regulatory risk:** unreviewed legal drafts, unresolved data-subject tooling, retention settings without enforcement, and jurisdictional placeholders.
4. **Payment readiness risk:** only Razorpay test keys are configured locally and the webhook secret is not yet registered in the dashboard; no live provider or signed activation drill exists. A “success” callback cannot and must not activate paid access.
5. **Feature-expectation risk:** enterprise plan text promises API access and organisation-wide capabilities that are not all implemented as distinct products.
6. **Security/operational risk:** development defaults, in-process rate limiting, no production secrets/host configuration, no backup/restore or incident process.
7. **Cost risk:** unbounded external lookups or monitoring could erode margin; quotas, caching and per-plan cost controls are not implemented.
8. **Market risk:** pricing and segment demand are assumptions from code seed data, not validated customer research.
