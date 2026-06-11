"""MacUX Finder — main application window."""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402
from pathlib import Path

from finder.bookmarks import BookmarkManager
from finder.file_model import DirectoryListing, FileItem, SortKey, ViewMode
from finder.file_ops import FileOpsError, trash_file, create_folder
from finder.icon_view import IconView
from finder.list_view import ListView
from finder.path_bar import PathBar
from finder.sidebar import FinderSidebar


class FinderWindow(Adw.ApplicationWindow):
    """macOS-inspired file manager window.

    Layout
    ------
    Adw.ToolbarView
      └─ Header: PathBar + view-mode toggle + search button
    Gtk.Paned (horizontal)
      ├─ FinderSidebar (left, 200 px)
      └─ Gtk.Stack (right)
           ├─ "icon"   → IconView
           └─ "list"   → ListView
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title("Finder")
        self.set_default_size(900, 600)
        self.add_css_class("finder-window")

        self._history: list[str] = []
        self._history_pos: int = -1
        self._current_path: Path = Path.home()
        self._current_view: ViewMode = ViewMode.ICON
        self._sort_key: SortKey = SortKey.NAME
        self._sort_reverse: bool = False
        self._show_hidden: bool = False
        self._bm = BookmarkManager()

        self._build_ui()
        self.navigate_to(str(Path.home()), add_to_history=False)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # Header
        header = Adw.HeaderBar()
        header.add_css_class("flat")
        header.set_title_widget(self._build_path_bar())
        header.pack_start(self._build_nav_buttons())
        header.pack_end(self._build_view_controls())
        toolbar_view.add_top_bar(header)

        # Main paned
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(200)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        toolbar_view.set_content(paned)

        # Sidebar
        self._sidebar = FinderSidebar(
            navigate_cb=self.navigate_to,
            bookmark_manager=self._bm,
        )
        paned.set_start_child(self._sidebar)

        # Content stack
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(120)
        paned.set_end_child(self._stack)

        self._icon_view = IconView(
            activate_cb=self._on_item_activated,
            selection_cb=self._on_item_selected,
        )
        self._stack.add_named(self._icon_view, "icon")

        self._list_view = ListView(
            activate_cb=self._on_item_activated,
            selection_cb=self._on_item_selected,
        )
        self._stack.add_named(self._list_view, "list")

    def _build_path_bar(self) -> Gtk.Widget:
        self._path_bar = PathBar(navigate_cb=self.navigate_to)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.set_hexpand(True)
        box.append(self._path_bar)
        return box

    def _build_nav_buttons(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        box.add_css_class("linked")

        self._btn_back = Gtk.Button(icon_name="go-previous-symbolic")
        self._btn_back.set_sensitive(False)
        self._btn_back.connect("clicked", lambda _: self.go_back())
        box.append(self._btn_back)

        self._btn_forward = Gtk.Button(icon_name="go-next-symbolic")
        self._btn_forward.set_sensitive(False)
        self._btn_forward.connect("clicked", lambda _: self.go_forward())
        box.append(self._btn_forward)

        return box

    def _build_view_controls(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        # View-mode toggle
        view_toggle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        view_toggle.add_css_class("linked")

        self._btn_icon_view = Gtk.ToggleButton(icon_name="view-grid-symbolic")
        self._btn_icon_view.set_active(True)
        self._btn_icon_view.connect("toggled", self._on_icon_view_toggled)
        view_toggle.append(self._btn_icon_view)

        self._btn_list_view = Gtk.ToggleButton(icon_name="view-list-symbolic")
        self._btn_list_view.set_group(self._btn_icon_view)
        self._btn_list_view.connect("toggled", self._on_list_view_toggled)
        view_toggle.append(self._btn_list_view)

        box.append(view_toggle)

        # Search
        self._search_btn = Gtk.ToggleButton(icon_name="system-search-symbolic")
        self._search_btn.connect("toggled", self._on_search_toggled)
        box.append(self._search_btn)

        return box

    # ── Navigation ─────────────────────────────────────────────────────────────

    def navigate_to(self, path: str, add_to_history: bool = True) -> None:
        p = Path(path)
        if not p.exists():
            return

        if p.is_file():
            self._open_file(p)
            return

        self._current_path = p
        if add_to_history:
            # Truncate forward history
            self._history = self._history[: self._history_pos + 1]
            self._history.append(str(p))
            self._history_pos = len(self._history) - 1

        self._refresh()

    def go_back(self) -> None:
        if self._history_pos > 0:
            self._history_pos -= 1
            self.navigate_to(self._history[self._history_pos], add_to_history=False)

    def go_forward(self) -> None:
        if self._history_pos < len(self._history) - 1:
            self._history_pos += 1
            self.navigate_to(self._history[self._history_pos], add_to_history=False)

    def _refresh(self) -> None:
        listing = DirectoryListing.load(
            self._current_path,
            show_hidden=self._show_hidden,
            sort_key=self._sort_key,
            sort_reverse=self._sort_reverse,
        )
        self._path_bar.set_path(self._current_path)
        self._icon_view.set_items(listing.items)
        self._list_view.set_items(listing.items)
        self._update_nav_sensitivity()

    def _update_nav_sensitivity(self) -> None:
        self._btn_back.set_sensitive(self._history_pos > 0)
        self._btn_forward.set_sensitive(
            self._history_pos < len(self._history) - 1
        )

    # ── File activation ────────────────────────────────────────────────────────

    def _on_item_activated(self, item: FileItem) -> None:
        if item.is_dir:
            self.navigate_to(str(item.path))
        else:
            self._open_file(item.path)

    def _on_item_selected(self, item: FileItem | None) -> None:
        pass  # status bar update (future)

    def _open_file(self, path: Path) -> None:
        try:
            import gi
            gi.require_version("Gio", "2.0")
            from gi.repository import Gio as _Gio
            f = _Gio.File.new_for_path(str(path))
            _Gio.AppInfo.launch_default_for_uri(f.get_uri(), None)
        except Exception:
            pass

    # ── View toggles ───────────────────────────────────────────────────────────

    def _on_icon_view_toggled(self, btn: Gtk.ToggleButton) -> None:
        if btn.get_active():
            self._current_view = ViewMode.ICON
            self._stack.set_visible_child_name("icon")

    def _on_list_view_toggled(self, btn: Gtk.ToggleButton) -> None:
        if btn.get_active():
            self._current_view = ViewMode.LIST
            self._stack.set_visible_child_name("list")

    def _on_search_toggled(self, btn: Gtk.ToggleButton) -> None:
        pass  # future: show search bar overlay

    # ── Context menu actions (keyboard / future right-click) ───────────────────

    def new_folder(self, name: str = "New Folder") -> None:
        try:
            create_folder(self._current_path, name)
            self._refresh()
        except FileOpsError:
            pass
