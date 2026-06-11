"""MacUX Dock — Trash icon widget.

Shows the system Trash with a full/empty state, drag-target overlay,
and a launch action (opens ~/.local/share/Trash in Finder or Nautilus).
"""

from __future__ import annotations

import logging
import subprocess

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gdk, Gio, GLib, Gtk

logger = logging.getLogger(__name__)

_TRASH_URI = "trash://"
_TRASH_FULL_ICON = "user-trash-full"
_TRASH_EMPTY_ICON = "user-trash"


class TrashWidget(Gtk.Overlay):
    """
    Dock Trash icon.

    Automatically reflects whether the trash is empty or full by monitoring
    the trash:// GIO mount point for changes.
    """

    __gtype_name__ = "MacuxTrashWidget"

    def __init__(self, icon_size: int = 48) -> None:
        super().__init__()
        self._icon_size = icon_size
        self._is_full = False
        self._monitor: Gio.FileMonitor | None = None

        self.add_css_class("macux-app-icon-wrapper")
        self._build()
        self._connect_drop_target()
        self._connect_gestures()
        self._start_monitor()
        self._update_state()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self._image = Gtk.Image.new_from_icon_name(_TRASH_EMPTY_ICON)
        self._image.set_pixel_size(self._icon_size)
        self._image.set_halign(Gtk.Align.CENTER)
        self._image.set_valign(Gtk.Align.CENTER)
        self.set_child(self._image)

        # Hover label
        self._label = Gtk.Label(label="Trash")
        self._label.add_css_class("macux-dock-label")
        self._label.set_halign(Gtk.Align.CENTER)
        self._label.set_valign(Gtk.Align.START)
        self._label.set_visible(False)
        self.add_overlay(self._label)

        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self._label.set_visible(True))
        motion.connect("leave", lambda *_: self._label.set_visible(False))
        self.add_controller(motion)

    def _connect_drop_target(self) -> None:
        """Accept file drops to move files to trash."""
        drop = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.MOVE)
        drop.connect("drop", self._on_drop)
        drop.connect("enter", self._on_drop_enter)
        drop.connect("leave", self._on_drop_leave)
        self.add_controller(drop)

    def _connect_gestures(self) -> None:
        click = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
        click.connect("released", self._on_click)
        self.add_controller(click)

    # ── Icon state ─────────────────────────────────────────────────────────────

    def set_icon_size(self, size: int) -> None:
        self._icon_size = size
        self._image.set_pixel_size(size)

    def _update_state(self) -> None:
        """Check if trash is empty or full and update icon accordingly."""
        try:
            trash = Gio.File.new_for_uri(_TRASH_URI)
            info = trash.query_info(
                Gio.FILE_ATTRIBUTE_TRASH_ITEM_COUNT,
                Gio.FileQueryInfoFlags.NONE,
                None,
            )
            count = info.get_attribute_uint32(Gio.FILE_ATTRIBUTE_TRASH_ITEM_COUNT)
            new_full = count > 0
        except Exception:
            new_full = False

        if new_full != self._is_full:
            self._is_full = new_full
            icon = _TRASH_FULL_ICON if self._is_full else _TRASH_EMPTY_ICON
            self._image.set_from_icon_name(icon)

    def _start_monitor(self) -> None:
        """Monitor trash:// for changes to update the icon."""
        try:
            trash = Gio.File.new_for_uri(_TRASH_URI)
            self._monitor = trash.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self._monitor.connect("changed", self._on_trash_changed)
        except Exception as exc:
            logger.debug("Could not monitor trash://: %s", exc)

    def _on_trash_changed(self, _monitor, _file, _other, _event) -> None:
        self._update_state()

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _on_click(self, gesture, n_press, x, y) -> None:
        if n_press == 2:  # double-click opens trash
            self._open_trash()

    def _on_drop(self, drop_target, value, x, y) -> bool:
        """Move a dropped GIO file to the trash."""
        try:
            file: Gio.File = value
            file.trash(None)
            GLib.timeout_add(100, lambda: (self._update_state(), False)[1])
            return True
        except Exception as exc:
            logger.warning("Trash drop failed: %s", exc)
            return False

    def _on_drop_enter(self, drop_target, x, y) -> Gdk.DragAction:
        self.add_css_class("drag-hover")
        return Gdk.DragAction.MOVE

    def _on_drop_leave(self, drop_target) -> None:
        self.remove_css_class("drag-hover")

    def _open_trash(self) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri(_TRASH_URI, None)
        except Exception:
            subprocess.Popen(["xdg-open", _TRASH_URI])
