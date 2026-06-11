"""MacUX Dock — single app icon widget.

DockIcon is a Gtk.Overlay containing:
  - Icon image (Gtk.Image, size controlled by MagnificationController)
  - Running indicator dot(s) underneath
  - Badge overlay (unread count) in top-right corner
  - Hover label tooltip above the icon
  - Bounce animation via CSS class toggling

GTK4 DnD is wired here:
  - Gtk.DragSource for dragging this icon OUT of the dock
  - The drop target for reordering is on DockBox (window.py)
"""

from __future__ import annotations

import logging
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk

logger = logging.getLogger(__name__)

ClickCallback = Callable[["DockIcon"], None]
DragCallback = Callable[["DockIcon"], None]


class DockIcon(Gtk.Overlay):
    """
    A single dock icon with running indicator, badge, and hover label.

    Signals:
      app-activated: emitted when the user left-clicks the icon
      app-pinned:    emitted when the user drags this icon to pin (unused in icon itself)
    """

    __gtype_name__ = "MacuxDockIcon"

    def __init__(
        self,
        desktop_id: str,
        app_name: str,
        icon_name: str,
        base_size: int = 48,
        on_click: ClickCallback | None = None,
        on_right_click: ClickCallback | None = None,
    ) -> None:
        super().__init__()

        self.desktop_id = desktop_id
        self.app_name = app_name
        self.icon_name = icon_name
        self._base_size = base_size
        self._on_click = on_click
        self._on_right_click = on_right_click

        self._running = False
        self._window_count = 0
        self._badge_count = 0
        self._is_bouncing = False

        self._build()
        self._connect_gestures()
        self._connect_drag()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.set_name("macux-dock-icon")
        self.add_css_class("macux-app-icon-wrapper")

        # Icon wrapper box (holds image + indicator)
        self._vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._vbox.set_valign(Gtk.Align.END)

        # App icon image
        self._image = Gtk.Image()
        self._image.set_pixel_size(self._base_size)
        self._image.set_valign(Gtk.Align.CENTER)
        self._image.set_halign(Gtk.Align.CENTER)
        self._set_icon(self.icon_name)
        self._vbox.append(self._image)

        # Running indicator row
        self._indicator_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=2,
        )
        self._indicator_box.set_halign(Gtk.Align.CENTER)
        self._indicator_box.add_css_class("macux-dock-indicator-row")
        self._vbox.append(self._indicator_box)
        self._update_indicator()

        self.set_child(self._vbox)

        # Badge overlay (positioned top-right)
        self._badge_label = Gtk.Label(label="")
        self._badge_label.add_css_class("macux-dock-badge")
        self._badge_label.set_halign(Gtk.Align.END)
        self._badge_label.set_valign(Gtk.Align.START)
        self._badge_label.set_visible(False)
        self.add_overlay(self._badge_label)

        # Hover label (show above icon, hidden by default)
        self._label = Gtk.Label(label=self.app_name)
        self._label.add_css_class("macux-dock-label")
        self._label.set_halign(Gtk.Align.CENTER)
        self._label.set_valign(Gtk.Align.START)
        self._label.set_visible(False)
        self.add_overlay(self._label)

        # Motion controller for hover label
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._on_hover_enter)
        motion.connect("leave", self._on_hover_leave)
        self.add_controller(motion)

    def _set_icon(self, icon_name: str) -> None:
        """Load icon by name or file path, fall back to generic."""
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        if icon_name.startswith("/"):
            self._image.set_from_file(icon_name)
        elif theme.has_icon(icon_name):
            self._image.set_from_icon_name(icon_name)
        else:
            self._image.set_from_icon_name("application-x-executable")

    # ── State setters ──────────────────────────────────────────────────────────

    def set_running(self, running: bool, window_count: int = 0) -> None:
        self._running = running
        self._window_count = window_count
        self._update_indicator()

    def set_badge(self, count: int) -> None:
        self._badge_count = count
        if count > 0:
            self._badge_label.set_label(str(min(count, 99)))
            self._badge_label.set_visible(True)
        else:
            self._badge_label.set_visible(False)

    def set_icon_size(self, size: int) -> None:
        """Called by MagnificationController on each animation frame."""
        self._image.set_pixel_size(size)

    def bounce(self, style: str = "launch") -> None:
        """Trigger bounce animation. style: 'launch' | 'alert' | 'once'"""
        if self._is_bouncing:
            return
        self._is_bouncing = True
        css_class = f"macux-bounce-{style}"
        self._image.add_css_class(css_class)
        GLib.timeout_add(
            800,
            lambda: (self._image.remove_css_class(css_class), self.__dict__.update({"_is_bouncing": False})) and False,
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _update_indicator(self) -> None:
        # Clear existing dots
        child = self._indicator_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._indicator_box.remove(child)
            child = next_child

        if not self._running:
            return

        n_dots = min(self._window_count, 2)  # 1 or 2 dots
        for _ in range(max(n_dots, 1)):
            dot = Gtk.Box()
            dot.set_size_request(5, 5)
            dot.add_css_class("macux-dock-indicator")
            if n_dots > 1:
                dot.add_css_class("multi")
            self._indicator_box.append(dot)

    def _connect_gestures(self) -> None:
        # Left click → activate
        click = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
        click.connect("released", self._on_primary_click)
        self.add_controller(click)

        # Right click → context menu
        right = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        right.connect("released", self._on_secondary_click)
        self.add_controller(right)

    def _connect_drag(self) -> None:
        # DnD: allow dragging the icon out for reordering
        drag_src = Gtk.DragSource()
        drag_src.set_actions(Gdk.DragAction.MOVE)
        drag_src.connect("prepare", self._on_drag_prepare)
        drag_src.connect("drag-begin", self._on_drag_begin)
        self.add_controller(drag_src)

    def _on_primary_click(self, gesture, n_press, x, y) -> None:
        if n_press == 1 and self._on_click:
            self._on_click(self)

    def _on_secondary_click(self, gesture, n_press, x, y) -> None:
        if self._on_right_click:
            self._on_right_click(self)

    def _on_drag_prepare(self, source, x, y) -> Gdk.ContentProvider | None:
        return Gdk.ContentProvider.new_for_value(GObject.Value(GObject.TYPE_STRING, self.desktop_id))

    def _on_drag_begin(self, source, drag) -> None:
        # Use the icon image as the drag icon
        paintable = self._image.get_paintable()
        if paintable:
            size = self._base_size
            Gtk.DragIcon.set_from_paintable(drag, paintable, size // 2, size // 2)

    def _on_hover_enter(self, controller, x, y) -> None:
        self._label.set_visible(True)

    def _on_hover_leave(self, controller) -> None:
        self._label.set_visible(False)
