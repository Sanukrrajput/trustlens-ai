"""Public, docs-backed support chat with session-scoped message logs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import enforce_rate_limit, get_repositories
from app.db.repositories import Repositories, utcnow
from app.schemas import SupportChatMessage, SupportChatReply, SupportChatRequest
from app.support.faq import fallback_suggestions, match_faq

router = APIRouter(prefix="/support", tags=["support"])

SESSION_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"

FALLBACK_ANSWER = (
    "I don’t have a grounded answer for that yet. I’m a documentation-based "
    "assistant, not a generative AI, so I won’t guess. Try one of the suggested "
    "questions, or submit a correction from an investigation report for human review."
)


def _message_out(doc: dict[str, Any]) -> SupportChatMessage:
    return SupportChatMessage(
        id=str(doc["_id"]),
        session_id=str(doc["session_id"]),
        role=str(doc["role"]),  # type: ignore[arg-type]
        text=str(doc["text"]),
        grounded=doc.get("grounded"),
        matched_question=doc.get("matched_question"),
        sources=list(doc.get("sources") or []),
        suggestions=list(doc.get("suggestions") or []),
        created_at=doc["created_at"],
    )


@router.post("/chat", response_model=SupportChatReply)
def chat(
    payload: SupportChatRequest,
    _: None = Depends(enforce_rate_limit),
    repos: Repositories = Depends(get_repositories),
) -> SupportChatReply:
    """Answer from curated documentation and log both sides to MongoDB.

    Messages are keyed by a client-generated random session ID. No account,
    IP, user agent or sensitive payment/KYC data is stored. The matcher makes
    no external model or provider calls; unmatched questions get an explicit
    fallback instead of an invented answer.
    """

    entry = match_faq(payload.message)
    if entry is None:
        answer = FALLBACK_ANSWER
        grounded = False
        matched_question = None
        sources: list[str] = []
        suggestions = fallback_suggestions()
    else:
        answer = entry.answer
        grounded = True
        matched_question = entry.question
        sources = list(entry.sources)
        suggestions = []

    timestamp = utcnow()
    repos.support_messages.insert(
        {
            "session_id": payload.session_id,
            "role": "user",
            "text": payload.message,
            "created_at": timestamp,
        }
    )
    stored = repos.support_messages.insert(
        {
            "session_id": payload.session_id,
            "role": "assistant",
            "text": answer,
            "grounded": grounded,
            "matched_question": matched_question,
            "sources": sources,
            "suggestions": suggestions,
            "created_at": timestamp,
        }
    )

    return SupportChatReply(
        id=str(stored["_id"]),
        answer=answer,
        grounded=grounded,
        matched_question=matched_question,
        sources=sources,
        suggestions=suggestions,
        session_id=payload.session_id,
        created_at=stored["created_at"],
    )


@router.get("/chat", response_model=list[SupportChatMessage])
def history(
    session_id: str = Query(pattern=SESSION_PATTERN),
    _: None = Depends(enforce_rate_limit),
    repos: Repositories = Depends(get_repositories),
) -> list[SupportChatMessage]:
    """Return the saved conversation for a browser session (max 100 messages)."""

    return [_message_out(doc) for doc in repos.support_messages.for_session(session_id)]


@router.delete("/chat")
def clear_history(
    session_id: str = Query(pattern=SESSION_PATTERN),
    _: None = Depends(enforce_rate_limit),
    repos: Repositories = Depends(get_repositories),
) -> dict[str, Any]:
    """Delete every stored message for a browser session."""

    deleted = repos.support_messages.delete_session(session_id)
    return {"status": "cleared", "session_id": session_id, "deleted": deleted}
