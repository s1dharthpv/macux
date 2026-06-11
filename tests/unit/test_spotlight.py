"""Unit tests for Phase 5 — MacUX Spotlight Search.

Coverage:
  - calculator: is_arithmetic, evaluate, edge cases, security
  - result: SearchResult dataclass, serialisation
  - query_router: routing, app scoring, calculator, files, web
  - indexer: open/close, _make_doc, search, update/delete, stats
  - spotlight_dbus: SpotlightInterface methods and properties
"""

from __future__ import annotations

import math
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# Calculator
# ══════════════════════════════════════════════════════════════════════════════

class TestIsArithmetic:
    def test_simple_addition(self):
        from spotlight.calculator import is_arithmetic
        assert is_arithmetic("2 + 3")

    def test_simple_subtraction(self):
        from spotlight.calculator import is_arithmetic
        assert is_arithmetic("10 - 4")

    def test_multiplication(self):
        from spotlight.calculator import is_arithmetic
        assert is_arithmetic("6 * 7")

    def test_division(self):
        from spotlight.calculator import is_arithmetic
        assert is_arithmetic("10 / 2")

    def test_power_caret(self):
        from spotlight.calculator import is_arithmetic
        assert is_arithmetic("2^8")

    def test_sqrt_function(self):
        from spotlight.calculator import is_arithmetic
        assert is_arithmetic("sqrt(16)")

    def test_trig_function(self):
        from spotlight.calculator import is_arithmetic
        assert is_arithmetic("sin(30)")

    def test_plain_text(self):
        from spotlight.calculator import is_arithmetic
        assert not is_arithmetic("hello world")

    def test_empty_string(self):
        from spotlight.calculator import is_arithmetic
        assert not is_arithmetic("")

    def test_mixed_text(self):
        from spotlight.calculator import is_arithmetic
        assert not is_arithmetic("open terminal")

    def test_parentheses_expression(self):
        from spotlight.calculator import is_arithmetic
        assert is_arithmetic("(3 + 5) * 2")


class TestEvaluate:
    def test_addition(self):
        from spotlight.calculator import evaluate
        assert evaluate("2 + 3") == "5"

    def test_subtraction(self):
        from spotlight.calculator import evaluate
        assert evaluate("10 - 4") == "6"

    def test_multiplication(self):
        from spotlight.calculator import evaluate
        assert evaluate("6 * 7") == "42"

    def test_division(self):
        from spotlight.calculator import evaluate
        result = evaluate("10 / 4")
        assert result == "2.5"

    def test_floor_division(self):
        from spotlight.calculator import evaluate
        assert evaluate("10 // 3") == "3"

    def test_modulo(self):
        from spotlight.calculator import evaluate
        assert evaluate("17 % 5") == "2"

    def test_power_caret(self):
        from spotlight.calculator import evaluate
        assert evaluate("2^8") == "256"

    def test_power_double_star(self):
        from spotlight.calculator import evaluate
        result = evaluate("2**10")
        # Thousands separator may be narrow no-break space (U+202F) or ASCII space
        assert result.replace(" ", "").replace(" ", "") == "1024"

    def test_sqrt(self):
        from spotlight.calculator import evaluate
        result = evaluate("sqrt(16)")
        assert result == "4"

    def test_pi_constant(self):
        from spotlight.calculator import evaluate
        result = evaluate("pi")
        assert result.startswith("3.14159")

    def test_nested_expression(self):
        from spotlight.calculator import evaluate
        assert evaluate("(3 + 5) * 2") == "16"

    def test_unary_minus(self):
        from spotlight.calculator import evaluate
        assert evaluate("-5") == "-5"

    def test_factorial(self):
        from spotlight.calculator import evaluate
        assert evaluate("factorial(5)") == "120"

    def test_abs(self):
        from spotlight.calculator import evaluate
        assert evaluate("abs(-42)") == "42"

    def test_division_by_zero(self):
        from spotlight.calculator import evaluate, CalculatorError
        with pytest.raises(CalculatorError, match="zero"):
            evaluate("1 / 0")

    def test_unsafe_import(self):
        from spotlight.calculator import evaluate, CalculatorError
        with pytest.raises(CalculatorError):
            evaluate("__import__('os').system('ls')")

    def test_unsafe_attribute(self):
        from spotlight.calculator import evaluate, CalculatorError
        with pytest.raises(CalculatorError):
            evaluate("().__class__")

    def test_unknown_name(self):
        from spotlight.calculator import evaluate, CalculatorError
        with pytest.raises(CalculatorError, match="Unknown name"):
            evaluate("foo")

    def test_sin_degrees(self):
        from spotlight.calculator import evaluate
        result = evaluate("sin(90)")
        assert result == "1"

    def test_cos_degrees(self):
        from spotlight.calculator import evaluate
        result = evaluate("cos(0)")
        assert result == "1"

    def test_log_base10(self):
        from spotlight.calculator import evaluate
        result = evaluate("log(100)")
        assert result == "2"

    def test_format_large_int(self):
        from spotlight.calculator import evaluate
        result = evaluate("1000000")
        assert " " in result or " " in result  # thousands separator (U+202F or ASCII)

    def test_infinity(self):
        from spotlight.calculator import evaluate
        result = evaluate("inf")
        assert "∞" in result

    def test_syntax_error(self):
        from spotlight.calculator import evaluate, CalculatorError
        with pytest.raises(CalculatorError):
            evaluate("2 + + +")


# ══════════════════════════════════════════════════════════════════════════════
# SearchResult
# ══════════════════════════════════════════════════════════════════════════════

class TestSearchResult:
    def test_defaults(self):
        from spotlight.result import SearchResult, CAT_FILES, ACTION_OPEN
        r = SearchResult(category=CAT_FILES, name="test.txt")
        assert r.score == 0.5
        assert r.action == ACTION_OPEN
        assert r.metadata == {}

    def test_to_dbus_dict(self):
        from spotlight.result import SearchResult, CAT_APPS, ACTION_LAUNCH
        r = SearchResult(
            category=CAT_APPS,
            name="Firefox",
            path="/usr/share/applications/firefox.desktop",
            icon="firefox",
            score=0.9,
            subtitle="Web Browser",
            action=ACTION_LAUNCH,
        )
        d = r.to_dbus_dict()
        assert d["name"] == "Firefox"
        assert d["type"] == CAT_APPS
        assert d["action"] == ACTION_LAUNCH
        assert isinstance(d["score"], float)

    def test_from_dbus_dict_round_trip(self):
        from spotlight.result import SearchResult, CAT_CALCULATOR, ACTION_COPY
        original = SearchResult(
            category=CAT_CALCULATOR,
            name="42",
            subtitle="6 * 7",
            action=ACTION_COPY,
            score=1.0,
        )
        restored = SearchResult.from_dbus_dict(original.to_dbus_dict())
        assert restored.name == original.name
        assert restored.category == original.category
        assert restored.action == original.action

    def test_from_dbus_dict_missing_fields(self):
        from spotlight.result import SearchResult, CAT_FILES, ACTION_OPEN
        r = SearchResult.from_dbus_dict({})
        assert r.category == CAT_FILES
        assert r.action == ACTION_OPEN


# ══════════════════════════════════════════════════════════════════════════════
# QueryRouter
# ══════════════════════════════════════════════════════════════════════════════

def _make_app_info(
    name: str,
    exec_base: str = "",
    icon: str = "application",
    comment: str = "",
    categories: list | None = None,
    nodisplay: bool = False,
    path: str = "/usr/share/applications/app.desktop",
) -> MagicMock:
    info = MagicMock()
    info.name = name
    info.exec_base = exec_base or name.lower().replace(" ", "")
    info.icon = icon
    info.comment = comment
    info.categories = categories or []
    info.nodisplay = nodisplay
    info.path = path
    return info


class TestQueryRouterAppSearch:
    def test_exact_name_match(self):
        from spotlight.query_router import QueryRouter
        registry = {"firefox": _make_app_info("Firefox", exec_base="firefox")}
        router = QueryRouter(app_registry=registry)
        results = router.search("Firefox")
        assert any(r.name == "Firefox" for r in results)

    def test_prefix_match(self):
        from spotlight.query_router import QueryRouter
        registry = {"terminal": _make_app_info("GNOME Terminal", exec_base="gnome-terminal")}
        router = QueryRouter(app_registry=registry)
        results = router.search("gnome", categories=["apps"])
        assert len(results) > 0

    def test_nodisplay_skipped(self):
        from spotlight.query_router import QueryRouter
        registry = {"hidden": _make_app_info("Hidden App", nodisplay=True)}
        router = QueryRouter(app_registry=registry)
        results = router.search("Hidden", categories=["apps"])
        assert all(r.name != "Hidden App" for r in results)

    def test_empty_query_returns_empty(self):
        from spotlight.query_router import QueryRouter
        registry = {"firefox": _make_app_info("Firefox")}
        router = QueryRouter(app_registry=registry)
        assert router.search("") == []
        assert router.search("   ") == []

    def test_max_results_respected(self):
        from spotlight.query_router import QueryRouter
        registry = {f"app{i}": _make_app_info(f"app{i}") for i in range(20)}
        router = QueryRouter(app_registry=registry, search_web=False)
        results = router.search("app", max_results=5)
        assert len(results) <= 5

    def test_set_registry(self):
        from spotlight.query_router import QueryRouter
        router = QueryRouter()
        router.set_registry({"vim": _make_app_info("Vim")})
        results = router.search("Vim", categories=["apps"])
        assert any(r.name == "Vim" for r in results)


class TestQueryRouterScoring:
    def test_exact_name_score_1(self):
        from spotlight.query_router import QueryRouter
        info = _make_app_info("Terminal")
        score = QueryRouter._score_app("terminal", info)
        assert score == 1.0

    def test_exact_exec_score_0_95(self):
        from spotlight.query_router import QueryRouter
        info = _make_app_info("GNOME Terminal", exec_base="terminal")
        score = QueryRouter._score_app("terminal", info)
        assert score == 0.95

    def test_starts_with_score(self):
        from spotlight.query_router import QueryRouter
        info = _make_app_info("Firefox")
        score = QueryRouter._score_app("fire", info)
        assert 0.85 <= score <= 0.90

    def test_contains_score(self):
        from spotlight.query_router import QueryRouter
        info = _make_app_info("Firefox Browser")
        score = QueryRouter._score_app("fox", info)
        assert score == 0.70

    def test_no_match_score_0(self):
        from spotlight.query_router import QueryRouter
        info = _make_app_info("Firefox")
        score = QueryRouter._score_app("terminal", info)
        assert score == 0.0

    def test_empty_query_score_0(self):
        from spotlight.query_router import QueryRouter
        info = _make_app_info("Firefox")
        assert QueryRouter._score_app("", info) == 0.0


class TestQueryRouterCalculator:
    def test_calculator_result_for_expression(self):
        from spotlight.query_router import QueryRouter
        router = QueryRouter(search_web=False)
        results = router.search("2 + 2", categories=["calculator"])
        assert len(results) == 1
        assert results[0].name == "4"

    def test_calculator_not_shown_for_text(self):
        from spotlight.query_router import QueryRouter
        router = QueryRouter(search_web=False)
        results = router.search("hello world", categories=["calculator"])
        assert len(results) == 0

    def test_calculator_first_in_mixed_results(self):
        from spotlight.query_router import QueryRouter
        from spotlight.result import CAT_CALCULATOR
        registry = {"calc": _make_app_info("Calculator", exec_base="gnome-calculator")}
        router = QueryRouter(app_registry=registry, search_web=False)
        results = router.search("sqrt(16)")
        if results:
            assert results[0].category == CAT_CALCULATOR


class TestQueryRouterWeb:
    def test_web_result_appended(self):
        from spotlight.query_router import QueryRouter
        from spotlight.result import CAT_WEB
        router = QueryRouter(search_web=True)
        results = router.search("open source linux", categories=["web"])
        assert any(r.category == CAT_WEB for r in results)

    def test_web_url_contains_query(self):
        from spotlight.query_router import QueryRouter
        from spotlight.result import CAT_WEB
        router = QueryRouter(search_web=True)
        results = router.search("ubuntu desktop", categories=["web"])
        web = [r for r in results if r.category == CAT_WEB]
        assert web
        assert "ubuntu" in web[0].path.lower()

    def test_web_not_shown_for_short_query(self):
        from spotlight.query_router import QueryRouter
        from spotlight.result import CAT_WEB
        router = QueryRouter(search_web=True)
        results = router.search("ab", categories=["web"])
        assert not any(r.category == CAT_WEB for r in results)

    def test_web_disabled(self):
        from spotlight.query_router import QueryRouter
        from spotlight.result import CAT_WEB
        router = QueryRouter(search_web=False)
        results = router.search("open source")
        assert not any(r.category == CAT_WEB for r in results)


# ══════════════════════════════════════════════════════════════════════════════
# SpotlightIndexer
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def tmp_index(tmp_path):
    """SpotlightIndexer with an isolated temp index directory."""
    from spotlight.indexer import SpotlightIndexer
    ix = SpotlightIndexer(
        index_dir=tmp_path / "index",
        search_dirs=[tmp_path / "docs"],
        max_depth=3,
    )
    ix.open()
    yield ix
    ix.close()


class TestSpotlightIndexer:
    def test_open_creates_index(self, tmp_index):
        assert tmp_index._ix is not None

    def test_empty_index_doc_count_zero(self, tmp_index):
        assert tmp_index.get_stats()["doc_count"] == 0

    def test_is_indexing_false_by_default(self, tmp_index):
        assert tmp_index.is_indexing is False

    def test_search_empty_index_returns_empty(self, tmp_index):
        results = tmp_index.search("anything")
        assert results == []

    def test_empty_query_returns_empty(self, tmp_index):
        results = tmp_index.search("")
        assert results == []

    def test_update_and_search(self, tmp_path, tmp_index):
        f = tmp_path / "docs" / "report.txt"
        f.parent.mkdir(exist_ok=True)
        f.write_text("hello")
        tmp_index.update_path(str(f))
        results = tmp_index.search("report")
        assert any(r["name"] == "report.txt" for r in results)

    def test_delete_path(self, tmp_path, tmp_index):
        f = tmp_path / "docs" / "delete_me.txt"
        f.parent.mkdir(exist_ok=True)
        f.write_text("data")
        tmp_index.update_path(str(f))
        tmp_index.delete_path(str(f))
        results = tmp_index.search("delete_me")
        assert len(results) == 0

    def test_update_nonexistent_path_deletes(self, tmp_path, tmp_index):
        fake = str(tmp_path / "ghost.txt")
        # Should not raise even if path doesn't exist
        tmp_index.delete_path(fake)

    def test_make_doc_file(self, tmp_path):
        from spotlight.indexer import SpotlightIndexer
        f = tmp_path / "notes.md"
        f.write_text("content")
        doc = SpotlightIndexer._make_doc(f)
        assert doc is not None
        assert doc["name"] == "notes.md"
        assert doc["category"] == "file"
        assert doc["ext"] == "md"

    def test_make_doc_folder(self, tmp_path):
        from spotlight.indexer import SpotlightIndexer
        d = tmp_path / "myfolder"
        d.mkdir()
        doc = SpotlightIndexer._make_doc(d)
        assert doc is not None
        assert doc["category"] == "folder"
        assert doc["icon"] == "folder"

    def test_make_doc_nonexistent_returns_none(self, tmp_path):
        from spotlight.indexer import SpotlightIndexer
        doc = SpotlightIndexer._make_doc(tmp_path / "ghost.txt")
        assert doc is None

    def test_get_stats_keys(self, tmp_index):
        stats = tmp_index.get_stats()
        assert "doc_count" in stats
        assert "index_dir" in stats
        assert "is_indexing" in stats

    def test_rebuild_sync(self, tmp_path, tmp_index):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / "file1.txt").write_text("hello")
        (docs_dir / "file2.txt").write_text("world")
        # Update search_dirs to actually point to docs
        tmp_index._search_dirs = [docs_dir]
        count = tmp_index.rebuild_sync()
        assert count >= 2

    def test_search_category_filter(self, tmp_path, tmp_index):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(exist_ok=True)
        f = docs_dir / "document.pdf"
        f.parent.mkdir(exist_ok=True)
        # Actually write to test
        # Categories: only "folder" — a file should not appear
        d = docs_dir / "subfolder"
        d.mkdir()
        tmp_index.update_path(str(d))
        results = tmp_index.search("subfolder", categories=["folder"])
        assert all(r["category"] == "folder" for r in results)


# ══════════════════════════════════════════════════════════════════════════════
# SpotlightInterface (DBus)
# ══════════════════════════════════════════════════════════════════════════════

def _make_interface(show_cb=None, hide_cb=None, query_cb=None):
    """Build a SpotlightInterface with mocked indexer and router."""
    from spotlight.spotlight_dbus import SpotlightInterface

    indexer = MagicMock()
    indexer.is_indexing = False
    indexer.get_stats.return_value = {"doc_count": 42, "is_indexing": False, "index_dir": "/tmp"}

    router = MagicMock()
    router.search.return_value = []

    return SpotlightInterface(
        indexer=indexer,
        router=router,
        show_cb=show_cb or MagicMock(),
        hide_cb=hide_cb or MagicMock(),
        query_cb=query_cb,
    )


class TestSpotlightInterfaceVisibility:
    def test_visible_false_by_default(self):
        iface = _make_interface()
        assert iface.Visible is False

    def test_show_sets_visible(self):
        show_cb = MagicMock()
        iface = _make_interface(show_cb=show_cb)
        iface.Show()
        assert iface.Visible is True
        show_cb.assert_called_once()

    def test_hide_sets_invisible(self):
        hide_cb = MagicMock()
        iface = _make_interface(hide_cb=hide_cb)
        iface.Show()
        iface.Hide()
        assert iface.Visible is False
        hide_cb.assert_called_once()

    def test_toggle_show_then_hide(self):
        iface = _make_interface()
        assert iface.Visible is False
        iface.Toggle()
        assert iface.Visible is True
        iface.Toggle()
        assert iface.Visible is False

    def test_show_with_query_calls_query_cb(self):
        query_cb = MagicMock()
        iface = _make_interface(query_cb=query_cb)
        iface.ShowWithQuery("terminal")
        query_cb.assert_called_once_with("terminal")
        assert iface.Visible is True


class TestSpotlightInterfaceSearch:
    def test_search_delegates_to_router(self):
        from spotlight.result import SearchResult, CAT_APPS, ACTION_LAUNCH
        iface = _make_interface()
        mock_result = SearchResult(
            category=CAT_APPS, name="Firefox",
            path="/usr/share/applications/firefox.desktop",
            action=ACTION_LAUNCH,
        )
        iface._router.search.return_value = [mock_result]
        results = iface.Search("firefox", [], 12)
        assert len(results) == 1
        assert results[0]["name"] == "Firefox"

    def test_search_empty_categories_passes_none(self):
        iface = _make_interface()
        iface._router.search.return_value = []
        iface.Search("query", [], 12)
        _, kwargs = iface._router.search.call_args
        assert kwargs["categories"] is None

    def test_search_with_categories(self):
        iface = _make_interface()
        iface._router.search.return_value = []
        iface.Search("query", ["apps", "files"], 5)
        _, kwargs = iface._router.search.call_args
        assert "apps" in kwargs["categories"]


class TestSpotlightInterfaceIndex:
    def test_rebuild_index_triggers_async(self):
        iface = _make_interface()
        iface.RebuildIndex()
        iface._indexer.rebuild_async.assert_called_once()

    def test_update_index_calls_update_path(self):
        iface = _make_interface()
        iface.UpdateIndex("/home/user/doc.txt")
        iface._indexer.update_path.assert_called_once_with("/home/user/doc.txt")

    def test_get_index_stats_returns_dict(self):
        iface = _make_interface()
        stats = iface.GetIndexStats()
        assert "doc_count" in stats
        assert stats["doc_count"] == 42
        assert "is_indexing" in stats

    def test_indexing_property(self):
        iface = _make_interface()
        iface._indexer.is_indexing = True
        assert iface.Indexing is True

    def test_index_doc_count_property(self):
        iface = _make_interface()
        assert iface.IndexDocCount == 42
