"""MacUX Launchpad — single page widget.

Each page is a Gtk.Grid placed inside an Adw.Carousel.  The grid has a fixed
number of columns (COLS) and rows (ROWS).  Apps and folders are attached to
specific (col, row) cells.

Cell size = icon_size + label_height + v_padding.  The grid is centred
horizontally and vertically within the page.
"""

from __future__ import annotations

import logging

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

logger = logging.getLogger(__name__)

# Default grid dimensions (same as macOS Launchpad)
_COLS = 7
_ROWS = 5

# Pixel spacing between icons
_H_SPACING = 20
_V_SPACING = 20


class LaunchpadPage(Gtk.Box):
    """
    A single Launchpad page: a centred grid of app/folder icons.

    Args:
        cols:       Number of columns in the grid.
        rows:       Number of rows in the grid.
    """

    __gtype_name__ = "MacuxLaunchpadPage"

    def __init__(self, cols: int = _COLS, rows: int = _ROWS) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.cols = cols
        self.rows = rows
        self._grid = Gtk.Grid()
        self._grid.set_row_spacing(_V_SPACING)
        self._grid.set_column_spacing(_H_SPACING)
        self._grid.set_halign(Gtk.Align.CENTER)
        self._grid.set_valign(Gtk.Align.CENTER)
        self._grid.set_hexpand(True)
        self._grid.set_vexpand(True)
        self.append(self._grid)
        self.set_hexpand(True)
        self.set_vexpand(True)

    # ── Public API ────────────────────────────────────────────────────────────

    def place(self, widget: Gtk.Widget, col: int, row: int) -> None:
        """Place *widget* at (col, row).  Replaces any existing occupant."""
        existing = self._grid.get_child_at(col, row)
        if existing is not None:
            self._grid.remove(existing)
        self._grid.attach(widget, col, row, 1, 1)

    def remove_at(self, col: int, row: int) -> None:
        """Remove the widget at (col, row), if any."""
        child = self._grid.get_child_at(col, row)
        if child is not None:
            self._grid.remove(child)

    def get_at(self, col: int, row: int) -> Gtk.Widget | None:
        """Return the widget at (col, row), or None."""
        return self._grid.get_child_at(col, row)

    def clear(self) -> None:
        """Remove all children from the grid."""
        children: list[Gtk.Widget] = []
        child = self._grid.get_first_child()
        while child:
            children.append(child)
            child = child.get_next_sibling()
        for c in children:
            self._grid.remove(c)

    def set_all_dimmed(self, dimmed: bool) -> None:
        """Dim/undim all icon widgets on this page (used during search)."""
        child = self._grid.get_first_child()
        while child:
            if hasattr(child, "set_dimmed"):
                child.set_dimmed(dimmed)
            child = child.get_next_sibling()
