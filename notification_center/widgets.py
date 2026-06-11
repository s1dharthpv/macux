# Copyright (C) 2026 Sidharth Thamban <sidharth.thamban@gmail.com>
"""MacUX Notification Center — calendar and date display widget state.

Pure Python dataclasses that represent widget state.  No GTK, no DBus.
"""

from __future__ import annotations

import calendar
import dataclasses
from datetime import date
from typing import Optional


@dataclasses.dataclass
class CalendarDay:
    """State for a single cell in the calendar grid."""

    date: int          # day of month (1–31)
    month_offset: int  # 0 = current month, -1 = previous, +1 = next
    is_today: bool
    is_selected: bool
    has_events: bool   # placeholder for future event integration


@dataclasses.dataclass
class CalendarMonth:
    """Full calendar grid for one month.

    ``weeks`` is always exactly 6 rows × 7 columns (ISO Mon-first).
    Cells outside the current month carry ``month_offset != 0``.
    """

    year: int
    month: int          # 1–12
    weeks: list[list[CalendarDay]]  # 6 rows × 7 cols

    @property
    def month_name(self) -> str:
        """Human-readable header, e.g. "June 2026"."""
        return date(self.year, self.month, 1).strftime("%B %Y")

    @classmethod
    def build(
        cls,
        year: int,
        month: int,
        today: Optional[date] = None,
    ) -> CalendarMonth:
        """Build a CalendarMonth for the given year/month.

        * Monday = column 0 (ISO week).
        * Always 6 rows × 7 columns; cells outside the current month
          are filled with days from the previous/next month and carry
          ``month_offset`` of -1 or +1.
        * ``is_today`` is set using *today* (defaults to ``date.today()``).
        * ``is_selected`` and ``has_events`` are always False.
        """
        if today is None:
            today = date.today()

        # calendar.monthcalendar returns up to 6 rows with Mon-first (default).
        # calendar module uses Monday=0 by default when we use
        # calendar.Calendar(firstweekday=0).
        cal = calendar.Calendar(firstweekday=0)  # 0 = Monday
        month_matrix = cal.monthdatescalendar(year, month)  # list of lists of date objects

        # Pad to exactly 6 rows (monthdatescalendar can return 4 or 5 rows for
        # some months; we always want 6 for a fixed-height grid).
        while len(month_matrix) < 6:
            last_row = month_matrix[-1]
            # Extend by one week from the last row
            next_week = [d.replace(day=d.day) for d in last_row]
            # Actually compute the dates properly
            from datetime import timedelta
            next_week = [last_row[-1] + timedelta(days=i + 1) for i in range(7)]
            month_matrix.append(next_week)

        weeks: list[list[CalendarDay]] = []
        for row in month_matrix[:6]:
            week: list[CalendarDay] = []
            for d in row:
                if d.month < month or (d.month == 12 and month == 1):
                    offset = -1
                elif d.month > month or (d.month == 1 and month == 12):
                    offset = 1
                else:
                    offset = 0
                week.append(
                    CalendarDay(
                        date=d.day,
                        month_offset=offset,
                        is_today=(d == today),
                        is_selected=False,
                        has_events=False,
                    )
                )
            weeks.append(week)

        return cls(year=year, month=month, weeks=weeks)


# ── Convenience helpers ────────────────────────────────────────────────────────


def build_calendar_month(
    year: int,
    month: int,
    today: Optional[date] = None,
) -> CalendarMonth:
    """Convenience wrapper for CalendarMonth.build()."""
    return CalendarMonth.build(year, month, today=today)


def navigate_month(cal: CalendarMonth, delta: int) -> CalendarMonth:
    """Return a new CalendarMonth shifted by *delta* months.

    Handles year wrap-around in both directions.
    """
    total_months = cal.year * 12 + (cal.month - 1) + delta
    new_year, new_month_0 = divmod(total_months, 12)
    return CalendarMonth.build(new_year, new_month_0 + 1)
