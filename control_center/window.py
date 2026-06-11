"""MacUX Control Center — GTK4 slide-down panel window.

Layout (360×auto, anchored top-right below menu bar):

  ┌──────────────────────────────────────────┐
  │ [WiFi][BT][Vol][Bright][Batt]   header   │
  ├──────────────────────────────────────────┤
  │                                          │
  │   Active panel content (Gtk.Stack)       │
  │                                          │
  └──────────────────────────────────────────┘

Panels:
  wifi       — toggle switch + network list (clickable rows)
  bluetooth  — toggle switch + device list
  volume     — per-sink rows with Gtk.Scale sliders
  brightness — single Gtk.Scale
  battery    — read-only status label + time remaining
"""

from __future__ import annotations

import logging
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Adw

from control_center.audio_model import AudioSink
from control_center.bluetooth_model import BluetoothDevice
from control_center.brightness_model import BrightnessState
from control_center.wifi_model import WiFiNetwork
from menu_bar.battery import BatteryState

logger = logging.getLogger(__name__)

WINDOW_WIDTH = 360
PANEL_ORDER = ("wifi", "bluetooth", "volume", "brightness", "battery")

_PANEL_ICONS = {
    "wifi":       "network-wireless-symbolic",
    "bluetooth":  "bluetooth-symbolic",
    "volume":     "audio-volume-high-symbolic",
    "brightness": "display-brightness-symbolic",
    "battery":    "battery-full-symbolic",
}

_CSS = b"""
.macux-cc {
    background-color: rgba(28, 28, 30, 0.95);
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.10);
}
.macux-cc-header {
    background: transparent;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    padding: 6px 8px;
}
.macux-cc-panel-btn {
    background: transparent;
    border: none;
    box-shadow: none;
    color: rgba(255,255,255,0.60);
    border-radius: 8px;
    padding: 4px 6px;
    min-width: 36px;
    min-height: 28px;
}
.macux-cc-panel-btn.active {
    background-color: rgba(255,255,255,0.15);
    color: rgba(255,255,255,0.95);
}
.macux-cc-section {
    padding: 10px 14px;
}
.macux-cc-label {
    font-size: 13px;
    color: rgba(255,255,255,0.90);
}
.macux-cc-sublabel {
    font-size: 11px;
    color: rgba(255,255,255,0.50);
}
.macux-cc-row {
    background: rgba(255,255,255,0.06);
    border-radius: 8px;
    padding: 8px 10px;
    margin: 3px 0;
}
.macux-cc-row:hover {
    background: rgba(255,255,255,0.10);
}
.macux-cc-slider scale trough {
    background: rgba(255,255,255,0.15);
    min-height: 4px;
    border-radius: 2px;
}
.macux-cc-slider scale trough highlight {
    background: rgba(255,255,255,0.85);
    border-radius: 2px;
}
"""


class ControlCenterWindow(Gtk.Window):
    """MacUX Control Center popup panel."""

    __gtype_name__ = "MacuxControlCenterWindow"

    def __init__(
        self,
        on_wifi_toggle: Callable[[bool], None] | None = None,
        on_wifi_connect: Callable[[str], None] | None = None,
        on_bt_toggle: Callable[[bool], None] | None = None,
        on_bt_connect: Callable[[str], None] | None = None,
        on_volume_change: Callable[[int, float], None] | None = None,
        on_brightness_change: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_wifi_toggle = on_wifi_toggle
        self._on_wifi_connect = on_wifi_connect
        self._on_bt_toggle = on_bt_toggle
        self._on_bt_connect = on_bt_connect
        self._on_volume_change = on_volume_change
        self._on_brightness_change = on_brightness_change

        self._panel_buttons: dict[str, Gtk.Button] = {}
        self._stack: Gtk.Stack | None = None
        self._wifi_list: Gtk.ListBox | None = None
        self._bt_list: Gtk.ListBox | None = None
        self._vol_box: Gtk.Box | None = None
        self._bright_scale: Gtk.Scale | None = None
        self._battery_label: Gtk.Label | None = None

        self._load_css()
        self._build()
        self.connect("map", self._on_map)

    # ── Public update API ─────────────────────────────────────────────────────

    def switch_panel(self, panel: str) -> None:
        if self._stack:
            self._stack.set_visible_child_name(panel)
        self._highlight_panel_button(panel)

    def update_wifi(self, networks: list[WiFiNetwork], enabled: bool) -> None:
        if self._wifi_list is None:
            return
        while row := self._wifi_list.get_row_at_index(0):
            self._wifi_list.remove(row)
        for net in networks:
            row = self._make_wifi_row(net)
            self._wifi_list.append(row)

    def update_bluetooth(self, devices: list[BluetoothDevice], powered: bool) -> None:
        if self._bt_list is None:
            return
        while row := self._bt_list.get_row_at_index(0):
            self._bt_list.remove(row)
        for dev in devices:
            row = self._make_bt_row(dev)
            self._bt_list.append(row)

    def update_audio(self, sinks: list[AudioSink]) -> None:
        if self._vol_box is None:
            return
        while child := self._vol_box.get_first_child():
            self._vol_box.remove(child)
        for sink in sinks:
            row = self._make_sink_row(sink)
            self._vol_box.append(row)

    def update_brightness(self, state: BrightnessState) -> None:
        if self._bright_scale:
            self._bright_scale.set_value(state.level)

    def update_battery(self, state: BatteryState) -> None:
        if self._battery_label:
            self._battery_label.set_label(state.format_tooltip())

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.set_title("Control Center")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(WINDOW_WIDTH, -1)
        self.add_css_class("macux-cc")

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header: panel switcher buttons
        header = self._build_header()
        outer.append(header)

        # Stack: one box per panel
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(120)

        for panel_id in PANEL_ORDER:
            page_box = self._build_panel(panel_id)
            self._stack.add_named(page_box, panel_id)

        outer.append(self._stack)
        self.set_child(outer)

        # Default panel
        self._stack.set_visible_child_name("wifi")
        self._highlight_panel_button("wifi")

    def _build_header(self) -> Gtk.Box:
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.add_css_class("macux-cc-header")
        header.set_halign(Gtk.Align.CENTER)

        for panel_id in PANEL_ORDER:
            icon_name = _PANEL_ICONS[panel_id]
            btn = Gtk.Button()
            img = Gtk.Image.new_from_icon_name(icon_name)
            img.set_pixel_size(16)
            btn.set_child(img)
            btn.add_css_class("macux-cc-panel-btn")
            btn.set_tooltip_text(panel_id.capitalize())
            btn.connect("clicked", self._on_panel_btn_clicked, panel_id)
            header.append(btn)
            self._panel_buttons[panel_id] = btn

        return header

    def _build_panel(self, panel_id: str) -> Gtk.Box:
        if panel_id == "wifi":
            return self._build_wifi_panel()
        if panel_id == "bluetooth":
            return self._build_bluetooth_panel()
        if panel_id == "volume":
            return self._build_volume_panel()
        if panel_id == "brightness":
            return self._build_brightness_panel()
        return self._build_battery_panel()

    def _build_wifi_panel(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("macux-cc-section")

        row0 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        lbl = Gtk.Label(label="Wi-Fi")
        lbl.add_css_class("macux-cc-label")
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.START)
        sw = Gtk.Switch()
        sw.set_active(True)
        sw.connect("state-set", lambda s, state: self._on_wifi_toggle and self._on_wifi_toggle(state))
        row0.append(lbl)
        row0.append(sw)
        box.append(row0)

        self._wifi_list = Gtk.ListBox()
        self._wifi_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._wifi_list.add_css_class("boxed-list")
        self._wifi_list.connect("row-activated", self._on_wifi_row_activated)
        box.append(self._wifi_list)
        return box

    def _build_bluetooth_panel(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("macux-cc-section")

        row0 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        lbl = Gtk.Label(label="Bluetooth")
        lbl.add_css_class("macux-cc-label")
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.START)
        sw = Gtk.Switch()
        sw.set_active(False)
        sw.connect("state-set", lambda s, state: self._on_bt_toggle and self._on_bt_toggle(state))
        row0.append(lbl)
        row0.append(sw)
        box.append(row0)

        self._bt_list = Gtk.ListBox()
        self._bt_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._bt_list.add_css_class("boxed-list")
        self._bt_list.connect("row-activated", self._on_bt_row_activated)
        box.append(self._bt_list)
        return box

    def _build_volume_panel(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("macux-cc-section")

        lbl = Gtk.Label(label="Sound Output")
        lbl.add_css_class("macux-cc-label")
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)

        self._vol_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(self._vol_box)
        return box

    def _build_brightness_panel(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("macux-cc-section")

        lbl = Gtk.Label(label="Display Brightness")
        lbl.add_css_class("macux-cc-label")
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name("display-brightness-low-symbolic")
        icon.set_pixel_size(14)
        row.append(icon)

        self._bright_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 5
        )
        self._bright_scale.set_hexpand(True)
        self._bright_scale.set_draw_value(False)
        self._bright_scale.add_css_class("macux-cc-slider")
        self._bright_scale.connect("value-changed", self._on_brightness_changed)
        row.append(self._bright_scale)

        icon2 = Gtk.Image.new_from_icon_name("display-brightness-high-symbolic")
        icon2.set_pixel_size(14)
        row.append(icon2)

        box.append(row)
        return box

    def _build_battery_panel(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("macux-cc-section")

        lbl = Gtk.Label(label="Battery")
        lbl.add_css_class("macux-cc-label")
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)

        self._battery_label = Gtk.Label(label="No battery detected")
        self._battery_label.add_css_class("macux-cc-sublabel")
        self._battery_label.set_halign(Gtk.Align.START)
        self._battery_label.set_wrap(True)
        box.append(self._battery_label)
        return box

    # ── Row builders ──────────────────────────────────────────────────────────

    def _make_wifi_row(self, net: WiFiNetwork) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(True)
        row._ssid = net.ssid

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hbox.add_css_class("macux-cc-row")

        icon = Gtk.Image.new_from_icon_name(net.icon_name())
        icon.set_pixel_size(14)
        hbox.append(icon)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        name_lbl = Gtk.Label(label=net.ssid)
        name_lbl.add_css_class("macux-cc-label")
        name_lbl.set_halign(Gtk.Align.START)
        vbox.append(name_lbl)

        lock = "🔒 " if net.secured else ""
        sub_lbl = Gtk.Label(label=f"{lock}{net.format_signal()}")
        sub_lbl.add_css_class("macux-cc-sublabel")
        sub_lbl.set_halign(Gtk.Align.START)
        vbox.append(sub_lbl)

        hbox.append(vbox)

        if net.connected:
            check = Gtk.Image.new_from_icon_name("object-select-symbolic")
            check.set_pixel_size(14)
            check.set_hexpand(True)
            check.set_halign(Gtk.Align.END)
            hbox.append(check)

        row.set_child(hbox)
        return row

    def _make_bt_row(self, dev: BluetoothDevice) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(True)
        row._address = dev.address

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hbox.add_css_class("macux-cc-row")

        icon = Gtk.Image.new_from_icon_name(dev.icon_name())
        icon.set_pixel_size(14)
        hbox.append(icon)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        name_lbl = Gtk.Label(label=dev.name)
        name_lbl.add_css_class("macux-cc-label")
        name_lbl.set_halign(Gtk.Align.START)
        vbox.append(name_lbl)

        status = "Connected" if dev.connected else ("Paired" if dev.paired else "Not paired")
        sub_lbl = Gtk.Label(label=status)
        sub_lbl.add_css_class("macux-cc-sublabel")
        sub_lbl.set_halign(Gtk.Align.START)
        vbox.append(sub_lbl)

        hbox.append(vbox)
        row.set_child(hbox)
        return row

    def _make_sink_row(self, sink: AudioSink) -> Gtk.Box:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        outer.add_css_class("macux-cc-row")

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name(sink.icon_name())
        icon.set_pixel_size(14)
        top.append(icon)

        lbl = Gtk.Label(label=sink.description)
        lbl.add_css_class("macux-cc-label")
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        top.append(lbl)

        pct = Gtk.Label(label=f"{sink.percent}%")
        pct.add_css_class("macux-cc-sublabel")
        top.append(pct)
        outer.append(top)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.5, 0.05)
        scale.set_value(sink.volume)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        scale.add_css_class("macux-cc-slider")
        _idx = sink.index
        scale.connect(
            "value-changed",
            lambda s: self._on_volume_change and self._on_volume_change(_idx, s.get_value()),
        )
        outer.append(scale)
        return outer

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_panel_btn_clicked(self, btn: Gtk.Button, panel_id: str) -> None:
        if self._stack:
            self._stack.set_visible_child_name(panel_id)
        self._highlight_panel_button(panel_id)

    def _on_wifi_row_activated(self, listbox, row) -> None:
        ssid = getattr(row, "_ssid", None)
        if ssid and self._on_wifi_connect:
            self._on_wifi_connect(ssid)

    def _on_bt_row_activated(self, listbox, row) -> None:
        addr = getattr(row, "_address", None)
        if addr and self._on_bt_connect:
            self._on_bt_connect(addr)

    def _on_brightness_changed(self, scale: Gtk.Scale) -> None:
        if self._on_brightness_change:
            self._on_brightness_change(round(scale.get_value()))

    def _highlight_panel_button(self, active_panel: str) -> None:
        for panel_id, btn in self._panel_buttons.items():
            if panel_id == active_panel:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")

    # ── CSS + positioning ─────────────────────────────────────────────────────

    def _load_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _on_map(self, window: Gtk.Window) -> None:
        display = Gdk.Display.get_default()
        if not display:
            return
        monitors = display.get_monitors()
        if monitors.get_n_items() == 0:
            return
        monitor = monitors.get_item(0)
        geo = monitor.get_geometry()
        # Position: top-right corner, just below menu bar (28px)
        try:
            import gi
            gi.require_version("GdkX11", "4.0")
            from gi.repository import GdkX11
            surface = self.get_surface()
            if surface and isinstance(surface, GdkX11.X11Surface):
                x = geo.x + geo.width - WINDOW_WIDTH - 4
                y = geo.y + 32  # just below the 28px menu bar
                surface.move(x, y)
        except Exception as exc:
            logger.debug("ControlCenter: X11 positioning failed: %s", exc)
