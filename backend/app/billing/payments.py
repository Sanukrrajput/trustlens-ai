"""Payment checkout creation and verified webhook processing.

No paid access is granted from a frontend success callback. Only HMAC-verified
provider events can activate or cancel a subscription.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import requests

from app.core.config import Settings
from app.core.security import utcnow
from app.db.repositories import Repositories

logger = logging.getLogger(__name__)


class PaymentConfigurationError(RuntimeError):
    pass


def razorpay_mode(key_id: str) -> str:
    """Derive a display-only mode label from the public key id.

    This never authorises anything; it only helps the UI avoid presenting test
    checkouts as live payments.
    """
    if key_id.startswith("rzp_live_"):
        return "live"
    if key_id.startswith("rzp_test_"):
        return "test"
    return "unknown"


class PaymentService:
    def __init__(self, settings: Settings, repos: Repositories) -> None:
        self.settings = settings
        self.repos = repos

    def create_checkout(
        self,
        *,
        user_id: str,
        user_email: str,
        plan: dict[str, Any],
        interval: str,
        provider: str,
        success_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict[str, Any]:
        amount = int(plan.get("price_yearly_paise" if interval == "yearly" else "price_monthly_paise") or 0)
        currency = str(plan.get("currency") or self.settings.payment_currency).upper()
        if amount <= 0:
            raise ValueError("this plan does not require an online checkout")
        if provider == "razorpay":
            return self._razorpay_order(user_id, user_email, plan, interval, amount, currency)
        if provider == "stripe":
            return self._stripe_session(user_id, user_email, plan, interval, amount, currency, success_url, cancel_url)
        raise ValueError("unsupported payment provider")

    def _razorpay_order(
        self,
        user_id: str,
        user_email: str,
        plan: dict[str, Any],
        interval: str,
        amount: int,
        currency: str,
    ) -> dict[str, Any]:
        if not self.settings.razorpay_key_id or not self.settings.razorpay_key_secret:
            raise PaymentConfigurationError("Razorpay is not configured on this deployment")
        payload = {
            "amount": amount,
            "currency": currency,
            "receipt": f"hs_{user_id[:8]}_{plan['code']}_{interval}",
            "notes": {
                "user_id": user_id,
                "plan_code": plan["code"],
                "interval": interval,
                "email": user_email,
            },
        }
        response = requests.post(
            "https://api.razorpay.com/v1/orders",
            json=payload,
            auth=(self.settings.razorpay_key_id, self.settings.razorpay_key_secret),
            timeout=15,
        )
        response.raise_for_status()
        order = response.json()
        return {
            "provider": "razorpay",
            "checkout_id": order["id"],
            "key_id": self.settings.razorpay_key_id,
            "checkout_url": None,
            "amount": amount,
            "currency": currency,
            "name": f"TrustLens AI — {plan['name']}",
            "description": f"{interval.capitalize()} subscription",
            "mode": razorpay_mode(self.settings.razorpay_key_id),
            "order": order,
        }

    def _stripe_session(
        self,
        user_id: str,
        user_email: str,
        plan: dict[str, Any],
        interval: str,
        amount: int,
        currency: str,
        success_url: str | None,
        cancel_url: str | None,
    ) -> dict[str, Any]:
        if not self.settings.stripe_secret_key:
            raise PaymentConfigurationError("Stripe is not configured on this deployment")
        base = (success_url or f"{self.settings.cors_origins[0]}/billing?status=success").split("?")[0]
        cancel = (cancel_url or f"{self.settings.cors_origins[0]}/billing?status=cancelled").split("?")[0]
        form = {
            "mode": "payment",
            "success_url": base + "?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": cancel,
            "client_reference_id": user_id,
            "customer_email": user_email,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": str(amount),
            "line_items[0][price_data][product_data][name]": f"TrustLens AI {plan['name']} ({interval})",
            "metadata[user_id]": user_id,
            "metadata[plan_code]": plan["code"],
            "metadata[interval]": interval,
        }
        response = requests.post(
            "https://api.stripe.com/v1/checkout/sessions",
            data=urlencode(form),
            headers={
                "Authorization": f"Bearer {self.settings.stripe_secret_key}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=15,
        )
        response.raise_for_status()
        session = response.json()
        return {
            "provider": "stripe",
            "checkout_id": session["id"],
            "key_id": None,
            "checkout_url": session.get("url"),
            "amount": amount,
            "currency": currency,
            "session": {"id": session["id"], "url": session.get("url")},
        }

    def verify_webhook(self, provider: str, raw_body: bytes, signature: str | None) -> dict[str, Any]:
        if provider == "razorpay":
            return self._verify_razorpay(raw_body, signature)
        if provider == "stripe":
            return self._verify_stripe(raw_body, signature)
        raise ValueError("unsupported payment provider")

    def _verify_razorpay(self, raw_body: bytes, signature: str | None) -> dict[str, Any]:
        secret = self.settings.razorpay_webhook_secret
        if not secret or not signature:
            raise ValueError("Razorpay webhook signing secret is not configured")
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("invalid Razorpay webhook signature")
        event = json.loads(raw_body.decode("utf-8"))
        return {"provider": "razorpay", "event": event}

    def _verify_stripe(self, raw_body: bytes, signature: str | None) -> dict[str, Any]:
        secret = self.settings.stripe_webhook_secret
        if not secret or not signature:
            raise ValueError("Stripe webhook signing secret is not configured")
        parts: dict[str, list[str]] = {}
        for item in signature.split(","):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            parts.setdefault(key.strip(), []).append(value.strip())
        timestamps = parts.get("t", [])
        signatures = parts.get("v1", [])
        if not timestamps or not signatures:
            raise ValueError("invalid Stripe signature header")
        signed_payload = f"{timestamps[0]}.".encode() + raw_body
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, value) for value in signatures):
            raise ValueError("invalid Stripe webhook signature")
        if abs(time.time() - int(timestamps[0])) > 300:
            raise ValueError("Stripe webhook timestamp outside tolerance")
        event = json.loads(raw_body.decode("utf-8"))
        return {"provider": "stripe", "event": event}

    POSITIVE_EVENTS = {
        "payment.captured",
        "order.paid",
        "subscription.charged",
        "checkout.session.completed",
        "invoice.payment_succeeded",
    }
    NEGATIVE_EVENTS = {
        "payment.failed",
        "subscription.cancelled",
        "customer.subscription.deleted",
        "charge.refunded",
        "refund.created",
    }

    @staticmethod
    def _event_entity_and_metadata(provider: str, event: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Find the entity and server-created notes/metadata for a provider event."""
        if provider == "razorpay":
            payload = event.get("payload") or {}
            payment = (payload.get("payment") or {}).get("entity") or {}
            order = (payload.get("order") or {}).get("entity") or {}
            subscription = (payload.get("subscription") or {}).get("entity") or {}
            refund = (payload.get("refund") or {}).get("entity") or {}
            obj = payment or subscription or order or refund or {}
            metadata = (
                order.get("notes")
                or payment.get("notes")
                or subscription.get("notes")
                or refund.get("notes")
                or {}
            )
            if order and not obj.get("order_id"):
                obj = {**obj, "order_id": order.get("id")}
            return obj, metadata
        obj = (event.get("data") or {}).get("object") or {}
        return obj, obj.get("metadata") or {}

    def handle_verified_event(self, provider: str, event: dict[str, Any]) -> dict[str, Any]:
        event_id = str(event.get("id") or event.get("event_id") or "")
        if not event_id:
            raise ValueError("webhook event is missing an id")
        existing = self.repos.payments.by_event(event_id)
        if existing:
            return {"status": "already_processed", "event_id": event_id}

        event_type = str(event.get("event") or event.get("type") or "")
        obj, metadata = self._event_entity_and_metadata(provider, event)
        user_id = str(metadata.get("user_id") or obj.get("client_reference_id") or "")
        plan_code = str(metadata.get("plan_code") or "professional")
        interval = str(metadata.get("interval") or "monthly")

        if event_type not in self.POSITIVE_EVENTS | self.NEGATIVE_EVENTS:
            status = "ignored"
        elif event_type in self.NEGATIVE_EVENTS:
            status = "cancelled" if "cancel" in event_type or "deleted" in event_type else "refunded"
        else:
            plan = self.repos.plans.find_one({"code": plan_code}) or {}
            expected_amount = plan.get("price_yearly_paise" if interval == "yearly" else "price_monthly_paise")
            amount = obj.get("amount") or obj.get("amount_total")
            currency = str(obj.get("currency") or "").upper()
            expected_currency = str(plan.get("currency") or self.settings.payment_currency).upper()
            if expected_amount and amount and int(amount) != int(expected_amount):
                status = "amount_mismatch"
            elif currency and expected_currency and currency != expected_currency:
                status = "currency_mismatch"
            else:
                status = "active"

        if not user_id:
            # Without server-created notes there is no account to update. Record
            # the verified event, but never report it as an entitlement change.
            status = "ignored"

        if user_id and status in {"active", "cancelled", "refunded"}:
            plan = self.repos.plans.find_one({"code": plan_code}) or {}
            period_end = utcnow() + (timedelta(days=365) if interval == "yearly" else timedelta(days=30))
            self.repos.subscriptions.upsert(
                user_id,
                {
                    "plan_code": plan_code,
                    "status": status,
                    "interval": interval,
                    "provider": provider,
                    "provider_reference": obj.get("id"),
                    "scan_limit": plan.get("scan_limit", 100),
                    "current_period_end": period_end,
                    "scans_used": 0,
                    "cancel_at_period_end": status == "cancelled",
                    "updated_at": utcnow(),
                },
            )

        self.repos.payments.insert(
            {
                "user_id": user_id or None,
                "provider": provider,
                "provider_event_id": event_id,
                "provider_payment_id": obj.get("id"),
                "event_type": event_type,
                "status": status,
                "amount": obj.get("amount") or obj.get("amount_total"),
                "currency": obj.get("currency"),
                "metadata": metadata,
                "raw_event": event,
                "created_at": utcnow(),
            }
        )
        return {
            "status": "processed" if status in {"active", "cancelled", "refunded"} else status,
            "event_id": event_id,
            "subscription_status": status,
        }
