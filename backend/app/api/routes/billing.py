"""Public plan catalogue, checkout initiation, subscription state and webhooks.

Access is only granted by HMAC-verified provider events handled in
``PaymentService.handle_verified_event``. Frontend success/cancel redirects never
activate a paid plan.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import get_app_settings, get_current_user, get_repositories
from app.billing.payments import PaymentConfigurationError, PaymentService
from app.core.config import Settings
from app.core.security import utcnow
from app.db.repositories import Repositories
from app.schemas import CheckoutOut, CheckoutRequest, PlanOut, SubscriptionOut
from app.services.plan_service import PlanService
from app.utils.serialization import json_safe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


class CancelRequest(BaseModel):
    cancel_at_period_end: bool = Field(default=True)


def _plans(settings: Settings, repos: Repositories, user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    service = PlanService(settings, repos)
    return service.plans(active_only=True)


def _safe_redirect(url: str | None, settings: Settings) -> str | None:
    """Reject off-origin redirects supplied by a client."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="redirect URL must be an absolute http(s) URL")
    allowed = {urlparse(origin).netloc for origin in settings.cors_origins}
    if parsed.netloc not in allowed:
        raise HTTPException(status_code=400, detail="redirect URL is not an approved origin")
    return url


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
) -> list[PlanOut]:
    return [PlanOut(**plan) for plan in _plans(settings, repos)]


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> SubscriptionOut:
    return SubscriptionOut(**PlanService(settings, repos).subscription_out(str(user["id"])))


@router.post("/checkout", response_model=CheckoutOut)
def create_checkout(
    payload: CheckoutRequest,
    request: Request,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> CheckoutOut:
    plans = PlanService(settings, repos)
    plan = plans.plan(payload.plan_code)
    if not plan or not plan.get("active", True):
        raise HTTPException(status_code=404, detail="plan not found")
    success_url = _safe_redirect(payload.success_url, settings)
    cancel_url = _safe_redirect(payload.cancel_url, settings)
    payment = PaymentService(settings, repos)
    try:
        result = payment.create_checkout(
            user_id=str(user["id"]),
            user_email=str(user.get("email") or ""),
            plan=plan,
            interval=payload.interval,
            provider=payload.provider,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PaymentConfigurationError as exc:
        # Honest failure: never simulate a checkout or grant access locally.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - provider/network failures must not leak secrets
        logger.exception("payment checkout failed provider=%s", payload.provider)
        raise HTTPException(status_code=502, detail="payment provider is temporarily unavailable") from exc

    repos.audit.log(
        str(user["id"]),
        "billing.checkout_created",
        target=payload.plan_code,
        metadata={"provider": result["provider"], "checkout_id": result["checkout_id"]},
        ip=request.client.host if request.client else None,
    )
    # The full provider payload is not part of the public contract; only checkout
    # identifiers and the client SDK key are returned.
    return CheckoutOut(
        provider=result["provider"],
        checkout_id=result["checkout_id"],
        key_id=result.get("key_id"),
        checkout_url=result.get("checkout_url"),
        amount=int(result["amount"]),
        currency=str(result["currency"]),
        name=result.get("name"),
        description=result.get("description"),
        mode=result.get("mode"),
    )


@router.post("/subscription/cancel", response_model=SubscriptionOut)
def cancel_subscription(
    payload: CancelRequest,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> SubscriptionOut:
    """Set the cancellation flag. Billing status still changes only via webhook."""
    plans = PlanService(settings, repos)
    plans.ensure_subscription(str(user["id"]))
    updated = repos.subscriptions.upsert(
        str(user["id"]),
        {"cancel_at_period_end": bool(payload.cancel_at_period_end), "updated_at": utcnow()},
    )
    repos.audit.log(str(user["id"]), "billing.cancel_requested", target=str(updated.get("_id")))
    return SubscriptionOut(**plans.subscription_out(str(user["id"])))


@router.post("/webhooks/{provider}")
async def payment_webhook(
    provider: str,
    request: Request,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
) -> dict[str, Any]:
    """Verify the provider signature against the raw body before any state change."""
    if provider not in {"razorpay", "stripe"}:
        raise HTTPException(status_code=404, detail="unknown payment provider")
    raw = await request.body()
    signature = (
        request.headers.get("x-razorpay-signature")
        if provider == "razorpay"
        else request.headers.get("stripe-signature")
    )
    payment = PaymentService(settings, repos)
    try:
        verified = payment.verify_webhook(provider, raw, signature)
        result = payment.handle_verified_event(provider, verified["event"])
    except ValueError as exc:
        logger.warning("rejected %s webhook: %s", provider, exc)
        raise HTTPException(status_code=400, detail="invalid webhook") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("webhook processing failed provider=%s", provider)
        raise HTTPException(status_code=500, detail="webhook processing failed") from exc

    repos.audit.log(
        "system",
        "billing.webhook_processed",
        target=provider,
        metadata={"event_id": result.get("event_id"), "status": result.get("status")},
        ip=request.client.host if request.client else None,
    )
    return json_safe(result) or result
