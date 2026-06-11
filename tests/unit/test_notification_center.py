"""Unit tests for Phase 9 — MacUX Notification Center.

Coverage:
  - Urgency enum values
  - CLOSE_REASON constants
  - Notification: strip_markup, short_body (truncate/no-truncate), icon_name_fallback, urgency default
  - format_timestamp: just-now / minutes / hours / yesterday / old date
  - NotificationPersistence: save, get_all ordering, dismiss, undismiss,
    clear_all, delete, delete_all, get_count, get_undismissed_count, exists,
    max_count eviction, replaces existing ID
  - _extract_urgency: default, explicit value, GLib.Variant wrapper
  - FreedesktopNotificationsInterface: next_id incrementing, replaces_id,
    on_notify callback, GetCapabilities, GetServerInformation
  - NotificationCenterInterface: visible/show/hide/toggle, GetCount,
    Clear, notify_notification_added, count_cb / clear_cb wiring
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock


# ══════════════════════════════════════════════════════════════════════════════
# Urgency + close reason constants
# ══════════════════════════════════════════════════════════════════════════════

class TestUrgency:
    def test_low_value(self):
        from notification_center.notification import Urgency
        assert int(Urgency.LOW) == 0

    def test_normal_value(self):
        from notification_center.notification import Urgency
        assert int(Urgency.NORMAL) == 1

    def test_critical_value(self):
        from notification_center.notification import Urgency
        assert int(Urgency.CRITICAL) == 2


class TestCloseReasons:
    def test_expired(self):
        from notification_center.notification import CLOSE_REASON_EXPIRED
        assert CLOSE_REASON_EXPIRED == 1

    def test_dismissed(self):
        from notification_center.notification import CLOSE_REASON_DISMISSED
        assert CLOSE_REASON_DISMISSED == 2

    def test_requested(self):
        from notification_center.notification import CLOSE_REASON_REQUESTED
        assert CLOSE_REASON_REQUESTED == 3

    def test_undefined(self):
        from notification_center.notification import CLOSE_REASON_UNDEFINED
        assert CLOSE_REASON_UNDEFINED == 4


# ══════════════════════════════════════════════════════════════════════════════
# Notification dataclass
# ══════════════════════════════════════════════════════════════════════════════

def _notif(**kwargs):
    from notification_center.notification import Notification
    defaults = dict(
        notif_id=1, app_name="TestApp", app_icon="",
        summary="Test", body="Test body", actions=[], hints={},
    )
    defaults.update(kwargs)
    return Notification(**defaults)


class TestNotification:
    def test_strip_markup_removes_tags(self):
        n = _notif(body="<b>Bold</b> and <i>italic</i>")
        assert n.strip_markup() == "Bold and italic"

    def test_strip_markup_no_tags(self):
        n = _notif(body="Plain text")
        assert n.strip_markup() == "Plain text"

    def test_strip_markup_nested_tags(self):
        n = _notif(body="<a href='x'><b>Link</b></a>")
        assert n.strip_markup() == "Link"

    def test_short_body_no_truncation(self):
        n = _notif(body="Short body")
        assert n.short_body(100) == "Short body"

    def test_short_body_truncates(self):
        n = _notif(body="A" * 110)
        result = n.short_body(100)
        assert result.endswith("…")
        assert len(result) == 101  # 100 chars + ellipsis

    def test_short_body_strips_markup(self):
        n = _notif(body="<b>Bold</b> text")
        assert n.short_body(100) == "Bold text"

    def test_urgency_default_normal(self):
        from notification_center.notification import Urgency
        n = _notif()
        assert n.urgency == int(Urgency.NORMAL)

    def test_icon_name_fallback_critical(self):
        from notification_center.notification import Urgency
        n = _notif(urgency=int(Urgency.CRITICAL))
        assert n.icon_name_fallback() == "dialog-warning-symbolic"

    def test_icon_name_fallback_low(self):
        from notification_center.notification import Urgency
        n = _notif(urgency=int(Urgency.LOW))
        assert n.icon_name_fallback() == "dialog-information-symbolic"

    def test_icon_name_fallback_normal(self):
        from notification_center.notification import Urgency
        n = _notif(urgency=int(Urgency.NORMAL))
        assert n.icon_name_fallback() == "notification-symbolic"

    def test_dismissed_default_false(self):
        assert _notif().dismissed is False

    def test_actions_stored(self):
        n = _notif(actions=["default", "Open", "close", "Close"])
        assert n.actions == ["default", "Open", "close", "Close"]


# ══════════════════════════════════════════════════════════════════════════════
# format_timestamp
# ══════════════════════════════════════════════════════════════════════════════

class TestFormatTimestamp:
    def test_just_now(self):
        from notification_center.notification import format_timestamp
        now = time.time()
        assert format_timestamp(now - 30, now=now) == "Just now"

    def test_just_now_zero_diff(self):
        from notification_center.notification import format_timestamp
        now = time.time()
        assert format_timestamp(now, now=now) == "Just now"

    def test_minutes_ago(self):
        from notification_center.notification import format_timestamp
        now = time.time()
        assert format_timestamp(now - 300, now=now) == "5m ago"

    def test_one_minute_ago(self):
        from notification_center.notification import format_timestamp
        now = time.time()
        assert format_timestamp(now - 60, now=now) == "1m ago"

    def test_hours_ago(self):
        from notification_center.notification import format_timestamp
        now = time.time()
        assert format_timestamp(now - 7200, now=now) == "2h ago"

    def test_one_hour_ago(self):
        from notification_center.notification import format_timestamp
        now = time.time()
        assert format_timestamp(now - 3600, now=now) == "1h ago"

    def test_yesterday(self):
        from notification_center.notification import format_timestamp
        now = time.time()
        assert format_timestamp(now - 86400 * 1.5, now=now) == "Yesterday"

    def test_old_date_format(self):
        from notification_center.notification import format_timestamp
        import datetime
        dt = datetime.datetime(2026, 3, 15, 9, 0)
        ts = dt.timestamp()
        now = dt.timestamp() + 86400 * 10  # 10 days later
        result = format_timestamp(ts, now=now)
        assert "Mar" in result
        assert "15" in result

    def test_boundary_59_seconds(self):
        from notification_center.notification import format_timestamp
        now = time.time()
        assert format_timestamp(now - 59, now=now) == "Just now"

    def test_boundary_60_seconds(self):
        from notification_center.notification import format_timestamp
        now = time.time()
        assert format_timestamp(now - 60, now=now) == "1m ago"


# ══════════════════════════════════════════════════════════════════════════════
# NotificationPersistence
# ══════════════════════════════════════════════════════════════════════════════

class TestNotificationPersistence:
    def _db(self, tmp_path, max_count=100):
        from notification_center.persistence import NotificationPersistence
        return NotificationPersistence(tmp_path / "notif.db", max_count=max_count)

    def test_save_and_get_all(self, tmp_path):
        db = self._db(tmp_path)
        n = _notif(notif_id=1, summary="Hello")
        db.save(n)
        rows = db.get_all()
        assert len(rows) == 1
        assert rows[0].summary == "Hello"

    def test_get_all_empty(self, tmp_path):
        db = self._db(tmp_path)
        assert db.get_all() == []

    def test_get_all_ordered_newest_first(self, tmp_path):
        db = self._db(tmp_path)
        now = time.time()
        db.save(_notif(notif_id=1, summary="Old", timestamp=now - 100))
        db.save(_notif(notif_id=2, summary="New", timestamp=now))
        rows = db.get_all()
        assert rows[0].summary == "New"
        assert rows[1].summary == "Old"

    def test_dismiss_sets_flag(self, tmp_path):
        db = self._db(tmp_path)
        db.save(_notif(notif_id=5))
        db.dismiss(5)
        rows = db.get_all()
        assert rows[0].dismissed is True

    def test_undismiss_clears_flag(self, tmp_path):
        db = self._db(tmp_path)
        db.save(_notif(notif_id=5))
        db.dismiss(5)
        db.undismiss(5)
        rows = db.get_all()
        assert rows[0].dismissed is False

    def test_get_all_exclude_dismissed(self, tmp_path):
        db = self._db(tmp_path)
        db.save(_notif(notif_id=1))
        db.save(_notif(notif_id=2))
        db.dismiss(1)
        undismissed = db.get_all(include_dismissed=False)
        assert len(undismissed) == 1
        assert undismissed[0].notif_id == 2

    def test_clear_all_dismisses_all(self, tmp_path):
        db = self._db(tmp_path)
        db.save(_notif(notif_id=1))
        db.save(_notif(notif_id=2))
        db.clear_all()
        assert db.get_undismissed_count() == 0

    def test_delete_removes_row(self, tmp_path):
        db = self._db(tmp_path)
        db.save(_notif(notif_id=3))
        db.delete(3)
        assert not db.exists(3)

    def test_delete_all_empties_table(self, tmp_path):
        db = self._db(tmp_path)
        db.save(_notif(notif_id=1))
        db.save(_notif(notif_id=2))
        db.delete_all()
        assert db.get_count() == 0

    def test_get_count(self, tmp_path):
        db = self._db(tmp_path)
        db.save(_notif(notif_id=1))
        db.save(_notif(notif_id=2))
        assert db.get_count() == 2

    def test_get_undismissed_count(self, tmp_path):
        db = self._db(tmp_path)
        db.save(_notif(notif_id=1))
        db.save(_notif(notif_id=2))
        db.dismiss(1)
        assert db.get_undismissed_count() == 1

    def test_exists_true(self, tmp_path):
        db = self._db(tmp_path)
        db.save(_notif(notif_id=7))
        assert db.exists(7) is True

    def test_exists_false(self, tmp_path):
        db = self._db(tmp_path)
        assert db.exists(99) is False

    def test_max_count_evicts_oldest(self, tmp_path):
        db = self._db(tmp_path, max_count=3)
        now = time.time()
        for i in range(1, 6):
            db.save(_notif(notif_id=i, timestamp=now + i))
        assert db.get_count() == 3
        rows = db.get_all()
        ids = {r.notif_id for r in rows}
        # Oldest (id 1, 2) should be evicted; newest (3, 4, 5) should remain
        assert 1 not in ids
        assert 2 not in ids
        assert 5 in ids

    def test_save_replaces_existing_id(self, tmp_path):
        db = self._db(tmp_path)
        db.save(_notif(notif_id=10, summary="Original"))
        db.save(_notif(notif_id=10, summary="Replaced"))
        rows = db.get_all()
        assert len(rows) == 1
        assert rows[0].summary == "Replaced"

    def test_urgency_persisted(self, tmp_path):
        from notification_center.notification import Urgency
        db = self._db(tmp_path)
        db.save(_notif(notif_id=1, urgency=int(Urgency.CRITICAL)))
        rows = db.get_all()
        assert rows[0].urgency == int(Urgency.CRITICAL)

    def test_body_persisted(self, tmp_path):
        db = self._db(tmp_path)
        db.save(_notif(notif_id=1, body="Some long body text here"))
        rows = db.get_all()
        assert rows[0].body == "Some long body text here"

    def test_survive_reopen(self, tmp_path):
        from notification_center.persistence import NotificationPersistence
        path = tmp_path / "notif.db"
        db1 = NotificationPersistence(path)
        db1.save(_notif(notif_id=1, summary="Persist me"))
        db2 = NotificationPersistence(path)
        rows = db2.get_all()
        assert len(rows) == 1
        assert rows[0].summary == "Persist me"


# ══════════════════════════════════════════════════════════════════════════════
# _extract_urgency
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractUrgency:
    def test_empty_hints_default_normal(self):
        from notification_center.fd_notifications import _extract_urgency
        from notification_center.notification import Urgency
        assert _extract_urgency({}) == int(Urgency.NORMAL)

    def test_explicit_low(self):
        from notification_center.fd_notifications import _extract_urgency
        from notification_center.notification import Urgency
        assert _extract_urgency({"urgency": 0}) == int(Urgency.LOW)

    def test_explicit_critical(self):
        from notification_center.fd_notifications import _extract_urgency
        from notification_center.notification import Urgency
        assert _extract_urgency({"urgency": 2}) == int(Urgency.CRITICAL)

    def test_glib_variant_unwrapped(self):
        from notification_center.fd_notifications import _extract_urgency
        from notification_center.notification import Urgency

        class FakeVariant:
            def unpack(self): return 2

        assert _extract_urgency({"urgency": FakeVariant()}) == int(Urgency.CRITICAL)

    def test_none_hints_key(self):
        from notification_center.fd_notifications import _extract_urgency
        from notification_center.notification import Urgency
        assert _extract_urgency({"urgency": None}) == int(Urgency.NORMAL)


# ══════════════════════════════════════════════════════════════════════════════
# FreedesktopNotificationsInterface
# ══════════════════════════════════════════════════════════════════════════════

def _make_fd_iface(on_notify=None, on_close=None):
    from notification_center.fd_notifications import FreedesktopNotificationsInterface
    return FreedesktopNotificationsInterface(
        on_notify=on_notify or MagicMock(),
        on_close=on_close or MagicMock(),
    )


class TestFreedesktopNotificationsInterface:
    def test_notify_returns_incremented_id(self):
        iface = _make_fd_iface()
        id1 = iface.Notify("App", 0, "", "Hello", "", [], {}, -1)
        id2 = iface.Notify("App", 0, "", "World", "", [], {}, -1)
        assert int(id2) == int(id1) + 1

    def test_notify_first_id_is_1(self):
        iface = _make_fd_iface()
        nid = iface.Notify("App", 0, "", "Test", "", [], {}, -1)
        assert int(nid) == 1

    def test_notify_replaces_id(self):
        iface = _make_fd_iface()
        iface.Notify("App", 0, "", "Original", "", [], {}, -1)
        replaced_id = iface.Notify("App", 1, "", "Replaced", "", [], {}, -1)
        assert int(replaced_id) == 1

    def test_notify_invokes_on_notify(self):
        on_notify = MagicMock()
        iface = _make_fd_iface(on_notify=on_notify)
        iface.Notify("Firefox", 0, "firefox", "New Tab", "Page loaded", [], {}, 3000)
        on_notify.assert_called_once()
        notif = on_notify.call_args[0][0]
        assert notif.app_name == "Firefox"
        assert notif.summary == "New Tab"
        assert notif.body == "Page loaded"

    def test_notify_parses_urgency_from_hints(self):
        from notification_center.notification import Urgency
        on_notify = MagicMock()
        iface = _make_fd_iface(on_notify=on_notify)
        iface.Notify("App", 0, "", "Alert", "", [], {"urgency": 2}, -1)
        notif = on_notify.call_args[0][0]
        assert notif.urgency == int(Urgency.CRITICAL)

    def test_notify_sets_expire_timeout(self):
        on_notify = MagicMock()
        iface = _make_fd_iface(on_notify=on_notify)
        iface.Notify("App", 0, "", "Msg", "", [], {}, 5000)
        notif = on_notify.call_args[0][0]
        assert notif.expire_timeout == 5000

    def test_get_capabilities_returns_list(self):
        iface = _make_fd_iface()
        caps = iface.GetCapabilities()
        assert isinstance(caps, list)
        assert "body" in caps
        assert "actions" in caps

    def test_get_server_information_tuple(self):
        iface = _make_fd_iface()
        info = iface.GetServerInformation()
        assert len(info) == 4
        name, vendor, version, spec = info
        assert "MacUX" in name
        assert spec == "1.2"

    def test_close_notification_invokes_on_close(self):
        on_close = MagicMock()
        iface = _make_fd_iface(on_close=on_close)
        iface.Notify("App", 0, "", "Test", "", [], {}, -1)
        iface.CloseNotification(1)
        on_close.assert_called_once()
        notif_id, reason = on_close.call_args[0]
        assert notif_id == 1

    def test_notify_next_id_not_reset_by_replaces(self):
        iface = _make_fd_iface()
        iface.Notify("App", 0, "", "A", "", [], {}, -1)  # id=1
        iface.Notify("App", 1, "", "B", "", [], {}, -1)  # replaces id=1
        new_id = iface.Notify("App", 0, "", "C", "", [], {}, -1)  # fresh
        assert int(new_id) == 2  # next_id incremented only for non-replace


# ══════════════════════════════════════════════════════════════════════════════
# NotificationCenterInterface
# ══════════════════════════════════════════════════════════════════════════════

def _make_nc_iface(show_cb=None, hide_cb=None, clear_cb=None, count_cb=None):
    from notification_center.notification_center_dbus import NotificationCenterInterface
    return NotificationCenterInterface(
        show_cb=show_cb or MagicMock(),
        hide_cb=hide_cb or MagicMock(),
        clear_cb=clear_cb,
        count_cb=count_cb,
    )


class TestNotificationCenterInterface:
    def test_visible_false_by_default(self):
        iface = _make_nc_iface()
        assert iface.Visible is False

    def test_show_sets_visible(self):
        show_cb = MagicMock()
        iface = _make_nc_iface(show_cb=show_cb)
        iface.Show()
        assert iface.Visible is True
        show_cb.assert_called_once()

    def test_hide_sets_invisible(self):
        hide_cb = MagicMock()
        iface = _make_nc_iface(hide_cb=hide_cb)
        iface.Show()
        iface.Hide()
        assert iface.Visible is False
        hide_cb.assert_called_once()

    def test_toggle_hidden_to_visible(self):
        show_cb = MagicMock()
        iface = _make_nc_iface(show_cb=show_cb)
        iface.Toggle()
        assert iface.Visible is True

    def test_toggle_visible_to_hidden(self):
        hide_cb = MagicMock()
        iface = _make_nc_iface(hide_cb=hide_cb)
        iface.Show()
        iface.Toggle()
        assert iface.Visible is False

    def test_get_count_no_cb_returns_zero(self):
        iface = _make_nc_iface()
        assert int(iface.GetCount()) == 0

    def test_get_count_uses_count_cb(self):
        iface = _make_nc_iface(count_cb=lambda: 7)
        assert int(iface.GetCount()) == 7

    def test_clear_invokes_clear_cb(self):
        clear_cb = MagicMock()
        iface = _make_nc_iface(clear_cb=clear_cb)
        iface.Clear()
        clear_cb.assert_called_once()

    def test_clear_no_cb_does_not_raise(self):
        iface = _make_nc_iface(clear_cb=None)
        iface.Clear()  # must not raise

    def test_notify_notification_added_updates_nothing_visible(self):
        iface = _make_nc_iface()
        iface.notify_notification_added(5, "App", "Summary")
        # No assertion needed; just must not raise

    def test_show_hide_sequence(self):
        show_cb = MagicMock()
        hide_cb = MagicMock()
        iface = _make_nc_iface(show_cb=show_cb, hide_cb=hide_cb)
        iface.Show()
        iface.Hide()
        iface.Show()
        assert show_cb.call_count == 2
        assert hide_cb.call_count == 1

    def test_multiple_toggles(self):
        iface = _make_nc_iface()
        for expected in [True, False, True, False]:
            iface.Toggle()
            assert iface.Visible is expected
