"""MacUX Notification Center — history panel window.

A slide-down panel anchored to the top-right of the screen (below the menu
bar) containing a scrollable list of NotificationCard widgets and a
"Clear All" button.
"""

from __future__ import annotations

import logging
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Adw

from notification_center.card import NotificationCard
from notification_center.notification import Notification

logger = logging.getLogger(__name__)

WINDOW_WIDTH   = 360
WINDOW_MAX_H   = 560
OFFSET_X       = 8
OFFSET_Y       = 36   # below 28 px menu bar

_CSS = b"""
.macux-nc {
    background-color: rgba(22, 22, 24, 0.96);
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.09);
}
.macux-nc-header {
    border-bottom: 1px solid rgba(255,255,255,0.07);
    padding: 8px 12px;
}
.macux-nc-title {
    font-size: 13px;
    font-weight: 700;
    color: rgba(255,255,255,0.90);
}
.macux-nc-clear {
    font-size: 12px;
    color: rgba(255,255,255,0.50);
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 0 4px;
}
.macux-nc-clear:hover {
    color: rgba(255,255,255,0.85);
}
.macux-nc-empty {
    font-size: 13px;
    color: rgba(255,255,255,0.35);
    padding: 24px 0;
}
"""


class NotificationCenterWindow(Gtk.Window):
    """Notification Center history panel."""

    __gtype_name__ = "MacuxNotificationCenterWindow"

    def __init__(
        self,
        on_dismiss: Callable[[int], None] | None = None,
        on_clear_all: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_dismiss   = on_dismiss
        self._on_clear_all = on_clear_all
        self._list_box: Gtk.ListBox | None = None
        self._empty_label: Gtk.Label | None = None
        self._cards: dict[int, Gtk.ListBoxRow] = {}  # notif_id → row

        self._load_css()
        self._build()
        self.connect("map", self._on_map)

    # ── Public API ─────────────────────────────────────────────────────────────

    def load_notifications(self, notifications: list[Notification]) -> None:
        """Populate the list from a list of Notification objects."""
        self._clear_list()
        for notif in notifications:
            self._add_card(notif)
        self._update_empty_state()

    def add_notification(self, notif: Notification) -> None:
        """Prepend a new notification card to the top of the list."""
        self._add_card(notif, prepend=True)
        self._update_empty_state()

    def remove_notification(self, notif_id: int) -> None:
        row = self._cards.pop(notif_id, None)
        if row and self._list_box:
            self._list_box.remove(row)
        self._update_empty_state()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.set_title("Notification Center")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(WINDOW_WIDTH, -1)
        self.add_css_class("macux-nc")

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.add_css_class("macux-nc-header")
        title = Gtk.Label(label="Notification Center")
        title.add_css_class("macux-nc-title")
        title.set_hexpand(True)
        title.set_halign(Gtk.Align.START)
        header.append(title)

        clear_btn = Gtk.Button(label="Clear All")
        clear_btn.add_css_class("macux-nc-clear")
        clear_btn.connect("clicked", self._on_clear_clicked)
        header.append(clear_btn)
        outer.append(header)

        # Scrollable list
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(80)
        scroll.set_max_content_height(WINDOW_MAX_H)
        scroll.set_propagate_natural_height(True)

        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.set_show_separators(False)
        scroll.set_child(self._list_box)
        outer.append(scroll)

        # Empty state
        self._empty_label = Gtk.Label(label="No notifications")
        self._empty_label.add_css_class("macux-nc-empty")
        self._empty_label.set_halign(Gtk.Align.CENTER)
        self._empty_label.set_visible(True)
        outer.append(self._empty_label)

        self.set_child(outer)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _add_card(self, notif: Notification, prepend: bool = False) -> None:
        if notif.notif_id in self._cards:
            # Replace existing card (handles replaces_id)
            self.remove_notification(notif.notif_id)

        card = NotificationCard(notif, on_dismiss=self._handle_dismiss)
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        row.set_child(card)

        self._cards[notif.notif_id] = row
        if self._list_box:
            if prepend:
                self._list_box.prepend(row)
            else:
                self._list_box.append(row)

    def _clear_list(self) -> None:
        if self._list_box:
            for row in list(self._cards.values()):
                self._list_box.remove(row)
        self._cards.clear()

    def _update_empty_state(self) -> None:
        if self._empty_label:
            self._empty_label.set_visible(len(self._cards) == 0)
        if self._list_box:
            self._list_box.set_visible(len(self._cards) > 0)

    def _handle_dismiss(self, notif_id: int) -> None:
        self.remove_notification(notif_id)
        if self._on_dismiss:
            self._on_dismiss(notif_id)

    def _on_clear_clicked(self, btn: Gtk.Button) -> None:
        self._clear_list()
        self._update_empty_state()
        if self._on_clear_all:
            self._on_clear_all()

    # ── CSS + positioning ─────────────────────────────────────────────────────

    def _load_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _on_map(self, window: Gtk.Window) -> None:
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
            x = geo.x + geo.width - WINDOW_WIDTH - OFFSET_X
            y = geo.y + OFFSET_Y
            surface.move(x, y)
        except Exception as exc:
            logger.debug("NotificationCenter: X11 positioning failed: %s", exc)
