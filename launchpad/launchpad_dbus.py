"""MacUX Launchpad — DBus service (com.macux.Launchpad).

Note: from __future__ import annotations is intentionally absent.
dasbus inspects type annotations at class-definition time; deferred
evaluation (PEP 563) turns all annotations into strings, which breaks
DBusSpecificationGenerator.  See dock/dock_dbus.py for the full story.
"""

import logging
from typing import Callable

from dasbus.connection import SessionMessageBus
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Bool, Int32, Str

logger = logging.getLogger(__name__)

DBUS_NAME = "com.macux.Launchpad"
DBUS_PATH = "/com/macux/Launchpad"

ShowHideCallback = Callable[[], None]
PageCallback = Callable[[int], None]


@dbus_interface("com.macux.Launchpad")
class LaunchpadInterface:
    """DBus interface for the MacUX Launchpad."""

    def __init__(
        self,
        show_cb: ShowHideCallback,
        hide_cb: ShowHideCallback,
        page_cb: PageCallback | None = None,
    ) -> None:
        self._show_cb = show_cb
        self._hide_cb = hide_cb
        self._page_cb = page_cb
        self._visible: bool = False
        self._current_page: int = 0

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

    def ShowOnPage(self, page: Int32) -> None:
        """Show the Launchpad and jump directly to the given page index."""
        self._current_page = int(page)
        self._visible = True
        if self._page_cb:
            self._page_cb(int(page))
        self._show_cb()
        self.Shown()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def Visible(self) -> Bool:
        return self._visible

    @property
    def CurrentPage(self) -> Int32:
        return self._current_page

    # ── Internal: called by the window when user changes page ─────────────────

    def notify_page_changed(self, page: int) -> None:
        self._current_page = page
        self.PageChanged(page)

    # ── Signals ────────────────────────────────────────────────────────────────

    @dbus_signal
    def Shown(self) -> None:
        pass

    @dbus_signal
    def Hidden(self) -> None:
        pass

    @dbus_signal
    def PageChanged(self, page: Int32) -> None:
        pass


class LaunchpadDBusServer:
    """Owns the com.macux.Launchpad session bus name."""

    def __init__(
        self,
        show_cb: ShowHideCallback,
        hide_cb: ShowHideCallback,
        page_cb: PageCallback | None = None,
    ) -> None:
        self._bus = SessionMessageBus()
        self._interface = LaunchpadInterface(
            show_cb=show_cb,
            hide_cb=hide_cb,
            page_cb=page_cb,
        )

    def start(self) -> None:
        self._bus.publish_object(DBUS_PATH, self._interface)
        self._bus.register_service(DBUS_NAME)
        logger.info("Launchpad DBus service registered: %s", DBUS_NAME)

    def stop(self) -> None:
        try:
            self._bus.unregister_service(DBUS_NAME)
            self._bus.unpublish_object(DBUS_PATH)
        except Exception:
            logger.exception("Error stopping Launchpad DBus server")

    @property
    def interface(self) -> LaunchpadInterface:
        return self._interface
