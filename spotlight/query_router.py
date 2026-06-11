"""MacUX Spotlight — query router.

Routes a search query to the appropriate backends and merges results:
  1. Apps   — searched via DesktopFileParser registry (in-memory, instant)
  2. Calculator — detected via regex, evaluated with AST evaluator
  3. Files/Folders — searched via Whoosh index
  4. Web    — always appended last when query length >= 3

Result ordering:
  - Calculator appears first (highest relevance when matched)
  - Apps appear before files (users search apps most often)
  - Files and folders interleaved by Whoosh score
  - Web suggestion always last
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from spotlight.calculator import CalculatorError, evaluate, is_arithmetic
from spotlight.result import (
    CAT_APPS, CAT_CALCULATOR, CAT_FILES, CAT_FOLDERS, CAT_WEB,
    ACTION_COPY, ACTION_LAUNCH, ACTION_OPEN, ACTION_URL,
    SearchResult,
)

if TYPE_CHECKING:
    from spotlight.indexer import SpotlightIndexer

logger = logging.getLogger(__name__)

# Minimum query length before file/folder search is triggered
_FILE_SEARCH_MIN_LEN = 2
# Minimum query length before web suggestion is shown
_WEB_SEARCH_MIN_LEN = 3

# Default web search template
_WEB_SEARCH_URL = "https://www.google.com/search?q={}"


class QueryRouter:
    """
    Routes Spotlight queries to the appropriate search backends.

    Usage::

        router = QueryRouter(app_registry, indexer, web_url_template)
        results = router.search("terminal", ["apps", "files"], max_results=12)
    """

    def __init__(
        self,
        app_registry: dict | None = None,
        indexer: SpotlightIndexer | None = None,
        web_url: str = _WEB_SEARCH_URL,
        search_web: bool = True,
    ) -> None:
        self._registry = app_registry or {}
        self._indexer = indexer
        self._web_url = web_url
        self._search_web = search_web

    # ── Public API ────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        categories: list[str] | None = None,
        max_results: int = 12,
    ) -> list[SearchResult]:
        """
        Run the query against all applicable backends.

        Args:
            query:       Raw user input.
            categories:  Which categories to include; None = all.
            max_results: Hard cap on total returned results.

        Returns:
            Ordered list of SearchResult objects (best first).
        """
        q = query.strip()
        if not q:
            return []

        cats = set(categories) if categories else set(
            [CAT_APPS, CAT_CALCULATOR, CAT_FILES, CAT_FOLDERS, CAT_WEB]
        )
        results: list[SearchResult] = []

        # 1. Calculator — insert at top if matched
        if CAT_CALCULATOR in cats and is_arithmetic(q):
            calc = self._calculator_result(q)
            if calc:
                results.append(calc)

        # 2. Apps
        if CAT_APPS in cats:
            results.extend(self._search_apps(q))

        # 3. Files + Folders from Whoosh
        file_cats = [c for c in ("file", "folder") if
                     (c == "file" and CAT_FILES in cats) or
                     (c == "folder" and CAT_FOLDERS in cats)]
        if file_cats and len(q) >= _FILE_SEARCH_MIN_LEN and self._indexer:
            results.extend(self._search_index(q, file_cats))

        # 4. Web suggestion
        if CAT_WEB in cats and self._search_web and len(q) >= _WEB_SEARCH_MIN_LEN:
            results.append(self._web_result(q))

        return results[:max_results]

    def set_registry(self, registry: dict) -> None:
        self._registry = registry

    # ── App search ────────────────────────────────────────────────────────────

    def _search_apps(self, query: str) -> list[SearchResult]:
        q = query.lower()
        scored: list[tuple[float, SearchResult]] = []

        for desktop_id, info in self._registry.items():
            if info.nodisplay:
                continue
            score = self._score_app(q, info)
            if score > 0.0:
                scored.append((score, SearchResult(
                    category=CAT_APPS,
                    name=info.name,
                    path=info.path,
                    icon=info.icon,
                    score=score,
                    subtitle=info.comment or info.categories[0] if info.categories else "",
                    action=ACTION_LAUNCH,
                    metadata={"desktop_id": desktop_id},
                )))

        scored.sort(key=lambda t: -t[0])
        return [r for _, r in scored[:8]]

    @staticmethod
    def _score_app(query: str, info) -> float:
        """
        Score an AppInfo against a query string (0.0 = no match).

        Scoring levels:
          1.0  exact name match
          0.95 exact exec_base match
          0.90 name starts with query
          0.80 name contains query as a word
          0.70 name contains query as substring
          0.60 exec_base starts with query
          0.50 comment / category contains query
          0.0  no match
        """
        name = info.name.lower()
        eb   = info.exec_base.lower()
        q    = query.strip().lower()

        if not q:
            return 0.0

        if name == q:
            return 1.0
        if eb == q:
            return 0.95
        if name.startswith(q):
            # Penalise longer names slightly
            return 0.90 - 0.05 * min((len(name) - len(q)) / max(len(name), 1), 0.5)
        # Word-boundary match (e.g. "term" → "GNOME Terminal")
        if any(w.startswith(q) for w in name.split()):
            return 0.80
        if q in name:
            return 0.70
        if eb.startswith(q):
            return 0.60
        comment = (info.comment or "").lower()
        if q in comment:
            return 0.50
        if any(q in c.lower() for c in info.categories):
            return 0.40
        return 0.0

    # ── Calculator ───────────────────────────────────────────────────────────

    def _calculator_result(self, query: str) -> SearchResult | None:
        try:
            result_str = evaluate(query)
        except CalculatorError as exc:
            logger.debug("Calculator: %s → %s", query, exc)
            return None
        except Exception:
            return None

        return SearchResult(
            category=CAT_CALCULATOR,
            name=result_str,
            path="",
            icon="accessories-calculator",
            score=1.0,
            subtitle=query,
            action=ACTION_COPY,
            metadata={"expression": query, "result": result_str},
        )

    # ── File / folder search ──────────────────────────────────────────────────

    def _search_index(self, query: str, file_cats: list[str]) -> list[SearchResult]:
        assert self._indexer is not None
        hits = self._indexer.search(query, categories=file_cats, max_results=20)
        out: list[SearchResult] = []
        for h in hits:
            cat = CAT_FOLDERS if h["category"] == "folder" else CAT_FILES
            icon = h.get("icon") or (
                "folder" if cat == CAT_FOLDERS else "text-x-generic"
            )
            out.append(SearchResult(
                category=cat,
                name=h["name"],
                path=h["path"],
                icon=icon,
                score=min(h["score"] / 10.0, 0.95),  # normalise Whoosh BM25
                subtitle=str(h["path"]),
                action=ACTION_OPEN,
            ))
        return out

    # ── Web ───────────────────────────────────────────────────────────────────

    def _web_result(self, query: str) -> SearchResult:
        from urllib.parse import quote_plus
        url = self._web_url.format(quote_plus(query))
        return SearchResult(
            category=CAT_WEB,
            name=f'Search the web for "{query}"',
            path=url,
            icon="web-browser",
            score=0.1,
            subtitle=url,
            action=ACTION_URL,
        )
