"""MacUX Finder — list view (Gtk.TreeView-style table)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GObject  # noqa: E402
from typing import Callable

from finder.file_model import FileItem, SortKey


class _FileRow(GObject.Object):
    __gtype_name__ = "FinderFileRow"

    def __init__(self, item: FileItem) -> None:
        super().__init__()
        self.item = item


class ListView(Gtk.ScrolledWindow):
    """Column list view for directory contents using Gtk.ColumnView."""

    def __init__(
        self,
        activate_cb: Callable[[FileItem], None] | None = None,
        selection_cb: Callable[[FileItem | None], None] | None = None,
        sort_changed_cb: Callable[[SortKey, bool], None] | None = None,
    ) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.set_vexpand(True)
        self.set_hexpand(True)

        self._activate_cb = activate_cb
        self._selection_cb = selection_cb
        self._sort_changed_cb = sort_changed_cb

        # Model
        self._store = Gtk.StringList()
        self._items: list[FileItem] = []

        # Selection model
        self._sel_model = Gtk.SingleSelection.new(None)
        self._sel_model.connect("selection-changed", self._on_selection_changed)

        # ColumnView
        self._col_view = Gtk.ColumnView.new(self._sel_model)
        self._col_view.set_show_row_separators(True)
        self._col_view.set_show_column_separators(False)
        self._col_view.add_css_class("list-view")
        self._col_view.connect("activate", self._on_activate)

        self._add_columns()
        self.set_child(self._col_view)

    def _add_columns(self) -> None:
        # Name column
        name_factory = Gtk.SignalListItemFactory()
        name_factory.connect("setup", self._setup_name_cell)
        name_factory.connect("bind", self._bind_name_cell)
        name_col = Gtk.ColumnViewColumn.new("Name", name_factory)
        name_col.set_resizable(True)
        name_col.set_expand(True)
        self._col_view.append_column(name_col)

        # Size column
        size_factory = Gtk.SignalListItemFactory()
        size_factory.connect("setup", self._setup_label_cell)
        size_factory.connect("bind", lambda _f, li: self._bind_attr_cell(li, "display_size"))
        size_col = Gtk.ColumnViewColumn.new("Size", size_factory)
        size_col.set_resizable(True)
        size_col.set_fixed_width(90)
        self._col_view.append_column(size_col)

        # Modified column
        mod_factory = Gtk.SignalListItemFactory()
        mod_factory.connect("setup", self._setup_label_cell)
        mod_factory.connect("bind", lambda _f, li: self._bind_attr_cell(li, "display_mtime"))
        mod_col = Gtk.ColumnViewColumn.new("Modified", mod_factory)
        mod_col.set_resizable(True)
        mod_col.set_fixed_width(130)
        self._col_view.append_column(mod_col)

        # Kind column
        kind_factory = Gtk.SignalListItemFactory()
        kind_factory.connect("setup", self._setup_label_cell)
        kind_factory.connect("bind", lambda _f, li: self._bind_attr_cell(li, "mime_type"))
        kind_col = Gtk.ColumnViewColumn.new("Kind", kind_factory)
        kind_col.set_resizable(True)
        kind_col.set_fixed_width(160)
        self._col_view.append_column(kind_col)

    # ── Cell factories ─────────────────────────────────────────────────────────

    def _setup_name_cell(self, _factory, list_item: Gtk.ListItem) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_start(4)
        img = Gtk.Image()
        img.set_pixel_size(16)
        lbl = Gtk.Label(xalign=0.0)
        lbl.set_ellipsize(3)
        lbl.set_hexpand(True)
        box.append(img)
        box.append(lbl)
        list_item.set_child(box)

    def _bind_name_cell(self, _factory, list_item: Gtk.ListItem) -> None:
        item = self._item_for(list_item)
        if item is None:
            return
        box = list_item.get_child()
        if not isinstance(box, Gtk.Box):
            return
        img = box.get_first_child()
        lbl = img.get_next_sibling() if img else None
        if img:
            img.set_from_icon_name(item.icon_name())
        if lbl:
            lbl.set_label(item.name)

    def _setup_label_cell(self, _factory, list_item: Gtk.ListItem) -> None:
        lbl = Gtk.Label(xalign=0.0)
        lbl.set_margin_start(4)
        list_item.set_child(lbl)

    def _bind_attr_cell(self, list_item: Gtk.ListItem, attr: str) -> None:
        item = self._item_for(list_item)
        lbl = list_item.get_child()
        if item and isinstance(lbl, Gtk.Label):
            lbl.set_label(str(getattr(item, attr, "")))

    def _item_for(self, list_item: Gtk.ListItem) -> FileItem | None:
        pos = list_item.get_position()
        if pos < len(self._items):
            return self._items[pos]
        return None

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_items(self, items: list[FileItem]) -> None:
        self._items = items
        model = Gtk.StringList.new([i.name for i in items])
        self._sel_model.set_model(model)
        self._col_view.set_model(self._sel_model)

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def _on_activate(self, _cv, position: int) -> None:
        if position < len(self._items) and self._activate_cb:
            self._activate_cb(self._items[position])

    def _on_selection_changed(self, sel: Gtk.SingleSelection, *_) -> None:
        if self._selection_cb is None:
            return
        pos = sel.get_selected()
        if pos < len(self._items):
            self._selection_cb(self._items[pos])
        else:
            self._selection_cb(None)
