"""MacUX Mission Control — Adw.Application entry point.

Registers the com.macux.MissionControl DBus service on the session bus.
"""

import logging
import sys

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio, GLib  # noqa: E402

from mission_control.mission_control_dbus import MissionControlInterface  # noqa: E402

_log = logging.getLogger(__name__)

_DBUS_PATH = "/com/macux/MissionControl"
_DBUS_NAME = "com.macux.MissionControl"


class MissionControlApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=_DBUS_NAME,
            flags=Gio.ApplicationFlags.IS_SERVICE,
        )
        self._mc_iface: MissionControlInterface | None = None
        self._registration_id: int = 0

    # ── Adw.Application lifecycle ──────────────────────────────────────────────

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._mc_iface = MissionControlInterface(
            activate_cb=self._on_activate_requested,
            deactivate_cb=self._on_deactivate_requested,
            window_selected_cb=self._on_window_selected,
        )
        connection = self.get_dbus_connection()
        if connection is not None:
            self._export_interface(connection)

    def do_dbus_register(
        self,
        connection: Gio.DBusConnection,
        object_path: str,
    ) -> bool:
        self._export_interface(connection)
        return Adw.Application.do_dbus_register(self, connection, object_path)

    def do_dbus_unregister(
        self,
        connection: Gio.DBusConnection,
        object_path: str,
    ) -> None:
        if self._registration_id:
            connection.unregister_object(self._registration_id)
            self._registration_id = 0
        Adw.Application.do_dbus_unregister(self, connection, object_path)

    def do_activate(self) -> None:
        pass

    # ── DBus export ────────────────────────────────────────────────────────────

    def _export_interface(self, connection: Gio.DBusConnection) -> None:
        if self._mc_iface is None or self._registration_id:
            return
        from dasbus.connection import SessionMessageBus

        bus = SessionMessageBus()
        try:
            bus.publish_object(_DBUS_PATH, self._mc_iface)
            bus.register_service(_DBUS_NAME)
            _log.info("MissionControlInterface published at %s", _DBUS_PATH)
        except Exception:
            _log.exception("Failed to publish MissionControlInterface")

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def _on_activate_requested(self) -> None:
        _log.debug("Mission Control activate requested via DBus")

    def _on_deactivate_requested(self) -> None:
        _log.debug("Mission Control deactivate requested via DBus")

    def _on_window_selected(self, xid: int) -> None:
        _log.debug("Window selected via Mission Control: xid=%d", xid)


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    app = MissionControlApplication()
    sys.exit(app.run(sys.argv))
