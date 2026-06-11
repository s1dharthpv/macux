"""MacUX Orchestrator Daemon — entry point and main loop."""

from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path

from gi.repository import GLib

logger = logging.getLogger(__name__)

_LOG_DIR = Path("~/.local/share/macux/logs").expanduser()
_COMPONENTS: list[dict] = [
    {
        "name": "dock",
        "command": [sys.executable, "-m", "dock"],
        "restart_on_crash": True,
        "max_restarts": 5,
        "restart_delay": 2.0,
    },
    {
        "name": "spotlight",
        "command": [sys.executable, "-m", "spotlight"],
        "restart_on_crash": True,
        "max_restarts": 5,
        "restart_delay": 2.0,
    },
    {
        "name": "launchpad",
        "command": [sys.executable, "-m", "launchpad"],
        "restart_on_crash": True,
        "max_restarts": 5,
        "restart_delay": 2.0,
    },
    {
        "name": "notification_center",
        "command": [sys.executable, "-m", "notification_center"],
        "restart_on_crash": True,
        "max_restarts": 5,
        "restart_delay": 2.0,
    },
    {
        "name": "control_center",
        "command": [sys.executable, "-m", "control_center"],
        "restart_on_crash": True,
        "max_restarts": 5,
        "restart_delay": 2.0,
    },
    {
        "name": "finder",
        "command": [sys.executable, "-m", "finder"],
        "restart_on_crash": True,
        "max_restarts": 3,
        "restart_delay": 3.0,
    },
]


def _configure_logging(debug: bool = False) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    fmt = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(_LOG_DIR / "macuxd.log"),
    ]
    logging.basicConfig(level=level, format=fmt, handlers=handlers)


class MacuxDaemon:
    """
    MacUX Orchestrator Daemon.

    Lifecycle:
      1. Load configuration
      2. Open databases
      3. Initialise theme engine (CSS generation, font detection)
      4. Register DBus service
      5. Start all components via watchdog
      6. Run GLib main loop
      7. On SIGTERM/SIGINT: stop all components, release DBus, exit cleanly
    """

    def __init__(self, debug: bool = False) -> None:
        self._debug = debug
        self._loop = GLib.MainLoop()
        self._config = None
        self._watchdog = None
        self._dbus_server = None
        self._databases: dict = {}
        self._theme_engine = None

    def run(self) -> int:
        """Start the daemon. Returns exit code."""
        _configure_logging(self._debug)
        logger.info("MacUX Daemon starting (pid=%d)", os.getpid())

        try:
            self._setup()
            self._register_signals()
            logger.info("MacUX Daemon ready. Running main loop.")
            self._loop.run()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received.")
        except Exception:
            logger.exception("Unhandled exception in daemon startup")
            return 1
        finally:
            self._shutdown()

        logger.info("MacUX Daemon exited cleanly.")
        return 0

    def _setup(self) -> None:
        from macuxd.config import ConfigManager
        from macuxd.db import open_all_databases
        from macuxd.dbus_service import DaemonDBusServer
        from macuxd.eventbus import EventBus
        from macuxd.watchdog import ComponentConfig, ComponentWatchdog
        from themes.theme_engine import ThemeEngine

        # Config
        self._config = ConfigManager()
        self._config.load()
        self._config.start_watching()
        logger.info("Configuration loaded.")

        # Databases
        self._databases = open_all_databases()
        logger.info("Databases opened.")

        # Event bus
        self._event_bus = EventBus()

        # Theme engine (non-GTK init: font detection + CSS generation)
        self._theme_engine = ThemeEngine(self._config)
        self._theme_engine.init()
        self._theme_engine.on_change(self._on_theme_changed)
        # Wire config changes → theme invalidation
        self._config.on_change(self._theme_engine.on_config_changed)
        logger.info(
            "Theme engine initialised (variant=%s).",
            self._theme_engine.get_variant(),
        )

        # Watchdog
        self._watchdog = ComponentWatchdog(
            state_change_callback=self._on_component_state_changed
        )
        for comp in _COMPONENTS:
            cfg = ComponentConfig(
                name=comp["name"],
                command=comp["command"],
                restart_on_crash=comp.get("restart_on_crash", True),
                max_restarts=comp.get("max_restarts", 5),
                restart_delay=comp.get("restart_delay", 2.0),
            )
            self._watchdog.register(cfg)

        # DBus — pass theme_engine so SetTheme can call engine.set_variant()
        self._dbus_server = DaemonDBusServer(
            self._config, self._watchdog, self._theme_engine
        )
        self._dbus_server.start()

        # Wire config changes to DBus signals
        self._config.on_change(self._on_config_changed)

        # Start components
        self._watchdog.start_all()
        logger.info("All components started.")

    def _shutdown(self) -> None:
        logger.info("Shutting down MacUX Daemon...")
        if self._watchdog:
            self._watchdog.stop_all()
        if self._config:
            self._config.stop_watching()
        for db in self._databases.values():
            db.close()
        if self._dbus_server:
            self._dbus_server.stop()
        logger.info("Shutdown complete.")

    def _register_signals(self) -> None:
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._handle_sigterm)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._handle_sigterm)

    def _handle_sigterm(self) -> bool:
        logger.info("Received termination signal, stopping...")
        self._loop.quit()
        return GLib.SOURCE_REMOVE

    def _on_config_changed(self, key: str, value) -> None:
        logger.debug("Config changed: %s = %r", key, value)
        if self._dbus_server:
            self._dbus_server.emit_system_event("macux.config", "changed", {"key": key})

    def _on_theme_changed(self, variant: str) -> None:
        logger.info("Theme changed to: %s", variant)
        if self._dbus_server:
            self._dbus_server.emit_theme_changed(variant)
        self._event_bus.publish("macux.theme", "changed", {"variant": variant})

    def _on_component_state_changed(self, component: str, state) -> None:
        logger.info("Component state: %s → %s", component, state.name)
        if self._dbus_server:
            self._dbus_server.emit_component_state_changed(component, state)
        self._event_bus.publish("macux.component", "state_changed", {
            "component": component,
            "state": state.name,
        })


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        prog="macuxd",
        description="MacUX Desktop Environment Orchestrator Daemon",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    args = parser.parse_args()

    if args.version:
        from macuxd import __version__
        print(f"MacUX Daemon v{__version__}")
        sys.exit(0)

    daemon = MacuxDaemon(debug=args.debug)
    sys.exit(daemon.run())


if __name__ == "__main__":
    main()
