"""MacUX Notification Center — org.freedesktop.Notifications DBus service.

Replaces the system notification daemon.  Registered on the session bus at:
  bus name:  org.freedesktop.Notifications
  path:      /org/freedesktop/Notifications

Note: from __future__ import annotations is intentionally absent.
dasbus inspects type annotations at class-definition time.
"""

import logging
import time
from typing import Callable, Tuple

from dasbus.connection import SessionMessageBus
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Bool, Int32, Str, Structure, UInt32

from notification_center.notification import (
    CLOSE_REASON_DISMISSED,
    CLOSE_REASON_EXPIRED,
    CLOSE_REASON_REQUESTED,
    Notification,
    Urgency,
)

logger = logging.getLogger(__name__)

FD_DBUS_NAME = "org.freedesktop.Notifications"
FD_DBUS_PATH = "/org/freedesktop/Notifications"

# Capabilities advertised to clients
_CAPABILITIES = [
    "body",
    "body-markup",
    "body-hyperlinks",
    "icon-static",
    "actions",
    "persistence",
    "sound",
]

NotifyCallback = Callable[[Notification], None]
CloseCallback  = Callable[[int, int], None]   # (notif_id, reason)


def _unpack_variant(value):
    """Unwrap a GLib.Variant or return the value unchanged."""
    if value is None:
        return None
    if hasattr(value, "unpack"):
        return value.unpack()
    return value


def _extract_urgency(hints: dict) -> int:
    """Pull urgency byte from hints dict; default NORMAL."""
    raw = hints.get("urgency")
    if raw is None:
        return int(Urgency.NORMAL)
    val = _unpack_variant(raw)
    try:
        return int(val)
    except (TypeError, ValueError):
        return int(Urgency.NORMAL)


@dbus_interface("org.freedesktop.Notifications")
class FreedesktopNotificationsInterface:
    """
    Implements the freedesktop.org Desktop Notifications specification v1.2.
    https://specifications.freedesktop.org/notification-spec/
    """

    def __init__(
        self,
        on_notify: NotifyCallback | None = None,
        on_close:  CloseCallback  | None = None,
    ) -> None:
        self._on_notify = on_notify
        self._on_close  = on_close
        self._next_id: int = 1

    # ── Core methods ──────────────────────────────────────────────────────────

    def Notify(
        self,
        app_name: Str,
        replaces_id: UInt32,
        app_icon: Str,
        summary: Str,
        body: Str,
        actions: list[Str],
        hints: Structure,
        expire_timeout: Int32,
    ) -> UInt32:
        """Create or replace a notification; returns the assigned ID."""
        if int(replaces_id) > 0:
            notif_id = int(replaces_id)
        else:
            notif_id = self._next_id
            self._next_id += 1

        urgency = _extract_urgency(dict(hints) if hints else {})

        notif = Notification(
            notif_id=notif_id,
            app_name=str(app_name),
            app_icon=str(app_icon),
            summary=str(summary),
            body=str(body),
            actions=[str(a) for a in (actions or [])],
            hints=dict(hints) if hints else {},
            urgency=urgency,
            expire_timeout=int(expire_timeout),
            timestamp=time.time(),
        )

        if self._on_notify:
            try:
                self._on_notify(notif)
            except Exception:
                logger.exception("FDNotifications: on_notify callback error")

        return UInt32(notif_id)

    def CloseNotification(self, id: UInt32) -> None:
        """Forcibly close the notification with the given ID."""
        notif_id = int(id)
        if self._on_close:
            try:
                self._on_close(notif_id, CLOSE_REASON_REQUESTED)
            except Exception:
                logger.exception("FDNotifications: on_close callback error")
        try:
            self.NotificationClosed(UInt32(notif_id), UInt32(CLOSE_REASON_REQUESTED))
        except Exception:
            pass

    def GetCapabilities(self) -> list[Str]:
        return list(_CAPABILITIES)

    def GetServerInformation(self) -> Tuple[Str, Str, Str, Str]:
        return ("MacUX Notification Center", "MacUX", "1.0", "1.2")

    # ── Signals ────────────────────────────────────────────────────────────────

    @dbus_signal
    def NotificationClosed(self, id: UInt32, reason: UInt32) -> None:
        pass

    @dbus_signal
    def ActionInvoked(self, id: UInt32, action_key: Str) -> None:
        pass

    # ── Internal helpers ───────────────────────────────────────────────────────

    def emit_closed(self, notif_id: int, reason: int) -> None:
        """Emit NotificationClosed signal safely (called by banner/app code)."""
        try:
            self.NotificationClosed(UInt32(notif_id), UInt32(reason))
        except Exception:
            pass

    def emit_action(self, notif_id: int, action_key: str) -> None:
        """Emit ActionInvoked signal safely."""
        try:
            self.ActionInvoked(UInt32(notif_id), Str(action_key))
        except Exception:
            pass


class FreedesktopNotificationsServer:
    """Owns the org.freedesktop.Notifications session bus name."""

    def __init__(
        self,
        on_notify: NotifyCallback | None = None,
        on_close:  CloseCallback  | None = None,
    ) -> None:
        self._bus = SessionMessageBus()
        self._interface = FreedesktopNotificationsInterface(
            on_notify=on_notify,
            on_close=on_close,
        )

    def start(self) -> None:
        self._bus.publish_object(FD_DBUS_PATH, self._interface)
        self._bus.register_service(FD_DBUS_NAME)
        logger.info("Notifications DBus service registered: %s", FD_DBUS_NAME)

    def stop(self) -> None:
        try:
            self._bus.unregister_service(FD_DBUS_NAME)
            self._bus.unpublish_object(FD_DBUS_PATH)
        except Exception:
            logger.exception("Error stopping Notifications DBus server")

    @property
    def interface(self) -> FreedesktopNotificationsInterface:
        return self._interface
