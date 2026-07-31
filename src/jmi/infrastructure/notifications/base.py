"""Notification abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class Notification:
    """A message to deliver over one or more channels."""

    subject: str
    body: str


class NotificationChannel(ABC):
    """A delivery channel (email, Telegram, console, ...)."""

    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Return whether the channel has the settings it needs to send."""

    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """Deliver *notification*. Return ``True`` on success."""
