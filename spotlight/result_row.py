"""MacUX Spotlight — single result row widget.

Each row contains:
  - Category icon (left, 32 px)
  - App/file icon (left, 32 px, themed)
  - Title label (primary text)
  - Subtitle label (path or description, secondary text)

The active selection is driven by the parent ListBox selection model.
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk

from spotlight.result import SearchResult


class ResultRow(Gtk.ListBoxRow):
    """A single search result row."""

    __gtype_name__ = "MacuxSpotlightResultRow"

    def __init__(self, result: SearchResult) -> None:
        super().__init__()
        self.result = result
        self._build()

    def _build(self) -> None:
        self.add_css_class("macux-spotlight-result")

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.set_margin_start(12)
        hbox.set_margin_end(12)
        hbox.set_margin_top(6)
        hbox.set_margin_bottom(6)

        # Icon
        icon = Gtk.Image()
        icon.set_pixel_size(32)
        if self.result.icon.startswith("/"):
            icon.set_from_file(self.result.icon)
        else:
            icon.set_from_icon_name(self.result.icon or "application-x-executable")
        icon.set_valign(Gtk.Align.CENTER)
        hbox.append(icon)

        # Text column
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        vbox.set_hexpand(True)
        vbox.set_valign(Gtk.Align.CENTER)

        title = Gtk.Label(label=self.result.name)
        title.set_halign(Gtk.Align.START)
        title.set_ellipsize(3)   # PANGO_ELLIPSIZE_END
        title.add_css_class("title")
        vbox.append(title)

        if self.result.subtitle:
            subtitle = Gtk.Label(label=self.result.subtitle)
            subtitle.set_halign(Gtk.Align.START)
            subtitle.set_ellipsize(3)
            subtitle.add_css_class("subtitle")
            subtitle.add_css_class("dim-label")
            vbox.append(subtitle)

        hbox.append(vbox)

        # Category badge (right-aligned)
        badge = Gtk.Label(label=self._category_label())
        badge.add_css_class("macux-badge")
        badge.set_valign(Gtk.Align.CENTER)
        hbox.append(badge)

        self.set_child(hbox)

    def _category_label(self) -> str:
        return {
            "apps":       "App",
            "files":      "File",
            "folders":    "Folder",
            "calculator": "=",
            "web":        "Web",
        }.get(self.result.category, self.result.category.title())
