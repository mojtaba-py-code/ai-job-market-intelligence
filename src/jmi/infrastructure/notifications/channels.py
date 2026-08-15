"""Concrete notification channels.

Channels degrade gracefully: if a channel is not configured it reports
``is_configured() == False`` and is skipped, so the platform never crashes for
lack of SMTP/Telegram credentials in development.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

import httpx

from ...config import Settings, get_settings
from ...logging import get_logger
from .base import Notification, NotificationChannel

logger = get_logger(__name__)


class ConsoleChannel(NotificationChannel):
    """Always-available channel that logs the notification."""

    name = "console"

    def is_configured(self) -> bool:
        return True

    def send(self, notification: Notification) -> bool:
        logger.info("notification", subject=notification.subject, body=notification.body)
        return True


class EmailChannel(NotificationChannel):
    name = "email"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def is_configured(self) -> bool:
        return bool(self.settings.smtp_host and self.settings.smtp_from)

    def send(self, notification: Notification) -> bool:
        if not self.is_configured():
            return False
        message = EmailMessage()
        message["Subject"] = notification.subject
        message["From"] = self.settings.smtp_from
        message["To"] = self.settings.smtp_from
        message.set_content(notification.body)
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as smtp:
                # Refuse to authenticate over a plaintext link: without this the
                # credentials would go out in the clear if STARTTLS is missing.
                smtp.starttls()
                if self.settings.smtp_username:
                    smtp.login(
                        self.settings.smtp_username,
                        self.settings.smtp_password.get_secret_value(),
                    )
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("email_send_failed", error=str(exc))
            return False
        return True


class TelegramChannel(NotificationChannel):
    name = "telegram"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def is_configured(self) -> bool:
        return bool(
            self.settings.telegram_bot_token.get_secret_value() and self.settings.telegram_chat_id
        )

    def send(self, notification: Notification) -> bool:
        if not self.is_configured():
            return False
        # The bot token sits in the path, so this URL is itself a credential —
        # it is built at the call site and never logged.
        token = self.settings.telegram_bot_token.get_secret_value()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": self.settings.telegram_chat_id,
            "text": f"*{notification.subject}*\n{notification.body}",
            "parse_mode": "Markdown",
        }
        try:
            response = httpx.post(url, json=payload, timeout=15)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("telegram_send_failed", error=str(exc))
            return False
        return True


def build_channels(settings: Settings | None = None) -> list[NotificationChannel]:
    """Return all configured channels (console is always included)."""
    settings = settings or get_settings()
    candidates: list[NotificationChannel] = [
        ConsoleChannel(),
        EmailChannel(settings),
        TelegramChannel(settings),
    ]
    return [c for c in candidates if c.is_configured()]
