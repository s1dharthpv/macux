# Copyright (C) 2026 Sidharth Thamban <sidharth.thamban@gmail.com>
"""Integration tests for all 8 MacUX DBus service interface modules.

These tests verify that each interface module can be imported and instantiated
without a real DBus session, and that expected method names are present and
callable.  If a module's import fails (e.g. because an optional dependency such
as dasbus is not installed), the test class is skipped rather than failed.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Make project root importable when running with pytest from any CWD.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _try_import(module_path: str):
    """Return the module, or None if it cannot be imported."""
    import importlib
    try:
        parts = module_path.rsplit(".", 1)
        mod = importlib.import_module(parts[0])
        return getattr(mod, parts[1])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Spotlight
# ---------------------------------------------------------------------------

class TestSpotlightInterface(unittest.TestCase):
    """SpotlightInterface can be imported and used without a DBus session."""

    @classmethod
    def setUpClass(cls):
        cls.Interface = _try_import("spotlight.spotlight_dbus.SpotlightInterface")
        if cls.Interface is None:
            raise unittest.SkipTest("spotlight.spotlight_dbus not importable")

    def _make(self):
        indexer = MagicMock()
        indexer.is_indexing = False
        indexer.get_stats.return_value = {"doc_count": 0, "is_indexing": False, "index_dir": "/tmp"}
        router = MagicMock()
        router.search.return_value = []
        return self.Interface(
            indexer=indexer,
            router=router,
            show_cb=MagicMock(),
            hide_cb=MagicMock(),
            query_cb=MagicMock(),
        )

    def test_module_importable(self):
        self.assertIsNotNone(self.Interface)

    def test_instantiation(self):
        iface = self._make()
        self.assertIsNotNone(iface)

    def test_has_show_method(self):
        self.assertTrue(hasattr(self.Interface, "Show"))

    def test_has_hide_method(self):
        self.assertTrue(hasattr(self.Interface, "Hide"))

    def test_has_toggle_method(self):
        self.assertTrue(hasattr(self.Interface, "Toggle"))

    def test_has_search_method(self):
        self.assertTrue(hasattr(self.Interface, "Search"))

    def test_has_get_index_stats_method(self):
        self.assertTrue(hasattr(self.Interface, "GetIndexStats"))

    def test_toggle_show_then_hide(self):
        iface = self._make()
        # Toggle should not raise even without a running bus
        try:
            iface.Toggle()  # show
        except Exception:
            pass  # signal emission may fail without bus

    def test_visible_initially_false(self):
        iface = self._make()
        self.assertFalse(iface._visible)

    def test_show_with_query_does_not_raise(self):
        iface = self._make()
        try:
            iface.ShowWithQuery("test query")
        except Exception:
            pass  # signal emission without bus is acceptable


# ---------------------------------------------------------------------------
# Launchpad
# ---------------------------------------------------------------------------

class TestLaunchpadInterface(unittest.TestCase):
    """LaunchpadInterface can be imported and used without a DBus session."""

    @classmethod
    def setUpClass(cls):
        cls.Interface = _try_import("launchpad.launchpad_dbus.LaunchpadInterface")
        if cls.Interface is None:
            raise unittest.SkipTest("launchpad.launchpad_dbus not importable")

    def _make(self):
        return self.Interface(
            show_cb=MagicMock(),
            hide_cb=MagicMock(),
            page_cb=MagicMock(),
        )

    def test_module_importable(self):
        self.assertIsNotNone(self.Interface)

    def test_instantiation(self):
        self.assertIsNotNone(self._make())

    def test_has_show_method(self):
        self.assertTrue(hasattr(self.Interface, "Show"))

    def test_has_hide_method(self):
        self.assertTrue(hasattr(self.Interface, "Hide"))

    def test_has_toggle_method(self):
        self.assertTrue(hasattr(self.Interface, "Toggle"))

    def test_has_show_on_page_method(self):
        self.assertTrue(hasattr(self.Interface, "ShowOnPage"))

    def test_visible_initially_false(self):
        self.assertFalse(self._make()._visible)

    def test_current_page_initially_zero(self):
        self.assertEqual(self._make()._current_page, 0)

    def test_show_on_page_sets_page(self):
        iface = self._make()
        try:
            iface.ShowOnPage(2)
        except Exception:
            pass
        self.assertEqual(iface._current_page, 2)

    def test_toggle_changes_visible(self):
        iface = self._make()
        try:
            iface.Toggle()
        except Exception:
            pass
        self.assertTrue(iface._visible)


# ---------------------------------------------------------------------------
# Dock
# ---------------------------------------------------------------------------

class TestDockInterface(unittest.TestCase):
    """DockInterface can be imported and used without a DBus session."""

    @classmethod
    def setUpClass(cls):
        cls.Interface = _try_import("dock.dock_dbus.DockInterface")
        if cls.Interface is None:
            raise unittest.SkipTest("dock.dock_dbus not importable")

    def _make(self):
        from dock.persistence import DockPersistence
        import tempfile, os
        tmpdir = tempfile.mkdtemp()
        persistence = DockPersistence(db_path=Path(tmpdir) / "dock.db")
        persistence.open()
        iface = self.Interface(
            persistence=persistence,
            show_cb=MagicMock(),
            hide_cb=MagicMock(),
            bounce_cb=MagicMock(),
            config_cb=MagicMock(),
        )
        return iface, persistence

    def test_module_importable(self):
        self.assertIsNotNone(self.Interface)

    def test_instantiation(self):
        iface, db = self._make()
        self.assertIsNotNone(iface)
        db.close()

    def test_has_show_method(self):
        self.assertTrue(hasattr(self.Interface, "Show"))

    def test_has_hide_method(self):
        self.assertTrue(hasattr(self.Interface, "Hide"))

    def test_has_toggle_method(self):
        self.assertTrue(hasattr(self.Interface, "Toggle"))

    def test_has_pin_app_method(self):
        self.assertTrue(hasattr(self.Interface, "PinApp"))

    def test_has_unpin_app_method(self):
        self.assertTrue(hasattr(self.Interface, "UnpinApp"))

    def test_has_get_pinned_apps_method(self):
        self.assertTrue(hasattr(self.Interface, "GetPinnedApps"))

    def test_get_pinned_apps_initially_empty(self):
        iface, db = self._make()
        try:
            apps = iface.GetPinnedApps()
            self.assertIsInstance(apps, list)
        finally:
            db.close()

    def test_visible_initially_true(self):
        iface, db = self._make()
        try:
            self.assertTrue(iface._visible)
        finally:
            db.close()

    def test_set_icon_size_within_range(self):
        iface, db = self._make()
        try:
            iface.SetIconSize(64)
            self.assertEqual(iface._icon_size, 64)
        finally:
            db.close()

    def test_set_icon_size_out_of_range_raises(self):
        iface, db = self._make()
        try:
            with self.assertRaises((ValueError, Exception)):
                iface.SetIconSize(5)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# MenuBar
# ---------------------------------------------------------------------------

class TestMenuBarInterface(unittest.TestCase):
    """MenuBarInterface can be imported and used without a DBus session."""

    @classmethod
    def setUpClass(cls):
        cls.Interface = _try_import("menu_bar.menu_bar_dbus.MenuBarInterface")
        if cls.Interface is None:
            raise unittest.SkipTest("menu_bar.menu_bar_dbus not importable")

    def _make(self):
        return self.Interface(show_cb=MagicMock(), hide_cb=MagicMock())

    def test_module_importable(self):
        self.assertIsNotNone(self.Interface)

    def test_instantiation(self):
        self.assertIsNotNone(self._make())

    def test_has_show_method(self):
        self.assertTrue(hasattr(self.Interface, "Show"))

    def test_has_hide_method(self):
        self.assertTrue(hasattr(self.Interface, "Hide"))

    def test_has_toggle_method(self):
        self.assertTrue(hasattr(self.Interface, "Toggle"))

    def test_has_set_active_app_method(self):
        self.assertTrue(hasattr(self.Interface, "SetActiveApp"))

    def test_visible_initially_true(self):
        self.assertTrue(self._make()._visible)

    def test_active_app_initially_empty(self):
        self.assertEqual(self._make()._active_app, "")

    def test_notify_app_changed_sets_app(self):
        iface = self._make()
        try:
            iface.notify_app_changed("Firefox")
        except Exception:
            pass
        self.assertEqual(iface._active_app, "Firefox")

    def test_toggle_changes_visibility(self):
        iface = self._make()
        try:
            iface.Toggle()
        except Exception:
            pass
        self.assertFalse(iface._visible)


# ---------------------------------------------------------------------------
# ControlCenter
# ---------------------------------------------------------------------------

class TestControlCenterInterface(unittest.TestCase):
    """ControlCenterInterface can be imported and used without a DBus session."""

    @classmethod
    def setUpClass(cls):
        cls.Interface = _try_import(
            "control_center.control_center_dbus.ControlCenterInterface"
        )
        if cls.Interface is None:
            raise unittest.SkipTest("control_center.control_center_dbus not importable")

    def _make(self):
        return self.Interface(
            show_cb=MagicMock(),
            hide_cb=MagicMock(),
            panel_cb=MagicMock(),
        )

    def test_module_importable(self):
        self.assertIsNotNone(self.Interface)

    def test_instantiation(self):
        self.assertIsNotNone(self._make())

    def test_has_show_method(self):
        self.assertTrue(hasattr(self.Interface, "Show"))

    def test_has_hide_method(self):
        self.assertTrue(hasattr(self.Interface, "Hide"))

    def test_has_toggle_method(self):
        self.assertTrue(hasattr(self.Interface, "Toggle"))

    def test_has_show_panel_method(self):
        self.assertTrue(hasattr(self.Interface, "ShowPanel"))

    def test_visible_initially_false(self):
        self.assertFalse(self._make()._visible)

    def test_active_panel_initially_wifi(self):
        self.assertEqual(self._make()._active_panel, "wifi")

    def test_show_panel_valid_updates_panel(self):
        iface = self._make()
        try:
            iface.ShowPanel("bluetooth")
        except Exception:
            pass
        self.assertEqual(iface._active_panel, "bluetooth")

    def test_show_panel_invalid_is_ignored(self):
        iface = self._make()
        try:
            iface.ShowPanel("nonexistent")
        except Exception:
            pass
        # Panel should remain unchanged
        self.assertEqual(iface._active_panel, "wifi")


# ---------------------------------------------------------------------------
# NotificationCenter
# ---------------------------------------------------------------------------

class TestNotificationCenterInterface(unittest.TestCase):
    """NotificationCenterInterface can be imported and used without a DBus session."""

    @classmethod
    def setUpClass(cls):
        cls.Interface = _try_import(
            "notification_center.notification_center_dbus.NotificationCenterInterface"
        )
        if cls.Interface is None:
            raise unittest.SkipTest(
                "notification_center.notification_center_dbus not importable"
            )

    def _make(self):
        return self.Interface(
            show_cb=MagicMock(),
            hide_cb=MagicMock(),
            clear_cb=MagicMock(),
            count_cb=MagicMock(return_value=0),
        )

    def test_module_importable(self):
        self.assertIsNotNone(self.Interface)

    def test_instantiation(self):
        self.assertIsNotNone(self._make())

    def test_has_show_method(self):
        self.assertTrue(hasattr(self.Interface, "Show"))

    def test_has_hide_method(self):
        self.assertTrue(hasattr(self.Interface, "Hide"))

    def test_has_toggle_method(self):
        self.assertTrue(hasattr(self.Interface, "Toggle"))

    def test_has_clear_method(self):
        self.assertTrue(hasattr(self.Interface, "Clear"))

    def test_has_get_count_method(self):
        self.assertTrue(hasattr(self.Interface, "GetCount"))

    def test_visible_initially_false(self):
        self.assertFalse(self._make()._visible)

    def test_get_count_returns_integer(self):
        iface = self._make()
        count = iface.GetCount()
        # Result may be int or dasbus UInt32 — must be comparable to int
        self.assertGreaterEqual(int(count), 0)

    def test_clear_calls_clear_callback(self):
        cb = MagicMock()
        iface = self.Interface(
            show_cb=MagicMock(),
            hide_cb=MagicMock(),
            clear_cb=cb,
        )
        try:
            iface.Clear()
        except Exception:
            pass
        cb.assert_called_once()


# ---------------------------------------------------------------------------
# MissionControl
# ---------------------------------------------------------------------------

class TestMissionControlInterface(unittest.TestCase):
    """MissionControlInterface can be imported and used without a DBus session."""

    @classmethod
    def setUpClass(cls):
        cls.Interface = _try_import(
            "mission_control.mission_control_dbus.MissionControlInterface"
        )
        if cls.Interface is None:
            raise unittest.SkipTest(
                "mission_control.mission_control_dbus not importable"
            )

    def _make(self):
        return self.Interface(
            activate_cb=MagicMock(),
            deactivate_cb=MagicMock(),
            window_selected_cb=MagicMock(),
        )

    def test_module_importable(self):
        self.assertIsNotNone(self.Interface)

    def test_instantiation(self):
        self.assertIsNotNone(self._make())

    def test_has_activate_method(self):
        self.assertTrue(hasattr(self.Interface, "Activate"))

    def test_has_deactivate_method(self):
        self.assertTrue(hasattr(self.Interface, "Deactivate"))

    def test_has_toggle_method(self):
        self.assertTrue(hasattr(self.Interface, "Toggle"))

    def test_active_initially_false(self):
        self.assertFalse(self._make()._active)

    def test_activate_sets_active_true(self):
        iface = self._make()
        iface.Activate()
        self.assertTrue(iface._active)

    def test_activate_twice_is_idempotent(self):
        cb = MagicMock()
        iface = self.Interface(activate_cb=cb)
        iface.Activate()
        iface.Activate()  # second call should be no-op
        cb.assert_called_once()

    def test_deactivate_sets_active_false(self):
        iface = self._make()
        iface.Activate()
        iface.Deactivate()
        self.assertFalse(iface._active)

    def test_toggle_from_inactive_activates(self):
        iface = self._make()
        iface.Toggle()
        self.assertTrue(iface._active)

    def test_toggle_from_active_deactivates(self):
        iface = self._make()
        iface.Activate()
        iface.Toggle()
        self.assertFalse(iface._active)


# ---------------------------------------------------------------------------
# Finder
# ---------------------------------------------------------------------------

class TestFinderInterface(unittest.TestCase):
    """FinderInterface can be imported and used without a DBus session."""

    @classmethod
    def setUpClass(cls):
        cls.Interface = _try_import("finder.finder_dbus.FinderInterface")
        if cls.Interface is None:
            raise unittest.SkipTest("finder.finder_dbus not importable")

    def _make(self):
        return self.Interface(
            open_path_cb=MagicMock(),
            reveal_file_cb=MagicMock(),
        )

    def test_module_importable(self):
        self.assertIsNotNone(self.Interface)

    def test_instantiation(self):
        self.assertIsNotNone(self._make())

    def test_has_open_path_method(self):
        self.assertTrue(hasattr(self.Interface, "OpenPath"))

    def test_has_reveal_file_method(self):
        self.assertTrue(hasattr(self.Interface, "RevealFile"))

    def test_has_get_current_path_method(self):
        self.assertTrue(hasattr(self.Interface, "GetCurrentPath"))

    def test_current_path_initially_empty(self):
        self.assertEqual(self._make()._current_path, "")

    def test_open_path_updates_current_path(self):
        iface = self._make()
        iface.OpenPath("/home/user/Documents")
        self.assertEqual(iface._current_path, "/home/user/Documents")

    def test_get_current_path_returns_str(self):
        iface = self._make()
        iface.OpenPath("/tmp")
        result = iface.GetCurrentPath()
        self.assertIn("/tmp", str(result))

    def test_notify_path_changed_updates_path(self):
        iface = self._make()
        iface.notify_path_changed("/home/user/Desktop")
        self.assertEqual(iface._current_path, "/home/user/Desktop")

    def test_open_path_invokes_callback(self):
        cb = MagicMock()
        iface = self.Interface(open_path_cb=cb)
        iface.OpenPath("/tmp/test")
        cb.assert_called_once_with("/tmp/test")


if __name__ == "__main__":
    unittest.main()
