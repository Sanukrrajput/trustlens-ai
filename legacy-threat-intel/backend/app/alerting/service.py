"""Notification delivery, deduplication and read-only-by-default response workflow."""

from __future__ import annotations

import hashlib
import hmac
import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from typing import TYPE_CHECKING, Any

import requests

from app.utils import make_id, redact, retry_with_backoff, utcnow

if TYPE_CHECKING:
    from app.config import Settings
    from app.db.repositories import Repositories

logger = logging.getLogger(__name__)
SEVERITY_RANK = {"informational": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class AlertService:
    def __init__(self, settings: "Settings", repos: "Repositories"):
        self.settings = settings
        self.repos = repos

    def process(self) -> dict[str, Any]:
        incidents = self.repos.incidents.find(
            {"status": {"$nin": ["closed", "resolved", "false_positive"]}},
            sort_field="last_seen",
            limit=200,
        )
        threshold = SEVERITY_RANK.get(self.settings.alert_min_severity.lower(), 3)
        created = delivered = failed = 0
        for incident in incidents:
            if SEVERITY_RANK.get(str(incident.get("severity")), 0) < threshold:
                continue
            dedupe_key = make_id("ntf", incident.get("incident_id"), incident.get("severity"))
            notification = {
                "notification_id": make_id("ntf", dedupe_key),
                "dedupe_key": dedupe_key,
                "type": "incident",
                "title": f"{str(incident.get('severity')).title()} risk incident",
                "message": str(incident.get("description") or incident.get("title") or "")[:1500],
                "severity": incident.get("severity"),
                "incident_id": incident.get("incident_id"),
                "risk_score": incident.get("risk_score", 0),
                "channel": "dashboard",
                "status": "pending",
                "read": False,
                "attempts": 0,
                "expires_at": utcnow() + timedelta(days=self.settings.notification_retention_days),
            }
            if not self.repos.notifications.create(notification):
                continue
            created += 1
            errors: list[str] = []
            for channel, sender in (("email", self._send_email), ("webhook", self._send_webhook)):
                try:
                    ok, error = retry_with_backoff(
                        lambda s=sender, n=notification: s(n),
                        attempts=3,
                        base_delay=1.0,
                        exceptions=(Exception,),
                    )
                    if not ok:
                        errors.append(f"{channel}: {error}")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{channel}: {redact(str(exc), 300)}")
            # Dashboard delivery always succeeds because the notification is stored above.
            status = "sent" if not errors or not self._has_external_channel() else "failed"
            self.repos.notifications.update_one(
                {"dedupe_key": dedupe_key},
                {
                    "$set": {
                        "status": status,
                        "errors": errors,
                        "sent_at": utcnow(),
                        "attempts": len(errors) + (2 if self._has_external_channel() else 0),
                        "channels": ["dashboard"] + (["email"] if self.settings.alert_emails else []) + (["webhook"] if self.settings.webhook_url else []),
                    }
                },
            )
            if status == "sent":
                delivered += 1
            else:
                failed += 1
        return {"notifications_created": created, "delivered": delivered, "failed": failed}

    def _has_external_channel(self) -> bool:
        return bool(self.settings.alert_emails and self.settings.smtp_host) or bool(self.settings.webhook_url)

    def _send_email(self, notification: dict[str, Any]) -> tuple[bool, str]:
        if not (self.settings.alert_emails and self.settings.smtp_host):
            return True, "not configured"
        message = EmailMessage()
        message["Subject"] = f"[SOC] {notification['title']}"
        message["From"] = self.settings.smtp_from or self.settings.smtp_user or "soc@localhost"
        message["To"] = ", ".join(self.settings.alert_emails)
        message.set_content(
            f"{notification['message']}\n\nIncident: {notification.get('incident_id')}\n"
            "Verify evidence in the dashboard before taking action."
        )
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as client:
            client.starttls()
            if self.settings.smtp_user and self.settings.smtp_password:
                client.login(self.settings.smtp_user, self.settings.smtp_password)
            client.send_message(message)
        return True, ""

    def _send_webhook(self, notification: dict[str, Any]) -> tuple[bool, str]:
        if not self.settings.webhook_url:
            return True, "not configured"
        body = (
            f"{notification['title']}\n{notification['message']}\n"
            f"Incident: {notification.get('incident_id')}\nRisk: {notification.get('risk_score')}"
        ).encode("utf-8")
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        if self.settings.webhook_secret:
            signature = hmac.new(self.settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-Signature-256"] = f"sha256={signature}"
        response = requests.post(self.settings.webhook_url, data=body, headers=headers, timeout=15)
        response.raise_for_status()
        return True, ""


class ResponseActionService:
    """Propose and approve actions; the platform never executes them automatically."""

    def __init__(self, settings: "Settings", repos: "Repositories"):
        self.settings = settings
        self.repos = repos

    def propose(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = {
            "action_id": make_id("act", payload["incident_id"], payload["action_type"], payload["target"], utcnow().isoformat()),
            "incident_id": payload["incident_id"],
            "action_type": payload["action_type"],
            "target": payload["target"],
            "rationale": payload.get("rationale", ""),
            "requested_by": payload.get("requested_by", "analyst"),
            "status": "pending_approval",
            "executed": False,
            "execution": "not_performed_by_platform",
            "requires_authorization": True,
            "recommended_steps": [
                "Verify the incident evidence and obtain written authorization from the asset/app owner.",
                "Record the approved change in your ITSM/change system before any manual implementation.",
                "Implement the action manually with a second operator where policy requires it.",
            ],
            "rollback_instructions": {
                "block_ip": "Remove the temporary block from the firewall/edge policy using the change record.",
                "disable_account": "Re-enable the account only after identity team verification and password reset.",
                "isolate_asset": "Restore network access after forensic imaging and asset-owner approval.",
                "reset_credentials": "Issue a new credential through the approved identity workflow; revoke old sessions.",
                "custom": "Reverse the manual change using the change record and document the outcome.",
            }.get(payload["action_type"], "Document and reverse the manual change using the change record."),
            "created_at": utcnow(),
        }
        stored = self.repos.actions.create(action)
        self.repos.audit.write(
            "response_action_proposed",
            action["requested_by"],
            {"action_id": action["action_id"], "target": action["target"], "action_type": action["action_type"]},
        )
        return stored

    def approve(self, action_id: str, approver: str, note: str) -> dict[str, Any]:
        if not self.settings.response_actions_enabled:
            raise PermissionError("RESPONSE_ACTIONS_ENABLED=false; approval workflow is disabled")
        action = self.repos.actions.find_one({"action_id": action_id})
        if not action:
            raise LookupError("response action not found")
        updated = self.repos.actions.approve(action_id, approver, note)
        self.repos.audit.write(
            "response_action_approved",
            approver,
            {
                "action_id": action_id,
                "target": action.get("target"),
                "action_type": action.get("action_type"),
                "note": note,
                "executed": False,
            },
        )
        return updated
