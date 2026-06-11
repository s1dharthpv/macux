"""MacUX Menu Bar — clock formatting.

All functions are pure: they take a datetime and return strings.
No GTK; fully testable without a display.
"""

from __future__ import annotations

import datetime


def format_time(dt: datetime.datetime, use_24h: bool = False) -> str:
    """
    Format the time portion of the menu bar clock.

    12h mode:  "3:04 PM"
    24h mode:  "15:04"
    """
    if use_24h:
        return dt.strftime("%H:%M")
    hour = dt.hour % 12 or 12
    minute = dt.strftime("%M")
    am_pm = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{minute} {am_pm}"


def format_date(dt: datetime.datetime) -> str:
    """Short date for the menu bar: "Tue Jun 10"."""
    # %-d = day without leading zero (Linux strftime)
    return dt.strftime("%a %b %-d")


def format_full(dt: datetime.datetime, use_24h: bool = False) -> str:
    """Combined date + time label: "Tue Jun 10  3:04 PM"."""
    return f"{format_date(dt)}  {format_time(dt, use_24h)}"


def format_tooltip(dt: datetime.datetime) -> str:
    """Expanded tooltip date: "Tuesday, June 10, 2026"."""
    return dt.strftime("%A, %B %-d, %Y")
