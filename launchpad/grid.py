"""MacUX Launchpad — pure-Python grid layout engine.

Responsible for the spatial logic of the paged icon grid.  No GTK here —
the grid engine is fully testable without a display.

Layout model
------------
  - Grid has COLS columns and ROWS rows per page.
  - Pages are numbered 0, 1, 2, …
  - Each app (or folder placeholder) occupies exactly one cell.
  - Cells are addressed as (page, row, col).
  - The linear index of a cell = page * COLS * ROWS + row * COLS + col.

Usage::

    layout = GridLayout(cols=7, rows=5)
    cells  = layout.auto_layout(list_of_desktop_ids)
    layout.page_count(cells)            # → 1 (if ≤35 apps)
    layout.find_empty(layout.occupied(cells))  # → GridCell(page=0, …)
"""

from __future__ import annotations

from dataclasses import dataclass

COLS_DEFAULT = 7
ROWS_DEFAULT = 5


@dataclass(frozen=True, order=True)
class GridCell:
    """An (page, row, col) coordinate inside the Launchpad grid."""

    page: int
    row: int
    col: int

    def linear_index(self, cols: int, rows: int) -> int:
        """Convert to a flat index across all pages."""
        return self.page * cols * rows + self.row * cols + self.col

    @classmethod
    def from_linear(cls, index: int, cols: int, rows: int) -> GridCell:
        """Construct from a flat index."""
        page, remainder = divmod(index, cols * rows)
        row, col = divmod(remainder, cols)
        return cls(page=page, row=row, col=col)


class GridLayout:
    """
    Manages the placement of app icons and folder icons in a paged grid.

    All methods are pure — they return new dicts instead of mutating state.
    """

    def __init__(self, cols: int = COLS_DEFAULT, rows: int = ROWS_DEFAULT) -> None:
        self.cols = cols
        self.rows = rows
        self.cells_per_page = cols * rows

    # ── Layout construction ───────────────────────────────────────────────────

    def auto_layout(self, desktop_ids: list[str]) -> dict[str, GridCell]:
        """Assign sequential GridCells to a list of desktop IDs (left-to-right, top-to-bottom)."""
        return {
            did: GridCell.from_linear(i, self.cols, self.rows)
            for i, did in enumerate(desktop_ids)
        }

    # ── Queries ───────────────────────────────────────────────────────────────

    def page_count(self, cells: dict[str, GridCell]) -> int:
        """Return the number of pages needed to show all cells (minimum 1)."""
        if not cells:
            return 1
        return max(c.page for c in cells.values()) + 1

    def apps_on_page(self, cells: dict[str, GridCell], page: int) -> dict[str, GridCell]:
        """Return only cells on a given page number."""
        return {k: v for k, v in cells.items() if v.page == page}

    def occupied(self, cells: dict[str, GridCell]) -> set[tuple[int, int, int]]:
        """Return the set of (page, row, col) tuples currently occupied."""
        return {(c.page, c.row, c.col) for c in cells.values()}

    def find_empty(
        self,
        occ: set[tuple[int, int, int]],
        start_page: int = 0,
    ) -> GridCell:
        """Find the first empty cell, starting from *start_page*."""
        page = start_page
        while True:
            for row in range(self.rows):
                for col in range(self.cols):
                    if (page, row, col) not in occ:
                        return GridCell(page=page, row=row, col=col)
            page += 1

    # ── Mutations (return new dicts) ─────────────────────────────────────────

    def move(
        self,
        cells: dict[str, GridCell],
        desktop_id: str,
        target: GridCell,
    ) -> dict[str, GridCell]:
        """
        Move *desktop_id* to *target*.

        If *target* is already occupied by a different app, that app is
        displaced to the next empty cell.
        """
        result = dict(cells)

        # Displace occupant if present
        occupant = next(
            (k for k, v in result.items() if v == target and k != desktop_id),
            None,
        )
        if occupant:
            occ = self.occupied({k: v for k, v in result.items() if k != desktop_id and k != occupant})
            new_cell = self.find_empty(occ)
            result[occupant] = new_cell

        result[desktop_id] = target
        return result

    def compact(self, cells: dict[str, GridCell]) -> dict[str, GridCell]:
        """
        Re-pack cells sequentially, preserving existing order by linear index.

        Useful after removing an app to close the resulting gap.
        """
        ordered = sorted(
            cells.items(),
            key=lambda kv: kv[1].linear_index(self.cols, self.rows),
        )
        return self.auto_layout([k for k, _ in ordered])

    def filter_to_pages(
        self,
        cells: dict[str, GridCell],
        desktop_ids: set[str],
    ) -> list[list[str]]:
        """
        Return apps visible in the given desktop_ids set, grouped by page.

        Result is a list of lists — one list per page, ordered by position.
        """
        visible = {k: v for k, v in cells.items() if k in desktop_ids}
        n_pages = self.page_count(visible) if visible else 1
        result: list[list[str]] = [[] for _ in range(n_pages)]
        for did, cell in sorted(visible.items(), key=lambda kv: kv[1]):
            result[cell.page].append(did)
        return result
