"""com.macux.MissionControl DBus service — Python companion to the GNOME extension.

IMPORTANT: do NOT add `from __future__ import annotations` to this file.
dasbus inspects type annotations eagerly at class-definition time; deferred
evaluation breaks DBusSpecificationGenerator.
"""

import logging
from typing import Callable, Optional

from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Bool, Str, UInt32

_log = logging.getLogger(__name__)


@dbus_interface("com.macux.MissionControl")
class MissionControlInterface:
    """Exposes Mission Control activate/deactivate/toggle to DBus clients."""

    def __init__(
        self,
        activate_cb: Optional[Callable[[], None]] = None,
        deactivate_cb: Optional[Callable[[], None]] = None,
        window_selected_cb: Optional[Callable[[int], None]] = None,
    ) -> None:
        self._active: bool = False
        self._activate_cb = activate_cb
        self._deactivate_cb = deactivate_cb
        self._window_selected_cb = window_selected_cb

    # ── Signals ────────────────────────────────────────────────────────────────

    @dbus_signal
    def Activated(self) -> None:
        pass

    @dbus_signal
    def Deactivated(self) -> None:
        pass

    @dbus_signal
    def WindowSelected(self, xid: UInt32) -> None:
        pass

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def Active(self) -> Bool:
        return Bool(self._active)

    # ── Methods ────────────────────────────────────────────────────────────────

    def Activate(self) -> None:
        if self._active:
            return
        self._active = True
        if self._activate_cb:
            try:
                self._activate_cb()
            except Exception:
                _log.exception("activate_cb raised")
        try:
            self.Activated()
        except Exception:
            pass

    def Deactivate(self) -> None:
        if not self._active:
            return
        self._active = False
        if self._deactivate_cb:
            try:
                self._deactivate_cb()
            except Exception:
                _log.exception("deactivate_cb raised")
        try:
            self.Deactivated()
        except Exception:
            pass

    def Toggle(self) -> None:
        if self._active:
            self.Deactivate()
        else:
            self.Activate()

    # ── Helper called by the GNOME extension proxy ─────────────────────────────

    def notify_activated(self) -> None:
        """Set active=True and emit Activated (called when extension triggers)."""
        self._active = True
        try:
            self.Activated()
        except Exception:
            pass

    def notify_deactivated(self) -> None:
        """Set active=False and emit Deactivated."""
        self._active = False
        try:
            self.Deactivated()
        except Exception:
            pass

    def notify_window_selected(self, xid: int) -> None:
        """Emit WindowSelected with *xid*."""
        try:
            self.WindowSelected(UInt32(xid))
        except Exception:
            pass
        if self._window_selected_cb:
            try:
                self._window_selected_cb(xid)
            except Exception:
                _log.exception("window_selected_cb raised")
