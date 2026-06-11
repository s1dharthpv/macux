"""MacUX Dock — main dock window.

DockWindow is a borderless GTK4 window that:
  - Renders the dock pill at the configured screen edge
  - Applies MagnificationController on cursor motion
  - Delegates show/hide to AutoHideController
  - Rebuilds icon list when pinned/running apps change
  - Positions itself on the primary monitor and reserves struts (X11)
  - Provides a Gtk.DropTarget on the pill for icon reordering via DnD

Layout (bottom dock)
--------------------
  DockWindow (Gtk.Window, no decorations)
  └── _root_box (Gtk.Box, vertical, transparent fill)
      └── _pill_box (Gtk.Box, horizontal, .macux-dock)
          ├── [DockIcon] ...  ← pinned apps
          ├── [DockSeparator]  ← only if running-only apps exist
          ├── [DockIcon] ...  ← running (non-pinned) apps
          ├── [DockSeparator]
          └── [TrashWidget]
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gdk, GLib, Gio, Gtk

from dock.autohide import AutoHideController
from dock.icon_widget import DockIcon
from dock.magnification import MagnificationConfig, MagnificationController
from dock.separator import DockSeparator
from dock.trash_widget import TrashWidget

if TYPE_CHECKING:
    from dock.app_monitor import AppMonitor
    from dock.desktop_file import AppInfo
    from dock.persistence import DockPersistence

logger = logging.getLogger(__name__)

# Gap between dock pill and screen edge (px)
_EDGE_MARGIN = 6
# Strip height to leave visible when hidden (px)
_HIDDEN_STRIP = 2
# Animation timer interval (ms)
_ANIM_INTERVAL_MS = 16
# Auto-hide check timer interval (ms)
_AUTOHIDE_INTERVAL_MS = 50


class DockWindow(Gtk.Window):
    """The MacUX Dock window."""

    def __init__(
        self,
        persistence: DockPersistence,
        app_registry: dict[str, AppInfo],
        app_monitor: AppMonitor,
        config: dict,
        theme_engine=None,
    ) -> None:
        super().__init__()

        self._db = persistence
        self._registry = app_registry
        self._monitor_obj = app_monitor
        self._cfg = config
        self._engine = theme_engine

        # Widget references keyed by desktop_id
        self._icon_widgets: dict[str, DockIcon] = {}
        self._icon_order: list[str] = []  # current visual order

        # Controllers
        self._mag = MagnificationController(
            MagnificationConfig(
                base_size=config.get("icon_size", 48),
                max_size=config.get("magnification_max", 72),
                radius=config.get("magnification_radius", 100),
            )
        )
        self._mag.enabled = bool(config.get("magnification", True))

        self._autohide = AutoHideController(
            enabled=bool(config.get("auto_hide", False)),
            hide_delay=float(config.get("auto_hide_delay", 0.5)),
            show_delay=float(config.get("auto_hide_show_delay", 0.1)),
        )
        self._autohide.on_hide(self._slide_out)
        self._autohide.on_show(self._slide_in)

        self._position = config.get("position", "bottom")  # bottom | left | right

        # Animation state
        self._anim_timer_id: int = 0
        self._autohide_timer_id: int = 0
        self._hidden_offset: int = 0  # pixels the dock is slid off-screen

        self._build_window()
        self._build_pill()
        self._populate()
        self._connect_app_monitor()
        self.connect("realize", self._on_realize)
        self.connect("map", self._on_map)

    # ── Window construction ────────────────────────────────────────────────────

    def _build_window(self) -> None:
        self.set_title("MacUX Dock")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_name("macux-dock-window")
        self.add_css_class("macux-dock-window")

        # Transparent background — the pill widget has the glass background
        self.set_opacity(1.0)

    def _build_pill(self) -> None:
        # Full-width transparent root box that anchors to screen bottom
        self._root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._root_box.set_valign(Gtk.Align.END)
        self._root_box.set_halign(Gtk.Align.CENTER)

        # The visible dock pill
        self._pill_box = Gtk.Box(
            orientation=(
                Gtk.Orientation.VERTICAL
                if self._position in ("left", "right")
                else Gtk.Orientation.HORIZONTAL
            ),
            spacing=4,
        )
        self._pill_box.set_margin_start(8)
        self._pill_box.set_margin_end(8)
        self._pill_box.set_margin_top(6)
        self._pill_box.set_margin_bottom(6)
        self._pill_box.add_css_class("macux-dock")
        self._pill_box.set_halign(Gtk.Align.CENTER)
        self._pill_box.set_valign(Gtk.Align.END)

        self._root_box.append(self._pill_box)
        self.set_child(self._root_box)

        # Motion tracking for magnification and auto-hide
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("enter", self._on_cursor_enter)
        motion.connect("leave", self._on_cursor_leave)
        self._pill_box.add_controller(motion)

        # Drop target for icon reordering
        drop = Gtk.DropTarget.new(type=None, actions=Gdk.DragAction.MOVE)
        drop.set_gtypes([str])
        drop.connect("drop", self._on_icon_drop)
        drop.connect("motion", self._on_drop_motion)
        self._pill_box.add_controller(drop)

    # ── Icon population ────────────────────────────────────────────────────────

    def _populate(self) -> None:
        """Rebuild the dock icon list from pinned apps + running apps."""
        # Remove all existing icons
        while True:
            child = self._pill_box.get_first_child()
            if child is None:
                break
            self._pill_box.remove(child)

        self._icon_widgets.clear()
        self._icon_order.clear()

        pinned = self._db.get_pinned_apps()
        running = self._monitor_obj.get_running_desktop_ids()

        show_trash = bool(self._cfg.get("show_trash", True))

        # Pinned apps
        for desktop_id in pinned:
            self._add_icon(desktop_id)

        # Separator if there are running-only apps
        running_only = running - set(pinned)
        if running_only:
            self._pill_box.append(DockSeparator())
            for desktop_id in sorted(running_only):
                self._add_icon(desktop_id)

        # Trash
        if show_trash:
            self._pill_box.append(DockSeparator())
            trash = TrashWidget(icon_size=self._cfg.get("icon_size", 48))
            self._pill_box.append(trash)

        # Update magnification controller width
        self._mag.resize(len(self._icon_order))

    def _add_icon(self, desktop_id: str) -> DockIcon | None:
        info = self._registry.get(desktop_id)
        if info is None:
            logger.debug("Dock: %s not in registry — skipping", desktop_id)
            return None

        icon = DockIcon(
            desktop_id=desktop_id,
            app_name=info.name,
            icon_name=info.icon,
            base_size=self._cfg.get("icon_size", 48),
            on_click=self._on_icon_click,
            on_right_click=self._on_icon_right_click,
        )

        running = self._monitor_obj.get_running_desktop_ids()
        wcount = self._monitor_obj.get_window_count(desktop_id)
        icon.set_running(desktop_id in running, wcount)

        self._pill_box.append(icon)
        self._icon_widgets[desktop_id] = icon
        self._icon_order.append(desktop_id)
        return icon

    # ── Running app monitor ────────────────────────────────────────────────────

    def _connect_app_monitor(self) -> None:
        self._monitor_obj.on_changed(self._on_running_changed)

    def _on_running_changed(self) -> None:
        running = self._monitor_obj.get_running_desktop_ids()
        # Update indicators for known icons
        for desktop_id, icon in self._icon_widgets.items():
            wcount = self._monitor_obj.get_window_count(desktop_id)
            icon.set_running(desktop_id in running, wcount)

        # Repopulate if a new running-only app appeared or disappeared
        all_visible = set(self._icon_order)
        pinned = set(self._db.get_pinned_apps())
        running_only = running - pinned
        if running_only != (all_visible - pinned):
            GLib.idle_add(self._populate)

    # ── Icon event handlers ────────────────────────────────────────────────────

    def _on_icon_click(self, icon: DockIcon) -> None:
        info = self._registry.get(icon.desktop_id)
        if info is None:
            return

        running = self._monitor_obj.get_running_desktop_ids()
        if icon.desktop_id in running:
            # Raise existing window — handled by AppMonitor/Wnck, here we just bounce
            pass
        else:
            # Launch
            if bool(self._cfg.get("bounce_on_launch", True)):
                icon.bounce("launch")
            self._launch_app(info)

    def _on_icon_right_click(self, icon: DockIcon) -> None:
        # Context menu — build popover
        menu = Gio.Menu()
        is_pinned = self._db.is_pinned(icon.desktop_id)
        if is_pinned:
            menu.append("Remove from Dock", f"dock.unpin::{icon.desktop_id}")
        else:
            menu.append("Keep in Dock", f"dock.pin::{icon.desktop_id}")
        menu.append("Show in Files", f"dock.show-in-files::{icon.desktop_id}")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(icon)
        popover.popup()

    @staticmethod
    def _launch_app(info) -> None:
        cmd = info.launch_command()
        if not cmd:
            return
        try:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                close_fds=True,
            )
        except Exception as exc:
            logger.warning("Failed to launch %s: %s", info.desktop_id, exc)

    # ── DnD icon reorder ──────────────────────────────────────────────────────

    def _on_icon_drop(self, drop_target, value, x, y) -> bool:
        """Handle dropping a dock icon to a new position."""
        desktop_id = str(value)
        if desktop_id not in self._icon_order:
            return False

        # Determine the new position based on x coordinate
        new_pos = self._position_from_x(x)
        old_pos = self._icon_order.index(desktop_id)
        if new_pos == old_pos:
            return True

        self._db.move_app(desktop_id, new_pos)
        GLib.idle_add(self._populate)
        return True

    def _on_drop_motion(self, drop_target, x, y) -> Gdk.DragAction:
        return Gdk.DragAction.MOVE

    def _position_from_x(self, x: float) -> int:
        """Convert cursor x → icon index (for horizontal dock)."""
        icon_size = self._cfg.get("icon_size", 48)
        spacing = 4
        pos = max(0, int(x / (icon_size + spacing)))
        return min(pos, len(self._icon_order) - 1)

    # ── Magnification ──────────────────────────────────────────────────────────

    def _on_motion(self, controller, x, y) -> None:
        if not self._mag.enabled:
            return

        centers = self._compute_icon_centers()
        self._mag.compute_target_sizes(cursor_x=x, icon_centers=centers)

        if not self._anim_timer_id:
            self._anim_timer_id = GLib.timeout_add(_ANIM_INTERVAL_MS, self._animate_step)

    def _animate_step(self) -> bool:
        still = self._mag.step()
        sizes = self._mag.icon_sizes_as_int()
        for i, desktop_id in enumerate(self._icon_order):
            widget = self._icon_widgets.get(desktop_id)
            if widget and i < len(sizes):
                widget.set_icon_size(sizes[i])
        if not still:
            self._anim_timer_id = 0
        return still

    def _compute_icon_centers(self) -> list[float]:
        """Return x-center of each icon in pill widget coordinates."""
        centers: list[float] = []
        icon_size = self._cfg.get("icon_size", 48)
        spacing = 4
        x = icon_size / 2
        for _ in self._icon_order:
            centers.append(x)
            x += icon_size + spacing
        return centers

    # ── Auto-hide ──────────────────────────────────────────────────────────────

    def _on_cursor_enter(self, controller, x, y) -> None:
        self._autohide.cursor_entered()

    def _on_cursor_leave(self, controller) -> None:
        self._mag.reset()
        self._anim_timer_id = 0
        # Reset icon sizes
        for icon in self._icon_widgets.values():
            icon.set_icon_size(self._cfg.get("icon_size", 48))
        self._autohide.cursor_left()

    def _slide_in(self) -> None:
        self.set_visible(True)
        self._autohide.animation_done()

    def _slide_out(self) -> None:
        # For true animation we'd use a GLib timer + CSS transitions;
        # for now just hide and leave a strip
        self._autohide.animation_done()

    # ── X11 window placement ───────────────────────────────────────────────────

    def _on_realize(self, _widget) -> None:
        """Set X11 window type to _NET_WM_WINDOW_TYPE_DOCK after realize."""
        try:
            from gi.repository import GdkX11
            surface = self.get_surface()
            if isinstance(surface, GdkX11.X11Surface):
                xid = surface.get_xid()
                self._set_x11_dock_type(xid)
                logger.debug("Set X11 DOCK window type (xid=%d)", xid)
        except Exception as exc:
            logger.debug("X11 dock type hint not set: %s", exc)

    def _on_map(self, _widget) -> None:
        """Position the dock at the screen edge after it is mapped."""
        GLib.idle_add(self._position_at_edge)

    def _position_at_edge(self) -> bool:
        display = Gdk.Display.get_default()
        if display is None:
            return False

        monitors = display.get_monitors()
        if monitors.get_n_items() == 0:
            return False

        monitor: Gdk.Monitor = monitors.get_item(0)
        geom = monitor.get_geometry()
        scale = monitor.get_scale_factor()

        # Measure dock natural size
        _, _, nat_width, nat_height = self._pill_box.get_preferred_size()
        icon_size = self._cfg.get("icon_size", 48)
        dock_h = nat_height or (icon_size + 28)
        dock_w = nat_width or (icon_size * 6)

        if self._position == "bottom":
            x = geom.x + (geom.width - dock_w) // 2
            y = geom.y + geom.height - dock_h - _EDGE_MARGIN
        elif self._position == "left":
            x = geom.x + _EDGE_MARGIN
            y = geom.y + (geom.height - dock_h) // 2
        else:  # right
            x = geom.x + geom.width - dock_w - _EDGE_MARGIN
            y = geom.y + (geom.height - dock_h) // 2

        try:
            from gi.repository import GdkX11
            surface = self.get_surface()
            if isinstance(surface, GdkX11.X11Surface):
                surface.move(x, y)
                self._set_x11_strut(surface.get_xid(), geom, dock_h, x, dock_w)
        except Exception as exc:
            logger.debug("Window positioning skipped: %s", exc)

        return False  # run once

    @staticmethod
    def _set_x11_dock_type(xid: int) -> None:
        subprocess.run(
            [
                "xprop", "-id", hex(xid),
                "-f", "_NET_WM_WINDOW_TYPE", "32a",
                "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DOCK",
            ],
            capture_output=True,
            timeout=2,
        )
        # Also hide from taskbar/pager
        subprocess.run(
            [
                "xprop", "-id", hex(xid),
                "-f", "_NET_WM_STATE", "32a",
                "-set", "_NET_WM_STATE",
                "_NET_WM_STATE_SKIP_TASKBAR,_NET_WM_STATE_SKIP_PAGER",
            ],
            capture_output=True,
            timeout=2,
        )

    @staticmethod
    def _set_x11_strut(xid: int, geom, dock_h: int, dock_x: int, dock_w: int) -> None:
        """Reserve screen space for the dock (bottom edge)."""
        # _NET_WM_STRUT_PARTIAL: left right top bottom
        #   left_start left_end right_start right_end top_start top_end
        #   bottom_start bottom_end
        strut_bottom = dock_h + _EDGE_MARGIN
        bottom_start = dock_x
        bottom_end = dock_x + dock_w - 1
        strut_values = (
            f"0, 0, 0, {strut_bottom}, "
            f"0, 0, 0, 0, 0, 0, "
            f"{bottom_start}, {bottom_end}"
        )
        subprocess.run(
            [
                "xprop", "-id", hex(xid),
                "-f", "_NET_WM_STRUT_PARTIAL", "32c",
                "-set", "_NET_WM_STRUT_PARTIAL", strut_values,
            ],
            capture_output=True,
            timeout=2,
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def show_dock(self) -> None:
        self.set_visible(True)

    def hide_dock(self) -> None:
        self.set_visible(False)

    def bounce_app(self, desktop_id: str, bounce_type: str) -> None:
        icon = self._icon_widgets.get(desktop_id)
        if icon:
            icon.bounce(bounce_type)

    def reload_config(self, config: dict) -> None:
        """Apply updated configuration without rebuilding."""
        self._cfg = config
        icon_size = config.get("icon_size", 48)
        for icon in self._icon_widgets.values():
            icon.set_icon_size(icon_size)
        self._mag.enabled = bool(config.get("magnification", True))
        self._autohide.enabled = bool(config.get("auto_hide", False))
        GLib.idle_add(self._position_at_edge)
