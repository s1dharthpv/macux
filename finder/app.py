"""MacUX Finder — Adw.Application entry point."""

from __future__ import annotations

import logging
import sys

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio  # noqa: E402

from finder.finder_dbus import FinderInterface  # noqa: E402

_log = logging.getLogger(__name__)

_DBUS_PATH = "/com/macux/Finder"
_DBUS_NAME = "com.macux.Finder"


class FinderApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=_DBUS_NAME,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self._finder_iface: FinderInterface | None = None
        self._window = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._finder_iface = FinderInterface(
            open_path_cb=self._on_open_path,
            reveal_file_cb=self._on_reveal_file,
        )
        self._setup_actions()

    def do_activate(self) -> None:
        if self._window is None:
            from finder.window import FinderWindow
            self._window = FinderWindow(application=self)
        self._window.present()

    def do_open(self, files, n_files: int, hint: str) -> None:
        self.do_activate()
        if files and self._window:
            self._window.navigate_to(files[0].get_path())

    def _setup_actions(self) -> None:
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Primary>q"])

        new_window_action = Gio.SimpleAction.new("new-window", None)
        new_window_action.connect("activate", self._on_new_window)
        self.add_action(new_window_action)
        self.set_accels_for_action("app.new-window", ["<Primary>n"])

    def _on_new_window(self, *_) -> None:
        from finder.window import FinderWindow
        win = FinderWindow(application=self)
        win.present()

    def _on_open_path(self, path: str) -> None:
        _log.debug("DBus open path: %s", path)
        if self._window:
            self._window.navigate_to(path)

    def _on_reveal_file(self, path: str) -> None:
        _log.debug("DBus reveal file: %s", path)
        from pathlib import Path as _Path
        parent = str(_Path(path).parent)
        if self._window:
            self._window.navigate_to(parent)


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    app = FinderApplication()
    sys.exit(app.run(sys.argv))
