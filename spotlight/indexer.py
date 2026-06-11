"""MacUX Spotlight — Whoosh file indexer with live inotify updates.

Index schema
------------
  doc_id    : unique path-based ID (avoids duplicate entries)
  name      : filename or app display name (boosted 2×)
  path      : absolute filesystem path
  category  : "file" | "folder" | "app"
  icon      : icon theme name or ""
  mtime     : file modification time (epoch float)
  ext       : lowercase extension without dot (e.g. "pdf")

Thread safety
-------------
All public methods are safe to call from the GLib main thread.
The initial indexing run and watchdog observer run in daemon threads.
Writers are short-lived: acquired, committed, released.  The searcher
is opened fresh for each query (Whoosh near-real-time reads).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

from whoosh import index as whoosh_index
from whoosh.analysis import LowercaseFilter, RegexTokenizer
from whoosh.fields import ID, KEYWORD, NUMERIC, STORED, TEXT, Schema
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh import query as whoosh_query

logger = logging.getLogger(__name__)

# Index storage location
_INDEX_DIR = Path("~/.local/share/macux/spotlight/index").expanduser()

# Default directories to index
_INDEX_DIRS: list[Path] = [
    Path.home(),
]

# File extensions to skip entirely (binary / not useful in search)
_SKIP_EXTENSIONS = frozenset(
    "pyc pyo so dll exe o obj a lib class jar war ear"
    " iso img bin dat db sqlite sqlite3"
    " jpg jpeg png gif bmp tiff webp svg"
    " mp3 mp4 mkv avi mov flac ogg wav opus"
    " zip tar gz bz2 xz 7z rar"
    " ttf otf woff woff2"
    " tmp swp lock".split()
)

# Maximum directory depth to walk
_MAX_DEPTH = 8

# Whoosh schema
# Tokenize filenames by alphanumeric runs so "report.txt" → ["report", "txt"]
_NAME_ANALYZER = RegexTokenizer(r"[A-Za-z0-9]+") | LowercaseFilter()

_SCHEMA = Schema(
    doc_id   = ID(stored=True, unique=True),
    name     = TEXT(stored=True, field_boost=2.0, analyzer=_NAME_ANALYZER),
    path     = ID(stored=True),
    category = ID(stored=True),
    icon     = STORED(),
    mtime    = NUMERIC(stored=True, numtype=float),
    ext      = KEYWORD(stored=True, commas=False),
)

IndexProgress = Callable[[int, str], None]   # (percent, current_path)
IndexDone     = Callable[[int, float], None]  # (doc_count, duration_sec)


class SpotlightIndexer:
    """
    Manages a Whoosh index of the user's filesystem.

    Usage::

        indexer = SpotlightIndexer()
        indexer.open()
        indexer.rebuild_async(on_progress=..., on_done=...)
        results = indexer.search("report", max_results=12)
        indexer.close()
    """

    def __init__(
        self,
        index_dir: Path | None = None,
        search_dirs: list[Path] | None = None,
        max_depth: int = _MAX_DEPTH,
    ) -> None:
        self._index_dir = index_dir or _INDEX_DIR
        self._search_dirs = search_dirs if search_dirs is not None else _INDEX_DIRS
        self._max_depth = max_depth
        self._ix = None
        self._observer = None
        self._indexing = False
        self._lock = threading.Lock()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open (or create) the Whoosh index on disk."""
        self._index_dir.mkdir(parents=True, exist_ok=True)
        if whoosh_index.exists_in(str(self._index_dir)):
            try:
                self._ix = whoosh_index.open_dir(str(self._index_dir))
                logger.debug("Opened existing Spotlight index (%d docs)", self._doc_count())
                return
            except Exception as exc:
                logger.warning("Could not open existing index: %s — recreating.", exc)

        self._ix = whoosh_index.create_in(str(self._index_dir), _SCHEMA)
        logger.debug("Created new Spotlight index.")

    def close(self) -> None:
        self._stop_observer()
        if self._ix:
            self._ix.close()
            self._ix = None

    # ── Indexing ───────────────────────────────────────────────────────────────

    @property
    def is_indexing(self) -> bool:
        return self._indexing

    def rebuild_async(
        self,
        on_progress: IndexProgress | None = None,
        on_done: IndexDone | None = None,
    ) -> None:
        """Start a full index rebuild in a daemon thread."""
        if self._indexing:
            logger.debug("Indexing already in progress — skipping rebuild.")
            return
        thread = threading.Thread(
            target=self._rebuild_worker,
            args=(on_progress, on_done),
            daemon=True,
            name="macux-spotlight-indexer",
        )
        thread.start()

    def rebuild_sync(
        self,
        on_progress: IndexProgress | None = None,
        on_done: IndexDone | None = None,
    ) -> int:
        """Rebuild the index synchronously (blocking). Returns doc count."""
        return self._rebuild_worker(on_progress, on_done)

    def update_path(self, path_str: str) -> None:
        """Add or update a single file in the index (called by watchdog)."""
        assert self._ix is not None, "Indexer not opened"
        path = Path(path_str)
        if not path.exists():
            self._delete_doc(path_str)
            return
        doc = self._make_doc(path)
        if doc:
            with self._lock:
                writer = self._ix.writer()
                writer.update_document(**doc)
                writer.commit()

    def delete_path(self, path_str: str) -> None:
        """Remove a path from the index."""
        self._delete_doc(path_str)

    # ── Search ─────────────────────────────────────────────────────────────────

    def search(
        self,
        query_str: str,
        categories: list[str] | None = None,
        max_results: int = 12,
    ) -> list[dict]:
        """
        Search the index.

        Args:
            query_str:   User's query text.
            categories:  Restrict to "file" and/or "folder". None = both.
            max_results: Maximum number of hits to return.

        Returns:
            List of dicts with keys: name, path, category, icon, ext, score.
        """
        assert self._ix is not None, "Indexer not opened"

        if not query_str.strip():
            return []

        try:
            with self._ix.searcher() as searcher:
                parser = MultifieldParser(
                    ["name", "ext"],
                    schema=_SCHEMA,
                    group=OrGroup,
                )
                parsed = parser.parse(query_str)

                # Optional category filter
                if categories:
                    cat_filter = whoosh_query.Or(
                        [whoosh_query.Term("category", c) for c in categories]
                    )
                    parsed = whoosh_query.And([parsed, cat_filter])

                hits = searcher.search(parsed, limit=max_results)
                return [
                    {
                        "name":     h["name"],
                        "path":     h["path"],
                        "category": h["category"],
                        "icon":     h.get("icon", ""),
                        "ext":      h.get("ext", ""),
                        "score":    h.score,
                    }
                    for h in hits
                ]
        except Exception as exc:
            logger.warning("Spotlight search error: %s", exc)
            return []

    def get_stats(self) -> dict:
        """Return index statistics."""
        count = self._doc_count()
        return {
            "doc_count":        count,
            "index_dir":        str(self._index_dir),
            "is_indexing":      self._indexing,
        }

    # ── Watchdog ───────────────────────────────────────────────────────────────

    def start_watching(self) -> None:
        """Start the inotify-based watchdog observer for live updates."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            indexer_ref = self

            class Handler(FileSystemEventHandler):
                def on_created(self, event):
                    if not event.is_directory:
                        indexer_ref.update_path(event.src_path)

                def on_modified(self, event):
                    if not event.is_directory:
                        indexer_ref.update_path(event.src_path)

                def on_deleted(self, event):
                    indexer_ref.delete_path(event.src_path)

                def on_moved(self, event):
                    indexer_ref.delete_path(event.src_path)
                    if not event.is_directory:
                        indexer_ref.update_path(event.dest_path)

            self._observer = Observer()
            handler = Handler()
            for d in self._search_dirs:
                if d.is_dir():
                    self._observer.schedule(handler, str(d), recursive=True)

            self._observer.daemon = True
            self._observer.start()
            logger.debug("Spotlight watchdog started.")
        except Exception as exc:
            logger.warning("Could not start watchdog observer: %s", exc)

    def _stop_observer(self) -> None:
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:
                pass
            self._observer = None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild_worker(
        self,
        on_progress: IndexProgress | None,
        on_done: IndexDone | None,
    ) -> int:
        assert self._ix is not None
        self._indexing = True
        t0 = time.monotonic()
        count = 0

        try:
            all_paths = list(self._collect_paths(on_progress))
            total = len(all_paths)

            try:
                with self._lock:
                    writer = self._ix.writer(limitmb=64)
                    for i, path in enumerate(all_paths):
                        doc = self._make_doc(path)
                        if doc:
                            writer.update_document(**doc)
                            count += 1
                        if on_progress and i % 100 == 0:
                            pct = int(i * 100 / max(total, 1))
                            on_progress(pct, str(path))
                    writer.commit()
            except Exception as exc:
                logger.exception("Indexing error: %s", exc)
                try:
                    writer.cancel()
                except Exception:
                    pass
        finally:
            self._indexing = False

        duration = time.monotonic() - t0
        logger.info("Spotlight index rebuilt: %d docs in %.1fs", count, duration)

        if on_done:
            try:
                on_done(count, duration)
            except Exception:
                pass

        return count

    def _collect_paths(self, on_progress: IndexProgress | None):
        """Yield all indexable Paths in the configured directories."""
        for root_dir in self._search_dirs:
            if not root_dir.is_dir():
                continue
            for path in self._walk(root_dir, depth=0):
                yield path

    def _walk(self, directory: Path, depth: int):
        """Walk directory tree up to max_depth, skipping hidden dirs."""
        if depth > self._max_depth:
            return
        try:
            for entry in os.scandir(directory):
                name = entry.name
                if name.startswith("."):
                    continue
                path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False):
                    yield path
                    yield from self._walk(path, depth + 1)
                elif entry.is_file(follow_symlinks=False):
                    ext = path.suffix.lstrip(".").lower()
                    if ext not in _SKIP_EXTENSIONS:
                        yield path
        except PermissionError:
            pass

    @staticmethod
    def _make_doc(path: Path) -> dict | None:
        """Build a Whoosh document dict for a filesystem path."""
        try:
            stat = path.stat()
        except OSError:
            return None

        is_dir = path.is_dir()
        category = "folder" if is_dir else "file"
        ext = "" if is_dir else path.suffix.lstrip(".").lower()

        # Skip large binary files (> 100 MB) in text search
        if not is_dir and stat.st_size > 100 * 1024 * 1024:
            return None

        return {
            "doc_id":   str(path),
            "name":     path.name,
            "path":     str(path),
            "category": category,
            "icon":     "folder" if is_dir else f"text-x-{ext}" if ext else "text-x-generic",
            "mtime":    float(stat.st_mtime),
            "ext":      ext,
        }

    def _delete_doc(self, path_str: str) -> None:
        if self._ix is None:
            return
        with self._lock:
            writer = self._ix.writer()
            writer.delete_by_term("doc_id", path_str)
            writer.commit()

    def _doc_count(self) -> int:
        if self._ix is None:
            return 0
        try:
            return self._ix.doc_count()
        except Exception:
            return 0
