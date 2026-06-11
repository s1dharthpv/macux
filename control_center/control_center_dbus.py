"""MacUX Control Center — DBus service (com.macux.ControlCenter).

Note: from __future__ import annotations is intentionally absent.
dasbus inspects type annotations at class-definition time.
"""

import logging
from typing import Callable

from dasbus.connection import SessionMessageBus
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Bool, Str

logger = logging.getLogger(__name__)

DBUS_NAME = "com.macux.ControlCenter"
DBUS_PATH = "/com/macux/ControlCenter"

VALID_PANELS = {"wifi", "bluetooth", "volume", "brightness", "battery"}

ShowHideCallback = Callable[[], None]
PanelCallback = Callable[[str], None]


@dbus_interface("com.macux.ControlCenter")
class ControlCenterInterface:
    """DBus interface for the MacUX Control Center."""

    def __init__(
        self,
        show_cb: ShowHideCallback,
        hide_cb: ShowHideCallback,
        panel_cb: PanelCallback | None = None,
    ) -> None:
        self._show_cb = show_cb
        self._hide_cb = hide_cb
        self._panel_cb = panel_cb
        self._visible: bool = False
        self._active_panel: str = "wifi"

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

    # ── Panel ──────────────────────────────────────────────────────────────────

    def ShowPanel(self, panel: Str) -> None:
        """Show the Control Center and switch to *panel*."""
        panel = str(panel).lower()
        if panel not in VALID_PANELS:
            logger.warning("ControlCenter: unknown panel %r", panel)
            return
        self._active_panel = panel
        if self._panel_cb:
            self._panel_cb(panel)
        self.PanelChanged(panel)
        if not self._visible:
            self.Show()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def Visible(self) -> Bool:
        return self._visible

    @property
    def ActivePanel(self) -> Str:
        return self._active_panel

    # ── Signals ────────────────────────────────────────────────────────────────

    @dbus_signal
    def Shown(self) -> None:
        pass

    @dbus_signal
    def Hidden(self) -> None:
        pass

    @dbus_signal
    def PanelChanged(self, panel: Str) -> None:
        pass

    # ── Internal ───────────────────────────────────────────────────────────────

    def notify_panel_changed(self, panel: str) -> None:
        """Called by the window when the user switches panels."""
        self._active_panel = panel
        try:
            self.PanelChanged(panel)
        except Exception:
            pass


class ControlCenterDBusServer:
    """Owns the com.macux.ControlCenter session bus name."""

    def __init__(
        self,
        show_cb: ShowHideCallback,
        hide_cb: ShowHideCallback,
        panel_cb: PanelCallback | None = None,
    ) -> None:
        self._bus = SessionMessageBus()
        self._interface = ControlCenterInterface(
            show_cb=show_cb,
            hide_cb=hide_cb,
            panel_cb=panel_cb,
        )

    def start(self) -> None:
        self._bus.publish_object(DBUS_PATH, self._interface)
        self._bus.register_service(DBUS_NAME)
        logger.info("ControlCenter DBus service registered: %s", DBUS_NAME)

    def stop(self) -> None:
        try:
            self._bus.unregister_service(DBUS_NAME)
            self._bus.unpublish_object(DBUS_PATH)
        except Exception:
            logger.exception("Error stopping ControlCenter DBus server")

    @property
    def interface(self) -> ControlCenterInterface:
        return self._interface
