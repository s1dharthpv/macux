"""MacUX Notification Center — transient notification banner.

A banner is a small popup that appears at the top-right of the screen
for a configurable duration then auto-dismisses.  Critical notifications
remain until manually dismissed.

Multiple banners are queued; only one is shown at a time.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from notification_center.notification import Notification, Urgency

logger = logging.getLogger(__name__)

BANNER_WIDTH   = 340
BANNER_OFFSET_X = 8   # px from right edge
BANNER_OFFSET_Y = 36  # px from top (below menu bar)
DEFAULT_TIMEOUT_MS = 5000   # 5 s for normal notifications
CRITICAL_TIMEOUT_MS = 0     # no auto-dismiss for critical

_CSS = b"""
.macux-banner {
    background-color: rgba(30, 30, 32, 0.96);
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.10);
    box-shadow: 0 4px 20px rgba(0,0,0,0.45);
}
.macux-banner-app {
    font-size: 11px;
    font-weight: 600;
    color: rgba(255,255,255,0.55);
}
.macux-banner-summary {
    font-size: 13px;
    font-weight: 600;
    color: rgba(255,255,255,0.95);
}
.macux-banner-body {
    font-size: 12px;
    color: rgba(255,255,255,0.75);
}
.macux-banner-critical {
    border: 1.5px solid rgba(255, 69, 58, 0.80);
}
"""


class NotificationBanner(Gtk.Window):
    """One transient banner for a single notification."""

    __gtype_name__ = "MacuxNotificationBanner"

    def __init__(
        self,
        notif: Notification,
        on_dismissed: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._notif = notif
        self._on_dismissed = on_dismissed
        self._timeout_id: int = 0

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(BANNER_WIDTH, -1)
        self.add_css_class("macux-banner")
        if notif.urgency == int(Urgency.CRITICAL):
            self.add_css_class("macux-banner-critical")

        self._build()
        self.connect("map", self._on_map)

    def _build(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(8)

        # App icon
        icon_name = self._notif.app_icon or self._notif.icon_name_fallback()
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(28)
        icon.set_valign(Gtk.Align.START)
        box.append(icon)

        # Text
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_hexpand(True)

        app_lbl = Gtk.Label(label=self._notif.app_name.upper())
        app_lbl.add_css_class("macux-banner-app")
        app_lbl.set_halign(Gtk.Align.START)
        vbox.append(app_lbl)

        summary_lbl = Gtk.Label(label=self._notif.summary)
        summary_lbl.add_css_class("macux-banner-summary")
        summary_lbl.set_halign(Gtk.Align.START)
        summary_lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END = 3
        vbox.append(summary_lbl)

        body = self._notif.short_body(80)
        if body:
            body_lbl = Gtk.Label(label=body)
            body_lbl.add_css_class("macux-banner-body")
            body_lbl.set_halign(Gtk.Align.START)
            body_lbl.set_wrap(True)
            body_lbl.set_wrap_mode(2)   # PANGO_WRAP_WORD_CHAR
            body_lbl.set_max_width_chars(40)
            vbox.append(body_lbl)

        box.append(vbox)

        # Dismiss button
        dismiss = Gtk.Button()
        dismiss.set_icon_name("window-close-symbolic")
        dismiss.add_css_class("flat")
        dismiss.set_valign(Gtk.Align.START)
        dismiss.connect("clicked", lambda _: self._dismiss())
        box.append(dismiss)

        self.set_child(box)

    def show_banner(self) -> None:
        self.present()

    def _dismiss(self) -> None:
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0
        if self._on_dismissed:
            self._on_dismissed(self._notif.notif_id)
        self.close()

    def _on_map(self, window: Gtk.Window) -> None:
        self._position()
        timeout = self._compute_timeout()
        if timeout > 0:
            self._timeout_id = GLib.timeout_add(timeout, self._dismiss)

    def _compute_timeout(self) -> int:
        if self._notif.urgency == int(Urgency.CRITICAL):
            return 0  # no auto-dismiss
        if self._notif.expire_timeout > 0:
            return self._notif.expire_timeout
        if self._notif.expire_timeout == 0:
            return 0
        return DEFAULT_TIMEOUT_MS

    def _position(self) -> None:
        try:
            import gi as _gi
            _gi.require_version("GdkX11", "4.0")
            from gi.repository import GdkX11
            surface = self.get_surface()
            if not surface or not isinstance(surface, GdkX11.X11Surface):
                return
            display = Gdk.Display.get_default()
            monitors = display.get_monitors()
            if not monitors.get_n_items():
                return
            monitor = monitors.get_item(0)
            geo = monitor.get_geometry()
            x = geo.x + geo.width - BANNER_WIDTH - BANNER_OFFSET_X
            y = geo.y + BANNER_OFFSET_Y
            surface.move(x, y)
        except Exception as exc:
            logger.debug("Banner: X11 positioning failed: %s", exc)


class BannerManager:
    """
    Queues and shows one banner at a time.

    Usage::

        mgr = BannerManager()
        mgr.load_css()
        mgr.enqueue(notif)
    """

    def __init__(self) -> None:
        self._queue: deque[Notification] = deque()
        self._current: NotificationBanner | None = None

    def load_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def enqueue(self, notif: Notification) -> None:
        self._queue.append(notif)
        self._show_next_if_idle()

    def _show_next_if_idle(self) -> None:
        if self._current is not None:
            return
        if not self._queue:
            return
        notif = self._queue.popleft()
        self._current = NotificationBanner(notif, on_dismissed=self._on_dismissed)
        self._current.show_banner()

    def _on_dismissed(self, notif_id: int) -> None:
        self._current = None
        # Schedule next banner after a brief gap
        GLib.timeout_add(200, self._show_next_if_idle)
