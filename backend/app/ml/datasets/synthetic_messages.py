"""Curated synthetic recruitment-message examples (NOT real-world data).

PROVENANCE AND HONESTY NOTICE
-----------------------------
Every example below was authored by the HireShield AI engineering team for the
sole purposes of (a) training a baseline recruitment-message classifier when no
real labelled message corpus is available, (b) exercising inference fallbacks,
and (c) documenting ambiguous and incomplete cases that a production system
must flag as inconclusive rather than silently classifying.

* These messages are NOT collected from real users, employers or candidates.
* They are NOT a representative sample of recruitment fraud in the wild.
* They are NOT evidence of production-grade performance. Any metrics produced
  from them must be reported as synthetic-benchmark metrics only.
* ``ambiguous`` and ``incomplete`` rows are excluded from supervised training by
  default. They exist to make uncertainty visible in tests and documentation.

The real job-description corpus used by this project is EMSCAD (University of the
Aegean / Kaggle mirror, CC0-origin). This synthetic corpus is only a stand-in for
the message channel, which EMSCAD does not cover.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

Label = Literal["legitimate", "fraudulent", "ambiguous", "incomplete"]

DATASET_PROVENANCE: dict[str, str | bool | int] = {
    "name": "hireshield_curated_synthetic_messages",
    "version": "1.0",
    "origin": "Hand-authored by HireShield AI engineers; no real user or employer data.",
    "license": "Project-authored content, released for internal evaluation only.",
    "real_world_data": False,
    "production_grade": False,
    "covers_channel": "recruitment messages (email/SMS/WhatsApp style)",
    "notes": (
        "Ambiguous and incomplete examples are intentionally included and are "
        "excluded from supervised training by default. Metrics from this corpus "
        "must be labelled synthetic and must never be presented as production KPIs."
    ),
}

# Each record: (text, label, category, rationale). Category is a finer-grained
# tag used in documentation and tests; label drives supervised training.
_SYNTHETIC_ROWS: tuple[tuple[str, Label, str, str], ...] = (
    # ---------------------------- legitimate ----------------------------
    ("Hi Alex, thanks for applying to Brightpath Analytics. Your interview with our hiring manager is confirmed for Tuesday at 11am via our official video link in the portal. There is no fee at any stage. Please reply if you need accommodations.", "legitimate", "interview_confirmation", "Official portal reference and explicit no-fee statement."),
    ("Dear Priya, we reviewed your CV for the Graduate Engineer role. We would like to schedule a technical conversation next week. All communication comes from @brightpath-analytics.com and you can verify the role on our careers page.", "legitimate", "verified_sender", "Verifiable domain and careers page."),
    ("Hello, this is a reminder that your onboarding paperwork for Northline Health is due Friday. Please log in to the candidate portal using the address in your original offer letter. Contact HR on the published switchboard if anything looks wrong.", "legitimate", "onboarding", "Points to known channel, no unusual demand."),
    ("Thank you for your interest in the Data Analyst position. We can confirm the salary band of 55,000 to 62,000 and the role is based in our Leeds office with two remote days. Interviews are conducted in person or via our corporate video account.", "legitimate", "transparent_terms", "Specific compensation and ordinary process."),
    ("Hi Sam, the recruiting team at Meridian Labs enjoyed your conversation. We will be in touch within five working days with an update. You can reach us on the number listed on our official website if you have questions.", "legitimate", "normal_followup", "Normal timeline and published contact route."),
    ("Please find the offer letter for the Operations Associate role attached. It has been sent from our verified corporate address and signed by the Head of People. You may verify the signatory through our main office.", "legitimate", "offer_letter", "Verifiable signatory and corporate sender."),
    ("We are hiring a part-time library assistant at the city council. Applications are handled through the council jobs portal only. No payment is required and we never request bank details before appointment.", "legitimate", "public_sector", "Explicit anti-fee language and official channel."),
    ("Good morning, your reference check for the Finance trainee role is complete. HR will confirm the start date after the standard background check, which is processed by our registered provider with your written consent.", "legitimate", "background_check", "Consent-based, registered provider."),
    ("Hi Jordan, quick note that the assessment link for the UX role is the same one emailed yesterday from our ATS. If you did not receive it, check the portal rather than replying to this message with personal data.", "legitimate", "security_awareness", "Encourages verification through known channel."),
    ("The interview panel for the Civil Engineer vacancy has confirmed your availability. Please bring two forms of photo ID to the reception desk; no other documents are needed at this stage.", "legitimate", "in_person", "Reasonable in-person verification request."),
    ("Hello, we are pleased to offer you the Summer Internship at Greenfield Energy. Details of the stipend, reporting line and equipment allowance are in the attached PDF issued by our HR system. Congratulations!", "legitimate", "internship_offer", "Concrete terms, official attachment."),
    ("Our records show you attended the assessment centre on 14 June. Feedback will be released through the candidate portal next Monday. We do not charge candidates for assessments or training.", "legitimate", "feedback", "No fee, portal-based process."),
    ("Hi Lee, the hiring manager asked me to confirm your preferred start date for the Warehouse Supervisor position. Our HR team will issue the contract only after both sides sign the offer, and payroll details are collected after appointment.", "legitimate", "contract_flow", "Payroll collected post-appointment, not before."),
    ("Reminder: the webinar about our graduate programme is open to all applicants. Register through the events page on our website. Attendance is optional and does not affect your application.", "legitimate", "webinar", "Optional, no coercive framing."),
    ("Dear Ms Rao, following your interview for the Teacher role, the school board has requested two professional references. Please upload them to the application portal when convenient; there is no deadline today.", "legitimate", "references", "Non-urgent, official upload channel."),

    # ---------------------------- fraudulent ----------------------------
    ("URGENT! Congratulations you are selected for Work From Home Data Entry. Pay Rs. 4,999 registration fee NOW to reserve your seat. Send wire transfer details to the HR agent immediately.", "fraudulent", "advance_fee", "Upfront fee, urgency, wire transfer, work-from-home."),
    ("Dear candidate, your interview is fixed for tomorrow. Deposit a security deposit of 250 USD via Western Union to block your slot. Act now, limited seats today only!", "fraudulent", "payment_demand", "Security deposit via untraceable channel plus urgency."),
    ("We saw your CV online. Earn 60,000 monthly working from home, no experience needed. Buy a gift card of 200 and share the PIN to start training immediately.", "fraudulent", "gift_card", "Gift-card PIN demand and unrealistic pay."),
    ("HR department: your offer letter is attached. To complete verification send a copy of your passport, Aadhaar and bank account number with CVV to this email within 24 hours.", "fraudulent", "credential_harvest", "Request for identity and banking secrets."),
    ("LAST CHANCE. Your application is shortlisted but you must pay a processing fee through MoneyGram before 5 pm today. Reply with the transaction ID to confirm.", "fraudulent", "time_pressure", "Artificial deadline and MoneyGram."),
    ("Hi, we are a reputed MNC hiring remote billing executives. No interview required. Transfer 1,500 to the training account and we will issue your appointment letter tomorrow.", "fraudulent", "no_interview_fee", "Skips interview and demands training payment."),
    ("Congratulations! You have won a placement with our client. Kindly share your social security number and routing number so we can process your first payment. This is time sensitive.", "fraudulent", "pii_request", "Requests SSN and bank routing data."),
    ("This is WhatsApp HR. Your job is confirmed. Pay 3,000 via crypto to the wallet in the attached image for background verification. Do not call the office, just transfer.", "fraudulent", "crypto", "Crypto payment and instruction to avoid verification."),
    ("We hired you after reviewing your profile. Before onboarding, purchase two gift cards from any store and send the codes. Our manager will reimburse along with your salary.", "fraudulent", "reimbursement_lie", "Classic gift-card advance-fee pattern."),
    ("Urgent requirement for 100 telecommuting staff. Registration charges 1,200 are refundable after 30 days. Send to the personal account mentioned below and forward the receipt.", "fraudulent", "refundable_fee", "Refund promise does not remove advance-fee risk."),
    ("Your CV matched our client requirement. We need your bank details to deposit the joining bonus before the interview. Please reply fast with account number and IFSC.", "fraudulent", "bonus_pretext", "Bank details requested pre-interview under bonus pretext."),
    ("Attention: your application was flagged for verification. Pay 799 through PayPal friends and family to a family account to avoid cancellation of your candidature.", "fraudulent", "threat", "Coercive threat plus friends-and-family payment."),
    ("Remote customer support vacancy. Training material will be sent after you pay the training fee. Limited time offer, only 5 seats left. Western Union or gift card accepted.", "fraudulent", "training_fee", "Training fee and scarcity pressure."),
    ("Hi, I am the recruiter from a government project. We can offer you a job without interview. Send passport copy and 2,000 processing amount today, the link is in the short URL.", "fraudulent", "short_link", "Short link, no interview, documents plus money."),
    ("FINAL REMINDER: your joining formalities are pending. Deposit the medical test fee to the account in this SMS and share the OTP received to complete registration.", "fraudulent", "otp_request", "OTP request is a definitive account-takeover signal."),
    ("We are offering data entry work, 15,000 per week, no qualification required. Send 500 as security money to confirm. Call only on this number, not the company switchboard.", "fraudulent", "unrealistic_pay", "Unrealistic pay, security money, detours verification."),
    ("Your profile is selected for an overseas placement. Pay the agent fee by wire transfer to our consultant and share your date of birth and passport details for visa processing.", "fraudulent", "overseas_placement", "Agent fee plus sensitive identity data."),
    ("The attached offer requires an immediate online assessment payment of 90 USD. Use the payment link in the attachment and reply with the card last four digits for confirmation.", "fraudulent", "attachment_payment", "Attachment-based payment and card data request."),
    ("Congratulations candidate. We will process your appointment after you submit a bank guarantee of 10,000. This is a formal government requirement and must be completed today.", "fraudulent", "government_pretext", "Invented formal requirement and urgency."),
    ("Hello from the recruitment cell. We noticed your resume on a job site. Work from home and earn daily. First, send a gift card code of 100 to verify your seriousness.", "fraudulent", "seriousness_deposit", "Gift card as proof of seriousness."),
    ("Your interview is scheduled but the system shows a pending verification charge. Pay 450 via MoneyGram within two hours or your application will be rejected automatically.", "fraudulent", "system_charge", "Fabricated system charge with deadline."),
    ("Please confirm your bank account number and CVV so our payroll team can credit the joining allowance before your first day. This is urgent as the payment batch closes tonight.", "fraudulent", "payroll_pretext", "CVV request is never legitimate."),
    ("We are a startup hiring interns. Send 1,000 to the founder's personal account for the laptop deposit. You can work from home immediately, no contract needed.", "fraudulent", "personal_account", "Personal account deposit and no contract."),
    ("Selected candidates must pay for the mandatory online Certification Course before joining. Fees are non-refundable and must be paid by gift card. Act immediately.", "fraudulent", "mandatory_course", "Mandatory paid course with gift card."),
    ("Hi, this is HR from the hiring team. Your appointment order is ready. Share your OTP and Aadhaar photo quickly so we can release the order today.", "fraudulent", "otp_aadhaar", "OTP plus identity document request."),

    # ---------------------------- ambiguous ----------------------------
    ("Hi, we would like to move forward. There is a one-time background check charge of 300 which is normally reimbursed in the first salary cycle. Please check with the office before paying.", "ambiguous", "reimbursable_fee", "Fee pattern is concerning but reimbursement claim and verification instruction make it uncertain."),
    ("Congratulations! We need your bank account details to send the joining allowance. Our HR head will call you on the number from your application to confirm first.", "ambiguous", "bank_details_with_call", "Sensitive request paired with a plausible verification step."),
    ("Urgent: the last date to apply is today. Please complete the form at the link in this message. The form also asks for identity proof, which we need for the government scheme.", "ambiguous", "urgency_with_scheme", "Urgency and ID request; legitimacy depends on the actual scheme and link."),
    ("Hello, you are shortlisted. Our training partner will contact you about the paid certification. Attendance is optional but recommended. Ask your placement coordinator for details.", "ambiguous", "third_party_training", "Third-party paid training is common but can be exploitative."),
    ("We received your application and noticed a mismatch in your dates. Please call the number on our website to clarify. Do not share documents over email until verified.", "ambiguous", "inconsistency_request", "Could be legitimate due diligence; needs independent verification."),

    # ---------------------------- incomplete ----------------------------
    ("Hi, please call us about the job.", "incomplete", "no_details", "No role, sender, payment or process detail to assess."),
    ("Congratulations, you are selected. We will share details soon.", "incomplete", "no_action", "No concrete demand or verifiable claim."),
    (" urgently needed  ", "incomplete", "fragment", "Fragment with no context."),
    ("Kindly check the attachment.", "incomplete", "no_attachment", "References an attachment that is not available for analysis."),
    ("Hello?", "incomplete", "greeting_only", "Greeting only."),
)


def load_synthetic_messages(
    *,
    include_ambiguous: bool = False,
    include_incomplete: bool = False,
) -> list[dict[str, str | bool]]:
    """Return curated synthetic records as dictionaries.

    Args:
        include_ambiguous: Include deliberately uncertain examples. Off by default
            because they have no trustworthy supervised label.
        include_incomplete: Include deliberately context-free fragments. Off by
            default for the same reason.

    Returns:
        Dictionaries with ``text``, ``label``, ``category``, ``rationale``,
        ``provenance`` and ``trainable`` keys. ``provenance`` is always the
        synthetic dataset name so downstream code cannot mistake it for real data.
    """
    rows: list[dict[str, str | bool]] = []
    for text, label, category, rationale in _SYNTHETIC_ROWS:
        if label == "ambiguous" and not include_ambiguous:
            continue
        if label == "incomplete" and not include_incomplete:
            continue
        rows.append(
            {
                "text": text,
                "label": label,
                "category": category,
                "rationale": rationale,
                "provenance": str(DATASET_PROVENANCE["name"]),
                "trainable": label in {"legitimate", "fraudulent"},
            }
        )
    return rows


def synthetic_message_dataframe(
    *,
    include_ambiguous: bool = False,
    include_incomplete: bool = False,
) -> pd.DataFrame:
    """Return the curated synthetic corpus as a pandas DataFrame."""
    return pd.DataFrame(load_synthetic_messages(
        include_ambiguous=include_ambiguous,
        include_incomplete=include_incomplete,
    ))
