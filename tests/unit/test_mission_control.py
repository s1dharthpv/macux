"""Unit tests for Phase 10 — Mission Control.

Covers:
- Rect properties and geometry helpers
- rows_cols_for_count
- scale_to_fit
- tile_windows (empty, single, multi, bounds, no overlap)
- WindowInfo / WorkspaceInfo
- MissionControlInterface state machine (no DBus signal mocking)
"""

import pytest
from unittest.mock import MagicMock

from mission_control.layout import (
    Rect,
    WindowInfo,
    WorkspaceInfo,
    rows_cols_for_count,
    scale_to_fit,
    tile_windows,
)


# ── Rect — basic properties ────────────────────────────────────────────────────

class TestRectBasicProperties:
    def test_area(self):
        assert Rect(0, 0, 10, 5).area == 50

    def test_area_zero_width(self):
        assert Rect(0, 0, 0, 5).area == 0

    def test_right(self):
        assert Rect(10, 20, 30, 40).right == 40

    def test_bottom(self):
        assert Rect(10, 20, 30, 40).bottom == 60

    def test_center_x(self):
        assert Rect(10, 20, 30, 40).center_x == 25

    def test_center_y(self):
        assert Rect(10, 20, 30, 40).center_y == 40

    def test_frozen(self):
        r = Rect(0, 0, 10, 10)
        with pytest.raises((TypeError, AttributeError)):
            r.x = 5  # type: ignore[misc]


# ── Rect — contains ────────────────────────────────────────────────────────────

class TestRectContains:
    def test_contains_self(self):
        r = Rect(0, 0, 100, 100)
        assert r.contains(r)

    def test_inner_inside_outer(self):
        outer = Rect(0, 0, 100, 100)
        inner = Rect(10, 10, 80, 80)
        assert outer.contains(inner)

    def test_outer_not_inside_inner(self):
        outer = Rect(0, 0, 100, 100)
        inner = Rect(10, 10, 80, 80)
        assert not inner.contains(outer)

    def test_partially_outside(self):
        r = Rect(0, 0, 100, 100)
        overlap = Rect(50, 50, 100, 100)
        assert not r.contains(overlap)

    def test_touching_edge_counts_as_contained(self):
        outer = Rect(0, 0, 100, 100)
        edge = Rect(0, 0, 100, 100)
        assert outer.contains(edge)

    def test_point_rect_inside(self):
        outer = Rect(0, 0, 100, 100)
        point = Rect(50, 50, 0, 0)
        assert outer.contains(point)


# ── Rect — overlaps ────────────────────────────────────────────────────────────

class TestRectOverlaps:
    def test_identical_rects_overlap(self):
        r = Rect(0, 0, 10, 10)
        assert r.overlaps(r)

    def test_adjacent_no_overlap(self):
        a = Rect(0, 0, 10, 10)
        b = Rect(10, 0, 10, 10)
        assert not a.overlaps(b)

    def test_one_pixel_overlap(self):
        a = Rect(0, 0, 11, 10)
        b = Rect(10, 0, 10, 10)
        assert a.overlaps(b)

    def test_completely_separate(self):
        a = Rect(0, 0, 5, 5)
        b = Rect(100, 100, 5, 5)
        assert not a.overlaps(b)

    def test_inner_overlaps_outer(self):
        outer = Rect(0, 0, 100, 100)
        inner = Rect(25, 25, 50, 50)
        assert outer.overlaps(inner)

    def test_above_no_overlap(self):
        a = Rect(0, 0, 10, 10)
        b = Rect(0, 10, 10, 10)
        assert not a.overlaps(b)


# ── rows_cols_for_count ────────────────────────────────────────────────────────

class TestRowsColsForCount:
    def test_zero(self):
        assert rows_cols_for_count(0) == (0, 0)

    def test_one(self):
        assert rows_cols_for_count(1) == (1, 1)

    def test_two(self):
        assert rows_cols_for_count(2) == (1, 2)

    def test_three(self):
        assert rows_cols_for_count(3) == (2, 2)

    def test_four(self):
        assert rows_cols_for_count(4) == (2, 2)

    def test_five(self):
        assert rows_cols_for_count(5) == (2, 3)

    def test_six(self):
        assert rows_cols_for_count(6) == (2, 3)

    def test_nine(self):
        assert rows_cols_for_count(9) == (3, 3)

    def test_ten(self):
        rows, cols = rows_cols_for_count(10)
        assert rows * cols >= 10

    def test_grid_fits_all(self):
        for n in range(1, 25):
            rows, cols = rows_cols_for_count(n)
            assert rows * cols >= n, f"n={n}: {rows}x{cols} doesn't fit"

    def test_cols_gte_rows(self):
        for n in range(1, 25):
            rows, cols = rows_cols_for_count(n)
            assert cols >= rows, f"n={n}: cols={cols} < rows={rows}"


# ── scale_to_fit ───────────────────────────────────────────────────────────────

class TestScaleToFit:
    def test_already_fits_returns_one(self):
        assert scale_to_fit(50, 50, 100, 100) == 1.0

    def test_same_size_returns_one(self):
        assert scale_to_fit(100, 100, 100, 100) == 1.0

    def test_width_limited(self):
        s = scale_to_fit(200, 100, 100, 200)
        assert abs(s - 0.5) < 1e-9

    def test_height_limited(self):
        s = scale_to_fit(100, 200, 200, 100)
        assert abs(s - 0.5) < 1e-9

    def test_never_exceeds_one(self):
        s = scale_to_fit(10, 10, 1000, 1000)
        assert s == 1.0

    def test_zero_src_width_returns_one(self):
        assert scale_to_fit(0, 100, 100, 100) == 1.0

    def test_zero_src_height_returns_one(self):
        assert scale_to_fit(100, 0, 100, 100) == 1.0

    def test_zero_dest_width_returns_one(self):
        assert scale_to_fit(100, 100, 0, 100) == 1.0

    def test_zero_dest_height_returns_one(self):
        assert scale_to_fit(100, 100, 100, 0) == 1.0

    def test_all_zero_returns_one(self):
        assert scale_to_fit(0, 0, 0, 0) == 1.0

    def test_aspect_ratio_preserved(self):
        s = scale_to_fit(400, 200, 200, 200)
        # width is the bottleneck: 400 → 200 = 0.5; that gives height 100 ≤ 200
        assert abs(s - 0.5) < 1e-9


# ── tile_windows ───────────────────────────────────────────────────────────────

def _win(xid: int, minimized: bool = False) -> WindowInfo:
    return WindowInfo(
        xid=xid,
        title=f"Window {xid}",
        app_name="TestApp",
        rect=Rect(0, 0, 1920, 1080),
        workspace_index=0,
        minimized=minimized,
    )


_SCREEN = Rect(0, 0, 1920, 1080)


class TestTileWindows:
    def test_empty_windows_returns_empty(self):
        result = tile_windows([], _SCREEN)
        assert result == {}

    def test_all_minimized_returns_empty(self):
        windows = [_win(1, minimized=True), _win(2, minimized=True)]
        result = tile_windows(windows, _SCREEN)
        assert result == {}

    def test_minimized_excluded(self):
        windows = [_win(1), _win(2, minimized=True), _win(3)]
        result = tile_windows(windows, _SCREEN)
        assert 2 not in result
        assert 1 in result
        assert 3 in result

    def test_single_window_covers_usable_area(self):
        result = tile_windows([_win(1)], _SCREEN, padding=20, bottom_reserve=100)
        assert 1 in result
        tile = result[1]
        assert tile.w > 0 and tile.h > 0

    def test_single_window_tile_within_screen(self):
        result = tile_windows([_win(1)], _SCREEN, padding=20, bottom_reserve=100)
        tile = result[1]
        assert tile.x >= 0
        assert tile.y >= 0
        assert tile.right <= _SCREEN.w
        assert tile.bottom <= _SCREEN.h

    def test_four_windows_all_keyed(self):
        windows = [_win(i) for i in range(1, 5)]
        result = tile_windows(windows, _SCREEN)
        assert set(result.keys()) == {1, 2, 3, 4}

    def test_nine_windows_all_keyed(self):
        windows = [_win(i) for i in range(1, 10)]
        result = tile_windows(windows, _SCREEN)
        assert len(result) == 9

    def test_tiles_have_positive_dimensions(self):
        windows = [_win(i) for i in range(1, 7)]
        result = tile_windows(windows, _SCREEN)
        for tile in result.values():
            assert tile.w > 0 and tile.h > 0

    def test_tiles_within_screen_bounds(self):
        windows = [_win(i) for i in range(1, 10)]
        result = tile_windows(windows, _SCREEN, padding=20, bottom_reserve=100)
        for tile in result.values():
            assert tile.x >= 0
            assert tile.y >= 0
            assert tile.right <= _SCREEN.w
            assert tile.bottom <= _SCREEN.h - 100

    def test_no_overlap_four_windows(self):
        """Adjacent tiles must not overlap."""
        windows = [_win(i) for i in range(1, 5)]
        tiles = list(tile_windows(windows, _SCREEN).values())
        for i, a in enumerate(tiles):
            for j, b in enumerate(tiles):
                if i != j:
                    assert not a.overlaps(b), f"tiles {i} and {j} overlap"

    def test_no_overlap_nine_windows(self):
        windows = [_win(i) for i in range(1, 10)]
        tiles = list(tile_windows(windows, _SCREEN).values())
        for i, a in enumerate(tiles):
            for j, b in enumerate(tiles):
                if i != j:
                    assert not a.overlaps(b)

    def test_custom_padding_respects_bounds(self):
        windows = [_win(1), _win(2)]
        result = tile_windows(windows, _SCREEN, padding=50, bottom_reserve=150)
        for tile in result.values():
            assert tile.x >= 0
            assert tile.y >= 0
            assert tile.right <= _SCREEN.w
            assert tile.bottom <= _SCREEN.h - 150

    def test_xid_mapping_is_correct(self):
        windows = [_win(42), _win(99)]
        result = tile_windows(windows, _SCREEN)
        assert 42 in result
        assert 99 in result

    def test_five_windows_grid_shape(self):
        windows = [_win(i) for i in range(1, 6)]
        result = tile_windows(windows, _SCREEN)
        assert len(result) == 5


# ── WindowInfo ─────────────────────────────────────────────────────────────────

class TestWindowInfo:
    def test_default_not_minimized(self):
        w = WindowInfo(xid=1, title="T", app_name="A",
                       rect=Rect(0, 0, 100, 100), workspace_index=0)
        assert not w.minimized

    def test_minimized_flag(self):
        w = WindowInfo(xid=2, title="T", app_name="A",
                       rect=Rect(0, 0, 100, 100), workspace_index=0,
                       minimized=True)
        assert w.minimized

    def test_fields_stored(self):
        r = Rect(10, 20, 300, 200)
        w = WindowInfo(xid=7, title="My Window", app_name="Foo",
                       rect=r, workspace_index=2)
        assert w.xid == 7
        assert w.title == "My Window"
        assert w.app_name == "Foo"
        assert w.rect == r
        assert w.workspace_index == 2


# ── WorkspaceInfo ──────────────────────────────────────────────────────────────

class TestWorkspaceInfo:
    def _make_ws(self):
        ws = WorkspaceInfo(index=0, name="Desktop 1")
        ws.windows = [
            WindowInfo(xid=1, title="A", app_name="X",
                       rect=Rect(0, 0, 100, 100), workspace_index=0),
            WindowInfo(xid=2, title="B", app_name="Y",
                       rect=Rect(0, 0, 100, 100), workspace_index=0,
                       minimized=True),
            WindowInfo(xid=3, title="C", app_name="Z",
                       rect=Rect(0, 0, 100, 100), workspace_index=0),
        ]
        return ws

    def test_window_count(self):
        ws = self._make_ws()
        assert ws.window_count == 3

    def test_visible_windows_excludes_minimized(self):
        ws = self._make_ws()
        visible = ws.visible_windows
        assert len(visible) == 2
        assert all(not w.minimized for w in visible)

    def test_empty_workspace(self):
        ws = WorkspaceInfo(index=1, name="Empty")
        assert ws.window_count == 0
        assert ws.visible_windows == []

    def test_all_minimized(self):
        ws = WorkspaceInfo(index=0, name="D")
        ws.windows = [
            WindowInfo(xid=i, title="T", app_name="A",
                       rect=Rect(0, 0, 10, 10), workspace_index=0,
                       minimized=True)
            for i in range(3)
        ]
        assert ws.visible_windows == []


# ── MissionControlInterface state machine ─────────────────────────────────────

def _make_mc_iface(
    activate_cb=None,
    deactivate_cb=None,
    window_selected_cb=None,
):
    from mission_control.mission_control_dbus import MissionControlInterface
    return MissionControlInterface(
        activate_cb=activate_cb or MagicMock(),
        deactivate_cb=deactivate_cb or MagicMock(),
        window_selected_cb=window_selected_cb or MagicMock(),
    )


class TestMissionControlInterface:
    def test_initial_inactive(self):
        iface = _make_mc_iface()
        assert iface._active is False

    def test_activate_sets_active(self):
        iface = _make_mc_iface()
        iface.Activate()
        assert iface._active is True

    def test_activate_calls_callback(self):
        cb = MagicMock()
        iface = _make_mc_iface(activate_cb=cb)
        iface.Activate()
        cb.assert_called_once()

    def test_activate_idempotent(self):
        cb = MagicMock()
        iface = _make_mc_iface(activate_cb=cb)
        iface.Activate()
        iface.Activate()
        cb.assert_called_once()  # second call is a no-op

    def test_deactivate_clears_active(self):
        iface = _make_mc_iface()
        iface.Activate()
        iface.Deactivate()
        assert iface._active is False

    def test_deactivate_calls_callback(self):
        cb = MagicMock()
        iface = _make_mc_iface(deactivate_cb=cb)
        iface.Activate()
        iface.Deactivate()
        cb.assert_called_once()

    def test_deactivate_when_inactive_is_noop(self):
        cb = MagicMock()
        iface = _make_mc_iface(deactivate_cb=cb)
        iface.Deactivate()
        cb.assert_not_called()

    def test_toggle_activates_when_inactive(self):
        iface = _make_mc_iface()
        iface.Toggle()
        assert iface._active is True

    def test_toggle_deactivates_when_active(self):
        iface = _make_mc_iface()
        iface.Activate()
        iface.Toggle()
        assert iface._active is False

    def test_toggle_twice_returns_to_original(self):
        iface = _make_mc_iface()
        iface.Toggle()
        iface.Toggle()
        assert iface._active is False

    def test_active_property_reflects_state(self):
        iface = _make_mc_iface()
        assert not iface.Active
        iface.Activate()
        assert iface.Active

    def test_notify_activated_sets_active(self):
        iface = _make_mc_iface()
        iface.notify_activated()
        assert iface._active is True

    def test_notify_deactivated_clears_active(self):
        iface = _make_mc_iface()
        iface.notify_activated()
        iface.notify_deactivated()
        assert iface._active is False

    def test_notify_window_selected_calls_callback(self):
        cb = MagicMock()
        iface = _make_mc_iface(window_selected_cb=cb)
        iface.notify_window_selected(12345)
        cb.assert_called_once_with(12345)

    def test_notify_window_selected_zero_xid(self):
        cb = MagicMock()
        iface = _make_mc_iface(window_selected_cb=cb)
        iface.notify_window_selected(0)
        cb.assert_called_once_with(0)

    def test_activate_without_callbacks_no_exception(self):
        from mission_control.mission_control_dbus import MissionControlInterface
        iface = MissionControlInterface()
        iface.Activate()  # must not raise
        assert iface._active is True

    def test_deactivate_without_callbacks_no_exception(self):
        from mission_control.mission_control_dbus import MissionControlInterface
        iface = MissionControlInterface()
        iface.Activate()
        iface.Deactivate()  # must not raise
        assert iface._active is False

    def test_window_selected_without_callback_no_exception(self):
        from mission_control.mission_control_dbus import MissionControlInterface
        iface = MissionControlInterface()
        iface.notify_window_selected(999)  # must not raise

    def test_activate_callback_exception_does_not_crash(self):
        cb = MagicMock(side_effect=RuntimeError("boom"))
        iface = _make_mc_iface(activate_cb=cb)
        iface.Activate()  # must not propagate
        assert iface._active is True

    def test_deactivate_callback_exception_does_not_crash(self):
        cb = MagicMock(side_effect=ValueError("oops"))
        iface = _make_mc_iface(deactivate_cb=cb)
        iface.Activate()
        iface.Deactivate()  # must not propagate
        assert iface._active is False

    def test_window_selected_callback_exception_does_not_crash(self):
        cb = MagicMock(side_effect=OSError("fail"))
        iface = _make_mc_iface(window_selected_cb=cb)
        iface.notify_window_selected(7)  # must not propagate

    def test_full_lifecycle(self):
        act = MagicMock()
        deact = MagicMock()
        sel = MagicMock()
        iface = _make_mc_iface(activate_cb=act, deactivate_cb=deact,
                               window_selected_cb=sel)

        assert not iface._active
        iface.Activate()
        assert iface._active
        iface.notify_window_selected(42)
        iface.Deactivate()
        assert not iface._active

        act.assert_called_once()
        deact.assert_called_once()
        sel.assert_called_once_with(42)
