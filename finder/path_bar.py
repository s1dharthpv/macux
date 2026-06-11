"""MacUX Finder — breadcrumb path bar widget."""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, GLib, Gtk  # noqa: E402
from pathlib import Path
from typing import Callable


class PathBar(Gtk.Box):
    """Horizontal breadcrumb bar showing path components as clickable buttons.

    Emits ``navigate(path: str)`` via the provided callback when a segment
    is clicked.
    """

    def __init__(
        self,
        navigate_cb: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add_css_class("path-bar")
        self._navigate_cb = navigate_cb
        self._path: Path | None = None

    def set_path(self, path: Path | str) -> None:
        """Replace the breadcrumb trail with *path*."""
        self._path = Path(path)
        self._rebuild()

    def _rebuild(self) -> None:
        # Remove all children
        child = self.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.remove(child)
            child = nxt

        if self._path is None:
            return

        parts = self._path.parts  # e.g. ('/', 'home', 'user', 'Documents')
        cumulative = Path("/")

        for i, part in enumerate(parts):
            if i == 0:
                label = "/"
            else:
                label = part
                cumulative = cumulative / part

            target = Path("/") if i == 0 else cumulative
            btn = Gtk.Button(label=label)
            btn.add_css_class("flat")
            btn.add_css_class("path-segment")
            if i == len(parts) - 1:
                btn.add_css_class("path-segment-current")

            captured_path = str(target)
            btn.connect("clicked", lambda _b, p=captured_path: self._on_segment_clicked(p))
            self.append(btn)

            if i < len(parts) - 1:
                sep = Gtk.Label(label="/")
                sep.add_css_class("path-separator")
                self.append(sep)

    def _on_segment_clicked(self, path: str) -> None:
        if self._navigate_cb:
            self._navigate_cb(path)
