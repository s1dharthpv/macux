"""MacUX Menu Bar — DBus service (com.macux.MenuBar).

Note: from __future__ import annotations is intentionally absent.
dasbus inspects type annotations at class-definition time (see dock_dbus.py).
"""

import logging
from typing import Callable

from dasbus.connection import SessionMessageBus
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Bool, Str

logger = logging.getLogger(__name__)

DBUS_NAME = "com.macux.MenuBar"
DBUS_PATH = "/com/macux/MenuBar"

ShowHideCallback = Callable[[], None]
AppCallback = Callable[[str], None]


@dbus_interface("com.macux.MenuBar")
class MenuBarInterface:
    """DBus interface for the MacUX Menu Bar."""

    def __init__(
        self,
        show_cb: ShowHideCallback,
        hide_cb: ShowHideCallback,
    ) -> None:
        self._show_cb = show_cb
        self._hide_cb = hide_cb
        self._visible: bool = True
        self._active_app: str = ""

    # ── Visibility ─────────────────────────────────────────────────────────────

    def Show(self) -> None:
        self._visible = True
        self._show_cb()
        self.Shown()

    def Hide(self) -> None:
        self._visible = False
        self._hide_cb()
        self.Hidden()

    def Toggle(self) -> None:
        if self._visible:
            self.Hide()
        else:
            self.Show()

    # ── App name ───────────────────────────────────────────────────────────────

    def SetActiveApp(self, app_name: Str) -> None:
        """Force the menu bar to show a specific app name (used by macuxd)."""
        self._active_app = app_name
        self.ActiveAppChanged(app_name)

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def Visible(self) -> Bool:
        return self._visible

    @property
    def ActiveApp(self) -> Str:
        return self._active_app

    # ── Signals ────────────────────────────────────────────────────────────────

    @dbus_signal
    def Shown(self) -> None:
        pass

    @dbus_signal
    def Hidden(self) -> None:
        pass

    @dbus_signal
    def ActiveAppChanged(self, app_name: Str) -> None:
        pass

    # ── Internal ───────────────────────────────────────────────────────────────

    def notify_app_changed(self, app_name: str) -> None:
        """Called by AppMenuConsumer when the focused window changes."""
        self._active_app = app_name
        try:
            self.ActiveAppChanged(app_name)
        except Exception:
            pass


class MenuBarDBusServer:
    """Owns the com.macux.MenuBar session bus name."""

    def __init__(
        self,
        show_cb: ShowHideCallback,
        hide_cb: ShowHideCallback,
    ) -> None:
        self._bus = SessionMessageBus()
        self._interface = MenuBarInterface(show_cb=show_cb, hide_cb=hide_cb)

    def start(self) -> None:
        self._bus.publish_object(DBUS_PATH, self._interface)
        self._bus.register_service(DBUS_NAME)
        logger.info("MenuBar DBus service registered: %s", DBUS_NAME)

    def stop(self) -> None:
        try:
            self._bus.unregister_service(DBUS_NAME)
            self._bus.unpublish_object(DBUS_PATH)
        except Exception:
            logger.exception("Error stopping MenuBar DBus server")

    @property
    def interface(self) -> MenuBarInterface:
        return self._interface
