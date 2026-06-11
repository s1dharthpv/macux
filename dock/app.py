"""MacUX Dock — Adw.Application entry point.

Sets up the full dock stack:
  1. Load config from macuxd DBus (or local config as fallback)
  2. Open persistence database
  3. Parse .desktop file registry
  4. Start AppMonitor (Wnck)
  5. Apply theme CSS via ThemeEngine
  6. Create DockWindow
  7. Register com.macux.Dock DBus service
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk

from dock.app_monitor import AppMonitor
from dock.desktop_file import DesktopFileParser
from dock.persistence import DockPersistence
from dock.window import DockWindow

logger = logging.getLogger(__name__)

_APP_ID = "com.macux.Dock"

# Default config if macuxd is unavailable
_DEFAULT_CONFIG: dict = {
    "position": "bottom",
    "icon_size": 48,
    "magnification": True,
    "magnification_max": 72,
    "magnification_radius": 100,
    "auto_hide": False,
    "auto_hide_delay": 0.5,
    "auto_hide_show_delay": 0.1,
    "show_running_indicators": True,
    "show_trash": True,
    "bounce_on_launch": True,
    "bounce_on_alert": True,
}


class DockApplication(Adw.Application):
    """
    MacUX Dock GTK4 Application.

    Lifecycle:
      - activate → create window, start monitors, register DBus
      - shutdown → stop monitors, close DB, unregister DBus
    """

    def __init__(self) -> None:
        super().__init__(
            application_id=_APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._window: DockWindow | None = None
        self._db: DockPersistence | None = None
        self._monitor: AppMonitor | None = None
        self._dbus_server = None
        self._config: dict = dict(_DEFAULT_CONFIG)

        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def _on_activate(self, _app) -> None:
        if self._window is not None:
            self._window.present()
            return

        self._load_config()
        self._open_db()
        self._apply_theme()

        registry = DesktopFileParser().load_all()
        self._monitor = AppMonitor(registry)
        self._monitor.start()

        self._window = DockWindow(
            persistence=self._db,
            app_registry=registry,
            app_monitor=self._monitor,
            config=self._config,
        )
        self._window.set_application(self)
        self._window.present()

        self._register_dbus()
        logger.info("MacUX Dock started.")

    def _on_shutdown(self, _app) -> None:
        logger.info("MacUX Dock shutting down...")
        if self._dbus_server:
            self._dbus_server.stop()
        if self._monitor:
            self._monitor.stop()
        if self._db:
            self._db.close()

    # ── Config ─────────────────────────────────────────────────────────────────

    def _load_config(self) -> None:
        """Load dock section from macuxd config via DBus, or use defaults."""
        try:
            from dasbus.connection import SessionMessageBus
            bus = SessionMessageBus()
            proxy = bus.get_proxy("com.macux.Daemon", "/com/macux/Daemon")
            for key, default in _DEFAULT_CONFIG.items():
                try:
                    val = proxy.GetConfig(f"dock.{key}")
                    self._config[key] = val
                except Exception:
                    self._config[key] = default
            logger.debug("Dock config loaded from macuxd.")
        except Exception as exc:
            logger.info("macuxd not available (%s) — using defaults.", exc)
            self._config = dict(_DEFAULT_CONFIG)

    # ── Database ───────────────────────────────────────────────────────────────

    def _open_db(self) -> None:
        self._db = DockPersistence()
        self._db.open()

        # Seed with sensible defaults if empty
        if not self._db.get_pinned_apps():
            self._seed_default_apps()

    def _seed_default_apps(self) -> None:
        """Pin a minimal set of useful apps on first launch."""
        defaults = [
            "org.gnome.Nautilus.desktop",
            "firefox.desktop",
            "org.gnome.Terminal.desktop",
            "org.gnome.Settings.desktop",
        ]
        for i, desktop_id in enumerate(defaults):
            try:
                self._db.pin_app(desktop_id, i)
            except Exception:
                pass

    # ── Theme ──────────────────────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        try:
            from themes.theme_engine import ThemeEngine
            engine = ThemeEngine()
            engine.init()
            engine.apply_to_display()
            engine.apply_component_css("dock")
            logger.debug("Dock theme applied.")
        except Exception as exc:
            logger.warning("Could not apply MacUX theme: %s", exc)

    # ── DBus ───────────────────────────────────────────────────────────────────

    def _register_dbus(self) -> None:
        if self._window is None or self._db is None:
            return
        try:
            from dock.dock_dbus import DockDBusServer
            self._dbus_server = DockDBusServer(
                persistence=self._db,
                show_cb=self._window.show_dock,
                hide_cb=self._window.hide_dock,
                bounce_cb=self._window.bounce_app,
                config_cb=self._on_config_changed,
            )
            self._dbus_server.start()
        except Exception as exc:
            logger.warning("Could not register Dock DBus service: %s", exc)

    def _on_config_changed(self, key: str, value) -> None:
        """Receive config changes from DBus and apply to window."""
        short_key = key.replace("dock.", "")
        self._config[short_key] = value
        if self._window:
            self._window.reload_config(self._config)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    )
    app = DockApplication()
    sys.exit(app.run(sys.argv))
