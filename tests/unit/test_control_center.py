"""Unit tests for Phase 8 — MacUX Control Center.

Coverage:
  - WiFiNetwork: icon_name signal tiers, format_signal, dataclass attrs
  - BluetoothDevice: icon_name by device_type, dataclass attrs
  - _device_type_from_class: COD major class → type string
  - AudioSink: percent property, icon_name (all 4 tiers), is_default
  - BrightnessState: icon_name (3 tiers + unavailable), available flag
  - BrightnessManager: set_level clamping logic (mocked sysfs)
  - VALID_PANELS constant
  - ControlCenterInterface: Show/Hide/Toggle, ShowPanel (valid/invalid),
    Visible/ActivePanel properties, notify_panel_changed, panel_cb invocation
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, mock_open


# ══════════════════════════════════════════════════════════════════════════════
# WiFiNetwork
# ══════════════════════════════════════════════════════════════════════════════

class TestWiFiNetwork:
    def _net(self, signal=80, secured=False, connected=False, ssid="TestNet", bssid="00:00:00:00:00:00"):
        from control_center.wifi_model import WiFiNetwork
        return WiFiNetwork(ssid=ssid, bssid=bssid, signal=signal,
                           secured=secured, connected=connected)

    def test_icon_excellent(self):
        assert self._net(signal=90).icon_name() == "network-wireless-signal-excellent-symbolic"

    def test_icon_good(self):
        assert self._net(signal=70).icon_name() == "network-wireless-signal-good-symbolic"

    def test_icon_ok(self):
        assert self._net(signal=45).icon_name() == "network-wireless-signal-ok-symbolic"

    def test_icon_weak(self):
        assert self._net(signal=20).icon_name() == "network-wireless-signal-weak-symbolic"

    def test_icon_boundary_81(self):
        assert self._net(signal=81).icon_name() == "network-wireless-signal-excellent-symbolic"

    def test_icon_boundary_56(self):
        assert self._net(signal=56).icon_name() == "network-wireless-signal-good-symbolic"

    def test_icon_boundary_31(self):
        assert self._net(signal=31).icon_name() == "network-wireless-signal-ok-symbolic"

    def test_icon_boundary_30(self):
        assert self._net(signal=30).icon_name() == "network-wireless-signal-weak-symbolic"

    def test_format_signal(self):
        assert self._net(signal=75).format_signal() == "75%"

    def test_format_signal_zero(self):
        assert self._net(signal=0).format_signal() == "0%"

    def test_secured_flag(self):
        net = self._net(secured=True)
        assert net.secured is True

    def test_connected_flag(self):
        net = self._net(connected=True)
        assert net.connected is True

    def test_default_not_connected(self):
        net = self._net()
        assert net.connected is False

    def test_ssid_stored(self):
        net = self._net(ssid="HomeWifi")
        assert net.ssid == "HomeWifi"


# ══════════════════════════════════════════════════════════════════════════════
# BluetoothDevice + _device_type_from_class
# ══════════════════════════════════════════════════════════════════════════════

class TestDeviceTypeFromClass:
    def test_audio_cod(self):
        from control_center.bluetooth_model import _device_type_from_class
        # Major class 4 (audio) = bits 8-12 of CoD: 0x04 << 8 = 0x0400
        cod = 0x0400
        assert _device_type_from_class(cod) == "audio"

    def test_input_cod(self):
        from control_center.bluetooth_model import _device_type_from_class
        cod = 0x0500
        assert _device_type_from_class(cod) == "input"

    def test_phone_cod(self):
        from control_center.bluetooth_model import _device_type_from_class
        cod = 0x0200
        assert _device_type_from_class(cod) == "phone"

    def test_unknown_cod(self):
        from control_center.bluetooth_model import _device_type_from_class
        assert _device_type_from_class(0x0100) == "other"

    def test_zero_cod(self):
        from control_center.bluetooth_model import _device_type_from_class
        assert _device_type_from_class(0) == "other"


class TestBluetoothDevice:
    def _dev(self, device_type="other", paired=False, connected=False):
        from control_center.bluetooth_model import BluetoothDevice
        return BluetoothDevice(
            address="AA:BB:CC:DD:EE:FF",
            name="Test Device",
            paired=paired,
            connected=connected,
            device_type=device_type,
        )

    def test_audio_icon(self):
        assert self._dev("audio").icon_name() == "audio-headphones-symbolic"

    def test_input_icon(self):
        assert self._dev("input").icon_name() == "input-keyboard-symbolic"

    def test_phone_icon(self):
        assert self._dev("phone").icon_name() == "phone-symbolic"

    def test_other_icon(self):
        assert self._dev("other").icon_name() == "bluetooth-symbolic"

    def test_paired_attr(self):
        assert self._dev(paired=True).paired is True

    def test_connected_attr(self):
        assert self._dev(connected=True).connected is True

    def test_address_stored(self):
        dev = self._dev()
        assert dev.address == "AA:BB:CC:DD:EE:FF"

    def test_name_stored(self):
        dev = self._dev()
        assert dev.name == "Test Device"

    def test_address_to_path(self):
        from control_center.bluetooth_model import BluetoothManager
        path = BluetoothManager._address_to_path("AA:BB:CC:DD:EE:FF")
        assert path == "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"


# ══════════════════════════════════════════════════════════════════════════════
# AudioSink
# ══════════════════════════════════════════════════════════════════════════════

class TestAudioSink:
    def _sink(self, volume=0.75, muted=False, is_default=False):
        from control_center.audio_model import AudioSink
        return AudioSink(
            index=0,
            name="alsa_output.pci-0000_00_1f.3",
            description="Built-in Audio",
            volume=volume,
            muted=muted,
            is_default=is_default,
        )

    def test_percent_75(self):
        assert self._sink(0.75).percent == 75

    def test_percent_rounds(self):
        assert self._sink(0.756).percent == 76

    def test_percent_zero(self):
        assert self._sink(0.0).percent == 0

    def test_percent_over_100(self):
        assert self._sink(1.5).percent == 150

    def test_icon_muted(self):
        assert self._sink(0.5, muted=True).icon_name() == "audio-volume-muted-symbolic"

    def test_icon_zero_volume(self):
        assert self._sink(0.0).icon_name() == "audio-volume-muted-symbolic"

    def test_icon_low(self):
        assert self._sink(0.2).icon_name() == "audio-volume-low-symbolic"

    def test_icon_medium(self):
        assert self._sink(0.5).icon_name() == "audio-volume-medium-symbolic"

    def test_icon_high(self):
        assert self._sink(0.9).icon_name() == "audio-volume-high-symbolic"

    def test_is_default_false(self):
        assert self._sink().is_default is False

    def test_is_default_true(self):
        assert self._sink(is_default=True).is_default is True

    def test_description_stored(self):
        s = self._sink()
        assert s.description == "Built-in Audio"


# ══════════════════════════════════════════════════════════════════════════════
# BrightnessState
# ══════════════════════════════════════════════════════════════════════════════

class TestBrightnessState:
    def _state(self, level=50, available=True):
        from control_center.brightness_model import BrightnessState
        return BrightnessState(level=level, available=available)

    def test_icon_high(self):
        assert self._state(80).icon_name() == "display-brightness-high-symbolic"

    def test_icon_medium(self):
        assert self._state(50).icon_name() == "display-brightness-medium-symbolic"

    def test_icon_low(self):
        assert self._state(20).icon_name() == "display-brightness-low-symbolic"

    def test_icon_boundary_66_medium(self):
        # level 66: 66 > 66 is False, 66 > 33 is True → medium
        assert self._state(66).icon_name() == "display-brightness-medium-symbolic"

    def test_icon_boundary_67_high(self):
        # level 67: 67 > 66 is True → high
        assert self._state(67).icon_name() == "display-brightness-high-symbolic"

    def test_icon_boundary_33_low(self):
        # level 33: 33 > 33 is False → low
        assert self._state(33).icon_name() == "display-brightness-low-symbolic"

    def test_icon_boundary_34_medium(self):
        # level 34: 34 > 33 is True → medium
        assert self._state(34).icon_name() == "display-brightness-medium-symbolic"

    def test_icon_unavailable_fallback(self):
        assert self._state(50, available=False).icon_name() == "display-brightness-symbolic"

    def test_available_true(self):
        assert self._state().available is True

    def test_available_false(self):
        assert self._state(available=False).available is False

    def test_level_stored(self):
        assert self._state(42).level == 42


# ══════════════════════════════════════════════════════════════════════════════
# BrightnessManager — set_level clamping
# ══════════════════════════════════════════════════════════════════════════════

class TestBrightnessManagerClamping:
    def _mgr(self):
        from control_center.brightness_model import BrightnessManager
        mgr = BrightnessManager.__new__(BrightnessManager)
        mgr._device_path = None   # no sysfs device
        mgr._max_brightness = 0
        return mgr

    def test_set_level_clamps_above_100(self):
        mgr = self._mgr()
        calls = []
        with patch.object(mgr, "_set_via_brightnessctl", side_effect=lambda p: calls.append(p)):
            mgr.set_level(120)
        assert calls[0] == 100

    def test_set_level_clamps_below_0(self):
        mgr = self._mgr()
        calls = []
        with patch.object(mgr, "_set_via_brightnessctl", side_effect=lambda p: calls.append(p)):
            mgr.set_level(-5)
        assert calls[0] == 0

    def test_set_level_normal_value(self):
        mgr = self._mgr()
        calls = []
        with patch.object(mgr, "_set_via_brightnessctl", side_effect=lambda p: calls.append(p)):
            mgr.set_level(70)
        assert calls[0] == 70

    def test_set_level_zero(self):
        mgr = self._mgr()
        calls = []
        with patch.object(mgr, "_set_via_brightnessctl", side_effect=lambda p: calls.append(p)):
            mgr.set_level(0)
        assert calls[0] == 0

    def test_set_level_sysfs_when_available(self):
        """When sysfs device is present, write raw brightness to file."""
        import tempfile
        from pathlib import Path
        from control_center.brightness_model import BrightnessManager
        with tempfile.TemporaryDirectory() as tmp:
            dev = Path(tmp)
            (dev / "brightness").write_text("0")
            (dev / "max_brightness").write_text("1000")
            mgr = BrightnessManager.__new__(BrightnessManager)
            mgr._device_path = dev
            mgr._max_brightness = 1000
            mgr.set_level(75)
            written = int((dev / "brightness").read_text().strip())
            assert written == 750  # 75% of 1000


# ══════════════════════════════════════════════════════════════════════════════
# VALID_PANELS
# ══════════════════════════════════════════════════════════════════════════════

class TestValidPanels:
    def test_wifi_in_valid(self):
        from control_center.control_center_dbus import VALID_PANELS
        assert "wifi" in VALID_PANELS

    def test_bluetooth_in_valid(self):
        from control_center.control_center_dbus import VALID_PANELS
        assert "bluetooth" in VALID_PANELS

    def test_volume_in_valid(self):
        from control_center.control_center_dbus import VALID_PANELS
        assert "volume" in VALID_PANELS

    def test_brightness_in_valid(self):
        from control_center.control_center_dbus import VALID_PANELS
        assert "brightness" in VALID_PANELS

    def test_battery_in_valid(self):
        from control_center.control_center_dbus import VALID_PANELS
        assert "battery" in VALID_PANELS

    def test_invalid_panel_excluded(self):
        from control_center.control_center_dbus import VALID_PANELS
        assert "airdrop" not in VALID_PANELS


# ══════════════════════════════════════════════════════════════════════════════
# ControlCenterInterface
# ══════════════════════════════════════════════════════════════════════════════

def _make_cc_iface(show_cb=None, hide_cb=None, panel_cb=None):
    from control_center.control_center_dbus import ControlCenterInterface
    return ControlCenterInterface(
        show_cb=show_cb or MagicMock(),
        hide_cb=hide_cb or MagicMock(),
        panel_cb=panel_cb,
    )


class TestControlCenterInterface:
    def test_visible_false_by_default(self):
        iface = _make_cc_iface()
        assert iface.Visible is False

    def test_active_panel_default_wifi(self):
        iface = _make_cc_iface()
        assert iface.ActivePanel == "wifi"

    def test_show_sets_visible(self):
        show_cb = MagicMock()
        iface = _make_cc_iface(show_cb=show_cb)
        iface.Show()
        assert iface.Visible is True
        show_cb.assert_called_once()

    def test_hide_sets_invisible(self):
        hide_cb = MagicMock()
        iface = _make_cc_iface(hide_cb=hide_cb)
        iface.Show()
        iface.Hide()
        assert iface.Visible is False
        hide_cb.assert_called_once()

    def test_toggle_hidden_to_visible(self):
        show_cb = MagicMock()
        iface = _make_cc_iface(show_cb=show_cb)
        iface.Toggle()
        assert iface.Visible is True

    def test_toggle_visible_to_hidden(self):
        hide_cb = MagicMock()
        iface = _make_cc_iface(hide_cb=hide_cb)
        iface.Show()
        iface.Toggle()
        assert iface.Visible is False

    def test_show_panel_valid(self):
        iface = _make_cc_iface()
        iface.ShowPanel("bluetooth")
        assert iface.ActivePanel == "bluetooth"

    def test_show_panel_shows_window(self):
        show_cb = MagicMock()
        iface = _make_cc_iface(show_cb=show_cb)
        assert not iface.Visible
        iface.ShowPanel("volume")
        assert iface.Visible is True

    def test_show_panel_invokes_panel_cb(self):
        panel_cb = MagicMock()
        iface = _make_cc_iface(panel_cb=panel_cb)
        iface.ShowPanel("brightness")
        panel_cb.assert_called_once_with("brightness")

    def test_show_panel_invalid_name_ignored(self):
        iface = _make_cc_iface()
        original = iface.ActivePanel
        iface.ShowPanel("airdrop")
        assert iface.ActivePanel == original

    def test_show_panel_case_insensitive(self):
        iface = _make_cc_iface()
        iface.ShowPanel("WIFI")
        assert iface.ActivePanel == "wifi"

    def test_notify_panel_changed_updates_active(self):
        iface = _make_cc_iface()
        iface.notify_panel_changed("battery")
        assert iface.ActivePanel == "battery"

    def test_notify_panel_changed_silences_dbus_error(self):
        iface = _make_cc_iface()
        # patch PanelChanged to raise; notify_panel_changed must not propagate
        original_pc = type(iface).PanelChanged
        class _Raise:
            def __get__(self, obj, cls): return self
            def __call__(self, *a): raise Exception("dbus error")
        type(iface).PanelChanged = _Raise()
        try:
            iface.notify_panel_changed("volume")  # should not raise
        finally:
            type(iface).PanelChanged = original_pc

    def test_show_then_hide_clears_visible(self):
        iface = _make_cc_iface()
        iface.Show()
        iface.Hide()
        assert iface.Visible is False

    def test_multiple_show_panel_changes(self):
        iface = _make_cc_iface()
        iface.ShowPanel("wifi")
        iface.ShowPanel("bluetooth")
        iface.ShowPanel("volume")
        assert iface.ActivePanel == "volume"

    def test_show_panel_no_panel_cb_ok(self):
        iface = _make_cc_iface(panel_cb=None)
        iface.ShowPanel("wifi")  # no callback — should not raise
        assert iface.ActivePanel == "wifi"

    def test_show_panel_battery(self):
        iface = _make_cc_iface()
        iface.ShowPanel("battery")
        assert iface.ActivePanel == "battery"
