"""Notification channels (console, email, Telegram) behind a common interface."""

from .base import Notification, NotificationChannel
from .channels import ConsoleChannel, EmailChannel, TelegramChannel, build_channels

__all__ = [
    "ConsoleChannel",
    "EmailChannel",
    "Notification",
    "NotificationChannel",
    "TelegramChannel",
    "build_channels",
]
