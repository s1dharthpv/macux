"""MacUX Spotlight — main search window.

Layout
------
  ┌─ SpotlightWindow (680 px wide, floating, no title bar) ─┐
  │  ┌──────────────────────────────────────────────────┐   │
  │  │  🔍  [search entry — 22 pt, rounded]             │   │
  │  └──────────────────────────────────────────────────┘   │
  │  ─ separator ─────────────────────────────────────────  │
  │  ┌──────────────────────────────────────────────────┐   │
  │  │  ResultRow                                        │   │
  │  │  ResultRow (selected)                             │   │
  │  │  …                                               │   │
  │  └──────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────┘

Keyboard:
  Esc         → hide window
  ↑ / ↓       → move selection
  Enter       → activate selected result
  Typing      → updates search (300 ms debounce)
"""

from __future__ import annotations

import logging
import subprocess
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, GLib, Gtk, Adw

from spotlight.result import SearchResult, ACTION_LAUNCH, ACTION_OPEN, ACTION_COPY, ACTION_URL
from spotlight.result_row import ResultRow

logger = logging.getLogger(__name__)

# Debounce delay for search (ms)
_DEBOUNCE_MS = 250

# Maximum rows shown in the result list
_MAX_VISIBLE_ROWS = 12

_CSS = b"""
.macux-spotlight-window {
    background-color: rgba(30, 30, 35, 0.90);
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.55),
                0 4px 16px rgba(0, 0, 0, 0.35);
}

.macux-spotlight-entry {
    font-size: 22px;
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 14px 16px;
    color: rgba(255, 255, 255, 0.95);
    caret-color: #5AB2FF;
}

.macux-spotlight-entry:focus {
    box-shadow: none;
    border: none;
    outline: none;
}

.macux-spotlight-separator {
    background-color: rgba(255, 255, 255, 0.10);
    min-height: 1px;
}

.macux-spotlight-results {
    background: transparent;
}

.macux-spotlight-result {
    background: transparent;
    border-radius: 8px;
    margin: 1px 6px;
}

.macux-spotlight-result:selected,
.macux-spotlight-result:hover {
    background-color: rgba(90, 170, 255, 0.25);
}

.macux-spotlight-result .title {
    font-size: 14px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.95);
}

.macux-spotlight-result .subtitle {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.50);
}

.macux-badge {
    font-size: 10px;
    color: rgba(255, 255, 255, 0.45);
    background-color: rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    padding: 1px 5px;
}
"""


class SpotlightWindow(Gtk.Window):
    """
    MacUX Spotlight search window.

    Args:
        on_search:   Callback invoked with the query string (debounced).
        on_activate: Callback invoked with the chosen SearchResult.
        on_hide:     Callback invoked when the window is dismissed.
    """

    __gtype_name__ = "MacuxSpotlightWindow"

    def __init__(
        self,
        on_search: Callable[[str], list[SearchResult]],
        on_activate: Callable[[SearchResult], None],
        on_hide: Callable[[], None],
    ) -> None:
        super().__init__()
        self._on_search = on_search
        self._on_activate = on_activate
        self._on_hide = on_hide
        self._debounce_id: int = 0
        self._results: list[SearchResult] = []

        self._load_css()
        self._build()
        self._connect_signals()

    # ── Public API ────────────────────────────────────────────────────────────

    def show_spotlight(self, query: str = "") -> None:
        """Present the window and optionally pre-fill a query."""
        self.present()
        if query:
            self._entry.set_text(query)
            self._entry.set_position(-1)
        else:
            self._entry.set_text("")
        self._results_box.set_visible(False)
        self._entry.grab_focus()

    def set_results(self, results: list[SearchResult]) -> None:
        """Replace the result list (called from search callback)."""
        self._results = results
        self._populate_results(results)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.set_title("Spotlight")
        self.set_default_size(680, -1)
        self.set_resizable(False)
        self.set_decorated(False)
        self.add_css_class("macux-spotlight-window")

        # Remove default window background
        self.set_opacity(1.0)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Search entry row
        entry_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry_row.set_margin_start(8)
        entry_row.set_margin_end(8)
        entry_row.set_margin_top(4)
        entry_row.set_margin_bottom(4)

        # Magnifying glass icon
        icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
        icon.set_pixel_size(20)
        icon.set_opacity(0.6)
        entry_row.append(icon)

        # Text entry
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("Spotlight Search")
        self._entry.set_hexpand(True)
        self._entry.add_css_class("macux-spotlight-entry")
        entry_row.append(self._entry)

        outer.append(entry_row)

        # Separator (hidden until there are results)
        self._separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self._separator.add_css_class("macux-spotlight-separator")
        self._separator.set_visible(False)
        outer.append(self._separator)

        # Scrollable result list (hidden until there are results)
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroll.set_max_content_height(_MAX_VISIBLE_ROWS * 52)
        self._scroll.set_propagate_natural_height(True)
        self._scroll.set_visible(False)

        self._list = Gtk.ListBox()
        self._list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list.add_css_class("macux-spotlight-results")
        self._scroll.set_child(self._list)
        outer.append(self._scroll)

        self._results_box = self._scroll
        self.set_child(outer)

    def _load_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── Signals ───────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._entry.connect("changed", self._on_entry_changed)

        # Key events on the entry
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self._entry.add_controller(key_ctrl)

        # Activate (double-click or Enter on list item)
        self._list.connect("row-activated", self._on_row_activated)

        # Hide when window loses focus
        self.connect("notify::is-active", self._on_active_changed)

    def _on_entry_changed(self, entry: Gtk.Entry) -> None:
        if self._debounce_id:
            GLib.source_remove(self._debounce_id)
        self._debounce_id = GLib.timeout_add(_DEBOUNCE_MS, self._do_search)

    def _do_search(self) -> bool:
        self._debounce_id = 0
        query = self._entry.get_text()
        if not query.strip():
            self._clear_results()
            return False
        results = self._on_search(query)
        self.set_results(results)
        return False  # one-shot

    def _on_key_pressed(
        self,
        controller: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            self._hide()
            return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Tab):
            self._move_selection(+1)
            return True
        if keyval in (Gdk.KEY_Up,):
            self._move_selection(-1)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            row = self._list.get_selected_row()
            if row:
                self._activate_row(row)
            elif self._results:
                self._activate_result(self._results[0])
            return True
        return False

    def _on_row_activated(self, listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        self._activate_row(row)

    def _on_active_changed(self, window: Gtk.Window, _param) -> None:
        if not window.is_active():
            self._hide()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _populate_results(self, results: list[SearchResult]) -> None:
        # Remove old rows
        while True:
            row = self._list.get_row_at_index(0)
            if row is None:
                break
            self._list.remove(row)

        if not results:
            self._clear_results()
            return

        for result in results[:_MAX_VISIBLE_ROWS]:
            row = ResultRow(result)
            self._list.append(row)

        # Auto-select first row
        first = self._list.get_row_at_index(0)
        if first:
            self._list.select_row(first)

        self._separator.set_visible(True)
        self._results_box.set_visible(True)

    def _clear_results(self) -> None:
        while True:
            row = self._list.get_row_at_index(0)
            if row is None:
                break
            self._list.remove(row)
        self._separator.set_visible(False)
        self._results_box.set_visible(False)

    def _move_selection(self, delta: int) -> None:
        current = self._list.get_selected_row()
        if current is None:
            if delta > 0:
                row = self._list.get_row_at_index(0)
                if row:
                    self._list.select_row(row)
            return
        idx = current.get_index() + delta
        idx = max(0, min(idx, len(self._results) - 1))
        row = self._list.get_row_at_index(idx)
        if row:
            self._list.select_row(row)
            row.grab_focus()

    def _activate_row(self, row: Gtk.ListBoxRow) -> None:
        if isinstance(row, ResultRow):
            self._activate_result(row.result)

    def _activate_result(self, result: SearchResult) -> None:
        self._hide()
        try:
            self._on_activate(result)
        except Exception:
            logger.exception("Error activating result: %s", result.name)

    def _hide(self) -> None:
        self.set_visible(False)
        self._on_hide()
