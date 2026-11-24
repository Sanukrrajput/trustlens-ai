# TrustLens AI — Local End-to-End Verification

**Verification date:** 2026-11-20

**Final evidence generated:** `2026-11-20T08:49:58.788151+00:00`

**Scope:** local functional verification of the final working tree before deployment

**Overall result:** **15 PASS, 1 PARTIAL, 0 FAIL** across the 16 requested capability areas.

**Deployment status:** **not deployed, not pushed.** Offer-first copy was finalised before the last test/E2E rerun; no deployment or push was performed.

---

## 1. Verification environment

The harness ran outside the repository so that working code and committed configuration were not altered.

| Setting | Value used |
|---|---|
| Database | `mongomock://` (in-memory MongoDB test double) |
| Celery | disabled (`CELERY_ENABLED=false`) |
| Task execution | eager (`TASK_ALWAYS_EAGER=true`) |
| Demo seeding | enabled with clearly labelled synthetic local accounts |
| JWT signing key | test-only value, never a production secret |
| External credentials | explicitly cleared to empty strings |
| External lookups | `RDAP_ENABLED=false`, `DNS_ENABLED=false`, `TLS_ENABLED=false` |
| Turnstile | disabled / reported `not_configured` |
| Test identities | synthetic `example.com` accounts only |
| Test URLs/domains | synthetic `*.example.test` values only |
| Real websites contacted | **none** |
| Real personal information | **none** |
| Production secrets exposed | **none** |

The public `/api/v1/system/config` endpoint reported `app_name = "TrustLens AI"` and all integration flags as `false`:

```text
virustotal=false, google_safe_browsing=false, google_web_risk=false,
mca_registry=false, rdap=false, dns=false, tls=false, smtp=false,
sms=false, razorpay=false, stripe=false, approved_job_sources=false,
cloudflare_turnstile=false
```

This is the honest unconfigured state. Unconfigured providers were not treated as clean evidence.

---

## 2. Method and evidence sources

The verification used the real FastAPI application, real route handlers, real security dependencies and real services wherever they are local. Only three areas used explicitly labelled local stubs:

1. `SafeURLFetcher.fetch` and `DomainAnalyser.analyse` for the URL **success** path.
2. `ocr_module.tesseract_available` and `pytesseract.image_to_string` for the OCR **success** path.
3. Chrome DOM/API behaviour via a Node harness, because a real browser installation was not used.

The URL **failure** path used the real `SafeURLFetcher` SSRF validation against loopback port 9. No connection was made to a real website.

Evidence files:

- `C:\Users\LENOVO\AppData\Local\Temp\opencode\e2e_harness.py`
- `C:\Users\LENOVO\AppData\Local\Temp\opencode\e2e_extension_harness.mjs`
- `C:\Users\LENOVO\AppData\Local\Temp\opencode\e2e_evidence.json`

Supporting suite results:

| Check | Result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest backend/tests -q --tb=line` | **115 passed** |
| Frontend `npm test -- --run` | **7 test files, 29 tests passed** |
| Browser extension `npm test` | **6 tests passed, 0 failed** |
| Standalone E2E harness | **15 PASS, 1 PARTIAL, 0 FAIL** |
| Production frontend build | passed |
| `docker compose config --quiet` | passed |
| `compileall` | passed |
| Ruff | passed |
| Secret scan | `ok`, 300 tracked files scanned |
| `pip check` | passed |
| `npm ls --omit=dev` | passed |
| `pip-audit` | 0 vulnerabilities |
| `npm audit` | 0 vulnerabilities |
| CI YAML parse | passed |

Container image builds were not run locally because the Docker daemon was unavailable; CI performs both builds.

### 2.1 Offer-first product and DIFrauD model checks

These checks sit outside the 16 harness features but were part of the final working-tree verification.

| Check | Result |
|---|---|
| Canonical product concept | `TRUSTLENS_CONCEPT.md` is the single source of truth: TrustLens is an offer-first verification product; recruitment is one category, not the product's identity. |
| Public naming | Public API reports `app_name = "TrustLens AI"`. Landing page title is `TrustLens AI — Verify before you act`; H1 is `Verify Before You Act. Decide With Evidence.` No user-facing `HireShield` text was found. `hireshield` remains only a compatibility database key/hostname. |
| Scanner default | Scanner UI defaults to the generic `offer` tab; recruitment is available as one category. |
| Live pricing copy | `/api/v1/billing/plans` and the rendered page show generic copy (`Basic screening for individual users.`, `Basic offer analysis`, `Offer monitoring`, `Multiple monitored entities`, `Institutional verification workspace.`). The stale job-centric plan strings were removed. |
| Browser spot-check | A cache-busted reload of the local Vite server (`http://127.0.0.1:5174/`; port `5173` was already occupied by an unrelated local dev server) after the final backend restart showed 0 console errors and 0 failed/4xx/5xx requests. `/health` returned `200`. |
| DIFrauD source handling | Dataset source is `https://huggingface.co/datasets/difraud/difraud` (MIT, revision marker `main`). Raw JSONL remains under gitignored `backend/data/datasets/difraud/` and was not committed. Obvious direct identifiers are redacted before training. No Hugging Face/Transformers/Torch dependency was added. |
| DIFrauD provenance | Loader emits `real_world_data=true` and `production_grade=false`; `docs/ML.md` documents limitations, family metrics and approval gates. |
| Model manifest | `backend/models/model_manifest.json` version `v20261120T083930Z-f6e8b1`. Approved families: `job_tfidf_logreg`, `job_tfidf_linearsvc`, `message_difraud_logreg`, `job_difraud_logreg`. Rejected: `message_tfidf_logreg`, `anomaly_iforest`, `anomaly_supervised`; their local artifacts are gitignored and must not be released. |
| Runtime model selection | Runtime predictor selected `job_model=job_difraud_logreg`, `message_model=message_difraud_logreg`, `offer_model=offer_rule_fallback`. All four approved artifacts load. DIFrauD models are preferred only when approved and loadable; fallbacks and approval gates remain intact. Generic offers remain rule-only and do not reuse recruitment text models. |

DIFrauD held-out metrics (from `docs/ML.md`, not a marketing claim):

| Family | Support | ROC-AUC | Recall | Precision | Error rate |
|---|---:|---:|---:|---:|---:|
| Message DIFrauD | 1,927 | 0.9943 | 1.0000 | 0.5390 | FPR 0.3746 |
| Job DIFrauD | 1,410 | 0.9401 | 0.7931 | 0.3239 | FNR 0.2069 |

---

## 3. Feature-by-feature results

### 1. Registration, login, refresh and logout — **PASS**

**Procedure:** Registered a synthetic user, logged in, read the authenticated profile, refreshed the token, logged out and retried the authenticated profile call.

**Actual result:**

- Registration returned `201`.
- Login returned `200`.
- `GET /auth/me` returned `200` before logout.
- Refresh returned `200`.
- Logout returned `200`.
- `GET /auth/me` after logout returned `401`, confirming logout revokes the access session.

**Failure path verified:** a logged-out token is rejected.

**Evidence:** account `e2e-auth-6e64413e@example.com`; statuses `201 / 200 / 200 / 200 / 200 / 401`.

**Limitations:** password-reset and email-verification token flows were not exercised in this run.

---

### 2. Suspicious offer text analysis — **PASS**

**Procedure:** Submitted a synthetic recruitment offer containing fee, OTP/account and urgency language with external consent disabled.

**Actual result:**

- Analysis `6b0009b7185e6d4906c3fa29` completed.
- Risk score **67**, category **High risk**.
- Canonical indicators: `payment_demand`, `sensitive_data_request`, `urgency_pressure`, `brand_campaign_not_verified`, `shared_infrastructure`.
- Five-category weights were applied: `content 0.30`, `url 0.25`, `brand 0.25`, `threat 0.10`, `community 0.10`.
- Seven missing-evidence entries were recorded.

**Evidence:** analysis ID above; 5/5 feature checks passed.

**Limitations:** text rules are observations, not proof of fraud. No external lookup was performed without consent.

---

### 3. URL workflow and SSRF-blocked failure — **PASS**

**Procedure:**

- Success path: labelled local stubs returned a safe synthetic fetch result and provenance-wrapped domain fact for `https://offers.example.test/careers/apply`.
- Failure path: the **real** `SafeURLFetcher` was called against `http://127.0.0.1:9/blocked`; `DomainAnalyser` was stubbed only after the block so no external lookup would occur.

**Actual result:**

- Stubbed success analysis `6b0009b8185e6d4906c3fa36` completed.
- `safe_url_fetch` evidence source status was `succeeded`.
- The provenance-wrapped domain fact was preserved: `domain_age_days = 120`, source `local_stub`, confidence `0.8`.
- Real fetch result status was `blocked` with error `port 9 is not in the allowed port list`.
- The API analysis recorded the `safe_url_fetch` source as `blocked` and still returned a structured assessment.
- The blocked result was explicitly **inconclusive**, with data coverage `0.3`, six missing-evidence entries and the summary: “This score must not be read as reassurance about the legitimacy of the offer.”

**Failure path verified:** loopback and disallowed ports are blocked before any network connection.

**Evidence:** analysis IDs `6b0009b8185e6d4906c3fa36` (success) and `6b0009b8185e6d4906c3fa39` (blocked); 7/7 checks passed.

**Limitations:**

- Success path used labelled stubs; no real URL was fetched.
- The blocked analysis displayed category text `Low observed risk`, but simultaneously set `inconclusive=true` and warned against reading it as reassurance. This presentation should be improved before launch (see Section 4).

---

### 4. Image OCR and PDF document analysis — **PASS**

**Procedure:** Used a labelled OCR stub, uploaded a synthetic PNG through `/analysis/document`, and uploaded a generated PDF containing suspicious text.

**Actual result:**

- Direct OCR status `ok`.
- Extracted entities: `jobs@example.test`, `https://offers.example.test`, phone number.
- OCR indicators: `image_contact_details`, `image_credential_request`, `image_payment_request`, each labelled as observations rather than proof.
- Image analysis `6b0009b8185e6d4906c3fa42` completed with `image_intelligence.status = ok`.
- PDF analysis `6b0009b8185e6d4906c3fa4a` completed and extracted the payment-demand sentence from the PDF.

**Evidence:** 8/8 checks passed.

**Limitations:** OCR success was produced by a labelled monkeypatch of `tesseract_available` and `pytesseract.image_to_string`; no OCR binary or real image was used.

---

### 5. OCR-not-configured handling — **PASS**

**Procedure:** Forced `tesseract_available=false` and exercised both direct OCR and the document upload API.

**Actual result:**

- Direct OCR status `not_configured`.
- Extracted text was empty; no image content was invented.
- Limitation: “Local OCR is not configured: no tesseract binary is available. No text was extracted from the image; do not treat the image as verified.”
- Indicator `image_ocr_unavailable` had status `technical_limitation`.
- API analysis `6b0009b9185e6d4906c3fa56` preserved `image_intelligence.status = not_configured`.
- Missing evidence recorded: “No text could be extracted from the submitted image; visual content was not verified.”

**Failure path verified:** unavailable OCR is reported honestly and does not become a clean or confident result.

**Evidence:** 6/6 checks passed.

**Limitations:** the unavailable state was forced locally to represent a deployment without a tesseract binary.

---

### 6. Brand and company verification — **PASS**

**Procedure:** Called `/company/verify` without consent, then exercised `BrandVerifier` with trusted official evidence and with user-supplied advert evidence.

**Actual result:**

- API company `Example Technologies` returned `verification_status = not_attempted` and `website.status = not_attempted` because consent was not provided.
- Trusted official-channel evidence produced `verified_official_campaign` with `campaign_verified = true`.
- User-supplied advert evidence produced only `verified_company`; `campaign_verified = false`.
- Missing campaign-authorisation evidence was retained.

**Failure path verified:** a user-supplied advert cannot verify a specific campaign, and a verified company does not automatically verify an offer.

**Evidence:** 7/7 checks passed.

**Limitations:** the campaign checks were module-level calls with synthetic evidence; no live brand channel or registry was contacted.

---

### 7. Threat-indicator matching — **PASS**

**Procedure:** As admin, listed threat sources, imported one synthetic domain indicator, analysed a reference to that domain, and checked the no-match path.

**Actual result:**

- `operator_import` source was present.
- Import returned `200` with `ingested = 1`.
- Analysis `6b0009ba185e6d4906c3fa6e` reported `threat_intelligence.status = ok`.
- Match: `blocked-offer.example.test`, source `operator_import`, severity `0.7`, status `unverified`.
- Canonical analysis indicator `threat_feed_match` was recorded.
- The match description explicitly states it is decision support and not proof of wrongdoing.
- No-match status was `no_match` with: “Absence of a threat-indicator match does not establish legitimacy.”

**Failure path verified:** no match is not converted into a legitimacy claim.

**Evidence:** 9/9 checks passed.

**Limitations:** only the local operator-import store was checked; external feeds were unconfigured.

---

### 8. Evidence-based risk assessment — **PASS**

**Procedure:** Inspected the stored suspicious-offer result for weights, uncertainty, coverage, explanation, recommended actions and timestamped evidence sources.

**Actual result:**

- Score `67`, category `High risk`.
- Uncertainty `0.58`, data coverage `0.3`, `inconclusive = true`.
- Unavailable signals: `url`, `brand`, `threat`, `community`.
- Weights normalised to 1.0 across exactly the five configured categories.
- Summary: “Assessment is inconclusive because the available evidence covers only 30% of signal categories. This score must not be read as reassurance about the legitimacy of the offer.”
- Evidence summary listed model fallback outputs and suspicious indicators with severity/confidence.
- Recommended actions included collecting missing evidence, not transferring money or sharing OTPs, and escalating to a human reviewer.
- Seven timestamped evidence sources were recorded, each with `name`, `status`, `attempted_at` and `observed_at`.

**Evidence:** analysis `6b0009b7185e6d4906c3fa29`; 7/7 checks passed.

**Limitations:** the score is an explainable screening blend, not a calibrated fraud probability.

---

### 9. Missing and unavailable evidence — **PASS**

**Procedure:** Submitted a low-signal offer with no external consent and compared the result with public integration flags.

**Actual result:**

- Missing evidence included unavailable registry evidence, domain reputation, verified sender identity, campaign authorisation and independent community corroboration.
- Technical limitations included “External corroboration was not attempted by the orchestrator because consent was not provided.”
- Risk was `inconclusive = true`, coverage `0.3`, unavailable signals `url`, `brand`, `threat`, `community`.
- Domain intelligence status was `not_attempted`.
- All public integration flags were `false`.

**Failure path verified:** absent providers are reported as unavailable; they are never treated as clean evidence.

**Evidence:** analysis `6b0009ba185e6d4906c3fa7c`; 7/7 checks passed.

**Limitations:** none specific to this flow.

---

### 10. PDF and CSV reporting — **PASS**

**Procedure:** Downloaded the stored offer analysis as PDF and exported analyses as CSV as admin.

**Actual result:**

- Report metadata endpoint returned `200`.
- PDF endpoint returned `200`, magic bytes `%PDF-1.4`, size 9,717 bytes.
- Content type `application/pdf`.
- Content disposition `attachment; filename="trustlens-report-6b0009b7185e6d4906c3fa29.pdf"`.
- Admin CSV export returned `200` with header `analysis_id,created_at,analysis_type,risk_score,risk_category,inconclusive,indicator_count`.

**Evidence:** 5/5 checks passed.

**Limitations:** none specific to this flow.

---

### 11. History and ownership — **PASS**

**Procedure:** Listed, filtered and read analyses as the owner; attempted the same reads as a stranger; confirmed admin support access.

**Actual result:**

- Owner listing total `1`; type-filtered listing returned one offer.
- Owner detail returned `200`.
- Stranger detail returned `404` (non-disclosure).
- Stranger PDF download returned `403`.
- Stranger report read returned `403`.
- Admin detail returned `200`.

**Failure paths verified:** strangers cannot read another user’s analysis, report or PDF.

**Evidence:** 7/7 checks passed.

**Limitations:** admin/owner override is intentional and must be protected by production operator controls.

---

### 12. Community reporting and moderation — **PASS**

**Procedure:** Submitted a correction and a community allegation, checked duplicate handling, verified non-admin denial, moderated two independent reports as admin, observed a new analysis, and exercised the false-report path.

**Actual result:**

- Feedback stored with `category = correction`; duplicate correction returned the same ID with `duplicate = true`.
- Community allegation stored separately with `category = community`.
- Non-admin moderation attempt returned `403`.
- Admin verified the first report and the second independent report.
- New analysis showed `community_intelligence.status = corroborated`, `independent_reporters = 2`, `weighted_support = 1.0`.
- One indicator `community_independently_corroborated` was emitted with `independently_verified = false` and the caveat “not proof of fraud”.
- A single report on a different entity produced `insufficient_independent_reports`.
- False report without a reason returned `400`.
- False report with reason returned `status = dismissed`, `is_false_report = true`.
- Audit actions included `admin.report_verified`, `admin.report_reviewed` and `admin.report_marked_false`.

**Failure paths verified:** single reports never create a risk signal; non-admins cannot moderate; false reports require a reason.

**Evidence:** 15/15 checks passed.

**Limitations:** moderator verification is a review decision, not independent external corroboration.

---

### 13. Chrome extension explicit-click analysis — **PASS**

**Procedure:** Ran a Node DOM/Chrome-API harness against the real `popup.js` code to check the permission and submission lifecycle.

**Actual result:**

- No API fetch, permission request or script injection occurred before the explicit click.
- After the click: exactly one permission request for `http://127.0.0.1:8000/*`, one active-tab injection and one POST to `http://127.0.0.1:8000/analysis/offer`.
- POST body fields: `client_request_id`, `consent_external_lookups`, `offer_category`, `source_url`, `text`.
- `consent_external_lookups` was `false`.
- Rendered risk category from the local fixture was `High risk`.
- On permission denial, no page data was sent; the UI showed: “Access to the configured API origin was not granted. No page data was sent.”

**Failure path verified:** denial sends no page content.

**Evidence:** Node harness returned `status: pass` with 5/5 checks; repository extension suite also passed 6/6 tests.

**Limitations:** this was a Node harness, not a real Chrome installation. The API response was a local fixture; the contract under test was permission timing and request construction.

---

### 14. Retention and deletion — **PARTIAL**

**Procedure:** Triggered the admin retention task, ran the retention service directly with a short policy, checked disabled mode, and inspected exposed DELETE routes.

**Actual result:**

- Admin retention task endpoint returned `200` with task `app.workers.tasks.cleanup_retention`.
- Direct purge deleted 2 expired documents: 1 `fraud_analyses` and 1 `audit_logs`.
- Recent document with marker `e2e-keep` remained.
- Policy days were applied as configured: analyses 10 days, audit logs 5 days.
- `RETENTION_ENABLED=false` returned `status = disabled` with zero deletions.
- No DELETE route is exposed by the API (`delete_routes = []`).

**Failure paths verified:** disabled retention deletes nothing; only timestamp-bearing documents are eligible.

**Evidence:** 6/6 harness checks passed; verdict is PARTIAL because of the missing self-service deletion capability below.

**Limitations:**

- Configured retention purge deletion works against `mongomock`; production MongoDB TTL behaviour was not verified.
- **There is no self-service account/data deletion API in this build.** Deletion is limited to the configured retention purge and repository-level operations. This must be addressed before launch if a user-facing deletion/DSAR flow is required.
- The admin retention endpoint ran with Celery disabled/eager; no Redis or worker deployment was tested.

---

### 15. Backup verification and restore — **PASS**

**Procedure:** Created a logical backup of a mongomock database with two synthetic documents, verified it, attempted restore without confirmation, restored with confirmation, then tampered with the manifest checksum.

**Actual result:**

- Backup created with `status = ok`, 1 collection, 2 documents.
- Verification returned `status = ok`, 1 collection, 2 documents, database `e2e_source`.
- Restore without `--confirm` returned `status = refused`, reason `explicit --confirm is required`.
- Confirmed restore returned `status = ok`, `total_restored = 2`.
- Restored target collection contained both documents.
- Tampered checksum was detected.

**Failure paths verified:** unconfirmed restore refused; corrupted/tampered manifest detected.

**Evidence:** 6/6 checks passed.

**Limitations:** the drill used `mongomock`, not production MongoDB. Backup files are not encrypted. A production restore drill has not been performed.

---

### 16. Admin permissions and unauthorized access — **PASS**

**Procedure:** Compared non-admin and admin access, attempted role escalation, checked request-ID handling and inspected security headers.

**Actual result:**

- Non-admin: `GET /admin/dashboard` 403, `GET /threat-intelligence/sources` 403, `POST /system/tasks/retention` 403.
- Admin: dashboard 200, users 200, models 200.
- Dashboard keys included `total_users`, `total_analyses`, `high_risk_count`, `inconclusive_count`, `api_requests_24h`, `scans_by_type`, `risk_distribution`, `daily_scans`, `generated_at`.
- Admin could not grant the `owner` role to another user: 403.
- Valid request ID `e2erequest123456` was echoed.
- Unsafe request ID `<script>alert(1)</script>` was replaced by a 32-character generated ID.
- Security headers: `x-content-type-options: nosniff`, `x-frame-options: DENY`.

**Failure paths verified:** admin endpoints deny ordinary users; role escalation is blocked; hostile request IDs are sanitised.

**Evidence:** 10/10 checks passed.

**Limitations:** admin/owner roles are trusted. Production still requires TLS, SSO/MFA and network-level operator controls.

---

## 4. Failure-path summary

The following negative cases were explicitly exercised:

| Failure case | Observed behaviour |
|---|---|
| Use access token after logout | `401` |
| Stranger reads another user’s analysis | `404` |
| Stranger downloads another user’s PDF | `403` |
| Stranger reads another user’s report | `403` |
| Non-admin calls moderation/admin/task endpoints | `403` |
| Admin attempts to grant `owner` role | `403` |
| Low-signal / unavailable evidence | `inconclusive=true`, coverage `0.3`, missing evidence listed |
| Loopback/disallowed URL port | real fetcher returned `blocked`, error `port 9 is not in the allowed port list` |
| OCR binary missing | `not_configured`, empty text, `technical_limitation` indicator |
| Threat store no match | `no_match`; explicitly not a legitimacy claim |
| Single verified community report | `insufficient_independent_reports`; no indicator |
| False report without reason | `400` |
| Duplicate correction/report | original ID returned with `duplicate=true` |
| Extension permission denied | no page data sent |
| Retention disabled | `status=disabled`, zero deletions |
| Restore without confirmation | `status=refused` |
| Tampered backup manifest | checksum error |
| Hostile `X-Request-ID` | sanitised to generated 32-character ID |

---

## 5. Remaining tasks before deployment

The local functional baseline is green, but the following items remain before production launch:

1. **Data deletion / privacy**
   - Add a self-service account and/or analysis deletion flow if required by the privacy policy.
   - Add a data export/DSAR workflow if required.
   - Complete legal review of retention periods and the audit-log carve-out.
   - Verify deletion behaviour against a real MongoDB deployment, including TTL indexes.

2. **Risk presentation**
   - The blocked-URL case produced `inconclusive=true` and an explicit warning, but the category string was `Low observed risk`. Ensure the web UI, PDF and API consumers surface `inconclusive` prominently and consider renaming/suppressing the reassuring category label when coverage is low.

3. **Real integrations**
   - Provision and configure RDAP, DNS, TLS, licensed corporate registry, threat feeds, SMTP/SMS and billing credentials as appropriate.
   - Install/verify a local tesseract binary if OCR is required.
   - Re-run the E2E harness with real **sandbox** credentials and clearly separate those results from this stubbed local verification.
   - Do not treat the labelled stubs in this report as evidence that external vendors are integrated.

4. **Production infrastructure**
   - Deploy MongoDB and Redis/Celery with credentials, TLS and network isolation.
   - Replace in-process rate limiting with a shared Redis-backed limiter for multi-worker deployments.
   - Configure `ALLOWED_HOSTS` and restrictive CORS origins.
   - Terminate TLS at a reverse proxy and enable HSTS in production.
   - Add monitoring, alerting, log retention and on-call ownership.

5. **Backup/restore readiness**
   - Store encrypted backups offsite with restricted permissions.
   - Perform a production restore drill against a non-production clone.
   - Verify backup retention and access controls.

6. **Browser extension**
   - Perform manual QA in a real Chrome MV3 installation.
   - Verify the packaged extension, update URL and store review requirements.

7. **Operational security**
   - Rotate the test-only signing key and never seed demo/admin accounts in production.
   - Require MFA/SSO for administrators; review audit-log access.
   - Keep CI security jobs blocking and review dependency advisories before each release.

8. **Build verification**
   - Build both container images on a machine with a Docker daemon; CI is configured to do this, but local daemon access was unavailable during this run.

9. **ML data governance**
   - Complete counsel/privacy review of the DIFrauD licence, redaction process and retention of the local raw corpus before any production use.
   - Keep the corpus and derived artifacts out of git; preserve the `production_grade=false` disclaimer in all operator and public surfaces.
   - Add drift/calibration monitoring and an explicit retrospective review of DIFrauD false-positive and false-negative cases.

---

## 6. Reproduction commands

From the repository root with the local virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q --tb=line
```

From `frontend/` and `browser-extension/`:

```powershell
npm test -- --run
npm test
```

Standalone harnesses, from the repository root:

```powershell
.\.venv\Scripts\python.exe C:\Users\LENOVO\AppData\Local\Temp\opencode\e2e_harness.py
node C:\Users\LENOVO\AppData\Local\Temp\opencode\e2e_extension_harness.mjs
```

Structured evidence is written to:

```text
C:\Users\LENOVO\AppData\Local\Temp\opencode\e2e_evidence.json
```

Bearer tokens were removed from the evidence file before it was written.

---

## 7. Final statement

All 16 requested capability areas were exercised locally. Fifteen passed and one is partial solely because self-service deletion is not implemented. Failure paths, unavailable integrations and stub boundaries are documented above. Offer-first naming and DIFrauD integration checks were also completed as described in Section 2.1. No deployment or push was performed, and this report is left uncommitted pending explicit approval.
