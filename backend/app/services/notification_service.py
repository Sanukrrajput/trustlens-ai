"""In-app, email and optional SMS notifications with deduplication."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlencode

import requests

from app.core.config import Settings
from app.core.security import utcnow
from app.db.repositories import Repositories

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, settings: Settings, repos: Repositories) -> None:
        self.settings = settings
        self.repos = repos

    def notify(
        self,
        *,
        user_id: str,
        user_email: str | None,
        kind: str,
        title: str,
        body: str,
        severity: str = "info",
        analysis_id: str | None = None,
        dedupe_key: str | None = None,
        send_email: bool | None = None,
        send_sms: bool = False,
        phone_number: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        document = {
            "user_id": user_id,
            "kind": kind,
            "title": title,
            "body": body,
            "severity": severity,
            "read": False,
            "analysis_id": analysis_id,
            "dedupe_key": dedupe_key or f"{kind}:{user_id}:{analysis_id or ''}:{title}",
            "created_at": utcnow(),
        }
        record, created = self.repos.notifications.create_deduped(document)
        if not created:
            return record, False

        should_email = self.settings.notify_email_on_high_risk if send_email is None else send_email
        if should_email and user_email:
            self.send_email(user_email, title, body, analysis_id)
        if send_sms and phone_number and self.settings.sms_provider_url:
            self.send_sms(phone_number, f"{title}: {body}")
        return record, True

    def send_email(self, to: str, subject: str, body: str, analysis_id: str | None = None) -> bool:
        if not self.settings.smtp_host or not self.settings.smtp_from:
            logger.info("email not configured; skipping delivery to %s", to)
            return False
        message = EmailMessage()
        message["From"] = self.settings.smtp_from
        message["To"] = to
        message["Subject"] = subject
        link = f"{self.settings.cors_origins[0]}/report/{analysis_id}" if analysis_id else self.settings.cors_origins[0]
        message.set_content(f"{body}\n\nReview: {link}\n\nHireShield AI")
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as client:
                if self.settings.smtp_use_tls:
                    client.starttls()
                if self.settings.smtp_user and self.settings.smtp_password:
                    client.login(self.settings.smtp_user, self.settings.smtp_password)
                client.send_message(message)
            return True
        except Exception as exc:  # noqa: BLE001 - delivery failures must not break scans
            logger.warning("email delivery failed: %s", exc)
            return False

    def send_sms(self, phone_number: str, text: str) -> bool:
        if not self.settings.sms_provider_url:
            return False
        try:
            payload = {
                "to": phone_number,
                "message": text[:480],
                "sender": self.settings.sms_sender_id,
            }
            headers = {}
            if self.settings.sms_provider_api_key:
                headers["Authorization"] = f"Bearer {self.settings.sms_provider_api_key}"
            response = requests.post(
                self.settings.sms_provider_url,
                json=payload,
                headers=headers,
                timeout=8,
            )
            response.raise_for_status()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("SMS delivery failed: %s", exc)
            return False

    def high_risk_notification(self, user_id: str, user_email: str | None, analysis_id: str, score: int) -> None:
        self.notify(
            user_id=user_id,
            user_email=user_email,
            kind="high_risk",
            title="Warning: suspicious recruitment opportunity detected",
            body=(
                f"This recruitment opportunity contains multiple suspicious indicators "
                f"(risk score {score}/100). Review the investigation before proceeding."
            ),
            severity="high" if score < 80 else "critical",
            analysis_id=analysis_id,
            dedupe_key=f"high_risk:{analysis_id}",
            send_email=True,
        )

    def monitoring_notification(
        self,
        user_id: str,
        user_email: str | None,
        *,
        task_name: str,
        company: str,
        title: str,
        analysis_id: str | None = None,
    ) -> None:
        self.notify(
            user_id=user_id,
            user_email=user_email,
            kind="monitoring",
            title=f"New listing matching {task_name}",
            body=f"A new listing possibly associated with {company} was detected: {title}",
            severity="medium",
            analysis_id=analysis_id,
            dedupe_key=f"monitoring:{user_id}:{task_name}:{company}:{title}",
            send_email=True,
        )
