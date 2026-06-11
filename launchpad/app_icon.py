"""MacUX Launchpad — single app icon widget.

Layout (vertical box):
  ┌────────────────────┐
  │  [80×80 icon img]  │
  │    App Name        │  ← 2-line, center-aligned, ellipsized
  └────────────────────┘

The widget emits an ``activated`` signal when clicked or Enter is pressed,
and is a DragSource for DnD reordering/folder-creation.
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, GObject, Gtk

_ICON_SIZE = 80
_LABEL_MAX_CHARS = 12


class AppIcon(Gtk.Box):
    """
    A single Launchpad app icon: thumbnail + name label.

    Signals:
        activated(desktop_id: str) — the user clicked or pressed Enter on it.
    """

    __gtype_name__ = "MacuxLaunchpadAppIcon"

    activated = GObject.Signal("activated", arg_types=(str,))

    def __init__(self, app_info, icon_size: int = _ICON_SIZE) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.app_info = app_info
        self._icon_size = icon_size
        self._dimmed = False
        self._build()
        self._setup_gestures()
        self.add_css_class("macux-launchpad-icon")

    # ── Public API ────────────────────────────────────────────────────────────

    def set_dimmed(self, dimmed: bool) -> None:
        """Dim the icon when a search query excludes it."""
        self._dimmed = dimmed
        if dimmed:
            self.add_css_class("dim")
        else:
            self.remove_css_class("dim")

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.START)

        # Icon image
        image = Gtk.Image()
        image.set_pixel_size(self._icon_size)
        icon_name = getattr(self.app_info, "icon", None) or "application-x-executable"
        image.set_from_icon_name(icon_name)
        image.set_halign(Gtk.Align.CENTER)
        image.add_css_class("macux-launchpad-icon-image")
        self.append(image)

        # Label
        label = Gtk.Label(label=self.app_info.name)
        label.set_halign(Gtk.Align.CENTER)
        label.set_max_width_chars(_LABEL_MAX_CHARS)
        label.set_ellipsize(3)   # PANGO_ELLIPSIZE_END
        label.set_wrap(True)
        label.set_wrap_mode(2)   # Pango.WrapMode.WORD_CHAR
        label.set_lines(2)
        label.set_justify(Gtk.Justification.CENTER)
        label.add_css_class("macux-launchpad-label")
        self.append(label)

    def _setup_gestures(self) -> None:
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("released", self._on_click)
        self.add_controller(click)

        # Keyboard: focusable widget so Tab navigation works
        self.set_focusable(True)
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        # Hover: subtle scale effect via CSS class
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self.add_css_class("hover"))
        motion.connect("leave", lambda *_: self.remove_css_class("hover"))
        self.add_controller(motion)

    def _on_click(self, gesture, n_press, x, y) -> None:
        self.activated.emit(self.app_info.path)

    def _on_key(self, controller, keyval, keycode, state) -> bool:
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.activated.emit(self.app_info.path)
            return True
        return False
