"""MacUX Notification Center — Notification dataclass and helpers.

All code here is pure Python (no GTK) so it can be tested without a display.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import IntEnum


class Urgency(IntEnum):
    LOW      = 0
    NORMAL   = 1
    CRITICAL = 2


# Reason codes for NotificationClosed signal (freedesktop spec §6.5)
CLOSE_REASON_EXPIRED    = 1
CLOSE_REASON_DISMISSED  = 2
CLOSE_REASON_REQUESTED  = 3
CLOSE_REASON_UNDEFINED  = 4

_MARKUP_RE = re.compile(r"<[^>]+>")


@dataclass
class Notification:
    """One desktop notification."""

    notif_id: int
    app_name: str
    app_icon: str
    summary: str
    body: str
    actions: list[str]
    hints: dict
    urgency: int = int(Urgency.NORMAL)
    expire_timeout: int = -1    # ms; -1 = default, 0 = never
    timestamp: float = field(default_factory=time.time)
    dismissed: bool = False

    def strip_markup(self) -> str:
        """Return *body* with HTML/markup tags removed."""
        return _MARKUP_RE.sub("", self.body)

    def short_body(self, max_chars: int = 100) -> str:
        """Body without markup, truncated to *max_chars*."""
        text = self.strip_markup()
        if len(text) > max_chars:
            return text[:max_chars] + "…"
        return text

    def icon_name_fallback(self) -> str:
        """Symbolic icon to use when app_icon is missing/not-a-path."""
        if self.urgency == int(Urgency.CRITICAL):
            return "dialog-warning-symbolic"
        if self.urgency == int(Urgency.LOW):
            return "dialog-information-symbolic"
        return "notification-symbolic"


def format_timestamp(timestamp: float, now: float | None = None) -> str:
    """
    Human-readable relative timestamp for notification cards.

    Returns one of: "Just now", "Xm ago", "Xh ago", "Yesterday", "Mon DD".
    """
    if now is None:
        now = time.time()
    diff = max(0.0, now - timestamp)
    if diff < 60:
        return "Just now"
    if diff < 3600:
        m = int(diff // 60)
        return f"{m}m ago"
    if diff < 86400:
        h = int(diff // 3600)
        return f"{h}h ago"
    if diff < 172800:
        return "Yesterday"
    import datetime
    return datetime.datetime.fromtimestamp(timestamp).strftime("%b %-d")
