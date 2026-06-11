"""MacUX Dock — running application monitor.

Uses Wnck (libwnck-3.0) to track which apps have open windows,
then maps them to .desktop file IDs so the dock can show indicators.

Matching strategy (in order):
  1. StartupWMClass field in .desktop file == window.get_class_instance_name()
  2. exec_base (basename of Exec) == window.get_class_instance_name() (lower)
  3. exec_base == window.get_class_group_name() (lower)

This is the same heuristic used by GNOME Shell and KDE.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

logger = logging.getLogger(__name__)

ChangeCallback = Callable[[], None]


class AppMonitor:
    """
    Tracks running applications via Wnck and maps them to desktop IDs.

    Must be used from the GLib main thread.

    Usage::

        monitor = AppMonitor(app_registry)
        monitor.start()
        ...
        ids = monitor.get_running_desktop_ids()  # {"firefox.desktop", ...}
        count = monitor.get_window_count("firefox.desktop")  # 2
        monitor.stop()
    """

    def __init__(self, app_registry: dict | None = None) -> None:
        """
        Args:
            app_registry: dict[desktop_id, AppInfo] from DesktopFileParser.
                          Can be updated live via set_registry().
        """
        self._registry: dict = app_registry or {}
        self._screen = None
        self._running: dict[str, set[int]] = {}  # desktop_id → set of xids
        self._signal_ids: list[int] = []
        self._callbacks: list[ChangeCallback] = []

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Initialise Wnck and connect window-open/close signals."""
        try:
            import gi
            gi.require_version("Wnck", "3.0")
            from gi.repository import Wnck

            self._screen = Wnck.Screen.get_default()
            if self._screen is None:
                logger.warning("AppMonitor: Wnck.Screen.get_default() returned None")
                return

            self._screen.force_update()

            # Connect signals
            self._signal_ids = [
                self._screen.connect("window-opened", self._on_window_opened),
                self._screen.connect("window-closed", self._on_window_closed),
            ]

            # Snapshot currently open windows
            for window in self._screen.get_windows():
                self._register_window(window)

            logger.debug(
                "AppMonitor started — %d running apps",
                len(self._running),
            )
        except Exception:
            logger.exception("AppMonitor: failed to initialise Wnck")

    def stop(self) -> None:
        """Disconnect Wnck signals."""
        if self._screen:
            for sig_id in self._signal_ids:
                try:
                    self._screen.disconnect(sig_id)
                except Exception:
                    pass
        self._signal_ids = []
        self._running.clear()

    def set_registry(self, registry: dict) -> None:
        """Update the app registry (e.g. after a rescan)."""
        self._registry = registry
        # Re-evaluate all open windows against new registry
        if self._screen:
            self._running.clear()
            for window in self._screen.get_windows():
                self._register_window(window)
            self._notify()

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_running_desktop_ids(self) -> set[str]:
        """Return the set of desktop_ids that have at least one open window."""
        return {did for did, xids in self._running.items() if xids}

    def get_window_count(self, desktop_id: str) -> int:
        """Return the number of open windows for the given app."""
        return len(self._running.get(desktop_id, set()))

    def on_changed(self, callback: ChangeCallback) -> None:
        """Register a callback invoked whenever running-app state changes."""
        self._callbacks.append(callback)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_window_opened(self, _screen, window) -> None:
        self._register_window(window)
        self._notify()

    def _on_window_closed(self, _screen, window, _unused=None) -> None:
        xid = window.get_xid()
        for xids in self._running.values():
            xids.discard(xid)
        self._notify()

    def _register_window(self, window) -> None:
        """Map a Wnck window to a desktop_id (if possible) and record it."""
        try:
            from gi.repository import Wnck
            wtype = window.get_window_type()
            if wtype not in (Wnck.WindowType.NORMAL, Wnck.WindowType.DIALOG):
                return
        except Exception:
            pass

        desktop_id = self._match_desktop_id(window)
        if desktop_id:
            xid = window.get_xid()
            self._running.setdefault(desktop_id, set()).add(xid)

    def _match_desktop_id(self, window) -> str | None:
        """
        Return the desktop_id for a Wnck.Window or None if unrecognised.

        Tries in order:
          1. StartupWMClass match
          2. exec_base vs class_instance_name
          3. exec_base vs class_group_name
        """
        try:
            wm_class = (window.get_class_instance_name() or "").lower()
            wm_group = (window.get_class_group_name() or "").lower()
        except Exception:
            return None

        for desktop_id, info in self._registry.items():
            # 1. StartupWMClass
            swc = info.startup_wm_class.lower() if info.startup_wm_class else ""
            if swc and (swc == wm_class or swc == wm_group):
                return desktop_id

            # 2. exec_base
            eb = info.exec_base.lower()
            if eb and (eb == wm_class or eb == wm_group):
                return desktop_id

            # 3. Name match (loose fallback)
            name_lower = info.name.lower().replace(" ", "-")
            if name_lower and (name_lower == wm_class or name_lower == wm_group):
                return desktop_id

        return None

    def _notify(self) -> None:
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                logger.exception("AppMonitor change callback raised")
