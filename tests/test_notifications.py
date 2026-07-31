"""Tests for notification channels and analytics edge cases."""

from __future__ import annotations

from jmi.analytics import AnalyticsEngine
from jmi.config import Settings
from jmi.infrastructure.notifications import (
    ConsoleChannel,
    EmailChannel,
    Notification,
    TelegramChannel,
    build_channels,
)


def test_console_channel_always_sends():
    channel = ConsoleChannel()
    assert channel.is_configured() is True
    assert channel.send(Notification("Subject", "Body")) is True


def test_email_channel_not_configured_when_no_host():
    channel = EmailChannel(Settings(smtp_host="", smtp_from="a@b.com"))
    assert channel.is_configured() is False
    assert channel.send(Notification("s", "b")) is False


def test_telegram_channel_not_configured_without_token():
    channel = TelegramChannel(Settings(telegram_bot_token="", telegram_chat_id=""))
    assert channel.is_configured() is False
    assert channel.send(Notification("s", "b")) is False


def test_build_channels_includes_console_by_default():
    channels = build_channels(Settings())
    assert any(isinstance(c, ConsoleChannel) for c in channels)
    # No SMTP/Telegram configured -> only console is active.
    assert all(c.is_configured() for c in channels)


def test_analytics_empty_dataset_is_safe():
    report = AnalyticsEngine([]).build_report()
    assert report.total_jobs == 0
    assert report.remote_percentage == 0.0
    assert report.top_skills == []
    assert report.salary_by_currency == []


def test_analytics_monthly_trend_counts_by_month():
    records = [
        {"posted_at": "2026-07-01", "skills": []},
        {"posted_at": "2026-07-15", "skills": []},
        {"posted_at": "2026-06-20", "skills": []},
    ]
    trend = {row["month"]: row["count"] for row in AnalyticsEngine(records).monthly_trend()}
    assert trend["2026-07"] == 2
    assert trend["2026-06"] == 1
