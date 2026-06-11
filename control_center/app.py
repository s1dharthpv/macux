"""MacUX Control Center — application entry point.

Wires together WifiManager, BluetoothManager, AudioController,
BrightnessManager, ControlCenterWindow, and ControlCenterDBusServer.
"""

from __future__ import annotations

import logging
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio, GLib, Adw

from control_center.audio_model import AudioController
from control_center.bluetooth_model import BluetoothManager
from control_center.brightness_model import BrightnessManager
from control_center.control_center_dbus import ControlCenterDBusServer
from control_center.wifi_model import WifiManager
from control_center.window import ControlCenterWindow
from menu_bar.battery import BatteryMonitor

logger = logging.getLogger(__name__)

# Refresh sinks every 5 s (PulseAudio doesn't reliably signal all changes)
_AUDIO_REFRESH_INTERVAL_MS = 5000


class ControlCenterApplication(Adw.Application):
    """MacUX Control Center Adw.Application."""

    def __init__(self) -> None:
        super().__init__(
            application_id="com.macux.ControlCenter",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._window: ControlCenterWindow | None = None
        self._dbus_server: ControlCenterDBusServer | None = None
        self._wifi_mgr: WifiManager | None = None
        self._bt_mgr: BluetoothManager | None = None
        self._audio_ctrl: AudioController | None = None
        self._bright_mgr: BrightnessManager | None = None
        self._battery_monitor: BatteryMonitor | None = None

        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_activate(self, app: Adw.Application) -> None:
        self._window = ControlCenterWindow(
            on_wifi_toggle=self._on_wifi_toggle,
            on_wifi_connect=self._on_wifi_connect,
            on_bt_toggle=self._on_bt_toggle,
            on_bt_connect=self._on_bt_connect,
            on_volume_change=self._on_volume_change,
            on_brightness_change=self._on_brightness_change,
        )
        self._window.set_application(app)

        # DBus server
        self._dbus_server = ControlCenterDBusServer(
            show_cb=self._show_window,
            hide_cb=self._hide_window,
            panel_cb=self._switch_panel,
        )
        self._dbus_server.start()

        # WiFi
        self._wifi_mgr = WifiManager(on_networks_changed=self._on_networks_changed)
        self._wifi_mgr.start()

        # Bluetooth
        self._bt_mgr = BluetoothManager(on_devices_changed=self._on_devices_changed)
        self._bt_mgr.start()

        # Audio
        self._audio_ctrl = AudioController(on_sinks_changed=self._on_sinks_changed)
        self._audio_ctrl.start()
        GLib.timeout_add(_AUDIO_REFRESH_INTERVAL_MS, self._refresh_audio)

        # Brightness
        self._bright_mgr = BrightnessManager()
        self._window.update_brightness(self._bright_mgr.get_state())

        # Battery
        self._battery_monitor = BatteryMonitor(on_change=self._on_battery_changed)
        self._battery_monitor.start()
        self._on_battery_changed(self._battery_monitor.get_state())

        # Initial data push
        self._on_networks_changed(self._wifi_mgr.get_networks())
        self._on_sinks_changed(self._audio_ctrl.get_sinks())

        # Initially hidden — show via DBus or keyboard shortcut
        self._window.set_visible(False)
        self._window.present()
        self._window.set_visible(False)

        logger.info("ControlCenter started (hidden)")

    def _on_shutdown(self, app: Adw.Application) -> None:
        if self._dbus_server:
            self._dbus_server.stop()

    # ── Show / hide ───────────────────────────────────────────────────────────

    def _show_window(self) -> None:
        if self._window:
            # Refresh data before showing
            if self._wifi_mgr:
                self._wifi_mgr.request_scan()
            if self._audio_ctrl:
                self._on_sinks_changed(self._audio_ctrl.get_sinks())
            if self._bright_mgr:
                self._window.update_brightness(self._bright_mgr.get_state())
            self._window.set_visible(True)
            self._window.present()

    def _hide_window(self) -> None:
        if self._window:
            self._window.set_visible(False)

    def _switch_panel(self, panel: str) -> None:
        if self._window:
            self._window.switch_panel(panel)

    # ── Manager callbacks ─────────────────────────────────────────────────────

    def _on_networks_changed(self, networks) -> None:
        if self._window and self._wifi_mgr:
            self._window.update_wifi(networks, self._wifi_mgr.is_enabled())

    def _on_devices_changed(self, devices) -> None:
        if self._window and self._bt_mgr:
            self._window.update_bluetooth(devices, self._bt_mgr.is_powered())

    def _on_sinks_changed(self, sinks) -> None:
        if self._window:
            self._window.update_audio(sinks)

    def _on_battery_changed(self, state) -> None:
        if self._window:
            self._window.update_battery(state)

    # ── UI callbacks ──────────────────────────────────────────────────────────

    def _on_wifi_toggle(self, enabled: bool) -> None:
        if self._wifi_mgr:
            self._wifi_mgr.set_enabled(enabled)

    def _on_wifi_connect(self, ssid: str) -> None:
        if self._wifi_mgr:
            self._wifi_mgr.connect(ssid)

    def _on_bt_toggle(self, powered: bool) -> None:
        if self._bt_mgr:
            self._bt_mgr.set_powered(powered)

    def _on_bt_connect(self, address: str) -> None:
        if self._bt_mgr:
            self._bt_mgr.connect_device(address)

    def _on_volume_change(self, sink_index: int, level: float) -> None:
        if self._audio_ctrl:
            self._audio_ctrl.set_volume(sink_index, level)

    def _on_brightness_change(self, percent: int) -> None:
        if self._bright_mgr:
            self._bright_mgr.set_level(percent)

    def _refresh_audio(self) -> bool:
        if self._audio_ctrl and self._window and self._window.get_visible():
            self._on_sinks_changed(self._audio_ctrl.get_sinks())
        return True  # keep timer running


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    app = ControlCenterApplication()
    sys.exit(app.run(sys.argv))
