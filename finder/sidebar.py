"""MacUX Finder — sidebar widget.

Three sections:
  Favorites  — standard XDG user dirs + bookmarks from BookmarkManager
  Devices    — mounted GIO volumes
  Tags       — placeholder (extensible)
"""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio, Gtk  # noqa: E402
from pathlib import Path
from typing import Callable

from finder.bookmarks import BookmarkManager

_XDG_DIRS: list[tuple[str, str, str]] = [
    ("user-home", "Home", str(Path.home())),
    ("folder-documents-symbolic", "Documents",
     str(Path.home() / "Documents")),
    ("folder-download-symbolic", "Downloads",
     str(Path.home() / "Downloads")),
    ("folder-pictures-symbolic", "Pictures",
     str(Path.home() / "Pictures")),
    ("folder-music-symbolic", "Music",
     str(Path.home() / "Music")),
    ("folder-videos-symbolic", "Videos",
     str(Path.home() / "Videos")),
    ("user-desktop-symbolic", "Desktop",
     str(Path.home() / "Desktop")),
]


class SidebarRow(Gtk.ListBoxRow):
    """A single row in the sidebar list."""

    def __init__(self, icon: str, label: str, path: str) -> None:
        super().__init__()
        self.path = path

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        img = Gtk.Image.new_from_icon_name(icon)
        img.set_pixel_size(16)
        box.append(img)

        lbl = Gtk.Label(label=label, xalign=0.0)
        lbl.set_hexpand(True)
        lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        box.append(lbl)

        self.set_child(box)


class FinderSidebar(Gtk.Box):
    """Left-hand sidebar with Favorites, Devices, and Tags sections."""

    def __init__(
        self,
        navigate_cb: Callable[[str], None] | None = None,
        bookmark_manager: BookmarkManager | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("finder-sidebar")
        self.set_size_request(200, -1)

        self._navigate_cb = navigate_cb
        self._bm = bookmark_manager or BookmarkManager()

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.append(scroll)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll.set_child(vbox)

        self._list = Gtk.ListBox()
        self._list.add_css_class("navigation-sidebar")
        self._list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list.connect("row-activated", self._on_row_activated)
        vbox.append(self._list)

        self._populate()

    def _populate(self) -> None:
        self._add_section_header("Favorites")
        for icon, label, path in _XDG_DIRS:
            if Path(path).exists():
                self._list.append(SidebarRow(icon, label, path))

        for bm in self._bm.all():
            if bm.path and bm.path.exists():
                self._list.append(
                    SidebarRow("folder-symbolic", bm.display_name, str(bm.path))
                )

        self._add_section_header("Devices")
        self._add_devices()

    def _add_section_header(self, title: str) -> None:
        hdr = Gtk.Label(label=title, xalign=0.0)
        hdr.add_css_class("sidebar-section-header")
        hdr.add_css_class("caption")
        hdr.set_margin_start(12)
        hdr.set_margin_top(12)
        hdr.set_margin_bottom(4)
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        row.set_selectable(False)
        row.set_child(hdr)
        self._list.append(row)

    def _add_devices(self) -> None:
        try:
            vm = Gio.VolumeMonitor.get()
            for mount in vm.get_mounts():
                root = mount.get_root()
                if root:
                    path = root.get_path() or ""
                    self._list.append(
                        SidebarRow(
                            "drive-harddisk-symbolic",
                            mount.get_name(),
                            path,
                        )
                    )
        except Exception:
            pass

    def _on_row_activated(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        if isinstance(row, SidebarRow) and self._navigate_cb:
            self._navigate_cb(row.path)

    def refresh(self) -> None:
        """Rebuild the sidebar (call after bookmark changes)."""
        child = self._list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._list.remove(child)
            child = nxt
        self._populate()
