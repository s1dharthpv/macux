"""MacUX Notification Center — notification card widget.

NotificationCard is a GTK4 widget representing one notification in the
history panel.  It contains: app icon, app name, summary, body excerpt,
relative timestamp, and a dismiss button.
"""

from __future__ import annotations

import time
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from notification_center.notification import Notification, format_timestamp

_CSS = b"""
.macux-notif-card {
    background-color: rgba(255,255,255,0.06);
    border-radius: 8px;
    padding: 10px 12px;
    margin: 3px 6px;
}
.macux-notif-card:hover {
    background-color: rgba(255,255,255,0.10);
}
.macux-notif-app {
    font-size: 11px;
    font-weight: 600;
    color: rgba(255,255,255,0.55);
}
.macux-notif-summary {
    font-size: 13px;
    font-weight: 600;
    color: rgba(255,255,255,0.92);
}
.macux-notif-body {
    font-size: 12px;
    color: rgba(255,255,255,0.68);
}
.macux-notif-time {
    font-size: 11px;
    color: rgba(255,255,255,0.40);
}
"""


class NotificationCard(Gtk.Box):
    """Single notification card for the history scroll list."""

    __gtype_name__ = "MacuxNotificationCard"

    def __init__(
        self,
        notif: Notification,
        on_dismiss: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._notif = notif
        self._on_dismiss = on_dismiss
        self.add_css_class("macux-notif-card")
        self._build()

    @property
    def notif_id(self) -> int:
        return self._notif.notif_id

    def _build(self) -> None:
        # App icon
        icon_name = self._notif.app_icon or self._notif.icon_name_fallback()
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(24)
        icon.set_valign(Gtk.Align.START)
        self.append(icon)

        # Text column
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_hexpand(True)

        # Top row: app name + timestamp
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        app_lbl = Gtk.Label(label=self._notif.app_name)
        app_lbl.add_css_class("macux-notif-app")
        app_lbl.set_halign(Gtk.Align.START)
        app_lbl.set_hexpand(True)
        top_row.append(app_lbl)

        time_lbl = Gtk.Label(label=format_timestamp(self._notif.timestamp))
        time_lbl.add_css_class("macux-notif-time")
        time_lbl.set_halign(Gtk.Align.END)
        top_row.append(time_lbl)
        vbox.append(top_row)

        summary_lbl = Gtk.Label(label=self._notif.summary)
        summary_lbl.add_css_class("macux-notif-summary")
        summary_lbl.set_halign(Gtk.Align.START)
        summary_lbl.set_ellipsize(3)
        vbox.append(summary_lbl)

        body = self._notif.short_body(120)
        if body:
            body_lbl = Gtk.Label(label=body)
            body_lbl.add_css_class("macux-notif-body")
            body_lbl.set_halign(Gtk.Align.START)
            body_lbl.set_wrap(True)
            body_lbl.set_max_width_chars(42)
            vbox.append(body_lbl)

        self.append(vbox)

        # Dismiss button
        btn = Gtk.Button()
        btn.set_icon_name("window-close-symbolic")
        btn.add_css_class("flat")
        btn.set_valign(Gtk.Align.START)
        btn.connect("clicked", lambda _: self._on_dismiss and self._on_dismiss(self._notif.notif_id))
        self.append(btn)
