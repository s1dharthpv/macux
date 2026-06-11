"""MacUX Launchpad — fullscreen window.

Structure
---------
  LaunchpadWindow (Gtk.Window, fullscreen, no decorations)
    └── Gtk.Overlay
          ├── bg_box  (dark translucent background)
          └── content_box (Gtk.Box VERTICAL)
                ├── search_entry (Gtk.SearchEntry, top centre)
                ├── carousel     (Adw.Carousel, flex)
                └── dots         (Adw.CarouselIndicatorDots)

Keyboard:
  Escape        → hide
  ← / →         → previous / next carousel page
  Any letter    → focus search entry and append character
  Backspace     → remove from search
  Enter         → launch selected / first visible app
"""

from __future__ import annotations

import logging
import subprocess
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from launchpad.app_filter import filter_apps
from launchpad.app_icon import AppIcon
from launchpad.folder_icon import FolderIcon
from launchpad.grid import GridCell, GridLayout
from launchpad.page_widget import LaunchpadPage
from launchpad.persistence import FolderData

logger = logging.getLogger(__name__)

_COLS = 7
_ROWS = 5

_CSS = b"""
.macux-launchpad-bg {
    background-color: rgba(0, 0, 0, 0.72);
}

.macux-launchpad-search {
    font-size: 18px;
    min-width: 400px;
    border-radius: 12px;
    background-color: rgba(255, 255, 255, 0.15);
    color: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.20);
    padding: 8px 16px;
    caret-color: white;
}

.macux-launchpad-search:focus {
    background-color: rgba(255, 255, 255, 0.20);
    box-shadow: 0 0 0 2px rgba(90, 170, 255, 0.40);
}

.macux-launchpad-icon {
    border-radius: 18px;
    padding: 8px 10px 6px 10px;
    transition: background-color 100ms;
}

.macux-launchpad-icon.hover {
    background-color: rgba(255, 255, 255, 0.10);
}

.macux-launchpad-icon.dim {
    opacity: 0.30;
}

.macux-launchpad-label {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.92);
    font-weight: 500;
}

.macux-launchpad-folder .macux-folder-frame {
    border-radius: 16px;
    background-color: rgba(255, 255, 255, 0.20);
    border: none;
    box-shadow: none;
}

.macux-launchpad-folder.hover .macux-folder-frame {
    background-color: rgba(255, 255, 255, 0.28);
}
"""


class LaunchpadWindow(Gtk.Window):
    """
    MacUX Launchpad fullscreen window.

    Args:
        registry:         desktop_id → AppInfo mapping.
        cells:            desktop_id → GridCell mapping (persisted positions).
        folders:          List of FolderData.
        on_activate:      Called with the desktop file path to launch.
        on_hide:          Called when the window is dismissed.
        on_page_changed:  Called with the new page index when the user swipes.
        cols, rows:       Grid dimensions (default 7×5).
    """

    __gtype_name__ = "MacuxLaunchpadWindow"

    def __init__(
        self,
        registry: dict,
        cells: dict[str, GridCell],
        folders: list[FolderData],
        on_activate: Callable[[str], None],
        on_hide: Callable[[], None],
        on_page_changed: Callable[[int], None] | None = None,
        cols: int = _COLS,
        rows: int = _ROWS,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._cells = cells
        self._folders = folders
        self._on_activate = on_activate
        self._on_hide = on_hide
        self._on_page_changed = on_page_changed
        self._cols = cols
        self._rows = rows
        self._layout = GridLayout(cols=cols, rows=rows)
        self._pages: list[LaunchpadPage] = []
        self._search_query = ""

        self._load_css()
        self._build()
        self._populate()
        self._connect_signals()

    # ── Public API ────────────────────────────────────────────────────────────

    def show_launchpad(self, page: int = 0) -> None:
        self.present()
        self.fullscreen()
        self._search_entry.set_text("")
        self._reset_filter()
        if 0 <= page < self._carousel.get_n_pages():
            target = self._carousel.get_nth_page(page)
            if target:
                self._carousel.scroll_to(target, False)
        GLib.idle_add(lambda: self._search_entry.grab_focus() or False)

    def update_registry(self, registry: dict, cells: dict[str, GridCell]) -> None:
        """Rebuild the grid when the app registry or positions change."""
        self._registry = registry
        self._cells = cells
        self._repopulate()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.set_title("Launchpad")
        self.set_decorated(False)
        self.set_resizable(True)

        overlay = Gtk.Overlay()

        # Dark background
        bg = Gtk.Box()
        bg.set_hexpand(True)
        bg.set_vexpand(True)
        bg.add_css_class("macux-launchpad-bg")
        overlay.set_child(bg)

        # Content on top of background
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_hexpand(True)
        content.set_vexpand(True)
        content.set_margin_top(40)
        content.set_margin_bottom(20)

        # Search entry
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search")
        self._search_entry.set_halign(Gtk.Align.CENTER)
        self._search_entry.add_css_class("macux-launchpad-search")
        content.append(self._search_entry)

        # Carousel
        self._carousel = Adw.Carousel()
        self._carousel.set_hexpand(True)
        self._carousel.set_vexpand(True)
        self._carousel.set_allow_scroll_wheel(True)
        content.append(self._carousel)

        # Page dots
        dots = Adw.CarouselIndicatorDots()
        dots.set_carousel(self._carousel)
        dots.set_halign(Gtk.Align.CENTER)
        content.append(dots)

        overlay.add_overlay(content)
        self.set_child(overlay)

    def _load_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── Populate ──────────────────────────────────────────────────────────────

    def _populate(self) -> None:
        # Remove existing pages from carousel
        for page_widget in self._pages:
            self._carousel.remove(page_widget)
        self._pages.clear()

        # Build set of folder-member desktop IDs (excluded from main grid)
        folder_members: set[str] = set()
        for f in self._folders:
            folder_members.update(f.members)

        # Determine page count
        grid_cells = {k: v for k, v in self._cells.items() if k not in folder_members}
        n_pages = max(self._layout.page_count(grid_cells), 1)

        # Create page widgets
        for _ in range(n_pages):
            page = LaunchpadPage(cols=self._cols, rows=self._rows)
            self._pages.append(page)
            self._carousel.append(page)

        # Place app icons
        for desktop_id, cell in grid_cells.items():
            if desktop_id not in self._registry:
                continue
            info = self._registry[desktop_id]
            icon = AppIcon(info)
            icon.connect("activated", self._on_icon_activated)
            if 0 <= cell.page < len(self._pages):
                self._pages[cell.page].place(icon, cell.col, cell.row)

        # Place folder icons
        for folder in self._folders:
            members = [self._registry[m] for m in folder.members if m in self._registry]
            folder_icon = FolderIcon(folder, members[:4])
            folder_icon.connect("activated", self._on_folder_activated)
            if 0 <= folder.page < len(self._pages):
                self._pages[folder.page].place(folder_icon, folder.col, folder.row)

        # If no pages were created, ensure at least one exists
        if not self._pages:
            page = LaunchpadPage(cols=self._cols, rows=self._rows)
            self._pages.append(page)
            self._carousel.append(page)

    def _repopulate(self) -> None:
        self._populate()

    # ── Signals ───────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._search_entry.connect("search-changed", self._on_search_changed)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        self._carousel.connect("page-changed", self._on_carousel_page_changed)

        # Hide when focus leaves window (click outside)
        self.connect("notify::is-active", self._on_active_changed)

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._search_query = entry.get_text().strip()
        self._apply_filter()

    def _apply_filter(self) -> None:
        if not self._search_query:
            self._reset_filter()
            return
        visible = filter_apps(self._registry, self._search_query)
        for page in self._pages:
            child = page._grid.get_first_child()
            while child:
                if isinstance(child, AppIcon):
                    desktop_id = child.app_info.path
                    # Match by path or by desktop_id key
                    is_visible = any(
                        self._registry.get(did) and self._registry[did].path == desktop_id
                        for did in visible
                    ) or any(
                        did for did in visible
                        if self._registry.get(did) and self._registry[did].name == child.app_info.name
                    )
                    child.set_dimmed(not is_visible)
                child = child.get_next_sibling()

    def _reset_filter(self) -> None:
        for page in self._pages:
            page.set_all_dimmed(False)

    def _on_key_pressed(
        self,
        controller: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            if self._search_query:
                self._search_entry.set_text("")
            else:
                self._hide()
            return True
        if keyval == Gdk.KEY_Left:
            self._navigate_page(-1)
            return True
        if keyval == Gdk.KEY_Right:
            self._navigate_page(+1)
            return True
        return False

    def _on_carousel_page_changed(self, carousel: Adw.Carousel, index: int) -> None:
        if self._on_page_changed:
            self._on_page_changed(index)

    def _on_icon_activated(self, icon: AppIcon, path: str) -> None:
        self._hide()
        try:
            self._on_activate(path)
        except Exception:
            logger.exception("Error launching %s", path)

    def _on_folder_activated(self, folder_icon: FolderIcon, folder_id: int) -> None:
        logger.debug("Folder %d opened", folder_id)

    def _on_active_changed(self, window: Gtk.Window, _param) -> None:
        if not window.is_active() and not self._search_entry.has_focus():
            self._hide()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _navigate_page(self, delta: int) -> None:
        current = round(self._carousel.get_position())
        target_idx = max(0, min(current + delta, self._carousel.get_n_pages() - 1))
        target_page = self._carousel.get_nth_page(target_idx)
        if target_page:
            self._carousel.scroll_to(target_page, True)

    def _hide(self) -> None:
        self.set_visible(False)
        self._on_hide()
