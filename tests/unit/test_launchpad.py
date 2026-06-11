"""Unit tests for Phase 6 — MacUX Launchpad.

Coverage:
  - GridCell: linear_index, from_linear, ordering
  - GridLayout: auto_layout, page_count, find_empty, move, compact, filter_to_pages
  - LaunchpadPersistence: CRUD for app positions and folders
  - app_filter: filter_apps()
  - FolderData: dataclass, cell property
  - LaunchpadInterface: Show/Hide/Toggle/ShowOnPage, properties, signals
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# GridCell
# ══════════════════════════════════════════════════════════════════════════════

class TestGridCell:
    def test_linear_index_first_cell(self):
        from launchpad.grid import GridCell
        c = GridCell(page=0, row=0, col=0)
        assert c.linear_index(7, 5) == 0

    def test_linear_index_second_col(self):
        from launchpad.grid import GridCell
        c = GridCell(page=0, row=0, col=1)
        assert c.linear_index(7, 5) == 1

    def test_linear_index_second_row(self):
        from launchpad.grid import GridCell
        c = GridCell(page=0, row=1, col=0)
        assert c.linear_index(7, 5) == 7

    def test_linear_index_second_page(self):
        from launchpad.grid import GridCell
        c = GridCell(page=1, row=0, col=0)
        assert c.linear_index(7, 5) == 35

    def test_from_linear_zero(self):
        from launchpad.grid import GridCell
        c = GridCell.from_linear(0, 7, 5)
        assert c == GridCell(page=0, row=0, col=0)

    def test_from_linear_mid(self):
        from launchpad.grid import GridCell
        c = GridCell.from_linear(8, 7, 5)
        assert c == GridCell(page=0, row=1, col=1)

    def test_from_linear_second_page(self):
        from launchpad.grid import GridCell
        c = GridCell.from_linear(35, 7, 5)
        assert c == GridCell(page=1, row=0, col=0)

    def test_from_linear_round_trip(self):
        from launchpad.grid import GridCell
        original = GridCell(page=2, row=3, col=5)
        idx = original.linear_index(7, 5)
        restored = GridCell.from_linear(idx, 7, 5)
        assert restored == original

    def test_frozen_immutable(self):
        from launchpad.grid import GridCell
        c = GridCell(page=0, row=0, col=0)
        with pytest.raises(Exception):
            c.page = 1  # type: ignore[misc]

    def test_ordering(self):
        from launchpad.grid import GridCell
        cells = [GridCell(page=0, row=1, col=0), GridCell(page=0, row=0, col=0)]
        assert sorted(cells)[0] == GridCell(page=0, row=0, col=0)


# ══════════════════════════════════════════════════════════════════════════════
# GridLayout
# ══════════════════════════════════════════════════════════════════════════════

class TestGridLayout:
    def _layout(self, cols=7, rows=5):
        from launchpad.grid import GridLayout
        return GridLayout(cols=cols, rows=rows)

    def test_auto_layout_empty(self):
        layout = self._layout()
        assert layout.auto_layout([]) == {}

    def test_auto_layout_single(self):
        from launchpad.grid import GridCell
        layout = self._layout()
        result = layout.auto_layout(["firefox"])
        assert result["firefox"] == GridCell(page=0, row=0, col=0)

    def test_auto_layout_fills_first_row(self):
        from launchpad.grid import GridCell
        layout = self._layout(cols=3, rows=2)
        apps = ["a", "b", "c"]
        result = layout.auto_layout(apps)
        assert result["a"] == GridCell(page=0, row=0, col=0)
        assert result["b"] == GridCell(page=0, row=0, col=1)
        assert result["c"] == GridCell(page=0, row=0, col=2)

    def test_auto_layout_wraps_to_next_row(self):
        from launchpad.grid import GridCell
        layout = self._layout(cols=3, rows=2)
        apps = ["a", "b", "c", "d"]
        result = layout.auto_layout(apps)
        assert result["d"] == GridCell(page=0, row=1, col=0)

    def test_auto_layout_wraps_to_next_page(self):
        from launchpad.grid import GridCell
        layout = self._layout(cols=3, rows=2)
        apps = [f"app{i}" for i in range(7)]  # 7 > 3*2=6
        result = layout.auto_layout(apps)
        assert result["app6"] == GridCell(page=1, row=0, col=0)

    def test_page_count_empty(self):
        layout = self._layout()
        assert layout.page_count({}) == 1

    def test_page_count_one_page(self):
        layout = self._layout(cols=3, rows=2)
        apps = layout.auto_layout(["a", "b", "c"])
        assert layout.page_count(apps) == 1

    def test_page_count_two_pages(self):
        layout = self._layout(cols=3, rows=2)
        apps = layout.auto_layout([f"app{i}" for i in range(7)])
        assert layout.page_count(apps) == 2

    def test_apps_on_page(self):
        layout = self._layout(cols=3, rows=2)
        all_apps = layout.auto_layout(["a", "b", "c", "d", "e", "f", "g"])
        page0 = layout.apps_on_page(all_apps, 0)
        assert "a" in page0
        assert "g" not in page0

    def test_find_empty_empty_grid(self):
        from launchpad.grid import GridCell
        layout = self._layout()
        cell = layout.find_empty(set())
        assert cell == GridCell(page=0, row=0, col=0)

    def test_find_empty_first_occupied(self):
        from launchpad.grid import GridCell
        layout = self._layout()
        occ = {(0, 0, 0)}
        cell = layout.find_empty(occ)
        assert cell == GridCell(page=0, row=0, col=1)

    def test_find_empty_page_full(self):
        from launchpad.grid import GridCell
        layout = self._layout(cols=2, rows=2)
        occ = {(0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1)}
        cell = layout.find_empty(occ)
        assert cell == GridCell(page=1, row=0, col=0)

    def test_move_to_empty_cell(self):
        from launchpad.grid import GridCell
        layout = self._layout()
        cells = layout.auto_layout(["a", "b"])
        target = GridCell(page=0, row=2, col=0)
        result = layout.move(cells, "a", target)
        assert result["a"] == target

    def test_move_displaces_occupant(self):
        from launchpad.grid import GridCell
        layout = self._layout(cols=3, rows=2)
        cells = {"a": GridCell(0, 0, 0), "b": GridCell(0, 0, 1)}
        result = layout.move(cells, "a", GridCell(0, 0, 1))
        assert result["a"] == GridCell(0, 0, 1)
        assert result["b"] != GridCell(0, 0, 1)

    def test_compact_removes_gaps(self):
        from launchpad.grid import GridCell
        layout = self._layout(cols=3, rows=2)
        # Leave a gap at position 1 (b removed)
        cells = {"a": GridCell(0, 0, 0), "c": GridCell(0, 0, 2)}
        compacted = layout.compact(cells)
        # After compaction, a→0, c→1
        assert compacted["a"].linear_index(3, 2) == 0
        assert compacted["c"].linear_index(3, 2) == 1

    def test_filter_to_pages(self):
        from launchpad.grid import GridCell
        layout = self._layout(cols=3, rows=2)
        cells = {
            "a": GridCell(0, 0, 0),
            "b": GridCell(0, 0, 1),
            "c": GridCell(0, 0, 2),
        }
        pages = layout.filter_to_pages(cells, {"a", "c"})
        assert len(pages) == 1
        assert "a" in pages[0]
        assert "b" not in pages[0]


# ══════════════════════════════════════════════════════════════════════════════
# FolderData
# ══════════════════════════════════════════════════════════════════════════════

class TestFolderData:
    def test_cell_property(self):
        from launchpad.grid import GridCell
        from launchpad.persistence import FolderData
        f = FolderData(folder_id=1, name="Utilities", page=0, row=1, col=3)
        assert f.cell == GridCell(page=0, row=1, col=3)

    def test_default_members(self):
        from launchpad.persistence import FolderData
        f = FolderData(folder_id=2, name="Games")
        assert f.members == []


# ══════════════════════════════════════════════════════════════════════════════
# LaunchpadPersistence
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db(tmp_path):
    from launchpad.persistence import LaunchpadPersistence
    p = LaunchpadPersistence(db_path=tmp_path / "layout.db")
    p.open()
    yield p
    p.close()


class TestLaunchpadPersistence:
    def test_open_creates_db(self, db, tmp_path):
        assert (tmp_path / "layout.db").exists()

    def test_empty_positions(self, db):
        assert db.get_app_positions() == {}

    def test_set_and_get_position(self, db):
        from launchpad.grid import GridCell
        db.set_app_position("firefox", GridCell(page=0, row=0, col=0))
        positions = db.get_app_positions()
        assert "firefox" in positions
        assert positions["firefox"] == GridCell(page=0, row=0, col=0)

    def test_update_position(self, db):
        from launchpad.grid import GridCell
        db.set_app_position("firefox", GridCell(page=0, row=0, col=0))
        db.set_app_position("firefox", GridCell(page=1, row=2, col=3))
        positions = db.get_app_positions()
        assert positions["firefox"] == GridCell(page=1, row=2, col=3)

    def test_remove_app(self, db):
        from launchpad.grid import GridCell
        db.set_app_position("firefox", GridCell(page=0, row=0, col=0))
        db.remove_app("firefox")
        assert "firefox" not in db.get_app_positions()

    def test_bulk_set(self, db):
        from launchpad.grid import GridCell, GridLayout
        layout = GridLayout(cols=3, rows=2)
        cells = layout.auto_layout(["a", "b", "c", "d"])
        db.set_app_positions_bulk(cells)
        positions = db.get_app_positions()
        assert len(positions) == 4
        assert positions["a"] == GridCell(page=0, row=0, col=0)

    def test_has_any_positions_false_initially(self, db):
        assert not db.has_any_positions()

    def test_has_any_positions_true_after_insert(self, db):
        from launchpad.grid import GridCell
        db.set_app_position("app", GridCell(0, 0, 0))
        assert db.has_any_positions()

    def test_create_folder(self, db):
        folder_id = db.create_folder("Utilities", page=0, row=4, col=6)
        assert isinstance(folder_id, int)
        assert folder_id > 0

    def test_get_folders_empty(self, db):
        assert db.get_folders() == []

    def test_get_folders_returns_folder(self, db):
        db.create_folder("Utilities", page=0, row=0, col=0)
        folders = db.get_folders()
        assert len(folders) == 1
        assert folders[0].name == "Utilities"

    def test_rename_folder(self, db):
        fid = db.create_folder("Old Name", page=0, row=0, col=0)
        db.rename_folder(fid, "New Name")
        folders = db.get_folders()
        assert folders[0].name == "New Name"

    def test_delete_folder(self, db):
        from launchpad.grid import GridCell
        fid = db.create_folder("Temp", page=0, row=0, col=0)
        db.set_app_position("app1", GridCell(0, 1, 0))
        db.add_to_folder(fid, "app1")
        db.delete_folder(fid)
        assert db.get_folders() == []
        # app1 should still exist but without a folder
        positions = db.get_app_positions()
        assert "app1" in positions

    def test_add_to_folder(self, db):
        from launchpad.grid import GridCell
        fid = db.create_folder("Utilities", page=0, row=0, col=0)
        db.set_app_position("calculator", GridCell(0, 0, 1))
        db.add_to_folder(fid, "calculator")
        folders = db.get_folders()
        assert "calculator" in folders[0].members
        # App in folder excluded from get_app_positions
        assert "calculator" not in db.get_app_positions()

    def test_remove_from_folder(self, db):
        from launchpad.grid import GridCell
        fid = db.create_folder("Utilities", page=0, row=0, col=0)
        db.set_app_position("calc", GridCell(0, 0, 1))
        db.add_to_folder(fid, "calc")
        db.remove_from_folder("calc", GridCell(0, 1, 2))
        positions = db.get_app_positions()
        assert "calc" in positions
        assert positions["calc"] == GridCell(0, 1, 2)

    def test_set_folder_position(self, db):
        from launchpad.grid import GridCell
        fid = db.create_folder("Dev", page=0, row=0, col=0)
        db.set_folder_position(fid, GridCell(page=1, row=2, col=3))
        folders = db.get_folders()
        f = folders[0]
        assert f.page == 1
        assert f.row == 2
        assert f.col == 3

    def test_persistence_survives_reopen(self, tmp_path):
        from launchpad.grid import GridCell
        from launchpad.persistence import LaunchpadPersistence
        p = LaunchpadPersistence(db_path=tmp_path / "p.db")
        p.open()
        p.set_app_position("vim", GridCell(0, 3, 5))
        p.close()

        p2 = LaunchpadPersistence(db_path=tmp_path / "p.db")
        p2.open()
        positions = p2.get_app_positions()
        p2.close()
        assert "vim" in positions
        assert positions["vim"] == GridCell(0, 3, 5)


# ══════════════════════════════════════════════════════════════════════════════
# app_filter
# ══════════════════════════════════════════════════════════════════════════════

def _make_info(name, exec_base="", categories=None, nodisplay=False):
    info = MagicMock()
    info.name = name
    info.exec_base = exec_base or name.lower()
    info.categories = categories or []
    info.nodisplay = nodisplay
    return info


class TestAppFilter:
    def test_empty_query_returns_all(self):
        from launchpad.app_filter import filter_apps
        registry = {"a": _make_info("Firefox"), "b": _make_info("Vim")}
        result = filter_apps(registry, "")
        assert "a" in result
        assert "b" in result

    def test_empty_query_excludes_nodisplay(self):
        from launchpad.app_filter import filter_apps
        registry = {"h": _make_info("Hidden", nodisplay=True)}
        result = filter_apps(registry, "")
        assert "h" not in result

    def test_name_contains(self):
        from launchpad.app_filter import filter_apps
        registry = {"ff": _make_info("Firefox")}
        result = filter_apps(registry, "fire")
        assert "ff" in result

    def test_name_case_insensitive(self):
        from launchpad.app_filter import filter_apps
        registry = {"ff": _make_info("Firefox")}
        result = filter_apps(registry, "FIRE")
        assert "ff" in result

    def test_exec_prefix_match(self):
        from launchpad.app_filter import filter_apps
        registry = {"t": _make_info("GNOME Terminal", exec_base="gnome-terminal")}
        result = filter_apps(registry, "gnome")
        assert "t" in result

    def test_category_match(self):
        from launchpad.app_filter import filter_apps
        registry = {"g": _make_info("GIMP", categories=["Graphics", "Raster"])}
        result = filter_apps(registry, "graphics")
        assert "g" in result

    def test_no_match(self):
        from launchpad.app_filter import filter_apps
        registry = {"ff": _make_info("Firefox")}
        result = filter_apps(registry, "zzznomatch")
        assert "ff" not in result

    def test_whitespace_only_query(self):
        from launchpad.app_filter import filter_apps
        registry = {"a": _make_info("App")}
        result = filter_apps(registry, "   ")
        assert "a" in result


# ══════════════════════════════════════════════════════════════════════════════
# LaunchpadInterface (DBus)
# ══════════════════════════════════════════════════════════════════════════════

def _make_iface(show_cb=None, hide_cb=None, page_cb=None):
    from launchpad.launchpad_dbus import LaunchpadInterface
    return LaunchpadInterface(
        show_cb=show_cb or MagicMock(),
        hide_cb=hide_cb or MagicMock(),
        page_cb=page_cb,
    )


class TestLaunchpadInterface:
    def test_visible_false_by_default(self):
        iface = _make_iface()
        assert iface.Visible is False

    def test_current_page_zero_by_default(self):
        iface = _make_iface()
        assert iface.CurrentPage == 0

    def test_show_sets_visible(self):
        show_cb = MagicMock()
        iface = _make_iface(show_cb=show_cb)
        iface.Show()
        assert iface.Visible is True
        show_cb.assert_called_once()

    def test_hide_sets_invisible(self):
        hide_cb = MagicMock()
        iface = _make_iface(hide_cb=hide_cb)
        iface.Show()
        iface.Hide()
        assert iface.Visible is False
        hide_cb.assert_called_once()

    def test_toggle_show(self):
        iface = _make_iface()
        assert not iface.Visible
        iface.Toggle()
        assert iface.Visible

    def test_toggle_hide(self):
        iface = _make_iface()
        iface.Show()
        iface.Toggle()
        assert not iface.Visible

    def test_show_on_page_sets_page(self):
        page_cb = MagicMock()
        iface = _make_iface(page_cb=page_cb)
        iface.ShowOnPage(3)
        assert iface.CurrentPage == 3
        assert iface.Visible is True
        page_cb.assert_called_once_with(3)

    def test_notify_page_changed_updates_current(self):
        iface = _make_iface()
        iface.notify_page_changed(2)
        assert iface.CurrentPage == 2

    def test_show_without_page_cb(self):
        iface = _make_iface()
        iface.ShowOnPage(1)
        assert iface.CurrentPage == 1
