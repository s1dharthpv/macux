"""MacUX Mission Control — pure Python layout engine.

All code is GTK-free and testable without a display.

Key types
---------
Rect          Immutable bounding box (x, y, w, h).
WindowInfo    Snapshot of one window (xid, title, app, rect, workspace).
WorkspaceInfo Snapshot of one workspace (index, name, windows).

Key functions
-------------
rows_cols_for_count(n)              → (rows, cols) for a near-square grid.
scale_to_fit(src_w, src_h, dw, dh) → float scale ≤ 1.0 (aspect-ratio safe).
tile_windows(windows, screen, …)    → {xid: Rect} tile bounding boxes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rect:
    """Axis-aligned bounding box."""

    x: int
    y: int
    w: int
    h: int

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def center_x(self) -> int:
        return self.x + self.w // 2

    @property
    def center_y(self) -> int:
        return self.y + self.h // 2

    def contains(self, other: Rect) -> bool:
        """Return True if *other* is fully inside *self*."""
        return (
            other.x >= self.x
            and other.y >= self.y
            and other.right <= self.right
            and other.bottom <= self.bottom
        )

    def overlaps(self, other: Rect) -> bool:
        """Return True if *self* and *other* overlap (share at least 1 pixel)."""
        return (
            self.x < other.right
            and self.right > other.x
            and self.y < other.bottom
            and self.bottom > other.y
        )


@dataclass
class WindowInfo:
    """Snapshot of a single desktop window."""

    xid: int
    title: str
    app_name: str
    rect: Rect           # original position and size on screen
    workspace_index: int
    minimized: bool = False


@dataclass
class WorkspaceInfo:
    """Snapshot of a single workspace."""

    index: int
    name: str
    windows: list[WindowInfo] = field(default_factory=list)

    @property
    def visible_windows(self) -> list[WindowInfo]:
        """All non-minimized windows on this workspace."""
        return [w for w in self.windows if not w.minimized]

    @property
    def window_count(self) -> int:
        return len(self.windows)


# ── Layout helpers ────────────────────────────────────────────────────────────

def rows_cols_for_count(n: int) -> tuple[int, int]:
    """
    Return (rows, cols) for a near-square grid that fits *n* items.

    Guarantees: rows * cols >= n, cols >= rows (wider than tall),
    and the number of empty cells is minimised.

    Examples::

        rows_cols_for_count(0)  → (0, 0)
        rows_cols_for_count(1)  → (1, 1)
        rows_cols_for_count(4)  → (2, 2)
        rows_cols_for_count(5)  → (2, 3)
        rows_cols_for_count(9)  → (3, 3)
    """
    if n == 0:
        return (0, 0)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return (rows, cols)


def scale_to_fit(src_w: int, src_h: int, dest_w: int, dest_h: int) -> float:
    """
    Return the scale factor (≤ 1.0) that fits (src_w × src_h) inside
    (dest_w × dest_h) while preserving aspect ratio.

    Returns 1.0 when the source already fits, or when dimensions are zero.
    """
    if src_w <= 0 or src_h <= 0 or dest_w <= 0 or dest_h <= 0:
        return 1.0
    return min(dest_w / src_w, dest_h / src_h, 1.0)


def tile_windows(
    windows: list[WindowInfo],
    screen: Rect,
    padding: int = 20,
    bottom_reserve: int = 100,
) -> dict[int, Rect]:
    """
    Calculate Mission Control tile bounding boxes for *windows*.

    Non-minimized windows are arranged in a near-square grid that fills the
    screen minus *padding* on all sides and *bottom_reserve* px at the
    bottom (for the workspace switcher).

    Returns a dict mapping ``xid → Rect`` where each Rect is the tile's
    bounding box.  The caller is responsible for scaling the window actor
    to fit within that box (see :func:`scale_to_fit`).

    Minimized windows are excluded from the output.
    """
    visible = [w for w in windows if not w.minimized]
    if not visible:
        return {}

    n = len(visible)
    rows, cols = rows_cols_for_count(n)

    usable_x = screen.x + padding
    usable_y = screen.y + padding
    usable_w = screen.w - 2 * padding
    usable_h = screen.h - bottom_reserve - 2 * padding

    cell_w = max(1, usable_w // cols)
    cell_h = max(1, usable_h // rows)
    inset = max(0, padding // 2)

    result: dict[int, Rect] = {}
    for i, win in enumerate(visible):
        row = i // cols
        col = i % cols
        result[win.xid] = Rect(
            x=usable_x + col * cell_w + inset,
            y=usable_y + row * cell_h + inset,
            w=max(1, cell_w - 2 * inset),
            h=max(1, cell_h - 2 * inset),
        )

    return result
