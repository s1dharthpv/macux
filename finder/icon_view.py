"""MacUX Finder — icon grid view."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib  # noqa: E402
from typing import Callable

from finder.file_model import FileItem


_ICON_SIZE = 72
_LABEL_WIDTH = 80


class FileIconCell(Gtk.Box):
    """A single cell in the icon view: large icon + filename label."""

    def __init__(self, item: FileItem) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.item = item
        self.set_size_request(_LABEL_WIDTH + 8, _ICON_SIZE + 28)
        self.set_halign(Gtk.Align.CENTER)

        img = Gtk.Image.new_from_icon_name(item.icon_name())
        img.set_pixel_size(_ICON_SIZE)
        self.append(img)

        lbl = Gtk.Label(label=item.name)
        lbl.set_max_width_chars(10)
        lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        lbl.set_wrap(False)
        lbl.set_width_chars(10)
        lbl.set_xalign(0.5)
        lbl.add_css_class("caption")
        self.append(lbl)


class IconView(Gtk.ScrolledWindow):
    """``Gtk.FlowBox``-backed icon grid for directory contents."""

    def __init__(
        self,
        activate_cb: Callable[[FileItem], None] | None = None,
        selection_cb: Callable[[FileItem | None], None] | None = None,
    ) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_vexpand(True)
        self.set_hexpand(True)

        self._activate_cb = activate_cb
        self._selection_cb = selection_cb
        self._items: list[FileItem] = []

        self._flow = Gtk.FlowBox()
        self._flow.set_valign(Gtk.Align.START)
        self._flow.set_max_children_per_line(20)
        self._flow.set_min_children_per_line(1)
        self._flow.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._flow.set_column_spacing(4)
        self._flow.set_row_spacing(4)
        self._flow.set_margin_start(12)
        self._flow.set_margin_top(12)
        self._flow.add_css_class("icon-view")
        self._flow.connect("child-activated", self._on_child_activated)
        self._flow.connect("selected-children-changed", self._on_selection_changed)
        self.set_child(self._flow)

    def set_items(self, items: list[FileItem]) -> None:
        self._items = items
        # Remove all children
        child = self._flow.get_child_at_index(0)
        while child:
            self._flow.remove(child)
            child = self._flow.get_child_at_index(0)

        for item in items:
            cell = FileIconCell(item)
            self._flow.append(cell)

    def _on_child_activated(self, _fb: Gtk.FlowBox, child: Gtk.FlowBoxChild) -> None:
        cell = child.get_child()
        if isinstance(cell, FileIconCell) and self._activate_cb:
            self._activate_cb(cell.item)

    def _on_selection_changed(self, _fb: Gtk.FlowBox) -> None:
        if self._selection_cb is None:
            return
        selected = self._flow.get_selected_children()
        if not selected:
            self._selection_cb(None)
            return
        cell = selected[0].get_child()
        if isinstance(cell, FileIconCell):
            self._selection_cb(cell.item)
