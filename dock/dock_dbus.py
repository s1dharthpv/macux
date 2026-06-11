"""MacUX Dock — DBus service implementation (com.macux.Dock).

Exposes the dock's show/hide, pin/unpin, and configuration API over the
session DBus so other components and macux-ctl can control it.

Note: from __future__ import annotations is intentionally absent.
dasbus inspects type annotations at class-definition time via the
@dbus_interface decorator; deferred evaluation (PEP 563) makes all
annotations strings, which breaks dasbus's DBusSpecificationGenerator.
"""

import logging
from typing import Callable

from dasbus.connection import SessionMessageBus
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Bool, Int32, Str

# Real import — needed at class-definition time because @dbus_interface
# inspects __init__ type annotations eagerly (no deferred evaluation).
from dock.persistence import DockPersistence

logger = logging.getLogger(__name__)

DBUS_NAME = "com.macux.Dock"
DBUS_PATH = "/com/macux/Dock"

ShowHideCallback = Callable[[], None]
PinCallback = Callable[[str, int], None]
UnpinCallback = Callable[[str], None]
BounceCallback = Callable[[str, str], None]
ConfigCallback = Callable[[str, object], None]


@dbus_interface("com.macux.Dock")
class DockInterface:
    """DBus interface for the MacUX Dock."""

    def __init__(
        self,
        persistence: DockPersistence,
        show_cb: ShowHideCallback,
        hide_cb: ShowHideCallback,
        bounce_cb: BounceCallback,
        config_cb: ConfigCallback,
    ) -> None:
        self._db = persistence
        self._show_cb = show_cb
        self._hide_cb = hide_cb
        self._bounce_cb = bounce_cb
        self._config_cb = config_cb
        self._visible: bool = True
        self._autohide: bool = True
        self._magnification: bool = True
        self._icon_size: int = 48
        self._position: str = "bottom"

    # ── Visibility ─────────────────────────────────────────────────────────────

    def Show(self) -> None:
        self._visible = True
        self._show_cb()
        self.VisibilityChanged(True)

    def Hide(self) -> None:
        self._visible = False
        self._hide_cb()
        self.VisibilityChanged(False)

    def Toggle(self) -> None:
        if self._visible:
            self.Hide()
        else:
            self.Show()

    # ── Pinned apps ────────────────────────────────────────────────────────────

    def PinApp(self, desktop_id: Str, position: Int32) -> None:
        self._db.pin_app(desktop_id, int(position))
        self.AppPinned(desktop_id, position)

    def UnpinApp(self, desktop_id: Str) -> None:
        self._db.unpin_app(desktop_id)
        self.AppUnpinned(desktop_id)

    def GetPinnedApps(self) -> list[Str]:
        return self._db.get_pinned_apps()

    def MovePinnedApp(self, desktop_id: Str, new_position: Int32) -> None:
        self._db.move_app(desktop_id, int(new_position))

    # ── Configuration ──────────────────────────────────────────────────────────

    def SetPosition(self, position: Str) -> None:
        valid = ("bottom", "left", "right")
        if position not in valid:
            raise ValueError(f"Invalid position {position!r}. Must be one of {valid}")
        self._position = position
        self._config_cb("dock.position", position)

    def SetIconSize(self, size: Int32) -> None:
        if not (16 <= size <= 256):
            raise ValueError(f"Icon size must be 16–256, got {size}")
        self._icon_size = int(size)
        self._config_cb("dock.icon_size", int(size))

    # ── Bounce ─────────────────────────────────────────────────────────────────

    def BounceApp(self, desktop_id: Str, bounce_type: Str) -> None:
        valid = ("launch", "alert", "once")
        if bounce_type not in valid:
            raise ValueError(f"Invalid bounce type {bounce_type!r}. Must be one of {valid}")
        self._bounce_cb(desktop_id, bounce_type)

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def AutoHide(self) -> Bool:
        return self._autohide

    @AutoHide.setter
    def AutoHide(self, value: Bool) -> None:
        self._autohide = bool(value)
        self._config_cb("dock.auto_hide", bool(value))

    @property
    def IconSize(self) -> Int32:
        return self._icon_size

    @IconSize.setter
    def IconSize(self, value: Int32) -> None:
        self.SetIconSize(value)

    @property
    def Position(self) -> Str:
        return self._position

    @Position.setter
    def Position(self, value: Str) -> None:
        self.SetPosition(value)

    @property
    def Visible(self) -> Bool:
        return self._visible

    @property
    def Magnification(self) -> Bool:
        return self._magnification

    @Magnification.setter
    def Magnification(self, value: Bool) -> None:
        self._magnification = bool(value)
        self._config_cb("dock.magnification", bool(value))

    # ── Signals ────────────────────────────────────────────────────────────────

    @dbus_signal
    def AppPinned(self, desktop_id: Str, position: Int32) -> None:
        pass

    @dbus_signal
    def AppUnpinned(self, desktop_id: Str) -> None:
        pass

    @dbus_signal
    def VisibilityChanged(self, visible: Bool) -> None:
        pass


class DockDBusServer:
    """Owns the session bus name for com.macux.Dock."""

    def __init__(
        self,
        persistence: DockPersistence,
        show_cb: ShowHideCallback,
        hide_cb: ShowHideCallback,
        bounce_cb: BounceCallback | None = None,
        config_cb: ConfigCallback | None = None,
    ) -> None:
        self._bus = SessionMessageBus()
        self._interface = DockInterface(
            persistence=persistence,
            show_cb=show_cb,
            hide_cb=hide_cb,
            bounce_cb=bounce_cb or (lambda *_: None),
            config_cb=config_cb or (lambda *_: None),
        )

    def start(self) -> None:
        self._bus.publish_object(DBUS_PATH, self._interface)
        self._bus.register_service(DBUS_NAME)
        logger.info("Dock DBus service registered: %s", DBUS_NAME)

    def stop(self) -> None:
        try:
            self._bus.unregister_service(DBUS_NAME)
            self._bus.unpublish_object(DBUS_PATH)
        except Exception:
            logger.exception("Error stopping Dock DBus server")

    def emit_app_pinned(self, desktop_id: str, position: int) -> None:
        self._interface.AppPinned(desktop_id, position)

    def emit_app_unpinned(self, desktop_id: str) -> None:
        self._interface.AppUnpinned(desktop_id)

    def emit_visibility_changed(self, visible: bool) -> None:
        self._interface.VisibilityChanged(visible)
