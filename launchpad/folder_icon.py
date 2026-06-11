"""MacUX Launchpad — folder icon widget.

A folder appears as a rounded square containing a 2×2 mosaic of the first
four member app icons, with a name label below — identical to macOS Launchpad
folders.

Clicking the folder opens a popover-style overlay grid listing all member apps.
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GObject, Gtk

_FOLDER_SIZE = 80   # overall folder thumbnail size
_MOSAIC_ICON = 28   # each of the 4 member icons inside the mosaic


class FolderIcon(Gtk.Box):
    """
    A Launchpad folder icon: mosaic thumbnail + name label.

    Signals:
        activated(folder_id: int) — user clicked the folder.
    """

    __gtype_name__ = "MacuxLaunchpadFolderIcon"

    activated = GObject.Signal("activated", arg_types=(int,))

    def __init__(self, folder_data, member_infos: list) -> None:
        """
        Args:
            folder_data:  FolderData instance (name, folder_id, …).
            member_infos: list of AppInfo for the first 4 members (for mosaic).
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.folder_data = folder_data
        self._members = member_infos[:4]
        self._build()
        self._setup_gestures()
        self.add_css_class("macux-launchpad-folder")

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.START)

        # Mosaic container
        frame = Gtk.Frame()
        frame.set_size_request(_FOLDER_SIZE, _FOLDER_SIZE)
        frame.add_css_class("macux-folder-frame")

        grid = Gtk.Grid()
        grid.set_row_spacing(2)
        grid.set_column_spacing(2)
        grid.set_halign(Gtk.Align.CENTER)
        grid.set_valign(Gtk.Align.CENTER)
        grid.set_margin_start(8)
        grid.set_margin_end(8)
        grid.set_margin_top(8)
        grid.set_margin_bottom(8)

        for i, info in enumerate(self._members):
            img = Gtk.Image()
            img.set_pixel_size(_MOSAIC_ICON)
            icon_name = getattr(info, "icon", None) or "application-x-executable"
            img.set_from_icon_name(icon_name)
            row, col = divmod(i, 2)
            grid.attach(img, col, row, 1, 1)

        # Fill missing slots with blank widgets
        for i in range(len(self._members), 4):
            placeholder = Gtk.Box()
            placeholder.set_size_request(_MOSAIC_ICON, _MOSAIC_ICON)
            row, col = divmod(i, 2)
            grid.attach(placeholder, col, row, 1, 1)

        frame.set_child(grid)
        self.append(frame)

        # Label
        label = Gtk.Label(label=self.folder_data.name)
        label.set_halign(Gtk.Align.CENTER)
        label.set_max_width_chars(12)
        label.set_ellipsize(3)
        label.add_css_class("macux-launchpad-label")
        self.append(label)

    def _setup_gestures(self) -> None:
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("released", self._on_click)
        self.add_controller(click)

        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self.add_css_class("hover"))
        motion.connect("leave", lambda *_: self.remove_css_class("hover"))
        self.add_controller(motion)

    def _on_click(self, gesture, n_press, x, y) -> None:
        self.activated.emit(self.folder_data.folder_id)
