"""MacUX Spotlight — application entry point.

Wires together:
  - SpotlightIndexer    (Whoosh file index)
  - QueryRouter         (app registry + calculator + files + web)
  - SpotlightWindow     (GTK4 UI)
  - SpotlightDBusServer (com.macux.Spotlight DBus service)

The app registers a GSettings keybinding and listens for DBus Show/Hide
calls.  On first launch it starts an async index rebuild.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from spotlight.indexer import SpotlightIndexer
from spotlight.query_router import QueryRouter
from spotlight.result import SearchResult, ACTION_LAUNCH, ACTION_OPEN, ACTION_COPY, ACTION_URL
from spotlight.window import SpotlightWindow

logger = logging.getLogger(__name__)

_APP_ID = "com.macux.spotlight"
_DESKTOP_DIRS: list[Path] = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
]


class SpotlightApplication(Adw.Application):
    """
    GTK4 application hosting the MacUX Spotlight search UI.

    Lifecycle:
      1. activate()  → build window, start indexer, register DBus
      2. User presses ⌘Space (or DBus Show) → window.show_spotlight()
      3. User activates a result              → _activate_result()
      4. User presses Escape or clicks away  → window hidden
      5. shutdown()  → indexer.close(), dbus_server.stop()
    """

    def __init__(self) -> None:
        super().__init__(
            application_id=_APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._window: Optional[SpotlightWindow] = None
        self._indexer: Optional[SpotlightIndexer] = None
        self._router: Optional[QueryRouter] = None
        self._dbus_server = None

    # ── Adw.Application overrides ─────────────────────────────────────────────

    def do_activate(self) -> None:
        self._setup_logging()
        self._setup_indexer()
        self._setup_router()
        self._setup_window()
        self._setup_dbus()
        self._start_indexing()

    def do_shutdown(self) -> None:
        if self._dbus_server:
            try:
                self._dbus_server.stop()
            except Exception:
                logger.exception("Error stopping Spotlight DBus server")

        if self._indexer:
            try:
                self._indexer.close()
            except Exception:
                logger.exception("Error closing Spotlight indexer")

        Adw.Application.do_shutdown(self)

    # ── Setup helpers ─────────────────────────────────────────────────────────

    def _setup_logging(self) -> None:
        logging.basicConfig(
            level=logging.DEBUG,
            format="[macux-spotlight] %(levelname)s %(name)s: %(message)s",
        )

    def _setup_indexer(self) -> None:
        self._indexer = SpotlightIndexer()
        self._indexer.open()
        self._indexer.start_watching()

    def _setup_router(self) -> None:
        app_registry = self._load_app_registry()
        self._router = QueryRouter(
            app_registry=app_registry,
            indexer=self._indexer,
        )

    def _setup_window(self) -> None:
        self._window = SpotlightWindow(
            on_search=self._do_search,
            on_activate=self._activate_result,
            on_hide=self._on_window_hidden,
        )
        self._window.set_application(self)

    def _setup_dbus(self) -> None:
        try:
            from spotlight.spotlight_dbus import SpotlightDBusServer
            self._dbus_server = SpotlightDBusServer(
                indexer=self._indexer,
                router=self._router,
                show_cb=self._show_window,
                hide_cb=self._hide_window,
                query_cb=self._set_query,
            )
            self._dbus_server.start()
        except Exception:
            logger.warning("Could not start Spotlight DBus server (continuing without it)")

    def _start_indexing(self) -> None:
        assert self._indexer is not None
        stats = self._indexer.get_stats()
        if stats.get("doc_count", 0) == 0:
            logger.info("Empty index detected — triggering background rebuild")
            self._indexer.rebuild_async(
                on_progress=None,
                on_done=self._on_index_done,
            )

    # ── Search ────────────────────────────────────────────────────────────────

    def _do_search(self, query: str) -> list[SearchResult]:
        if not self._router:
            return []
        return self._router.search(query, max_results=12)

    # ── Result activation ─────────────────────────────────────────────────────

    def _activate_result(self, result: SearchResult) -> None:
        action = result.action

        if action == ACTION_LAUNCH:
            self._launch_app(result.path)
        elif action == ACTION_OPEN:
            self._open_file(result.path)
        elif action == ACTION_COPY:
            self._copy_to_clipboard(result.name)
        elif action == ACTION_URL:
            self._open_url(result.path)
        else:
            logger.warning("Unknown action %r for result %r", action, result.name)

    @staticmethod
    def _launch_app(desktop_path: str) -> None:
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

    @staticmethod
    def _open_file(path: str) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri(f"file://{path}", None)
        except Exception:
            try:
                subprocess.Popen(["xdg-open", path])
            except Exception:
                logger.exception("Failed to open %s", path)

    @staticmethod
    def _open_url(url: str) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
        except Exception:
            try:
                subprocess.Popen(["xdg-open", url])
            except Exception:
                logger.exception("Failed to open URL %s", url)

    def _copy_to_clipboard(self, text: str) -> None:
        display = Gdk.Display.get_default()
        if display:
            clipboard = display.get_clipboard()
            clipboard.set(text)
            logger.debug("Copied to clipboard: %s", text)

    # ── Window visibility ─────────────────────────────────────────────────────

    def _show_window(self) -> None:
        GLib.idle_add(self._show_window_idle)

    def _show_window_idle(self) -> bool:
        if self._window:
            self._window.show_spotlight()
        return False

    def _hide_window(self) -> None:
        GLib.idle_add(self._hide_window_idle)

    def _hide_window_idle(self) -> bool:
        if self._window:
            self._window.set_visible(False)
        return False

    def _set_query(self, query: str) -> None:
        GLib.idle_add(self._set_query_idle, query)

    def _set_query_idle(self, query: str) -> bool:
        if self._window:
            self._window.show_spotlight(query)
        return False

    def _on_window_hidden(self) -> None:
        if self._dbus_server:
            try:
                self._dbus_server.interface.Hidden()
            except Exception:
                pass

    # ── Index callbacks ────────────────────────────────────────────────────────

    def _on_index_done(self, doc_count: int, duration_sec: float) -> None:
        logger.info("Spotlight index ready: %d docs in %.1fs", doc_count, duration_sec)

    # ── App registry ──────────────────────────────────────────────────────────

    @staticmethod
    def _load_app_registry() -> dict:
        """Load all .desktop files from standard locations."""
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

        logger.debug("Loaded %d .desktop files for Spotlight", len(registry))
        return registry


def main() -> None:
    """Entry point invoked by __main__.py and the macux-spotlight script."""
    app = SpotlightApplication()
    sys.exit(app.run(sys.argv))
