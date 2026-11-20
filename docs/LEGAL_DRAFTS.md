# TrustLens AI — Legal Documents (NON-LAWYER DRAFTS)

> ## MANDATORY NOTICE — READ FIRST
>
> **These are non-lawyer product drafts, not legal advice and not ready for publication or production use.** They were prepared to capture how the current software behaves and to give qualified counsel a starting point. They contain unresolved jurisdiction, entity, contact and policy placeholders. **A qualified lawyer licensed in the relevant jurisdiction(s) must review, revise and approve every document below before TrustLens AI is launched, sold, or offered to external users.**
>
> Draft date: 18 November 2026. Product behaviour reflected: the current repository only; no live production deployment, external API credentials or payment provider was configured at that time.

---

## Placeholders to resolve before counsel review

| Placeholder | Meaning |
| --- | --- |
| `[CONTROLLER LEGAL NAME]` | Legal entity acting as data controller / service provider. |
| `[JURISDICTION]` / `[GOVERNING LAW]` | Governing law and courts for customer terms. |
| `[DATA JURISDICTION]` | Country/region where data is stored and processed. |
| `[EFFECTIVE DATE]` / `[VERSION]` | Publication and version control. |
| `[PRIVACY CONTACT]` / `[DPO CONTACT]` / `[SUPPORT CONTACT]` | Monitored contact channels. |
| `[REGULATOR / AUTHORITY]` | Relevant data-protection or consumer authority. |
| `[PROCESSOR SUBPROCESSOR LIST]` | Current hosting, database, provider and payment subprocessors. |
| `[BREACH NOTIFICATION WINDOW]` | Contractually agreed notification period. |
| `[RETENTION SCHEDULE]` | Final, legally reviewed retention periods. The engineering defaults are 365 days for investigations and 730 for audit logs and are now enforced by [RETENTION.md](RETENTION.md), but counsel must approve the schedule before real data is processed. |
| `[COOKIE INVENTORY]` | Verified list of cookies/local storage keys and their purposes. |

---

## 1. Terms of Service — DRAFT

**Effective date:** `[EFFECTIVE DATE]` · **Version:** `[VERSION]` · **Governing law:** `[GOVERNING LAW]`

### 1.1 Nature of the service
TrustLens AI is a decision-support service that analyses job postings, recruiter messages, URLs, documents and company information and returns risk indicators, explanatory evidence and reports. It is not an employment agency, background-check bureau, credit-reference agency, legal adviser, fraud insurer, or guarantor of the legitimacy of any opportunity or person.

### 1.2 Eligibility and accounts
You must provide accurate account information and be authorised to submit the content you upload. Registration requires affirmative consent to the Privacy Policy and these Terms. You are responsible for credentials and activity under your account. Roles and administrative permissions are controlled by the service; attempting to obtain unauthorised roles is prohibited.

### 1.3 Consent to external lookups
External public-source and registry lookups are performed only when you enable the relevant consent control. Declining limits the analysis to local techniques. Sources attempted and sources succeeded are recorded in the report. Corporate-registry verification requires a separate consent and a licensed data source.

### 1.4 Plans, billing and cancellation
Plans, prices and scan limits displayed in the application come from the live plan service. Payments are processed by the configured payment provider; the application does not store card details. Paid access is activated only after the provider sends a verified payment event to the service; a browser redirect alone does not activate a paid plan. Cancellation requests set a flag, with status changes still driven by provider events. Renewal, refund, tax and invoice terms must be inserted by counsel and aligned with the provider configuration: `[PAYMENT TERMS TO BE INSERTED]`.

### 1.5 User content and feedback
You retain rights in content you submit. You grant TrustLens AI a limited licence to process it to provide the service, maintain history and review corrections, subject to the Privacy Policy. You may submit a correction or report about an assessment; the service records it as pending review and does not promise a particular outcome or response time.

### 1.6 Suspension and termination
We may suspend or terminate access for breach of the Acceptable Use policy, unlawful submissions, security risk, non-payment, or where required by law. `[TERMINATION NOTICE AND APPEAL TERMS TO BE INSERTED BY COUNSEL]`.

### 1.7 Limitation of liability
To the maximum extent permitted by law, TrustLens AI and its contributors are not liable for decisions you make, losses arising from fraud, or indirect or consequential damages. Nothing excludes liability that cannot lawfully be excluded. `[FINAL LIABILITY LANGUAGE REQUIRED FROM COUNSEL]`.

### 1.8 Governing law
These terms are governed by `[GOVERNING LAW]`, with exclusive jurisdiction in `[JURISDICTION]`, subject to any mandatory consumer protections.

---

## 2. Privacy Policy — DRAFT

**Effective date:** `[EFFECTIVE DATE]` · **Controller:** `[CONTROLLER LEGAL NAME]` · **Contact:** `[PRIVACY CONTACT]`

### 2.1 Categories of personal data processed
Based on current code behaviour:

* **Account data:** name, email, organisation, role, preferences, email-verification state, authentication tokens (stored client-side in `localStorage`) and password hashes (server-side, Argon2).
* **Submitted content:** job descriptions, messages, URLs, uploaded PDFs/images/text, and extracted entities such as names, emails, phone numbers, salary and payment demands.
* **Assessment data:** indicators, model predictions, component scores, risk category, source status, missing evidence, technical limitations, reports and generated PDFs.
* **Operational data:** monitoring rules, notifications, audit logs, task records, API usage counters, payment events and correction reports.

### 2.2 Purposes
The service uses this data to provide and secure analysis, corroborate signals with consent, maintain investigation history and entitlements, send configured notifications, troubleshoot, review corrections and compute aggregate, de-identified quality metrics.

### 2.3 Legal bases — **counsel must complete**
`[LEGAL BASIS FOR CONTRACT PERFORMANCE]`, `[LEGAL BASIS FOR LEGITIMATE INTERESTS]`, `[LEGAL BASIS FOR CONSENT]`, `[LEGAL BASIS FOR LEGAL OBLIGATIONS]`. Consent for external lookups is technically separate from the registration consent; counsel should confirm whether it also satisfies the applicable legal basis.

### 2.4 External sources and consent
External lookups are off unless you enable `consent_external_lookups`; corporate-registry lookup has a separate `consent_corporate_registry_lookup` gate. Optional providers include commercial domain reputation, Google Web Risk (the commercial alternative to non-commercial Safe Browsing v4), and a licensed corporate-registry intermediary. Provider identities and their privacy terms belong in `[PROCESSOR SUBPROCESSOR LIST]`.

### 2.5 Retention and deletion
Configuration defines `RETENTION_DAYS=365` and `AUDIT_RETENTION_DAYS=730`, and Stage 8 implemented automated enforcement with shorter caps for support chats (30 days), notifications (180), domain cache (30) and task status (7). See [RETENTION.md](RETENTION.md). These are **engineering defaults, not a legally approved schedule**; the final `[RETENTION SCHEDULE]` must still be reviewed. The current API has no self-service export or deletion endpoints; data-subject requests must be handled through `[PRIVACY CONTACT]` until such functionality exists. A correction can be requested from a report.

### 2.6 Security
Access uses short-lived bearer tokens with refresh and revocation, role-based admin controls, upload validation, SSRF protections and security headers. No system can guarantee absolute security; suspected compromise should be reported to `[SUPPORT CONTACT]`.

### 2.7 Transfers, sharing and rights
Data location is `[DATA JURISDICTION]`. Transfers, processors and international transfer mechanisms must be listed by counsel. Data-subject rights (access, correction, deletion, portability, objection, withdrawal of consent) and the procedure to exercise them are `[RIGHTS AND PROCEDURE TO BE INSERTED]`, including complaint rights before `[REGULATOR / AUTHORITY]`.

### 2.8 Children and students
The service is not intended for children under `[AGE THRESHOLD]`. Student and university use requires an institutional agreement and consent design reviewed by counsel.

---

## 3. Data Processing Agreement (DPA) — DRAFT

**Between:** `[CONTROLLER LEGAL NAME]` and the customer entity identified in an order form. **Effective:** `[EFFECTIVE DATE]`.

### 3.1 Roles and scope
Where the customer determines the purposes of processing submitted recruitment content, the customer is the controller and TrustLens AI is the processor. Where TrustLens AI determines purposes such as security, fraud prevention and aggregate quality measurement, it may act as an independent controller for those limited purposes; counsel must confirm this split.

### 3.2 Instructions
The processor handles personal data only to provide the service, comply with law and documented customer instructions. External lookups occur only with the relevant user consent. Product changes that materially affect processing require notice: `[CHANGE NOTIFICATION TERMS]`.

### 3.3 Confidentiality and security
Personnel with access are bound by confidentiality. Technical and organisational measures include Argon2 password hashing, token revocation, RBAC, HTTPS/TLS at the deployment boundary, input validation, SSRF protections, audit logging and access scoping. Additional measures required by contract: `[SECURITY SCHEDULE]`.

### 3.4 Subprocessors
Current subprocessors to be enumerated: hosting, MongoDB provider, Redis/cache provider, email/SMS provider (if configured), domain/registry and threat-intelligence providers, and payment provider. List: `[PROCESSOR SUBPROCESSOR LIST]`. Notice/objection mechanics: `[SUBPROCESSOR NOTICE TERMS]`.

### 3.5 Assistance, breaches and audit
The processor will assist with data-subject requests and security inquiries, notify the controller of a confirmed personal-data breach within `[BREACH NOTIFICATION WINDOW]`, and provide audit information on reasonable notice: `[AUDIT TERMS]`.

### 3.6 Deletion and return
On termination, data is returned or deleted in accordance with `[RETENTION SCHEDULE]` and legal retention requirements. An automated purge exists but its periods require legal approval; that approval is a launch prerequisite.

### 3.7 Liability
`[DPA LIABILITY / INDEMNITY TERMS REQUIRED FROM COUNSEL]`.

---

## 4. Acceptable Use Policy — DRAFT

You must not:

* submit content you are not entitled to analyse, or content containing passwords, one-time codes, full financial credentials or highly sensitive personal data;
* use outputs to harass, defame, discriminate against, or make automated employment decisions about individuals;
* rely solely on a score to deny an opportunity, accuse a person, or take legal action without independent verification and human review;
* attempt to circumvent authentication, role checks, rate limits, upload validation, sandboxing or audit controls;
* reverse engineer models, extract artifacts, or probe the service for bulk data scraping;
* use the service to build profiles of individuals unrelated to recruitment-fraud prevention;
* configure monitoring to fetch unapproved sources or use licensed registry/threat data outside its licence;
* introduce malware, automate abusive submissions, or interfere with service availability.

Violations may result in suspension or termination and, where required, reporting to `[REGULATOR / AUTHORITY]`. `[ENFORCEMENT AND APPEAL PROCESS TO BE INSERTED]`.

---

## 5. Cookie and Consent Notice — DRAFT

> **Current implementation note:** the frontend stores `trustlens.access_token`, `trustlens.refresh_token` and `trustlens.user` in browser `localStorage`. No analytics or advertising cookies were found in the code. Verify the final deployment before publishing a cookie table: `[COOKIE INVENTORY]`.

### 5.1 Consent captured by the product
| Control | Where | Effect |
| --- | --- | --- |
| Privacy policy and terms consent | Registration (`consent_privacy`, `consent_terms`) | Both are required; registration is rejected if either is false. |
| External lookups | Job/message/URL/document analysis and company verification (`consent_external_lookups`) | When false, external URL/domain/company lookups are not attempted. |
| Corporate registry lookup | Company verification (`consent_corporate_registry_lookup`) | Separate gate; no registry request is made without it. |

### 5.2 Managing choices
Users can decline external lookups per submission, avoid submitting unnecessary personal data, and manage notification/theme/monitoring preferences in Settings. Withdrawal of consent does not retroactively change a completed assessment; correction requests can be submitted from a report. `[COOKIE WITHDRAWAL MECHANISM, IF ANY]`.

### 5.3 Notice
We use strictly necessary client storage to keep you signed in and remember preferences. `[INSERT COOKIE TABLE ONLY IF ADDITIONAL STORAGE IS ADDED]`.

---

## 6. Disclaimers — DRAFT

1. **No guarantee.** Risk scores, categories, model predictions and indicators are probabilistic and can be wrong. A low score does not mean an employer, message or opportunity is legitimate. An inconclusive result means available evidence was insufficient.
2. **Approved model limits.** The two approved models are English-language, text-only classifiers trained on the EMSCAD corpus. Their reported ROC-AUC is high (0.9891 / 0.9914) while precision is 0.375 / 0.4595. Message and anomaly models are rejected and the system uses explicit rule fallbacks. Sigmoid-mapped scores and `confidence` values are not calibrated probabilities.
3. **Not a background check or legal advice.** The service does not verify identity, employment history, creditworthiness or criminal records, and does not provide legal conclusions.
4. **Third-party information.** Domain, reputation and registry results depend on external providers and licensed intermediaries; availability, accuracy and licence restrictions vary. Unconfigured sources are reported as unavailable.
5. **Human review required.** Do not pay fees, share OTPs or banking credentials, or make adverse decisions based solely on a TrustLens result.
6. **No service guarantee.** `[SLA / AVAILABILITY LANGUAGE TO BE INSERTED]`. The current repository does not evidence a production uptime commitment.

---

## 7. Takedown and Correction Workflow — DRAFT

### 7.1 What exists today
From any report, a user can submit feedback with type `false_positive`, `missed_fraud`, `identity_correction` or `other`, plus details and an optional evidence URL. The API stores it with status `pending_review`. An administrator can update report review state through the admin report endpoint. No public takedown endpoint, reviewer SLA, identity-verification step or appeal mechanism was found in the code.

### 7.2 Proposed workflow (requires product implementation and counsel approval)
1. **Receive** a correction or takedown request via the report feedback form or `[PRIVACY CONTACT]`.
2. **Log** the request, timestamp, requester, affected analysis and claimed error; preserve the original assessment and evidence for audit.
3. **Verify** the requester's relationship to the content using `[IDENTITY VERIFICATION PROCEDURE]`.
4. **Review** against the stored indicators, source statuses and model limitations; do not treat a user assertion as proof.
5. **Decide:** keep the assessment, annotate it, update evidence logic/models, or restrict access where lawful. Record the reason.
6. **Respond** within `[RESPONSE SLA]`; inform the requester of the outcome and any appeal route.
7. **Appeal** to `[APPEAL CONTACT / BODY]` within `[APPEAL WINDOW]`.
8. **Retain** decision records per `[RETENTION SCHEDULE]`; report aggregate correction rates for quality monitoring.

### 7.3 Legal coordination
Requests involving alleged defamation, privacy breaches, regulated data or law-enforcement demands must be escalated to `[LEGAL CONTACT]` before action. Nothing in this drafts section creates a contractual promise of removal or a specific outcome.

---

## MANDATORY FINAL REVIEW STATEMENT

**These documents must not be published or relied upon as-is.** Before any production or commercial use, qualified legal counsel licensed in `[JURISDICTION]` (and any other applicable market) must review and approve the Terms, Privacy Policy, DPA, Acceptable Use Policy, cookie/consent notice, disclaimers and correction workflow; fill every placeholder; confirm regulatory obligations (including `[REGULATOR / AUTHORITY]` requirements); and align all statements with the deployed system. Product, security and operations owners must then verify that the deployed behaviour matches the approved text.
