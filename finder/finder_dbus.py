"""com.macux.Finder DBus service.

IMPORTANT: do NOT add `from __future__ import annotations` to this file.
dasbus inspects type annotations eagerly at class-definition time; deferred
evaluation breaks DBusSpecificationGenerator.
"""

import logging
from typing import Callable, Optional

from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Str

_log = logging.getLogger(__name__)


@dbus_interface("com.macux.Finder")
class FinderInterface:
    """Exposes Finder navigation and file reveal to DBus clients."""

    def __init__(
        self,
        open_path_cb: Optional[Callable[[str], None]] = None,
        reveal_file_cb: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._current_path: str = ""
        self._open_path_cb = open_path_cb
        self._reveal_file_cb = reveal_file_cb

    # ── Signals ────────────────────────────────────────────────────────────────

    @dbus_signal
    def PathChanged(self, path: Str) -> None:
        pass

    @dbus_signal
    def SelectionChanged(self, path: Str) -> None:
        pass

    # ── Methods ────────────────────────────────────────────────────────────────

    def OpenPath(self, path: Str) -> None:
        p = str(path)
        self._current_path = p
        if self._open_path_cb:
            try:
                self._open_path_cb(p)
            except Exception:
                _log.exception("open_path_cb raised")
        try:
            self.PathChanged(Str(p))
        except Exception:
            pass

    def RevealFile(self, path: Str) -> None:
        p = str(path)
        if self._reveal_file_cb:
            try:
                self._reveal_file_cb(p)
            except Exception:
                _log.exception("reveal_file_cb raised")
        try:
            self.SelectionChanged(Str(p))
        except Exception:
            pass

    def GetCurrentPath(self) -> Str:
        return Str(self._current_path)

    # ── Notification helpers ───────────────────────────────────────────────────

    def notify_path_changed(self, path: str) -> None:
        """Called by the app layer when the user navigates to a new directory."""
        self._current_path = path
        try:
            self.PathChanged(Str(path))
        except Exception:
            pass

    def notify_selection_changed(self, path: str) -> None:
        """Called by the app layer when the selection changes."""
        try:
            self.SelectionChanged(Str(path))
        except Exception:
            pass
