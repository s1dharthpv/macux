"""MacUX Dock — separator widget between pinned and running sections."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


class DockSeparator(Gtk.Box):
    """
    A vertical hairline separator between dock sections.

    Styled via .macux-dock-separator CSS class (themes/gtk4/components/dock.css).
    """

    __gtype_name__ = "MacuxDockSeparator"

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("macux-dock-separator")
        self.set_valign(Gtk.Align.CENTER)
        self.set_size_request(1, 32)
