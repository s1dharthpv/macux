"""Unit tests for Phase 4 — MacUX Dock.

Tests cover:
  - MagnificationController (pure math)
  - AutoHideController (state machine)
  - DesktopFileParser (file I/O)
  - DockPersistence (SQLite)
  - AppMonitor._match_desktop_id (matching logic)
  - DockDBusServer interface methods (with mocked persistence)
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── MagnificationController ────────────────────────────────────────────────────

class TestMagnificationConfig:
    def test_default_config(self):
        from dock.magnification import MagnificationConfig
        cfg = MagnificationConfig()
        assert cfg.base_size == 48
        assert cfg.max_size == 72
        assert cfg.radius == 100

    def test_invalid_base_size(self):
        from dock.magnification import MagnificationConfig
        with pytest.raises(ValueError, match="base_size"):
            MagnificationConfig(base_size=0)

    def test_invalid_max_size(self):
        from dock.magnification import MagnificationConfig
        with pytest.raises(ValueError, match="max_size"):
            MagnificationConfig(base_size=72, max_size=48)

    def test_invalid_radius(self):
        from dock.magnification import MagnificationConfig
        with pytest.raises(ValueError, match="radius"):
            MagnificationConfig(radius=0)

    def test_invalid_lerp_speed(self):
        from dock.magnification import MagnificationConfig
        with pytest.raises(ValueError, match="lerp_speed"):
            MagnificationConfig(lerp_speed=0.0)


class TestMagnificationController:
    def _ctrl(self, base=48, max_s=72, radius=100, lerp_speed=0.25):
        from dock.magnification import MagnificationConfig, MagnificationController
        return MagnificationController(MagnificationConfig(base, max_s, radius, lerp_speed))

    def test_cursor_at_center_gives_max_size(self):
        ctrl = self._ctrl(base=48, max_s=72, radius=100)
        # Icon center at x=50, cursor at x=50 → distance 0 → max
        targets = ctrl.compute_target_sizes(cursor_x=50.0, icon_centers=[50.0])
        assert abs(targets[0] - 72.0) < 0.1

    def test_cursor_far_away_gives_base_size(self):
        ctrl = self._ctrl(base=48, max_s=72, radius=100)
        # Cursor at 500, icon at 0 → distance 500 >> radius → base
        targets = ctrl.compute_target_sizes(cursor_x=500.0, icon_centers=[0.0])
        assert abs(targets[0] - 48.0) < 0.1

    def test_cursor_at_radius_gives_base_size(self):
        ctrl = self._ctrl(base=48, max_s=72, radius=100)
        targets = ctrl.compute_target_sizes(cursor_x=100.0, icon_centers=[0.0])
        assert abs(targets[0] - 48.0) < 0.1

    def test_multiple_icons_gradient(self):
        ctrl = self._ctrl(base=48, max_s=72, radius=100)
        # Cursor between icon 1 (x=48) and icon 2 (x=96)
        centers = [0.0, 48.0, 96.0, 144.0]
        targets = ctrl.compute_target_sizes(cursor_x=48.0, icon_centers=centers)
        # Icon 1 (center=48) should be largest
        assert targets[1] == max(targets)
        # Outer icons should be smaller
        assert targets[0] < targets[1]
        assert targets[3] < targets[1]

    def test_returns_correct_count(self):
        ctrl = self._ctrl()
        centers = [24.0, 72.0, 120.0]
        targets = ctrl.compute_target_sizes(cursor_x=72.0, icon_centers=centers)
        assert len(targets) == 3

    def test_step_lerps_toward_target(self):
        ctrl = self._ctrl(base=48, max_s=72, radius=100, lerp_speed=0.5)
        ctrl.compute_target_sizes(cursor_x=50.0, icon_centers=[50.0])
        # Initial current is base_size, target is max_size
        initial = ctrl.current_sizes[0]
        ctrl.step()
        after = ctrl.current_sizes[0]
        assert after > initial  # moving toward max

    def test_step_returns_false_when_settled(self):
        ctrl = self._ctrl(lerp_speed=1.0)
        ctrl.compute_target_sizes(cursor_x=0.0, icon_centers=[500.0])
        # Already at base, target is base → settled immediately
        ctrl._current = [48.0]
        ctrl._targets = [48.0]
        result = ctrl.step()
        assert result is False

    def test_reset_snaps_to_base(self):
        ctrl = self._ctrl(base=48, max_s=72)
        ctrl.compute_target_sizes(cursor_x=50.0, icon_centers=[50.0])
        ctrl.step()  # now it's moving toward 72
        ctrl.reset()
        assert all(abs(s - 48.0) < 0.1 for s in ctrl.current_sizes)

    def test_enabled_false_returns_base_sizes(self):
        ctrl = self._ctrl(base=48, max_s=72, radius=100)
        ctrl.enabled = False
        targets = ctrl.compute_target_sizes(cursor_x=50.0, icon_centers=[50.0, 100.0])
        assert all(t == 48.0 for t in targets)

    def test_resize_adjusts_arrays(self):
        ctrl = self._ctrl()
        ctrl.resize(5)
        assert len(ctrl.current_sizes) == 5

    def test_icon_sizes_as_int(self):
        ctrl = self._ctrl(base=48)
        ctrl.resize(3)
        ints = ctrl.icon_sizes_as_int()
        assert ints == [48, 48, 48]
        assert all(isinstance(s, int) for s in ints)

    def test_magnification_is_symmetric(self):
        ctrl = self._ctrl(base=48, max_s=72, radius=100)
        centers = [0.0, 200.0]
        left = ctrl.compute_target_sizes(cursor_x=0.0, icon_centers=centers)
        right = ctrl.compute_target_sizes(cursor_x=200.0, icon_centers=centers)
        assert abs(left[0] - right[1]) < 0.01
        assert abs(left[1] - right[0]) < 0.01


# ── AutoHideController ─────────────────────────────────────────────────────────

class TestAutoHideController:
    def _ctrl(self, enabled=True, hide_delay=0.5):
        from dock.autohide import AutoHideController
        return AutoHideController(enabled=enabled, hide_delay=hide_delay)

    def test_initial_state_is_shown(self):
        from dock.autohide import AutoHideState
        ctrl = self._ctrl()
        assert ctrl.state == AutoHideState.SHOWN

    def test_cursor_left_transitions_to_hiding(self):
        from dock.autohide import AutoHideState
        ctrl = self._ctrl()
        ctrl.cursor_left()
        assert ctrl.state == AutoHideState.HIDING

    def test_cursor_entered_from_hiding_shows(self):
        from dock.autohide import AutoHideState
        ctrl = self._ctrl()
        ctrl.cursor_left()
        ctrl.cursor_entered()
        assert ctrl.state == AutoHideState.SHOWING

    def test_timer_tick_fires_hide(self):
        from dock.autohide import AutoHideState
        hidden = []
        ctrl = self._ctrl(hide_delay=0.5)
        ctrl.on_hide(lambda: hidden.append(True))
        ctrl.cursor_left()
        ctrl.timer_tick(0.3)  # not yet
        assert ctrl.state == AutoHideState.HIDING
        ctrl.timer_tick(0.3)  # now past delay
        assert ctrl.state == AutoHideState.HIDDEN
        assert hidden

    def test_timer_cancelled_by_enter(self):
        from dock.autohide import AutoHideState
        hidden = []
        ctrl = self._ctrl(hide_delay=0.5)
        ctrl.on_hide(lambda: hidden.append(True))
        ctrl.cursor_left()
        ctrl.timer_tick(0.2)
        ctrl.cursor_entered()  # cancels
        ctrl.timer_tick(0.5)   # tick after cancel — should not fire hide
        assert not hidden

    def test_animation_done_shown_from_showing(self):
        from dock.autohide import AutoHideState
        ctrl = self._ctrl()
        ctrl.cursor_left()
        ctrl.timer_tick(1.0)  # → HIDDEN
        ctrl.cursor_entered()  # → SHOWING
        ctrl.animation_done()  # → SHOWN
        assert ctrl.state == AutoHideState.SHOWN

    def test_animation_done_hidden_from_hiding(self):
        from dock.autohide import AutoHideState
        ctrl = self._ctrl()
        ctrl.cursor_left()  # → HIDING
        ctrl.animation_done()  # → HIDDEN
        assert ctrl.state == AutoHideState.HIDDEN

    def test_disabled_cursor_left_has_no_effect(self):
        from dock.autohide import AutoHideState
        ctrl = self._ctrl(enabled=False)
        ctrl.cursor_left()
        assert ctrl.state == AutoHideState.SHOWN

    def test_disable_forces_show(self):
        from dock.autohide import AutoHideState
        shown = []
        ctrl = self._ctrl()
        ctrl.on_show(lambda: shown.append(True))
        ctrl.cursor_left()
        ctrl.timer_tick(1.0)  # → HIDDEN
        ctrl.enabled = False
        assert ctrl.state == AutoHideState.SHOWN
        assert shown

    def test_on_show_callback(self):
        shown = []
        ctrl = self._ctrl()
        ctrl.on_show(lambda: shown.append(1))
        ctrl.cursor_left()
        ctrl.timer_tick(1.0)
        ctrl.cursor_entered()
        assert shown

    def test_on_hide_callback(self):
        hidden = []
        ctrl = self._ctrl(hide_delay=0.1)
        ctrl.on_hide(lambda: hidden.append(1))
        ctrl.cursor_left()
        ctrl.timer_tick(0.2)
        assert hidden


# ── DesktopFileParser ─────────────────────────────────────────────────────────

class TestDesktopFileParser:
    def _write_desktop(self, directory: Path, filename: str, content: str) -> Path:
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        return path

    def _basic_entry(self, name="Test App", exec_str="testapp %u", icon="testapp"):
        return f"""[Desktop Entry]
Type=Application
Name={name}
Exec={exec_str}
Icon={icon}
Categories=Utility;
"""

    def test_load_all_finds_desktop_files(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        self._write_desktop(tmp_path, "test.desktop", self._basic_entry())
        parser = DesktopFileParser(search_dirs=[tmp_path])
        apps = parser.load_all()
        assert "test.desktop" in apps

    def test_parses_name(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        self._write_desktop(tmp_path, "app.desktop", self._basic_entry(name="My App"))
        parser = DesktopFileParser(search_dirs=[tmp_path])
        apps = parser.load_all()
        assert apps["app.desktop"].name == "My App"

    def test_parses_exec(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        self._write_desktop(tmp_path, "app.desktop", self._basic_entry(exec_str="/usr/bin/myapp --flag"))
        apps = DesktopFileParser(search_dirs=[tmp_path]).load_all()
        assert apps["app.desktop"].exec == "/usr/bin/myapp --flag"

    def test_exec_base_strips_path_and_args(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        self._write_desktop(tmp_path, "app.desktop", self._basic_entry(exec_str="/usr/bin/myapp %u"))
        apps = DesktopFileParser(search_dirs=[tmp_path]).load_all()
        assert apps["app.desktop"].exec_base == "myapp"

    def test_parses_icon(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        self._write_desktop(tmp_path, "app.desktop", self._basic_entry(icon="my-icon"))
        apps = DesktopFileParser(search_dirs=[tmp_path]).load_all()
        assert apps["app.desktop"].icon == "my-icon"

    def test_parses_categories(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        content = self._basic_entry() + "Categories=Network;WebBrowser;\n"
        self._write_desktop(tmp_path, "app.desktop", content)
        apps = DesktopFileParser(search_dirs=[tmp_path]).load_all()
        assert "Network" in apps["app.desktop"].categories
        assert "WebBrowser" in apps["app.desktop"].categories

    def test_nodisplay_false_by_default(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        self._write_desktop(tmp_path, "app.desktop", self._basic_entry())
        apps = DesktopFileParser(search_dirs=[tmp_path]).load_all()
        assert apps["app.desktop"].nodisplay is False

    def test_nodisplay_true_when_set(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        content = self._basic_entry() + "NoDisplay=true\n"
        self._write_desktop(tmp_path, "app.desktop", content)
        apps = DesktopFileParser(search_dirs=[tmp_path]).load_all()
        assert apps["app.desktop"].nodisplay is True

    def test_startup_wm_class_parsed(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        content = self._basic_entry() + "StartupWMClass=TestApp\n"
        self._write_desktop(tmp_path, "app.desktop", content)
        apps = DesktopFileParser(search_dirs=[tmp_path]).load_all()
        assert apps["app.desktop"].startup_wm_class == "TestApp"

    def test_skips_non_application_types(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        content = "[Desktop Entry]\nType=Link\nName=Link\nURL=http://example.com\n"
        self._write_desktop(tmp_path, "link.desktop", content)
        apps = DesktopFileParser(search_dirs=[tmp_path]).load_all()
        assert "link.desktop" not in apps

    def test_later_dir_overrides_earlier(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        dir1 = tmp_path / "sys"
        dir2 = tmp_path / "user"
        dir1.mkdir()
        dir2.mkdir()
        self._write_desktop(dir1, "app.desktop", self._basic_entry(name="System App"))
        self._write_desktop(dir2, "app.desktop", self._basic_entry(name="User App"))
        apps = DesktopFileParser(search_dirs=[dir1, dir2]).load_all()
        assert apps["app.desktop"].name == "User App"

    def test_find_by_exact_desktop_id(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        self._write_desktop(tmp_path, "firefox.desktop", self._basic_entry(name="Firefox"))
        parser = DesktopFileParser(search_dirs=[tmp_path])
        parser.load_all()
        result = parser.find("firefox.desktop")
        assert result is not None
        assert result.name == "Firefox"

    def test_find_by_name_prefix(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        self._write_desktop(tmp_path, "firefox.desktop", self._basic_entry(name="Firefox"))
        parser = DesktopFileParser(search_dirs=[tmp_path])
        parser.load_all()
        result = parser.find("fire")
        assert result is not None

    def test_find_returns_none_for_unknown(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        parser = DesktopFileParser(search_dirs=[tmp_path])
        parser.load_all()
        assert parser.find("zzz-not-here") is None

    def test_launch_command_strips_field_codes(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        self._write_desktop(tmp_path, "app.desktop", self._basic_entry(exec_str="myapp %U"))
        apps = DesktopFileParser(search_dirs=[tmp_path]).load_all()
        cmd = apps["app.desktop"].launch_command()
        assert "%U" not in cmd
        assert "myapp" in cmd

    def test_get_by_desktop_id(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        self._write_desktop(tmp_path, "app.desktop", self._basic_entry())
        parser = DesktopFileParser(search_dirs=[tmp_path])
        parser.load_all()
        assert parser.get("app.desktop") is not None
        assert parser.get("missing.desktop") is None

    def test_empty_dir_returns_empty_dict(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        apps = DesktopFileParser(search_dirs=[tmp_path]).load_all()
        assert apps == {}

    def test_corrupted_file_is_skipped(self, tmp_path):
        from dock.desktop_file import DesktopFileParser
        (tmp_path / "bad.desktop").write_bytes(b"\xff\xfe")
        apps = DesktopFileParser(search_dirs=[tmp_path]).load_all()
        # Should not raise; bad file silently skipped
        assert "bad.desktop" not in apps


# ── DockPersistence ────────────────────────────────────────────────────────────

class TestDockPersistence:
    def _db(self, tmp_path) -> "DockPersistence":
        from dock.persistence import DockPersistence
        db = DockPersistence(db_path=tmp_path / "dock.db")
        db.open()
        return db

    def test_opens_and_closes(self, tmp_path):
        db = self._db(tmp_path)
        db.close()

    def test_empty_pinned_apps(self, tmp_path):
        db = self._db(tmp_path)
        assert db.get_pinned_apps() == []
        db.close()

    def test_pin_app(self, tmp_path):
        db = self._db(tmp_path)
        db.pin_app("firefox.desktop", 0)
        assert "firefox.desktop" in db.get_pinned_apps()
        db.close()

    def test_pin_app_position_order(self, tmp_path):
        db = self._db(tmp_path)
        db.pin_app("a.desktop", 0)
        db.pin_app("b.desktop", 1)
        db.pin_app("c.desktop", 2)
        assert db.get_pinned_apps() == ["a.desktop", "b.desktop", "c.desktop"]
        db.close()

    def test_pin_app_inserts_at_position(self, tmp_path):
        db = self._db(tmp_path)
        db.pin_app("a.desktop", 0)
        db.pin_app("c.desktop", 1)
        db.pin_app("b.desktop", 1)  # insert between a and c
        apps = db.get_pinned_apps()
        assert apps.index("b.desktop") < apps.index("c.desktop")
        db.close()

    def test_unpin_app(self, tmp_path):
        db = self._db(tmp_path)
        db.pin_app("firefox.desktop", 0)
        db.unpin_app("firefox.desktop")
        assert "firefox.desktop" not in db.get_pinned_apps()
        db.close()

    def test_unpin_compacts_positions(self, tmp_path):
        db = self._db(tmp_path)
        db.pin_app("a.desktop", 0)
        db.pin_app("b.desktop", 1)
        db.pin_app("c.desktop", 2)
        db.unpin_app("b.desktop")
        apps = db.get_pinned_apps()
        assert apps == ["a.desktop", "c.desktop"]
        db.close()

    def test_unpin_nonexistent_is_noop(self, tmp_path):
        db = self._db(tmp_path)
        db.unpin_app("ghost.desktop")  # should not raise
        db.close()

    def test_move_app(self, tmp_path):
        db = self._db(tmp_path)
        db.pin_app("a.desktop", 0)
        db.pin_app("b.desktop", 1)
        db.pin_app("c.desktop", 2)
        db.move_app("a.desktop", 2)
        apps = db.get_pinned_apps()
        assert apps[2] == "a.desktop"
        db.close()

    def test_is_pinned_true(self, tmp_path):
        db = self._db(tmp_path)
        db.pin_app("app.desktop", 0)
        assert db.is_pinned("app.desktop") is True
        db.close()

    def test_is_pinned_false(self, tmp_path):
        db = self._db(tmp_path)
        assert db.is_pinned("missing.desktop") is False
        db.close()

    def test_pin_append_with_none_position(self, tmp_path):
        db = self._db(tmp_path)
        db.pin_app("a.desktop", 0)
        db.pin_app("b.desktop")  # position=None → append
        apps = db.get_pinned_apps()
        assert apps[-1] == "b.desktop"
        db.close()

    def test_second_open_idempotent_schema(self, tmp_path):
        from dock.persistence import DockPersistence
        db1 = DockPersistence(db_path=tmp_path / "dock.db")
        db1.open()
        db1.pin_app("a.desktop", 0)
        db1.close()

        db2 = DockPersistence(db_path=tmp_path / "dock.db")
        db2.open()
        assert "a.desktop" in db2.get_pinned_apps()
        db2.close()


# ── AppMonitor matching ─────────────────────────────────────────────────────────

class TestAppMonitorMatching:
    def _monitor(self, registry=None):
        from dock.app_monitor import AppMonitor
        return AppMonitor(app_registry=registry or {})

    def _mock_window(self, class_instance="firefox", class_group="Firefox"):
        w = MagicMock()
        w.get_class_instance_name.return_value = class_instance
        w.get_class_group_name.return_value = class_group
        w.get_xid.return_value = 12345
        w.get_window_type.return_value = 0  # NORMAL
        return w

    def _make_info(self, desktop_id, name, exec_str, startup_wm_class=""):
        from dock.desktop_file import AppInfo
        return AppInfo(
            desktop_id=desktop_id,
            name=name,
            exec=exec_str,
            icon="icon",
            categories=[],
            startup_wm_class=startup_wm_class,
            nodisplay=False,
            path=f"/usr/share/applications/{desktop_id}",
        )

    def test_match_by_startup_wm_class(self):
        monitor = self._monitor({
            "firefox.desktop": self._make_info(
                "firefox.desktop", "Firefox", "/usr/bin/firefox",
                startup_wm_class="Firefox",
            )
        })
        window = self._mock_window(class_instance="firefox", class_group="Firefox")
        result = monitor._match_desktop_id(window)
        assert result == "firefox.desktop"

    def test_match_by_exec_base(self):
        monitor = self._monitor({
            "gedit.desktop": self._make_info(
                "gedit.desktop", "Text Editor", "/usr/bin/gedit %f",
            )
        })
        window = self._mock_window(class_instance="gedit", class_group="Gedit")
        result = monitor._match_desktop_id(window)
        assert result == "gedit.desktop"

    def test_no_match_returns_none(self):
        monitor = self._monitor({
            "calc.desktop": self._make_info("calc.desktop", "Calculator", "gnome-calculator"),
        })
        window = self._mock_window(class_instance="xterm", class_group="XTerm")
        result = monitor._match_desktop_id(window)
        assert result is None

    def test_get_running_empty(self):
        monitor = self._monitor()
        assert monitor.get_running_desktop_ids() == set()

    def test_get_window_count_zero_for_unknown(self):
        monitor = self._monitor()
        assert monitor.get_window_count("ghost.desktop") == 0

    def test_on_changed_callback_registered(self):
        monitor = self._monitor()
        called = []
        monitor.on_changed(lambda: called.append(1))
        assert len(monitor._callbacks) == 1


# ── DockDBusServer interface ──────────────────────────────────────────────────

class TestDockInterfaceMethods:
    def _iface(self, tmp_path):
        from dock.persistence import DockPersistence
        from dock.dock_dbus import DockInterface

        db = DockPersistence(db_path=tmp_path / "dock.db")
        db.open()

        show_calls = []
        hide_calls = []
        bounce_calls = []
        config_calls = []

        iface = DockInterface(
            persistence=db,
            show_cb=lambda: show_calls.append(True),
            hide_cb=lambda: hide_calls.append(True),
            bounce_cb=lambda d, t: bounce_calls.append((d, t)),
            config_cb=lambda k, v: config_calls.append((k, v)),
        )

        return iface, db, show_calls, hide_calls, bounce_calls, config_calls

    def test_show_sets_visible(self, tmp_path):
        iface, *_ = self._iface(tmp_path)
        iface._visible = False
        iface.Show()
        assert iface.Visible is True

    def test_hide_sets_invisible(self, tmp_path):
        iface, *_ = self._iface(tmp_path)
        iface.Hide()
        assert iface.Visible is False

    def test_toggle_shows_when_hidden(self, tmp_path):
        iface, *_ = self._iface(tmp_path)
        iface._visible = False
        iface.Toggle()
        assert iface.Visible is True

    def test_toggle_hides_when_shown(self, tmp_path):
        iface, *_ = self._iface(tmp_path)
        iface._visible = True
        iface.Toggle()
        assert iface.Visible is False

    def test_pin_app(self, tmp_path):
        iface, db, *_ = self._iface(tmp_path)
        iface.PinApp("firefox.desktop", 0)
        assert db.is_pinned("firefox.desktop")

    def test_unpin_app(self, tmp_path):
        iface, db, *_ = self._iface(tmp_path)
        iface.PinApp("firefox.desktop", 0)
        iface.UnpinApp("firefox.desktop")
        assert not db.is_pinned("firefox.desktop")

    def test_get_pinned_apps(self, tmp_path):
        iface, db, *_ = self._iface(tmp_path)
        iface.PinApp("a.desktop", 0)
        iface.PinApp("b.desktop", 1)
        apps = iface.GetPinnedApps()
        assert "a.desktop" in apps
        assert "b.desktop" in apps

    def test_set_position_valid(self, tmp_path):
        iface, _, _, _, _, config_calls = self._iface(tmp_path)
        iface.SetPosition("left")
        assert iface.Position == "left"
        assert any("dock.position" in str(c) for c in config_calls)

    def test_set_position_invalid_raises(self, tmp_path):
        iface, *_ = self._iface(tmp_path)
        with pytest.raises(ValueError, match="Invalid position"):
            iface.SetPosition("top")

    def test_set_icon_size_valid(self, tmp_path):
        iface, _, _, _, _, config_calls = self._iface(tmp_path)
        iface.SetIconSize(64)
        assert iface.IconSize == 64

    def test_set_icon_size_out_of_range_raises(self, tmp_path):
        iface, *_ = self._iface(tmp_path)
        with pytest.raises(ValueError, match="Icon size"):
            iface.SetIconSize(8)

    def test_bounce_valid(self, tmp_path):
        iface, _, _, _, bounce_calls, _ = self._iface(tmp_path)
        iface.BounceApp("firefox.desktop", "launch")
        assert ("firefox.desktop", "launch") in bounce_calls

    def test_bounce_invalid_type_raises(self, tmp_path):
        iface, *_ = self._iface(tmp_path)
        with pytest.raises(ValueError, match="Invalid bounce type"):
            iface.BounceApp("app.desktop", "wiggle")

    def test_autohide_property(self, tmp_path):
        iface, *_ = self._iface(tmp_path)
        iface.AutoHide = False
        assert iface.AutoHide is False

    def test_magnification_property(self, tmp_path):
        iface, *_ = self._iface(tmp_path)
        iface.Magnification = False
        assert iface.Magnification is False

    def test_show_calls_callback(self, tmp_path):
        iface, _, show_calls, *_ = self._iface(tmp_path)
        iface._visible = False
        iface.Show()
        assert show_calls

    def test_hide_calls_callback(self, tmp_path):
        iface, _, _, hide_calls, *_ = self._iface(tmp_path)
        iface.Hide()
        assert hide_calls
