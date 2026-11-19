"""Public, docs-backed support chat endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import enforce_rate_limit
from app.schemas import SupportChatReply, SupportChatRequest
from app.support.faq import fallback_suggestions, match_faq

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/chat", response_model=SupportChatReply)
def chat(
    payload: SupportChatRequest,
    _: None = Depends(enforce_rate_limit),
) -> SupportChatReply:
    """Answer a support question from curated documentation.

    The endpoint is stateless: messages are not stored and no external model or
    provider is called. Unmatched questions receive an explicit fallback rather
    than a fabricated answer.
    """

    entry = match_faq(payload.message)
    if entry is None:
        return SupportChatReply(
            answer=(
                "I don’t have a grounded answer for that yet. I’m a documentation-based "
                "assistant, not a generative AI, so I won’t guess. Try one of the suggested "
                "questions, or submit a correction from an investigation report for human review."
            ),
            grounded=False,
            suggestions=fallback_suggestions(),
        )

    return SupportChatReply(
        answer=entry.answer,
        grounded=True,
        matched_question=entry.question,
        sources=list(entry.sources),
    )
