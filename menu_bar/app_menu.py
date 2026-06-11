"""MacUX Menu Bar — AppMenu Registrar consumer.

Tracks the focused window via Wnck, fetches its application menu from
com.canonical.AppMenu.Registrar (appmenu-gtk-module), and parses the
dbusmenu layout into a MenuItem tree.

Gracefully no-ops when:
  - appmenu-gtk-module / the registrar service is not installed
  - Wnck is unavailable
  - A window has no exported menu

Usage::

    consumer = AppMenuConsumer(
        on_app_changed=lambda name: window.set_app_title(name),
        on_menu_changed=lambda root: window.rebuild_menu(root),
    )
    consumer.start()
"""

from __future__ import annotations

import logging
from typing import Callable

from menu_bar.menu_model import MenuItem, parse_layout

logger = logging.getLogger(__name__)

_REGISTRAR_BUS  = "com.canonical.AppMenu.Registrar"
_REGISTRAR_PATH = "/com/canonical/AppMenu/Registrar"


class AppMenuConsumer:
    """
    Bridges the focused window's exported app menu into the menu bar.

    Callbacks
    ---------
    on_app_changed(app_name: str)
        Called when the focused window changes.  *app_name* is the WM class
        group name or window title (best effort).

    on_menu_changed(root: MenuItem | None)
        Called with the parsed menu tree (root node, children = top-level
        items).  Passes None when the window has no menu.
    """

    def __init__(
        self,
        on_app_changed: Callable[[str], None],
        on_menu_changed: Callable[[MenuItem | None], None],
    ) -> None:
        self._on_app_changed = on_app_changed
        self._on_menu_changed = on_menu_changed
        self._registrar = None
        self._session_bus = None
        self._current_xid: int | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._start_wnck()
        self._connect_registrar()

    # ── Wnck focus tracking ───────────────────────────────────────────────────

    def _start_wnck(self) -> None:
        try:
            import gi
            gi.require_version("Wnck", "3.0")
            from gi.repository import Wnck
            screen = Wnck.Screen.get_default()
            screen.force_update()
            screen.connect("active-window-changed", self._on_active_window_changed)
            win = screen.get_active_window()
            if win:
                self._handle_window(win)
        except Exception as exc:
            logger.warning("AppMenuConsumer: Wnck unavailable: %s", exc)

    def _on_active_window_changed(self, screen, _prev) -> None:
        win = screen.get_active_window()
        if win:
            self._handle_window(win)
        else:
            self._on_app_changed("")
            self._on_menu_changed(None)

    def _handle_window(self, win) -> None:
        xid = win.get_xid()
        app_name = win.get_class_group_name() or win.get_name() or ""
        self._on_app_changed(app_name)
        if xid != self._current_xid:
            self._current_xid = xid
            self._fetch_menu(xid)

    # ── AppMenu Registrar ─────────────────────────────────────────────────────

    def _connect_registrar(self) -> None:
        try:
            from dasbus.connection import SessionMessageBus
            self._session_bus = SessionMessageBus()
            self._registrar = self._session_bus.get_proxy(
                _REGISTRAR_BUS, _REGISTRAR_PATH
            )
        except Exception as exc:
            logger.warning("AppMenuConsumer: AppMenu Registrar unavailable: %s", exc)

    def _fetch_menu(self, xid: int) -> None:
        if self._registrar is None:
            self._on_menu_changed(None)
            return
        try:
            service_name, menu_path = self._registrar.GetMenuForWindow(xid)
            self._load_dbusmenu(str(service_name), str(menu_path))
        except Exception as exc:
            logger.debug("AppMenuConsumer: no menu for XID %d: %s", xid, exc)
            self._on_menu_changed(None)

    def _load_dbusmenu(self, service_name: str, menu_path: str) -> None:
        if not service_name or not menu_path:
            self._on_menu_changed(None)
            return
        try:
            proxy = self._session_bus.get_proxy(service_name, menu_path)
            _revision, layout = proxy.GetLayout(0, -1, [])
            raw = layout.unpack() if hasattr(layout, "unpack") else layout
            root = parse_layout(raw)
            self._on_menu_changed(root)
            proxy.LayoutUpdated.connect(
                lambda _rev, _parent: self._load_dbusmenu(service_name, menu_path)
            )
        except Exception as exc:
            logger.debug("AppMenuConsumer: menu load error: %s", exc)
            self._on_menu_changed(None)
