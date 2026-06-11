"""MacUX Launchpad — application entry point.

Wires together:
  - LaunchpadPersistence  (SQLite positions + folders)
  - GridLayout            (page/cell calculation)
  - LaunchpadWindow       (GTK4 fullscreen UI)
  - LaunchpadDBusServer   (com.macux.Launchpad DBus service)

On first launch (empty DB) all installed apps are auto-laid-out in
alphabetical order.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from launchpad.grid import GridLayout
from launchpad.persistence import LaunchpadPersistence
from launchpad.window import LaunchpadWindow

logger = logging.getLogger(__name__)

_APP_ID = "com.macux.launchpad"
_DESKTOP_DIRS: list[Path] = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
]


class LaunchpadApplication(Adw.Application):
    """
    GTK4 application hosting the MacUX Launchpad.

    Lifecycle:
      1. activate()  → load DB, build window, register DBus
      2. DBus Show / keybinding → window.show_launchpad()
      3. User activates icon    → launch app, hide window
      4. Escape                 → window hidden (app stays running)
      5. shutdown()             → db.close(), dbus.stop()
    """

    def __init__(self) -> None:
        super().__init__(
            application_id=_APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._db: LaunchpadPersistence | None = None
        self._registry: dict = {}
        self._window: LaunchpadWindow | None = None
        self._dbus_server = None

    # ── Adw.Application overrides ─────────────────────────────────────────────

    def do_activate(self) -> None:
        self._setup_logging()
        self._setup_db()
        self._load_registry()
        self._setup_window()
        self._setup_dbus()

    def do_shutdown(self) -> None:
        if self._dbus_server:
            try:
                self._dbus_server.stop()
            except Exception:
                logger.exception("Error stopping Launchpad DBus server")
        if self._db:
            self._db.close()
        Adw.Application.do_shutdown(self)

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_logging(self) -> None:
        logging.basicConfig(
            level=logging.DEBUG,
            format="[macux-launchpad] %(levelname)s %(name)s: %(message)s",
        )

    def _setup_db(self) -> None:
        self._db = LaunchpadPersistence()
        self._db.open()

    def _load_registry(self) -> None:
        self._registry = self._scan_desktop_files()
        logger.info("Launchpad: %d apps loaded", len(self._registry))

        if not self._db.has_any_positions():
            self._auto_layout()

    def _setup_window(self) -> None:
        assert self._db is not None
        cells = self._db.get_app_positions()
        folders = self._db.get_folders()
        self._window = LaunchpadWindow(
            registry=self._registry,
            cells=cells,
            folders=folders,
            on_activate=self._activate_app,
            on_hide=self._on_window_hidden,
            on_page_changed=self._on_page_changed,
        )
        self._window.set_application(self)

    def _setup_dbus(self) -> None:
        try:
            from launchpad.launchpad_dbus import LaunchpadDBusServer
            self._dbus_server = LaunchpadDBusServer(
                show_cb=self._show_window,
                hide_cb=self._hide_window,
                page_cb=self._goto_page,
            )
            self._dbus_server.start()
        except Exception:
            logger.warning("Could not start Launchpad DBus server (continuing without it)")

    # ── Auto-layout ───────────────────────────────────────────────────────────

    def _auto_layout(self) -> None:
        assert self._db is not None
        layout = GridLayout()
        sorted_ids = sorted(
            [did for did, info in self._registry.items() if not info.nodisplay],
            key=lambda did: self._registry[did].name.lower(),
        )
        cells = layout.auto_layout(sorted_ids)
        self._db.set_app_positions_bulk(cells)
        logger.info("Auto-layout: placed %d apps", len(cells))

    # ── App activation ────────────────────────────────────────────────────────

    def _activate_app(self, desktop_path: str) -> None:
        try:
            app_info = Gio.DesktopAppInfo.new_from_filename(desktop_path)
            if app_info:
                app_info.launch([], None)
                return
        except Exception:
            pass
        try:
            subprocess.Popen(["gtk-launch", Path(desktop_path).stem])
        except Exception:
            logger.exception("Failed to launch %s", desktop_path)

    # ── Window visibility callbacks ───────────────────────────────────────────

    def _show_window(self) -> None:
        GLib.idle_add(self._show_window_idle)

    def _show_window_idle(self) -> bool:
        if self._window:
            self._window.show_launchpad()
        return False

    def _hide_window(self) -> None:
        GLib.idle_add(self._hide_window_idle)

    def _hide_window_idle(self) -> bool:
        if self._window:
            self._window.set_visible(False)
        return False

    def _goto_page(self, page: int) -> None:
        GLib.idle_add(lambda: self._window and self._window.show_launchpad(page=page) or False)

    def _on_window_hidden(self) -> None:
        if self._dbus_server:
            try:
                self._dbus_server.interface.Hidden()
            except Exception:
                pass

    def _on_page_changed(self, page: int) -> None:
        if self._dbus_server:
            try:
                self._dbus_server.interface.notify_page_changed(page)
            except Exception:
                pass

    # ── App registry ──────────────────────────────────────────────────────────

    def _scan_desktop_files(self) -> dict:
        try:
            from dock.desktop_file import DesktopFileParser
        except ImportError:
            return {}

        registry: dict = {}
        parser = DesktopFileParser()
        for directory in _DESKTOP_DIRS:
            if not directory.is_dir():
                continue
            for desktop_file in directory.glob("*.desktop"):
                try:
                    info = parser.parse(desktop_file)
                    if info and not info.nodisplay:
                        registry[desktop_file.stem] = info
                except Exception:
                    continue
        return registry


def main() -> None:
    app = LaunchpadApplication()
    sys.exit(app.run(sys.argv))
