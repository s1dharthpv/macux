"""MacUX Menu Bar — application entry point.

Wires together:
  • AppMenuConsumer (window focus → dbusmenu tree)
  • BatteryMonitor, NetworkMonitor, VolumeMonitor
  • MenuBarWindow (GTK4 top bar)
  • MenuBarDBusServer (com.macux.MenuBar)
"""

from __future__ import annotations

import logging
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio, GLib, Adw

from menu_bar.app_menu import AppMenuConsumer
from menu_bar.battery import BatteryMonitor
from menu_bar.menu_bar_dbus import MenuBarDBusServer
from menu_bar.menu_model import MenuItem
from menu_bar.network import NetworkMonitor
from menu_bar.volume import VolumeMonitor
from menu_bar.window import MenuBarWindow

logger = logging.getLogger(__name__)


class MenuBarApplication(Adw.Application):
    """MacUX Menu Bar Adw.Application."""

    def __init__(self) -> None:
        super().__init__(
            application_id="com.macux.MenuBar",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._window: MenuBarWindow | None = None
        self._dbus_server: MenuBarDBusServer | None = None
        self._battery_monitor: BatteryMonitor | None = None
        self._network_monitor: NetworkMonitor | None = None
        self._volume_monitor: VolumeMonitor | None = None
        self._app_consumer: AppMenuConsumer | None = None

        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_activate(self, app: Adw.Application) -> None:
        self._window = MenuBarWindow()
        self._window.set_application(app)

        # DBus server
        self._dbus_server = MenuBarDBusServer(
            show_cb=self._show_bar,
            hide_cb=self._hide_bar,
        )
        self._dbus_server.start()

        # Monitors
        self._battery_monitor = BatteryMonitor(on_change=self._on_battery_changed)
        self._battery_monitor.start()

        self._network_monitor = NetworkMonitor(on_change=self._on_network_changed)
        self._network_monitor.start()

        self._volume_monitor = VolumeMonitor(on_change=self._on_volume_changed)
        self._volume_monitor.start()

        # Push initial state
        self._on_battery_changed(self._battery_monitor.get_state())
        self._on_network_changed(self._network_monitor.get_state())
        self._on_volume_changed(self._volume_monitor.get_state())

        # App menu consumer
        self._app_consumer = AppMenuConsumer(
            on_app_changed=self._on_app_changed,
            on_menu_changed=self._on_menu_changed,
        )
        self._app_consumer.start()

        self._window.present()
        logger.info("MenuBar started")

    def _on_shutdown(self, app: Adw.Application) -> None:
        if self._dbus_server:
            self._dbus_server.stop()

    # ── Show / hide ───────────────────────────────────────────────────────────

    def _show_bar(self) -> None:
        if self._window:
            self._window.set_visible(True)

    def _hide_bar(self) -> None:
        if self._window:
            self._window.set_visible(False)

    # ── Monitor callbacks (run on GLib main thread via idle_add) ──────────────

    def _on_battery_changed(self, state) -> None:
        if self._window:
            self._window.update_battery(state)

    def _on_network_changed(self, state) -> None:
        if self._window:
            self._window.update_network(state)

    def _on_volume_changed(self, state) -> None:
        if self._window:
            self._window.update_volume(state)

    def _on_app_changed(self, app_name: str) -> None:
        if self._dbus_server:
            self._dbus_server.interface.notify_app_changed(app_name)

    def _on_menu_changed(self, menu_root: MenuItem | None) -> None:
        if self._window and self._dbus_server:
            app_name = self._dbus_server.interface.ActiveApp
            self._window.update_app_menu(app_name, menu_root)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    app = MenuBarApplication()
    sys.exit(app.run(sys.argv))
