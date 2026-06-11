"""MacUX Menu Bar — top-of-screen window.

Layout (28 px tall, full screen width):
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  [App Name]  [File]  [Edit]  [View]  [Window]  [Help]  ···  [🔔][📶][🔋][🔊][clock] │
  └──────────────────────────────────────────────────────────────────────────┘
    ← left_box (app name + menu items, HBox)       right_box (indicators) →

X11 anchoring: after map, move to (0, 0) and set _NET_WM_STRUT_PARTIAL to
reserve 28 px at the top of every workspace.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Adw

from menu_bar.battery import BatteryState
from menu_bar.clock import format_full
from menu_bar.menu_model import MenuItem, visible_items
from menu_bar.network import NetworkState
from menu_bar.volume import VolumeState

logger = logging.getLogger(__name__)

BAR_HEIGHT = 28

_CSS = b"""
.macux-menubar {
    background-color: rgba(20, 20, 22, 0.88);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.macux-menubar-btn {
    font-size: 13px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.95);
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 0 8px;
    border-radius: 4px;
    min-height: 22px;
}

.macux-menubar-btn:hover {
    background-color: rgba(255, 255, 255, 0.12);
}

.macux-appname {
    font-weight: 700;
}

.macux-indicator {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.88);
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 0 6px;
    min-height: 22px;
    border-radius: 4px;
}

.macux-indicator:hover {
    background-color: rgba(255, 255, 255, 0.10);
}

.macux-clock {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.95);
    padding: 0 8px;
}
"""


class MenuBarWindow(Gtk.Window):
    """
    MacUX Menu Bar: a 28 px top bar with app menu on the left and
    system indicators (network, battery, volume, clock) on the right.
    """

    __gtype_name__ = "MacuxMenuBarWindow"

    def __init__(self) -> None:
        super().__init__()
        self._app_name: str = ""
        self._menu_buttons: list[Gtk.MenuButton] = []
        self._clock_label: Gtk.Label | None = None
        self._battery_label: Gtk.Label | None = None
        self._battery_icon: Gtk.Image | None = None
        self._network_icon: Gtk.Image | None = None
        self._volume_icon: Gtk.Image | None = None
        self._clock_timeout_id: int = 0

        self._load_css()
        self._build()
        self.connect("map", self._on_map)

    # ── Public API ────────────────────────────────────────────────────────────

    def update_app_menu(self, app_name: str, menu_root: MenuItem | None) -> None:
        """Rebuild the left side for the newly focused app."""
        self._app_name = app_name
        self._rebuild_app_menu(app_name, menu_root)

    def update_battery(self, state: BatteryState) -> None:
        if self._battery_icon:
            self._battery_icon.set_from_icon_name(state.icon_name())
        if self._battery_label:
            self._battery_label.set_label(state.format_label())
            self._battery_label.set_visible(bool(state.format_label()))
        if self._battery_icon:
            self._battery_icon.set_tooltip_text(state.format_tooltip())

    def update_network(self, state: NetworkState) -> None:
        if self._network_icon:
            self._network_icon.set_from_icon_name(state.icon_name())
            self._network_icon.set_tooltip_text(state.format_tooltip())

    def update_volume(self, state: VolumeState) -> None:
        if self._volume_icon:
            self._volume_icon.set_from_icon_name(state.icon_name())
            self._volume_icon.set_tooltip_text(state.format_tooltip())

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.set_title("MacUX Menu Bar")
        self.set_decorated(False)
        self.set_resizable(False)
        self.add_css_class("macux-menubar")

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        outer.set_hexpand(True)
        outer.set_valign(Gtk.Align.CENTER)

        # Left: app name + menu items
        self._left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._left_box.set_hexpand(True)
        self._left_box.set_valign(Gtk.Align.CENTER)
        self._left_box.set_margin_start(8)
        outer.append(self._left_box)

        # Right: indicators
        right = self._build_indicators()
        right.set_valign(Gtk.Align.CENTER)
        right.set_margin_end(8)
        outer.append(right)

        self.set_child(outer)

    def _build_indicators(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        # Network icon
        self._network_icon = Gtk.Image.new_from_icon_name("network-offline-symbolic")
        self._network_icon.set_pixel_size(14)
        net_btn = self._wrap_indicator(self._network_icon)
        box.append(net_btn)

        # Battery icon + label
        bat_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self._battery_icon = Gtk.Image.new_from_icon_name("battery-missing-symbolic")
        self._battery_icon.set_pixel_size(14)
        bat_box.append(self._battery_icon)
        self._battery_label = Gtk.Label(label="")
        self._battery_label.add_css_class("macux-indicator")
        self._battery_label.set_visible(False)
        bat_box.append(self._battery_label)
        bat_btn = self._wrap_indicator(bat_box)
        box.append(bat_btn)

        # Volume icon
        self._volume_icon = Gtk.Image.new_from_icon_name("audio-volume-medium-symbolic")
        self._volume_icon.set_pixel_size(14)
        vol_btn = self._wrap_indicator(self._volume_icon)
        box.append(vol_btn)

        # Clock
        self._clock_label = Gtk.Label()
        self._clock_label.add_css_class("macux-clock")
        self._update_clock()
        self._clock_timeout_id = GLib.timeout_add_seconds(30, self._update_clock)
        box.append(self._clock_label)

        return box

    def _wrap_indicator(self, widget: Gtk.Widget) -> Gtk.Button:
        btn = Gtk.Button()
        btn.set_child(widget)
        btn.add_css_class("macux-indicator")
        return btn

    def _load_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── App menu ──────────────────────────────────────────────────────────────

    def _rebuild_app_menu(self, app_name: str, menu_root: MenuItem | None) -> None:
        # Remove existing buttons
        while True:
            child = self._left_box.get_first_child()
            if child is None:
                break
            self._left_box.remove(child)
        self._menu_buttons.clear()

        # App name button (bold)
        app_btn = Gtk.Button(label=app_name or "Desktop")
        app_btn.add_css_class("macux-menubar-btn")
        app_btn.add_css_class("macux-appname")
        self._left_box.append(app_btn)

        if menu_root is None:
            return

        # One button per top-level menu item
        for item in visible_items(menu_root):
            if item.is_separator:
                continue
            btn = self._build_menu_button(item)
            self._left_box.append(btn)
            self._menu_buttons.append(btn)

    def _build_menu_button(self, item: MenuItem) -> Gtk.MenuButton:
        menu = Gtk.PopoverMenu.new_from_model(self._item_to_gio_menu(item))
        btn = Gtk.MenuButton(label=item.display_label, popover=menu)
        btn.add_css_class("macux-menubar-btn")
        return btn

    @staticmethod
    def _item_to_gio_menu(item: MenuItem) -> Gio.Menu:
        from gi.repository import Gio
        gio_menu = Gio.Menu()
        for child in item.children:
            if child.is_separator:
                continue
            if child.is_submenu:
                section = Gio.Menu()
                for grandchild in child.children:
                    if not grandchild.is_separator and grandchild.visible:
                        section.append(grandchild.display_label, f"app.dbusmenu.{grandchild.item_id}")
                gio_menu.append_section(child.display_label or None, section)
            elif child.visible and child.enabled:
                gio_menu.append(child.display_label, f"app.dbusmenu.{child.item_id}")
        return gio_menu

    # ── Clock ─────────────────────────────────────────────────────────────────

    def _update_clock(self) -> bool:
        import datetime
        if self._clock_label:
            self._clock_label.set_label(format_full(datetime.datetime.now()))
        return True  # keep timeout running

    # ── X11 anchoring ─────────────────────────────────────────────────────────

    def _on_map(self, window: Gtk.Window) -> None:
        display = Gdk.Display.get_default()
        if not display:
            return
        monitors = display.get_monitors()
        if monitors.get_n_items() == 0:
            return
        monitor = monitors.get_item(0)
        geo = monitor.get_geometry()
        # Full screen width, 28 px tall
        self.set_default_size(geo.width, BAR_HEIGHT)
        self._position_x11(geo.width)

    def _position_x11(self, screen_width: int) -> None:
        try:
            import gi
            gi.require_version("GdkX11", "4.0")
            from gi.repository import GdkX11
            surface = self.get_surface()
            if surface and isinstance(surface, GdkX11.X11Surface):
                surface.move(0, 0)
                xid = surface.get_xid()
                # _NET_WM_WINDOW_TYPE = _NET_WM_WINDOW_TYPE_DOCK
                subprocess.run(
                    ["xprop", "-id", str(xid),
                     "-f", "_NET_WM_WINDOW_TYPE", "32a",
                     "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DOCK"],
                    check=False, capture_output=True,
                )
                # Reserve 28 px at the top
                subprocess.run(
                    ["xprop", "-id", str(xid),
                     "-f", "_NET_WM_STRUT_PARTIAL", "32c",
                     "-set", "_NET_WM_STRUT_PARTIAL",
                     f"0, 0, {BAR_HEIGHT}, 0, 0, 0, 0, 0, 0, {screen_width}, 0, 0"],
                    check=False, capture_output=True,
                )
        except Exception as exc:
            logger.debug("MenuBar: X11 anchoring failed: %s", exc)
