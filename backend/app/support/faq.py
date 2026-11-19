"""Grounded, curated answers for the in-app support assistant.

This is intentionally not a generative model. Every answer comes from an
explicit entry sourced from repository documentation, and unmatched questions
receive an honest fallback instead of an invented response.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "can", "do", "does", "for",
    "from", "get", "how", "i", "if", "in", "is", "it", "me", "my", "of",
    "on", "or", "so", "that", "the", "there", "this", "to", "was", "what",
    "when", "where", "which", "who", "why", "will", "with", "you", "your",
}


@dataclass(frozen=True)
class FaqEntry:
    topic: str
    question: str
    answer: str
    keywords: tuple[str, ...]
    phrases: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()


FAQ_ENTRIES: tuple[FaqEntry, ...] = (
    FaqEntry(
        topic="greeting",
        question="Hello",
        answer=(
            "Hello. I’m the HireShield support assistant. I answer common questions from the "
            "project documentation and will say when I don’t have a grounded answer."
        ),
        keywords=("hello", "hey"),
        phrases=("hello", "hi there", "good morning", "good afternoon"),
    ),
    FaqEntry(
        topic="purpose",
        question="What does HireShield AI do?",
        answer=(
            "HireShield assists recruitment-fraud investigations. It extracts signals from job "
            "text, messages, URLs or documents, combines them with approved text models and "
            "optional public-source checks, then shows weighted evidence, limitations and "
            "sources so a person can make the final decision."
        ),
        keywords=("hireshield", "purpose", "product", "platform", "does", "work", "detect", "fraud"),
        phrases=("what is hireshield", "what does hireshield do", "how does it work"),
        sources=("README.md",),
    ),
    FaqEntry(
        topic="judgement",
        question="Is HireShield a replacement for my own judgement?",
        answer=(
            "No. HireShield surfaces evidence and confidence, not certainty. An inconclusive "
            "result is a valid outcome and means you should seek independent confirmation "
            "before acting on a listing or sender."
        ),
        keywords=("judgement", "judgment", "replace", "replacement", "decide", "decision", "certain", "certainty"),
        phrases=("replace my judgement", "replace my judgment", "make the decision for me"),
        sources=("README.md", "frontend/src/lib/demo.ts"),
    ),
    FaqEntry(
        topic="guarantee",
        question="Do you guarantee that a job is legitimate?",
        answer=(
            "No service can guarantee legitimacy. HireShield combines public signals, extraction "
            "and models, and explicitly labels missing evidence and technical limitations. A low "
            "risk score is not proof that an opportunity is safe."
        ),
        keywords=("guarantee", "guaranteed", "legitimate", "legitimacy", "safe", "proof", "genuine"),
        phrases=("guarantee", "is it legitimate", "is it safe", "low score mean safe"),
        sources=("README.md", "docs/LAUNCH_READINESS.md"),
    ),
    FaqEntry(
        topic="scoring",
        question="How is the risk score calculated?",
        answer=(
            "Risk is a weighted combination of evidence components (ML text signal, rules, "
            "domain signals, company signals, history and message pressure). Corroborated, "
            "independently verified indicators carry more weight than isolated or unverified "
            "ones. The report shows component scores, evidence status and coverage so you can "
            "see why a conclusion was reached."
        ),
        keywords=("risk", "score", "scoring", "weight", "weights", "calculated", "components", "evidence"),
        phrases=("risk score", "how is score", "calculate risk"),
        sources=("README.md", "docs/API.md"),
    ),
    FaqEntry(
        topic="confidence",
        question="Is the model confidence a fraud probability?",
        answer=(
            "No. The approved text-model scores are ranking signals. For the LinearSVC model the "
            "displayed confidence is a sigmoid-mapped decision margin, not a calibrated fraud "
            "probability. Message and anomaly scores use labelled rule fallbacks because their "
            "candidate models were not approved. Do not quote these values as production accuracy."
        ),
        keywords=("confidence", "probability", "calibrated", "model", "models", "accuracy", "margin", "fraud probability"),
        phrases=("is confidence", "fraud probability", "calibrated probability", "model accuracy"),
        sources=("docs/LAUNCH_READINESS.md §4",),
    ),
    FaqEntry(
        topic="inconclusive",
        question="What should I do with an inconclusive result?",
        answer=(
            "Treat inconclusive as a valid result, not a failure. Check the listed missing "
            "evidence and technical limitations, then verify the employer, domain and offer "
            "through independent channels before paying, sharing documents or accepting."
        ),
        keywords=("inconclusive", "unverified", "missing", "unknown", "limited", "limitations"),
        phrases=("inconclusive", "missing evidence", "not enough evidence"),
        sources=("README.md", "docs/LAUNCH_READINESS.md"),
    ),
    FaqEntry(
        topic="single_word",
        question="Will a single suspicious word make a listing high risk?",
        answer=(
            "No. Risk is calculated from weighted evidence across multiple dimensions. A single "
            "suspicious phrase can be a signal, but corroborated indicators and independent "
            "verification matter more than isolated wording."
        ),
        keywords=("single", "word", "phrase", "suspicious", "isolated", "one"),
        phrases=("single suspicious word", "one suspicious word", "one word"),
        sources=("frontend/src/lib/demo.ts",),
    ),
    FaqEntry(
        topic="correction",
        question="Can I correct an assessment?",
        answer=(
            "Yes. Signed-in users can open a report and submit a correction with supporting "
            "context. Corrections are reviewed and can inform future rule and model improvements. "
            "This is a review workflow, not an instant score override."
        ),
        keywords=("correct", "correction", "feedback", "appeal", "wrong", "mistake", "report"),
        phrases=("correct an assessment", "report a correction", "result is wrong", "submit feedback"),
        sources=("frontend/src/lib/demo.ts", "frontend/src/pages/ReportPage.tsx"),
    ),
    FaqEntry(
        topic="billing",
        question="Is billing or payment available here?",
        answer=(
            "Check /api/v1/system/config for the live state. In this free evaluation deployment "
            "Razorpay and Stripe are not configured, so no payment can be taken and billing is "
            "reported as disabled. When a provider is configured, activation depends on signed "
            "webhooks, not on returning from the checkout page. HireShield never collects card, "
            "CVV, bank, PAN or KYC data; those details stay with the payment provider."
        ),
        keywords=("billing", "payment", "pay", "price", "pricing", "plan", "plans", "razorpay", "stripe", "subscription", "invoice", "checkout", "pan", "kyc", "card"),
        phrases=("how much", "how do i pay", "payment", "billing", "razorpay", "subscription", "credit card"),
        sources=("docs/RENDER_DEPLOYMENT.md", "docs/RAZORPAY_SETUP.md", "docs/LAUNCH_READINESS.md"),
    ),
    FaqEntry(
        topic="turnstile",
        question="Is bot protection enabled?",
        answer=(
            "Cloudflare Turnstile activates only when both the site key and secret key are "
            "configured for the deployment hostname. With either key missing, login reports "
            "`not_configured` and no challenge is run; it is not simulated."
        ),
        keywords=("turnstile", "captcha", "bot", "challenge", "site key", "secret key"),
        phrases=("turnstile", "captcha", "bot protection", "bot check"),
        sources=("README.md", "docs/LAUNCH_READINESS.md"),
    ),
    FaqEntry(
        topic="integrations",
        question="Which external intelligence sources are configured?",
        answer=(
            "The authoritative answer is the `integrations` object returned by "
            "`/api/v1/system/config`. Unconfigured providers are reported as unavailable rather "
            "than simulated. RDAP, DNS and TLS checks need no API key; credentialed reputation, "
            "Google Web Risk and corporate-registry adapters need keys and consent. This "
            "deployment has no credentialed providers configured."
        ),
        keywords=("integration", "integrations", "provider", "providers", "virustotal", "safe browsing", "web risk", "mca", "rdap", "dns", "tls", "registry", "configured"),
        phrases=("external source", "intelligence source", "which providers", "is virustotal", "is rdap"),
        sources=("docs/LAUNCH_READINESS.md §3", "backend/app/api/routes/system.py"),
    ),
    FaqEntry(
        topic="scheduler",
        question="Are scheduled monitoring jobs running?",
        answer=(
            "No. Render’s free plan has no background workers or cron, so Celery and Redis are "
            "disabled, scheduled monitoring does not run, and any triggered task executes "
            "in-process with no retry-after-restart queue. `/api/v1/system/config` reports "
            "`job_monitoring: false`."
        ),
        keywords=("monitoring", "scheduler", "scheduled", "cron", "beat", "celery", "worker", "redis", "background", "jobs"),
        phrases=("scheduled job", "cron", "background worker", "celery", "monitoring job"),
        sources=("render.yaml", "docs/RENDER_DEPLOYMENT.md"),
    ),
    FaqEntry(
        topic="cold_start",
        question="Why is the first request slow?",
        answer=(
            "The API runs on a free Render web service that sleeps after about 15 minutes of "
            "inactivity. The first request after sleep can take roughly a minute while the "
            "container starts. This deployment is for evaluation, not time-sensitive traffic "
            "such as payment webhooks."
        ),
        keywords=("slow", "sleep", "sleeping", "cold", "start", "wake", "delay", "free", "render"),
        phrases=("why slow", "cold start", "first request", "sleeping", "takes a minute"),
        sources=("docs/RENDER_DEPLOYMENT.md",),
    ),
    FaqEntry(
        topic="deployment",
        question="Where is this deployment hosted?",
        answer=(
            "This evaluation deployment uses Render’s free plan: API at "
            "`https://hireshield-api-wets.onrender.com`, frontend at "
            "`https://hireshield-web-j72o.onrender.com`, with an external MongoDB Atlas M0 "
            "database. It is not a production launch and has no paid workers, Redis or backups."
        ),
        keywords=("deploy", "deployment", "host", "hosted", "url", "render", "atlas", "database", "mongo"),
        phrases=("where hosted", "deployment url", "live site", "api url"),
        sources=("docs/RENDER_DEPLOYMENT.md", "docs/LAUNCH_READINESS.md"),
    ),
    FaqEntry(
        topic="privacy",
        question="How do I export or delete my data?",
        answer=(
            "Self-service export and deletion are not implemented yet. The legal drafts describe "
            "a manual data-subject process, and settings pages direct requests to the support "
            "contact. Retention values exist in configuration but no automated purge job is "
            "evidenced, so do not assume data is automatically erased."
        ),
        keywords=("export", "delete", "deletion", "privacy", "gdpr", "data", "retention", "purge", "erase"),
        phrases=("delete my data", "export my data", "data retention", "right to be forgotten"),
        sources=("docs/LAUNCH_READINESS.md", "docs/LEGAL_DRAFTS.md", "frontend/src/pages/SettingsPage.tsx"),
    ),
    FaqEntry(
        topic="rbac",
        question="Does the login area selector grant admin access?",
        answer=(
            "No. Choosing “Admin login” only routes the sign-in form. Privileges come from the "
            "verified account role stored on the server, and admin endpoints require admin or "
            "owner. The selector cannot grant a role."
        ),
        keywords=("admin", "owner", "role", "roles", "rbac", "login", "access", "privilege", "selector"),
        phrases=("admin login", "admin access", "grant admin", "role selector"),
        sources=("README.md", "docs/LAUNCH_READINESS.md"),
    ),
    FaqEntry(
        topic="demo",
        question="Are demo accounts available in production?",
        answer=(
            "No. This deployment sets `SEED_DEMO_DATA=false`, so no demo or admin accounts are "
            "created. Create a real account and have an administrator promote it in MongoDB. "
            "Never use the development demo credentials in a shared environment."
        ),
        keywords=("demo", "seed", "seeded", "admin account", "credentials", "password", "register"),
        phrases=("demo account", "demo credentials", "default password", "admin account"),
        sources=("docs/RENDER_DEPLOYMENT.md",),
    ),
)

FALLBACK_SUGGESTIONS = (
    "How is the risk score calculated?",
    "What should I do with an inconclusive result?",
    "Can I correct an assessment?",
    "Which external intelligence sources are configured?",
    "Are scheduled monitoring jobs running?",
)


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in _normalise(text).split() if len(token) > 2 and token not in STOPWORDS}


def match_faq(message: str) -> FaqEntry | None:
    """Return the best grounded FAQ entry, or None when evidence is too weak."""

    normalised = _normalise(message)
    question_tokens = _tokens(message)
    best: FaqEntry | None = None
    best_score = 0

    for entry in FAQ_ENTRIES:
        score = 0
        for phrase in entry.phrases:
            if _normalise(phrase) in normalised:
                score += 4
        score += 2 * len(question_tokens & set(entry.keywords))
        if score > best_score:
            best, best_score = entry, score

    return best if best_score >= 4 else None


def fallback_suggestions() -> list[str]:
    return list(FALLBACK_SUGGESTIONS)
