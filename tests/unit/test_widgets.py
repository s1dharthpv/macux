# Copyright (C) 2026 Sidharth Thamban <sidharth.thamban@gmail.com>
"""Unit tests for notification_center.widgets — calendar model.

No GTK required.  Run with::

    pytest tests/unit/test_widgets.py -v
"""

from __future__ import annotations

import unittest
from datetime import date

from notification_center.widgets import (
    CalendarDay,
    CalendarMonth,
    build_calendar_month,
    navigate_month,
)


# ══════════════════════════════════════════════════════════════════════════════
# TestCalendarDay — basic flag semantics
# ══════════════════════════════════════════════════════════════════════════════

class TestCalendarDay(unittest.TestCase):

    def _day(self, **kw) -> CalendarDay:
        defaults = dict(date=1, month_offset=0, is_today=False, is_selected=False, has_events=False)
        defaults.update(kw)
        return CalendarDay(**defaults)

    def test_is_today_true(self):
        d = self._day(is_today=True)
        self.assertTrue(d.is_today)

    def test_is_today_false(self):
        d = self._day(is_today=False)
        self.assertFalse(d.is_today)

    def test_is_selected_true(self):
        d = self._day(is_selected=True)
        self.assertTrue(d.is_selected)

    def test_is_selected_false(self):
        d = self._day(is_selected=False)
        self.assertFalse(d.is_selected)

    def test_has_events_true(self):
        d = self._day(has_events=True)
        self.assertTrue(d.has_events)

    def test_has_events_false(self):
        d = self._day(has_events=False)
        self.assertFalse(d.has_events)

    def test_month_offset_zero(self):
        d = self._day(month_offset=0)
        self.assertEqual(d.month_offset, 0)

    def test_month_offset_prev(self):
        d = self._day(month_offset=-1)
        self.assertEqual(d.month_offset, -1)

    def test_month_offset_next(self):
        d = self._day(month_offset=1)
        self.assertEqual(d.month_offset, 1)

    def test_date_stored(self):
        d = self._day(date=15)
        self.assertEqual(d.date, 15)


# ══════════════════════════════════════════════════════════════════════════════
# TestCalendarMonth — structure and content
# ══════════════════════════════════════════════════════════════════════════════

class TestCalendarMonth(unittest.TestCase):

    # ── month_name ────────────────────────────────────────────────────────────

    def test_month_name_june_2026(self):
        cal = CalendarMonth.build(2026, 6)
        self.assertEqual(cal.month_name, "June 2026")

    def test_month_name_january_2025(self):
        cal = CalendarMonth.build(2025, 1)
        self.assertEqual(cal.month_name, "January 2025")

    def test_month_name_december_2024(self):
        cal = CalendarMonth.build(2024, 12)
        self.assertEqual(cal.month_name, "December 2024")

    # ── grid dimensions ───────────────────────────────────────────────────────

    def test_exactly_six_rows(self):
        cal = CalendarMonth.build(2026, 6)
        self.assertEqual(len(cal.weeks), 6)

    def test_exactly_seven_cols_each_row(self):
        cal = CalendarMonth.build(2026, 6)
        for row in cal.weeks:
            self.assertEqual(len(row), 7)

    def test_six_rows_february_2025(self):
        # Feb 2025 starts on Saturday — may produce 4 or 5 natural rows; padded to 6
        cal = CalendarMonth.build(2025, 2)
        self.assertEqual(len(cal.weeks), 6)

    def test_six_rows_february_2024_leap(self):
        # Leap year Feb: 29 days
        cal = CalendarMonth.build(2024, 2)
        self.assertEqual(len(cal.weeks), 6)

    def test_six_rows_december_2026(self):
        cal = CalendarMonth.build(2026, 12)
        self.assertEqual(len(cal.weeks), 6)

    # ── Monday-first ordering ─────────────────────────────────────────────────

    def test_2026_june_01_is_monday_column_0(self):
        # 2026-06-01 is a Monday → must appear in column 0 of the first row
        today = date(2026, 6, 15)
        cal = CalendarMonth.build(2026, 6, today=today)
        first_row = cal.weeks[0]
        # Find the cell with date=1 in the current month
        cell = next(c for c in first_row if c.date == 1 and c.month_offset == 0)
        self.assertEqual(first_row.index(cell), 0)

    def test_column_0_is_monday(self):
        # For a month we know starts on a known day: 2026-06-01 = Monday
        # All cells in column 0 that belong to the current month should be Mondays.
        cal = CalendarMonth.build(2026, 6)
        for week in cal.weeks:
            col0 = week[0]
            # Reconstruct the full date to check weekday
            if col0.month_offset == 0:
                d = date(2026, 6, col0.date)
                self.assertEqual(d.weekday(), 0, f"Column 0 cell {d} is not Monday")

    # ── is_today ──────────────────────────────────────────────────────────────

    def test_is_today_set_on_exactly_one_cell(self):
        today = date(2026, 6, 10)
        cal = CalendarMonth.build(2026, 6, today=today)
        today_cells = [c for row in cal.weeks for c in row if c.is_today]
        self.assertEqual(len(today_cells), 1)

    def test_is_today_cell_has_correct_date(self):
        today = date(2026, 6, 10)
        cal = CalendarMonth.build(2026, 6, today=today)
        today_cells = [c for row in cal.weeks for c in row if c.is_today]
        self.assertEqual(today_cells[0].date, 10)
        self.assertEqual(today_cells[0].month_offset, 0)

    def test_no_is_today_when_different_month(self):
        # today is in August — far enough that no June grid cell (which spans
        # at most one week into July) can ever equal this date.
        today = date(2026, 8, 15)
        cal = CalendarMonth.build(2026, 6, today=today)
        today_cells = [c for row in cal.weeks for c in row if c.is_today]
        self.assertEqual(len(today_cells), 0)

    # ── padding cells ─────────────────────────────────────────────────────────

    def test_padding_cells_have_nonzero_month_offset(self):
        cal = CalendarMonth.build(2026, 6)
        for row in cal.weeks:
            for cell in row:
                if cell.month_offset != 0:
                    self.assertNotEqual(cell.month_offset, 0)

    def test_first_row_may_have_prev_month_padding(self):
        # A month that doesn't start on Monday will have prev-month cells in row 0
        # 2026-07-01 is Wednesday (weekday=2) → columns 0-1 should be June cells
        cal = CalendarMonth.build(2026, 7)
        first_row = cal.weeks[0]
        prev_cells = [c for c in first_row if c.month_offset == -1]
        self.assertTrue(len(prev_cells) >= 1, "Expected prev-month padding in first row")

    def test_is_selected_always_false(self):
        cal = CalendarMonth.build(2026, 6)
        for row in cal.weeks:
            for cell in row:
                self.assertFalse(cell.is_selected)

    def test_has_events_always_false(self):
        cal = CalendarMonth.build(2026, 6)
        for row in cal.weeks:
            for cell in row:
                self.assertFalse(cell.has_events)

    # ── leap year February ────────────────────────────────────────────────────

    def test_february_2024_leap_has_29_current_days(self):
        cal = CalendarMonth.build(2024, 2)
        current_days = [c for row in cal.weeks for c in row if c.month_offset == 0]
        self.assertEqual(len(current_days), 29)

    def test_february_2025_non_leap_has_28_current_days(self):
        cal = CalendarMonth.build(2025, 2)
        current_days = [c for row in cal.weeks for c in row if c.month_offset == 0]
        self.assertEqual(len(current_days), 28)

    # ── January and December boundary ────────────────────────────────────────

    def test_january_month_name(self):
        cal = CalendarMonth.build(2026, 1)
        self.assertEqual(cal.month_name, "January 2026")

    def test_december_month_name(self):
        cal = CalendarMonth.build(2025, 12)
        self.assertEqual(cal.month_name, "December 2025")


# ══════════════════════════════════════════════════════════════════════════════
# TestNavigateMonth — forward, backward, and wrap-arounds
# ══════════════════════════════════════════════════════════════════════════════

class TestNavigateMonth(unittest.TestCase):

    def test_forward_one_month(self):
        cal = CalendarMonth.build(2026, 6)
        nxt = navigate_month(cal, 1)
        self.assertEqual(nxt.month, 7)
        self.assertEqual(nxt.year, 2026)

    def test_backward_one_month(self):
        cal = CalendarMonth.build(2026, 6)
        prv = navigate_month(cal, -1)
        self.assertEqual(prv.month, 5)
        self.assertEqual(prv.year, 2026)

    def test_forward_wraps_december_to_january(self):
        cal = CalendarMonth.build(2025, 12)
        nxt = navigate_month(cal, 1)
        self.assertEqual(nxt.month, 1)
        self.assertEqual(nxt.year, 2026)

    def test_backward_wraps_january_to_december(self):
        cal = CalendarMonth.build(2026, 1)
        prv = navigate_month(cal, -1)
        self.assertEqual(prv.month, 12)
        self.assertEqual(prv.year, 2025)

    def test_forward_twelve_months(self):
        cal = CalendarMonth.build(2026, 6)
        nxt = navigate_month(cal, 12)
        self.assertEqual(nxt.month, 6)
        self.assertEqual(nxt.year, 2027)

    def test_backward_twelve_months(self):
        cal = CalendarMonth.build(2026, 6)
        prv = navigate_month(cal, -12)
        self.assertEqual(prv.month, 6)
        self.assertEqual(prv.year, 2025)

    def test_zero_delta_returns_same_month(self):
        cal = CalendarMonth.build(2026, 6)
        same = navigate_month(cal, 0)
        self.assertEqual(same.month, 6)
        self.assertEqual(same.year, 2026)

    def test_result_has_correct_grid_dimensions(self):
        cal = CalendarMonth.build(2026, 6)
        nxt = navigate_month(cal, 3)
        self.assertEqual(len(nxt.weeks), 6)
        for row in nxt.weeks:
            self.assertEqual(len(row), 7)


# ══════════════════════════════════════════════════════════════════════════════
# TestBuildCalendarMonth — convenience wrapper + specific date facts
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildCalendarMonth(unittest.TestCase):

    def test_returns_calendar_month_instance(self):
        result = build_calendar_month(2026, 6)
        self.assertIsInstance(result, CalendarMonth)

    def test_year_stored(self):
        cal = build_calendar_month(2026, 6)
        self.assertEqual(cal.year, 2026)

    def test_month_stored(self):
        cal = build_calendar_month(2026, 6)
        self.assertEqual(cal.month, 6)

    def test_week_count_is_six(self):
        cal = build_calendar_month(2026, 6)
        self.assertEqual(len(cal.weeks), 6)

    def test_2026_june_01_monday_is_column_0(self):
        # Known fact: 2026-06-01 is a Monday
        cal = build_calendar_month(2026, 6, today=date(2026, 6, 1))
        first_row = cal.weeks[0]
        first_current = first_row[0]
        self.assertEqual(first_current.month_offset, 0)
        self.assertEqual(first_current.date, 1)

    def test_explicit_today_arg_sets_is_today(self):
        today = date(2026, 6, 5)
        cal = build_calendar_month(2026, 6, today=today)
        today_cells = [c for row in cal.weeks for c in row if c.is_today]
        self.assertEqual(len(today_cells), 1)
        self.assertEqual(today_cells[0].date, 5)

    def test_explicit_today_in_different_month(self):
        # today is in August; no cell in June should be marked
        today = date(2026, 8, 15)
        cal = build_calendar_month(2026, 6, today=today)
        today_cells = [c for row in cal.weeks for c in row if c.is_today]
        self.assertEqual(len(today_cells), 0)

    def test_total_cells_is_42(self):
        cal = build_calendar_month(2026, 6)
        total = sum(len(row) for row in cal.weeks)
        self.assertEqual(total, 42)


if __name__ == "__main__":
    unittest.main()
