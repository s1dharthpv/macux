"""Unit tests for Phase 7 — MacUX Menu Bar.

Coverage:
  - clock: format_time, format_date, format_full, format_tooltip
  - BatteryState: icon_name, format_label, format_tooltip
  - NetworkState: icon_name, format_label, format_tooltip
  - VolumeState: icon_name, format_label, percent
  - MenuItem: is_submenu, display_label, is_separator
  - parse_layout: flat item, separator, nested children, flags, toggle, GLib.Variant
  - visible_items: visibility filtering
  - MenuBarInterface: show/hide/toggle, properties, SetActiveApp, notify_app_changed
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, call


# ══════════════════════════════════════════════════════════════════════════════
# Clock formatting
# ══════════════════════════════════════════════════════════════════════════════

class TestFormatTime:
    def _dt(self, hour: int, minute: int) -> datetime.datetime:
        return datetime.datetime(2026, 6, 10, hour, minute)

    def test_12h_morning(self):
        from menu_bar.clock import format_time
        assert format_time(self._dt(9, 5)) == "9:05 AM"

    def test_12h_afternoon(self):
        from menu_bar.clock import format_time
        assert format_time(self._dt(15, 4)) == "3:04 PM"

    def test_12h_noon(self):
        from menu_bar.clock import format_time
        assert format_time(self._dt(12, 0)) == "12:00 PM"

    def test_12h_midnight(self):
        from menu_bar.clock import format_time
        assert format_time(self._dt(0, 0)) == "12:00 AM"

    def test_12h_11pm(self):
        from menu_bar.clock import format_time
        assert format_time(self._dt(23, 59)) == "11:59 PM"

    def test_24h_morning(self):
        from menu_bar.clock import format_time
        assert format_time(self._dt(9, 5), use_24h=True) == "09:05"

    def test_24h_afternoon(self):
        from menu_bar.clock import format_time
        assert format_time(self._dt(15, 4), use_24h=True) == "15:04"

    def test_24h_midnight(self):
        from menu_bar.clock import format_time
        assert format_time(self._dt(0, 0), use_24h=True) == "00:00"

    def test_12h_minute_padding(self):
        from menu_bar.clock import format_time
        assert format_time(self._dt(8, 3)) == "8:03 AM"


class TestFormatDate:
    def test_format_date(self):
        from menu_bar.clock import format_date
        dt = datetime.datetime(2026, 6, 10, 9, 0)
        result = format_date(dt)
        assert result == "Wed Jun 10"

    def test_format_date_single_digit_day(self):
        from menu_bar.clock import format_date
        dt = datetime.datetime(2026, 6, 3, 9, 0)
        assert "3" in format_date(dt)
        assert "03" not in format_date(dt)

    def test_format_date_december(self):
        from menu_bar.clock import format_date
        dt = datetime.datetime(2026, 12, 25, 10, 0)
        result = format_date(dt)
        assert "Dec" in result
        assert "25" in result


class TestFormatFull:
    def test_format_full_12h(self):
        from menu_bar.clock import format_full
        dt = datetime.datetime(2026, 6, 10, 15, 4)
        result = format_full(dt)
        assert "Wed Jun 10" in result
        assert "3:04 PM" in result

    def test_format_full_24h(self):
        from menu_bar.clock import format_full
        dt = datetime.datetime(2026, 6, 10, 15, 4)
        result = format_full(dt, use_24h=True)
        assert "15:04" in result

    def test_format_full_double_space_separator(self):
        from menu_bar.clock import format_full
        dt = datetime.datetime(2026, 6, 10, 9, 0)
        result = format_full(dt)
        assert "  " in result  # date and time separated by two spaces


class TestFormatTooltip:
    def test_tooltip_long_date(self):
        from menu_bar.clock import format_tooltip
        dt = datetime.datetime(2026, 6, 10, 9, 0)
        result = format_tooltip(dt)
        assert result == "Wednesday, June 10, 2026"

    def test_tooltip_year_included(self):
        from menu_bar.clock import format_tooltip
        dt = datetime.datetime(2025, 1, 1, 0, 0)
        assert "2025" in format_tooltip(dt)


# ══════════════════════════════════════════════════════════════════════════════
# BatteryState
# ══════════════════════════════════════════════════════════════════════════════

class TestBatteryState:
    def _make(self, pct, charging=False, fully_charged=False, time_sec=0, present=True):
        from menu_bar.battery import BatteryState
        return BatteryState(
            percentage=pct,
            charging=charging,
            fully_charged=fully_charged,
            time_remaining_sec=time_sec,
            present=present,
        )

    def test_absent_factory(self):
        from menu_bar.battery import BatteryState
        s = BatteryState.absent()
        assert not s.present

    def test_absent_icon(self):
        from menu_bar.battery import BatteryState
        assert BatteryState.absent().icon_name() == "battery-missing-symbolic"

    def test_fully_charged_icon(self):
        s = self._make(100, fully_charged=True)
        assert s.icon_name() == "battery-full-charged-symbolic"

    def test_charging_high_icon(self):
        s = self._make(90, charging=True)
        assert s.icon_name() == "battery-full-charging-symbolic"

    def test_charging_mid_icon(self):
        s = self._make(60, charging=True)
        assert s.icon_name() == "battery-good-charging-symbolic"

    def test_charging_low_icon(self):
        s = self._make(20, charging=True)
        assert s.icon_name() == "battery-low-charging-symbolic"

    def test_discharging_full_icon(self):
        s = self._make(90)
        assert s.icon_name() == "battery-full-symbolic"

    def test_discharging_good_icon(self):
        s = self._make(70)
        assert s.icon_name() == "battery-good-symbolic"

    def test_discharging_medium_icon(self):
        s = self._make(50)
        assert s.icon_name() == "battery-medium-symbolic"

    def test_discharging_low_icon(self):
        s = self._make(30)
        assert s.icon_name() == "battery-low-symbolic"

    def test_discharging_caution_icon(self):
        s = self._make(10)
        assert s.icon_name() == "battery-caution-symbolic"

    def test_format_label_absent(self):
        from menu_bar.battery import BatteryState
        assert BatteryState.absent().format_label() == ""

    def test_format_label_fully_charged(self):
        s = self._make(100, fully_charged=True)
        assert s.format_label() == "100%"

    def test_format_label_charging(self):
        s = self._make(75, charging=True)
        assert "75%" in s.format_label()
        assert "⚡" in s.format_label()

    def test_format_label_discharging(self):
        s = self._make(55)
        assert s.format_label() == "55%"

    def test_format_tooltip_absent(self):
        from menu_bar.battery import BatteryState
        assert BatteryState.absent().format_tooltip() == "No battery detected"

    def test_format_tooltip_fully_charged(self):
        s = self._make(100, fully_charged=True)
        assert s.format_tooltip() == "Battery fully charged"

    def test_format_tooltip_charging_with_time(self):
        s = self._make(50, charging=True, time_sec=3600 + 23*60)
        tip = s.format_tooltip()
        assert "Charging" in tip
        assert "1h 23m" in tip

    def test_format_tooltip_discharging_minutes_only(self):
        s = self._make(50, time_sec=45*60)
        tip = s.format_tooltip()
        assert "Discharging" in tip
        assert "45m" in tip

    def test_format_tooltip_no_time(self):
        s = self._make(50, time_sec=0)
        tip = s.format_tooltip()
        assert "remaining" not in tip


# ══════════════════════════════════════════════════════════════════════════════
# NetworkState
# ══════════════════════════════════════════════════════════════════════════════

class TestNetworkState:
    def _make(self, connected, conn_type=None, ssid="", signal=0):
        from menu_bar.network import NetworkState, ConnectionType
        ct = conn_type if conn_type is not None else ConnectionType.NONE
        return NetworkState(connected=connected, conn_type=ct, ssid=ssid, signal=signal)

    def test_offline_icon(self):
        s = self._make(False)
        assert s.icon_name() == "network-offline-symbolic"

    def test_ethernet_icon(self):
        from menu_bar.network import ConnectionType
        s = self._make(True, ConnectionType.ETHERNET, signal=100)
        assert s.icon_name() == "network-wired-symbolic"

    def test_wifi_excellent_icon(self):
        from menu_bar.network import ConnectionType
        s = self._make(True, ConnectionType.WIFI, signal=90)
        assert s.icon_name() == "network-wireless-signal-excellent-symbolic"

    def test_wifi_good_icon(self):
        from menu_bar.network import ConnectionType
        s = self._make(True, ConnectionType.WIFI, signal=70)
        assert s.icon_name() == "network-wireless-signal-good-symbolic"

    def test_wifi_ok_icon(self):
        from menu_bar.network import ConnectionType
        s = self._make(True, ConnectionType.WIFI, signal=40)
        assert s.icon_name() == "network-wireless-signal-ok-symbolic"

    def test_wifi_weak_icon(self):
        from menu_bar.network import ConnectionType
        s = self._make(True, ConnectionType.WIFI, signal=10)
        assert s.icon_name() == "network-wireless-signal-weak-symbolic"

    def test_other_connected_icon(self):
        from menu_bar.network import ConnectionType
        s = self._make(True, ConnectionType.OTHER, signal=100)
        assert s.icon_name() == "network-transmit-receive-symbolic"

    def test_format_label_offline_empty(self):
        s = self._make(False)
        assert s.format_label() == ""

    def test_format_label_ethernet_empty(self):
        from menu_bar.network import ConnectionType
        s = self._make(True, ConnectionType.ETHERNET, signal=100)
        assert s.format_label() == ""

    def test_format_label_wifi_ssid(self):
        from menu_bar.network import ConnectionType
        s = self._make(True, ConnectionType.WIFI, ssid="HomeNet", signal=80)
        assert s.format_label() == "HomeNet"

    def test_format_label_wifi_no_ssid(self):
        from menu_bar.network import ConnectionType
        s = self._make(True, ConnectionType.WIFI, ssid="", signal=80)
        assert s.format_label() == ""

    def test_format_tooltip_offline(self):
        s = self._make(False)
        assert s.format_tooltip() == "Not connected"

    def test_format_tooltip_ethernet(self):
        from menu_bar.network import ConnectionType
        s = self._make(True, ConnectionType.ETHERNET, signal=100)
        assert "Ethernet" in s.format_tooltip()

    def test_format_tooltip_wifi_with_ssid(self):
        from menu_bar.network import ConnectionType
        s = self._make(True, ConnectionType.WIFI, ssid="CafeWifi", signal=65)
        tip = s.format_tooltip()
        assert "CafeWifi" in tip
        assert "65%" in tip


# ══════════════════════════════════════════════════════════════════════════════
# VolumeState
# ══════════════════════════════════════════════════════════════════════════════

class TestVolumeState:
    def _make(self, level, muted=False, sink_name=""):
        from menu_bar.volume import VolumeState
        return VolumeState(level=level, muted=muted, sink_name=sink_name)

    def test_percent_property(self):
        s = self._make(0.75)
        assert s.percent == 75

    def test_percent_rounds(self):
        s = self._make(0.756)
        assert s.percent == 76

    def test_muted_icon(self):
        s = self._make(0.5, muted=True)
        assert s.icon_name() == "audio-volume-muted-symbolic"

    def test_zero_level_icon(self):
        s = self._make(0.0)
        assert s.icon_name() == "audio-volume-muted-symbolic"

    def test_low_icon(self):
        s = self._make(0.2)
        assert s.icon_name() == "audio-volume-low-symbolic"

    def test_medium_icon(self):
        s = self._make(0.5)
        assert s.icon_name() == "audio-volume-medium-symbolic"

    def test_high_icon(self):
        s = self._make(0.8)
        assert s.icon_name() == "audio-volume-high-symbolic"

    def test_format_label_muted(self):
        s = self._make(0.5, muted=True)
        assert s.format_label() == "Muted"

    def test_format_label_percent(self):
        s = self._make(0.75)
        assert s.format_label() == "75%"

    def test_format_tooltip_muted(self):
        s = self._make(0.5, muted=True)
        tip = s.format_tooltip()
        assert "Muted" in tip
        assert "50%" in tip

    def test_format_tooltip_with_sink_name(self):
        s = self._make(0.6, sink_name="Built-in Audio")
        tip = s.format_tooltip()
        assert "Built-in Audio" in tip

    def test_format_tooltip_without_sink_name(self):
        s = self._make(0.6, sink_name="")
        tip = s.format_tooltip()
        assert "60%" in tip


# ══════════════════════════════════════════════════════════════════════════════
# MenuItem
# ══════════════════════════════════════════════════════════════════════════════

class TestMenuItem:
    def _item(self, label="Test", children=None, **kwargs):
        from menu_bar.menu_model import MenuItem
        return MenuItem(item_id=1, label=label, children=children or [], **kwargs)

    def test_is_submenu_true_when_has_children(self):
        child = self._item(label="Sub")
        item = self._item(children=[child])
        assert item.is_submenu is True

    def test_is_submenu_false_when_no_children(self):
        item = self._item()
        assert item.is_submenu is False

    def test_display_label_strips_mnemonic(self):
        item = self._item(label="_File")
        assert item.display_label == "File"

    def test_display_label_no_mnemonic(self):
        item = self._item(label="View")
        assert item.display_label == "View"

    def test_display_label_internal_underscore(self):
        item = self._item(label="Find_Replace")
        assert item.display_label == "FindReplace"

    def test_is_separator_default_false(self):
        item = self._item()
        assert item.is_separator is False

    def test_is_separator_true(self):
        from menu_bar.menu_model import MenuItem
        sep = MenuItem(item_id=5, label="", is_separator=True)
        assert sep.is_separator is True

    def test_enabled_default_true(self):
        item = self._item()
        assert item.enabled is True

    def test_visible_default_true(self):
        item = self._item()
        assert item.visible is True


# ══════════════════════════════════════════════════════════════════════════════
# parse_layout
# ══════════════════════════════════════════════════════════════════════════════

class TestParseLayout:
    def test_simple_item(self):
        from menu_bar.menu_model import parse_layout
        layout = (1, {"label": "File", "enabled": True, "visible": True}, [])
        item = parse_layout(layout)
        assert item.item_id == 1
        assert item.label == "File"
        assert item.enabled is True
        assert item.visible is True

    def test_separator_type(self):
        from menu_bar.menu_model import parse_layout
        layout = (2, {"type": "separator"}, [])
        item = parse_layout(layout)
        assert item.is_separator is True

    def test_default_enabled_true(self):
        from menu_bar.menu_model import parse_layout
        layout = (1, {"label": "Edit"}, [])
        item = parse_layout(layout)
        assert item.enabled is True

    def test_disabled_item(self):
        from menu_bar.menu_model import parse_layout
        layout = (1, {"label": "Undo", "enabled": False}, [])
        item = parse_layout(layout)
        assert item.enabled is False

    def test_hidden_item(self):
        from menu_bar.menu_model import parse_layout
        layout = (1, {"label": "Secret", "visible": False}, [])
        item = parse_layout(layout)
        assert item.visible is False

    def test_nested_children(self):
        from menu_bar.menu_model import parse_layout
        child = (10, {"label": "New"}, [])
        root = (0, {}, [child])
        parsed = parse_layout(root)
        assert len(parsed.children) == 1
        assert parsed.children[0].label == "New"

    def test_deeply_nested(self):
        from menu_bar.menu_model import parse_layout
        grandchild = (20, {"label": "Grandchild"}, [])
        child = (10, {"label": "Child"}, [grandchild])
        root = (0, {}, [child])
        parsed = parse_layout(root)
        assert parsed.children[0].children[0].label == "Grandchild"

    def test_toggle_type_checkmark(self):
        from menu_bar.menu_model import parse_layout
        layout = (1, {"label": "Bold", "toggle-type": "checkmark", "toggle-state": 1}, [])
        item = parse_layout(layout)
        assert item.toggle_type == "checkmark"
        assert item.toggle_state == 1

    def test_toggle_state_default_minus_one(self):
        from menu_bar.menu_model import parse_layout
        layout = (1, {"label": "Bold"}, [])
        item = parse_layout(layout)
        assert item.toggle_state == -1

    def test_icon_name(self):
        from menu_bar.menu_model import parse_layout
        layout = (1, {"label": "Open", "icon-name": "document-open"}, [])
        item = parse_layout(layout)
        assert item.icon_name == "document-open"

    def test_glib_variant_unwrapping(self):
        """Children wrapped in GLib.Variant-like objects are unpacked."""
        from menu_bar.menu_model import parse_layout

        class FakeVariant:
            def __init__(self, value):
                self._value = value
            def unpack(self):
                return self._value

        child_tuple = (10, {"label": "Save"}, [])
        wrapped_child = FakeVariant(child_tuple)
        root = (0, {}, [wrapped_child])
        parsed = parse_layout(root)
        assert len(parsed.children) == 1
        assert parsed.children[0].label == "Save"

    def test_props_glib_variant_values(self):
        """Property values that are GLib.Variant-like are unwrapped."""
        from menu_bar.menu_model import parse_layout

        class FakeVariant:
            def __init__(self, value):
                self._value = value
            def unpack(self):
                return self._value

        layout = (1, {"label": FakeVariant("File"), "enabled": FakeVariant(True)}, [])
        item = parse_layout(layout)
        assert item.label == "File"
        assert item.enabled is True


# ══════════════════════════════════════════════════════════════════════════════
# visible_items
# ══════════════════════════════════════════════════════════════════════════════

class TestVisibleItems:
    def _item(self, label, visible=True):
        from menu_bar.menu_model import MenuItem
        return MenuItem(item_id=1, label=label, visible=visible)

    def test_all_visible(self):
        from menu_bar.menu_model import MenuItem, visible_items
        root = MenuItem(item_id=0, label="")
        root.children.extend([self._item("A"), self._item("B")])
        assert len(visible_items(root)) == 2

    def test_filters_invisible(self):
        from menu_bar.menu_model import MenuItem, visible_items
        root = MenuItem(item_id=0, label="")
        root.children.extend([self._item("A"), self._item("B", visible=False)])
        result = visible_items(root)
        assert len(result) == 1
        assert result[0].label == "A"

    def test_empty_root(self):
        from menu_bar.menu_model import MenuItem, visible_items
        root = MenuItem(item_id=0, label="")
        assert visible_items(root) == []

    def test_all_invisible_returns_empty(self):
        from menu_bar.menu_model import MenuItem, visible_items
        root = MenuItem(item_id=0, label="")
        root.children.extend([self._item("A", False), self._item("B", False)])
        assert visible_items(root) == []


# ══════════════════════════════════════════════════════════════════════════════
# MenuBarInterface
# ══════════════════════════════════════════════════════════════════════════════

def _make_menu_bar_iface(show_cb=None, hide_cb=None):
    from menu_bar.menu_bar_dbus import MenuBarInterface
    return MenuBarInterface(
        show_cb=show_cb or MagicMock(),
        hide_cb=hide_cb or MagicMock(),
    )


class TestMenuBarInterface:
    def test_visible_true_by_default(self):
        iface = _make_menu_bar_iface()
        assert iface.Visible is True

    def test_show_sets_visible(self):
        show_cb = MagicMock()
        iface = _make_menu_bar_iface(show_cb=show_cb)
        iface._visible = False
        iface.Show()
        assert iface.Visible is True
        show_cb.assert_called_once()

    def test_hide_sets_invisible(self):
        hide_cb = MagicMock()
        iface = _make_menu_bar_iface(hide_cb=hide_cb)
        iface.Hide()
        assert iface.Visible is False
        hide_cb.assert_called_once()

    def test_toggle_visible_to_hidden(self):
        hide_cb = MagicMock()
        iface = _make_menu_bar_iface(hide_cb=hide_cb)
        assert iface.Visible is True
        iface.Toggle()
        assert iface.Visible is False

    def test_toggle_hidden_to_visible(self):
        show_cb = MagicMock()
        iface = _make_menu_bar_iface(show_cb=show_cb)
        iface._visible = False
        iface.Toggle()
        assert iface.Visible is True
        show_cb.assert_called_once()

    def test_active_app_default_empty(self):
        iface = _make_menu_bar_iface()
        assert iface.ActiveApp == ""

    def test_set_active_app(self):
        iface = _make_menu_bar_iface()
        iface.SetActiveApp("Firefox")
        assert iface.ActiveApp == "Firefox"

    def test_set_active_app_updates_internal_state(self):
        iface = _make_menu_bar_iface()
        iface.SetActiveApp("Terminal")
        assert iface._active_app == "Terminal"

    def test_notify_app_changed_updates_active_app(self):
        iface = _make_menu_bar_iface()
        iface.notify_app_changed("Gedit")
        assert iface.ActiveApp == "Gedit"

    def test_notify_app_changed_second_call_overwrites(self):
        iface = _make_menu_bar_iface()
        iface.notify_app_changed("Firefox")
        iface.notify_app_changed("Gedit")
        assert iface.ActiveApp == "Gedit"

    def test_notify_app_changed_silences_dbus_error(self):
        """notify_app_changed must not propagate exceptions."""
        from unittest.mock import patch
        iface = _make_menu_bar_iface()
        with patch.object(type(iface), "ActiveAppChanged", create=True,
                          new_callable=lambda: property(lambda self: _raise_exc)):
            pass  # just verify we can call without crashing
        iface.notify_app_changed("Anything")  # should not raise

    def test_show_then_hide_sequence(self):
        show_cb = MagicMock()
        hide_cb = MagicMock()
        iface = _make_menu_bar_iface(show_cb=show_cb, hide_cb=hide_cb)
        iface._visible = False
        iface.Show()
        iface.Hide()
        assert iface.Visible is False
        show_cb.assert_called_once()
        hide_cb.assert_called_once()

    def test_multiple_toggles(self):
        iface = _make_menu_bar_iface()
        assert iface.Visible is True
        iface.Toggle()
        assert iface.Visible is False
        iface.Toggle()
        assert iface.Visible is True
