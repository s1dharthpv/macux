"""MacUX Daemon DBus service — implements com.macux.Daemon interface."""

import logging
from typing import Any

from dasbus.connection import SessionMessageBus
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Str, Bool, Variant

from macuxd.config import ConfigManager
from macuxd.watchdog import ComponentWatchdog, ComponentState
from themes.theme_engine import ThemeEngine

logger = logging.getLogger(__name__)

DBUS_NAME = "com.macux.Daemon"
DBUS_PATH = "/com/macux/Daemon"


@dbus_interface("com.macux.Daemon")
class MacuxDaemonInterface:
    """DBus interface implementation for the MacUX orchestrator daemon."""

    def __init__(
        self,
        config: ConfigManager,
        watchdog: ComponentWatchdog,
        theme_engine: ThemeEngine | None = None,
    ) -> None:
        self._config = config
        self._watchdog = watchdog
        self._theme_engine = theme_engine

    # --- Version / health ---

    def GetVersion(self) -> Str:
        from macuxd import __version__
        return __version__

    def Ping(self) -> Bool:
        return True

    # --- Configuration ---

    def GetConfig(self, key: Str) -> Variant:
        value = self._config.get(key)
        if value is None:
            raise ValueError(f"Config key not found: {key!r}")
        return value  # dasbus handles GVariant boxing

    def SetConfig(self, key: Str, value: Variant) -> None:
        self._config.set(key, value)
        self.ConfigChanged(key, value)

    def ReloadConfig(self) -> None:
        self._config.load()
        logger.info("Config reloaded via DBus")

    def ResetConfig(self, key: Str) -> None:
        self._config.reset(key)
        new_val = self._config.get(key)
        self.ConfigChanged(key, new_val)

    # --- Component management ---

    def GetComponents(self) -> list[Str]:
        return list(self._watchdog.get_all_statuses().keys())

    def GetComponentStatus(self, component: Str) -> dict[Str, Variant]:
        status = self._watchdog.get_status(component)
        if not status:
            raise ValueError(f"Unknown component: {component!r}")
        return {
            "state": status.state.name,
            "pid": status.pid or -1,
            "restarts": status.restarts,
        }

    def RestartComponent(self, component: Str) -> None:
        logger.info("DBus: restart requested for %s", component)
        self._watchdog.restart(component)

    def StopComponent(self, component: Str) -> None:
        self._watchdog.stop(component)

    def StartComponent(self, component: Str) -> None:
        self._watchdog.start(component)

    # --- Theme ---

    def SetTheme(self, theme: Str) -> None:
        if theme not in ("light", "dark", "auto"):
            raise ValueError(f"Invalid theme: {theme!r}. Must be light|dark|auto")
        self._config.set("global.theme", theme)
        if self._theme_engine is not None:
            self._theme_engine.set_variant(theme)
        self.ThemeChanged(theme)

    def GetTheme(self) -> Str:
        if self._theme_engine is not None:
            return self._theme_engine.get_variant()
        return self._config.get("global.theme", "auto")

    def GetThemeCSS(self, component: Str) -> Str:
        """Return the CSS for a specific component (used by component processes)."""
        if self._theme_engine is None:
            return ""
        try:
            return self._theme_engine.build_component_css(component)
        except Exception as exc:
            logger.warning("GetThemeCSS(%s) failed: %s", component, exc)
            return ""

    # --- Signals (dasbus generates stubs) ---

    @dbus_signal
    def ConfigChanged(self, key: Str, value: Variant) -> None:
        pass

    @dbus_signal
    def ThemeChanged(self, theme: Str) -> None:
        pass

    @dbus_signal
    def ComponentStateChanged(self, component: Str, state: Str) -> None:
        pass

    @dbus_signal
    def SystemEvent(self, category: Str, event: Str, data: dict) -> None:
        pass


class DaemonDBusServer:
    """Owns the DBus name and registers the MacuxDaemonInterface."""

    def __init__(
        self,
        config: ConfigManager,
        watchdog: ComponentWatchdog,
        theme_engine: ThemeEngine | None = None,
    ) -> None:
        self._bus = SessionMessageBus()
        self._interface = MacuxDaemonInterface(config, watchdog, theme_engine)
        self._proxy = None

    def start(self) -> None:
        self._bus.publish_object(DBUS_PATH, self._interface)
        self._bus.register_service(DBUS_NAME)
        logger.info("DBus service registered: %s at %s", DBUS_NAME, DBUS_PATH)

    def stop(self) -> None:
        try:
            self._bus.unregister_service(DBUS_NAME)
            self._bus.unpublish_object(DBUS_PATH)
        except Exception:
            logger.exception("Error while stopping DBus server")

    def emit_component_state_changed(self, component: str, state: ComponentState) -> None:
        self._interface.ComponentStateChanged(component, state.name)

    def emit_system_event(self, category: str, event: str, data: dict[str, Any]) -> None:
        self._interface.SystemEvent(category, event, data)

    def emit_theme_changed(self, variant: str) -> None:
        self._interface.ThemeChanged(variant)
