"""MacUX Notification Center — application entry point.

Wires together:
  • FreedesktopNotificationsServer  (org.freedesktop.Notifications — receives all desktop notifications)
  • NotificationPersistence         (SQLite WAL history store)
  • BannerManager                   (transient top-right popups)
  • NotificationCenterWindow        (scrollable history panel)
  • NotificationCenterDBusServer    (com.macux.NotificationCenter — external control)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gio, GLib, Adw

from notification_center.banner import BannerManager
from notification_center.fd_notifications import (
    CLOSE_REASON_DISMISSED,
    FreedesktopNotificationsServer,
)
from notification_center.notification import Notification
from notification_center.notification_center_dbus import NotificationCenterDBusServer
from notification_center.persistence import NotificationPersistence
from notification_center.window import NotificationCenterWindow

logger = logging.getLogger(__name__)

_DB_PATH = Path.home() / ".local" / "share" / "macux" / "notifications.db"
_MAX_STORED = 100


class NotificationCenterApplication(Adw.Application):
    """MacUX Notification Center Adw.Application."""

    def __init__(self) -> None:
        super().__init__(
            application_id="com.macux.NotificationCenter",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._window: NotificationCenterWindow | None = None
        self._fd_server: FreedesktopNotificationsServer | None = None
        self._nc_dbus: NotificationCenterDBusServer | None = None
        self._persistence: NotificationPersistence | None = None
        self._banners: BannerManager | None = None

        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_activate(self, app: Adw.Application) -> None:
        # Persistence
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._persistence = NotificationPersistence(_DB_PATH, max_count=_MAX_STORED)

        # Banner manager
        self._banners = BannerManager()
        self._banners.load_css()

        # History window (initially hidden)
        self._window = NotificationCenterWindow(
            on_dismiss=self._on_card_dismissed,
            on_clear_all=self._on_clear_all,
        )
        self._window.set_application(app)
        self._window.set_visible(False)

        # Load history
        history = self._persistence.get_all(include_dismissed=False)
        self._window.load_notifications(history)

        # DBus: com.macux.NotificationCenter
        self._nc_dbus = NotificationCenterDBusServer(
            show_cb=self._show_window,
            hide_cb=self._hide_window,
            clear_cb=self._on_clear_all,
            count_cb=self._persistence.get_undismissed_count,
        )
        self._nc_dbus.start()

        # DBus: org.freedesktop.Notifications
        self._fd_server = FreedesktopNotificationsServer(
            on_notify=self._on_notify_received,
            on_close=self._on_close_requested,
        )
        self._fd_server.start()

        logger.info("NotificationCenter started")

    def _on_shutdown(self, app: Adw.Application) -> None:
        if self._fd_server:
            self._fd_server.stop()
        if self._nc_dbus:
            self._nc_dbus.stop()

    # ── Show / hide ───────────────────────────────────────────────────────────

    def _show_window(self) -> None:
        if self._window:
            self._window.set_visible(True)
            self._window.present()

    def _hide_window(self) -> None:
        if self._window:
            self._window.set_visible(False)

    # ── Notification callbacks ─────────────────────────────────────────────────

    def _on_notify_received(self, notif: Notification) -> None:
        """Called on the GLib main thread via idle_add from fd_notifications."""
        if self._persistence:
            self._persistence.save(notif)

        if self._banners:
            self._banners.enqueue(notif)

        if self._window:
            self._window.add_notification(notif)

        if self._nc_dbus:
            self._nc_dbus.interface.notify_notification_added(
                notif.notif_id, notif.app_name, notif.summary
            )

    def _on_close_requested(self, notif_id: int, reason: int) -> None:
        if self._persistence:
            self._persistence.dismiss(notif_id)
        if self._window:
            self._window.remove_notification(notif_id)

    def _on_card_dismissed(self, notif_id: int) -> None:
        if self._persistence:
            self._persistence.dismiss(notif_id)
        if self._fd_server:
            self._fd_server.interface.emit_closed(notif_id, CLOSE_REASON_DISMISSED)

    def _on_clear_all(self) -> None:
        if self._persistence:
            self._persistence.clear_all()
        if self._window:
            self._window.load_notifications([])


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    app = NotificationCenterApplication()
    sys.exit(app.run(sys.argv))
