"""MacUX Notification Center — com.macux.NotificationCenter DBus service.

Note: from __future__ import annotations is intentionally absent.
dasbus inspects type annotations at class-definition time.
"""

import logging
from typing import Callable

from dasbus.connection import SessionMessageBus
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Bool, Int32, Str, UInt32

logger = logging.getLogger(__name__)

DBUS_NAME = "com.macux.NotificationCenter"
DBUS_PATH = "/com/macux/NotificationCenter"

ShowHideCallback  = Callable[[], None]
ClearCallback     = Callable[[], None]
CountCallback     = Callable[[], int]


@dbus_interface("com.macux.NotificationCenter")
class NotificationCenterInterface:
    """DBus interface for the MacUX Notification Center."""

    def __init__(
        self,
        show_cb:  ShowHideCallback,
        hide_cb:  ShowHideCallback,
        clear_cb: ClearCallback | None = None,
        count_cb: CountCallback | None = None,
    ) -> None:
        self._show_cb  = show_cb
        self._hide_cb  = hide_cb
        self._clear_cb = clear_cb
        self._count_cb = count_cb
        self._visible: bool = False

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

    # ── Notification operations ────────────────────────────────────────────────

    def Clear(self) -> None:
        """Dismiss all notifications."""
        if self._clear_cb:
            self._clear_cb()
        self.Cleared()

    def GetCount(self) -> UInt32:
        """Return number of undismissed notifications."""
        if self._count_cb:
            return UInt32(self._count_cb())
        return UInt32(0)

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def Visible(self) -> Bool:
        return self._visible

    # ── Signals ────────────────────────────────────────────────────────────────

    @dbus_signal
    def Shown(self) -> None:
        pass

    @dbus_signal
    def Hidden(self) -> None:
        pass

    @dbus_signal
    def Cleared(self) -> None:
        pass

    @dbus_signal
    def NotificationAdded(self, notif_id: UInt32, app_name: Str, summary: Str) -> None:
        pass

    # ── Internal ───────────────────────────────────────────────────────────────

    def notify_notification_added(self, notif_id: int, app_name: str, summary: str) -> None:
        """Called by the app layer when a new notification arrives."""
        try:
            self.NotificationAdded(UInt32(notif_id), Str(app_name), Str(summary))
        except Exception:
            pass


class NotificationCenterDBusServer:
    """Owns the com.macux.NotificationCenter session bus name."""

    def __init__(
        self,
        show_cb:  ShowHideCallback,
        hide_cb:  ShowHideCallback,
        clear_cb: ClearCallback | None = None,
        count_cb: CountCallback | None = None,
    ) -> None:
        self._bus = SessionMessageBus()
        self._interface = NotificationCenterInterface(
            show_cb=show_cb,
            hide_cb=hide_cb,
            clear_cb=clear_cb,
            count_cb=count_cb,
        )

    def start(self) -> None:
        self._bus.publish_object(DBUS_PATH, self._interface)
        self._bus.register_service(DBUS_NAME)
        logger.info("NotificationCenter DBus service registered: %s", DBUS_NAME)

    def stop(self) -> None:
        try:
            self._bus.unregister_service(DBUS_NAME)
            self._bus.unpublish_object(DBUS_PATH)
        except Exception:
            logger.exception("Error stopping NotificationCenter DBus server")

    @property
    def interface(self) -> NotificationCenterInterface:
        return self._interface
