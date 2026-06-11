"""MacUX Spotlight — DBus service (com.macux.Spotlight).

No 'from __future__ import annotations' — dasbus inspects type annotations
at class-definition time.  See dock/dock_dbus.py for the full explanation.
"""

import logging
from typing import Callable

from dasbus.connection import SessionMessageBus
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Bool, Int32, Str, Structure

from spotlight.indexer import SpotlightIndexer
from spotlight.query_router import QueryRouter
from spotlight.result import SearchResult

logger = logging.getLogger(__name__)

DBUS_NAME = "com.macux.Spotlight"
DBUS_PATH = "/com/macux/Spotlight"

ShowHideCallback = Callable[[], None]
QueryCallback = Callable[[str], None]


@dbus_interface("com.macux.Spotlight")
class SpotlightInterface:
    """DBus interface for the MacUX Spotlight search."""

    def __init__(
        self,
        indexer: SpotlightIndexer,
        router: QueryRouter,
        show_cb: ShowHideCallback,
        hide_cb: ShowHideCallback,
        query_cb: QueryCallback | None = None,
    ) -> None:
        self._indexer = indexer
        self._router = router
        self._show_cb = show_cb
        self._hide_cb = hide_cb
        self._query_cb = query_cb
        self._visible: bool = False

    # ── Visibility ─────────────────────────────────────────────────────────────

    def Show(self) -> None:
        self._visible = True
        self._show_cb()
        self.Shown()

    def Hide(self) -> None:
        self._visible = False
        self._hide_cb()
        self.Hidden()

    def Toggle(self) -> None:
        if self._visible:
            self.Hide()
        else:
            self.Show()

    def ShowWithQuery(self, query: Str) -> None:
        self._visible = True
        self._show_cb()
        if self._query_cb:
            self._query_cb(query)
        self.Shown()

    # ── Search ─────────────────────────────────────────────────────────────────

    def Search(self, query: Str, categories: list[Str], max_results: Int32) -> list[Structure]:
        """
        Run a search and return results as a list of dicts (DBus aa{sv}).
        """
        cats = list(categories) if categories else None
        results = self._router.search(
            query, categories=cats, max_results=int(max_results)
        )
        return [r.to_dbus_dict() for r in results]

    # ── Indexing ───────────────────────────────────────────────────────────────

    def RebuildIndex(self) -> None:
        self.IndexingStarted()
        self._indexer.rebuild_async(
            on_progress=self._on_index_progress,
            on_done=self._on_index_done,
        )

    def UpdateIndex(self, path: Str) -> None:
        self._indexer.update_path(path)

    def GetIndexStats(self) -> Structure:
        stats = self._indexer.get_stats()
        return {
            "doc_count":   int(stats.get("doc_count", 0)),
            "is_indexing": bool(stats.get("is_indexing", False)),
            "index_dir":   str(stats.get("index_dir", "")),
        }

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def Visible(self) -> Bool:
        return self._visible

    @property
    def Indexing(self) -> Bool:
        return self._indexer.is_indexing

    @property
    def IndexDocCount(self) -> Int32:
        return self._indexer.get_stats().get("doc_count", 0)

    # ── Signals ────────────────────────────────────────────────────────────────

    @dbus_signal
    def Shown(self) -> None:
        pass

    @dbus_signal
    def Hidden(self) -> None:
        pass

    @dbus_signal
    def IndexingStarted(self) -> None:
        pass

    @dbus_signal
    def IndexingCompleted(self, doc_count: Int32, duration_ms: Int32) -> None:
        pass

    @dbus_signal
    def IndexingProgress(self, percent: Int32, current_path: Str) -> None:
        pass

    # ── Internal callbacks from indexer thread ────────────────────────────────

    def _on_index_progress(self, percent: int, current_path: str) -> None:
        try:
            self.IndexingProgress(percent, current_path)
        except Exception:
            pass

    def _on_index_done(self, doc_count: int, duration_sec: float) -> None:
        try:
            self.IndexingCompleted(int(doc_count), int(duration_sec * 1000))
        except Exception:
            pass


class SpotlightDBusServer:
    """Owns the com.macux.Spotlight session bus name."""

    def __init__(
        self,
        indexer: SpotlightIndexer,
        router: QueryRouter,
        show_cb: ShowHideCallback,
        hide_cb: ShowHideCallback,
        query_cb: QueryCallback | None = None,
    ) -> None:
        self._bus = SessionMessageBus()
        self._interface = SpotlightInterface(
            indexer=indexer,
            router=router,
            show_cb=show_cb,
            hide_cb=hide_cb,
            query_cb=query_cb,
        )

    def start(self) -> None:
        self._bus.publish_object(DBUS_PATH, self._interface)
        self._bus.register_service(DBUS_NAME)
        logger.info("Spotlight DBus service registered: %s", DBUS_NAME)

    def stop(self) -> None:
        try:
            self._bus.unregister_service(DBUS_NAME)
            self._bus.unpublish_object(DBUS_PATH)
        except Exception:
            logger.exception("Error stopping Spotlight DBus server")

    @property
    def interface(self) -> SpotlightInterface:
        return self._interface
