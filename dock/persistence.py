"""MacUX Dock — pinned-app persistence layer.

Stores the ordered list of pinned dock apps in a WAL-mode SQLite database.
The database path defaults to ~/.local/share/macux/dock.db but can be
overridden (useful for tests).
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path("~/.local/share/macux/dock.db").expanduser()

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version   INTEGER NOT NULL,
    applied   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS pinned_apps (
    desktop_id TEXT    NOT NULL PRIMARY KEY,
    position   INTEGER NOT NULL,
    added_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pinned_apps_position ON pinned_apps(position);
"""


class DockPersistence:
    """
    Manages the dock's pinned-app database.

    Thread safety: the caller must ensure that all methods are called from
    the same thread (the GLib main thread).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or _DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the database, creating it and running migrations if needed."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._apply_schema()
        logger.debug("DockPersistence: opened %s", self._path)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Pinned apps ───────────────────────────────────────────────────────────

    def get_pinned_apps(self) -> list[str]:
        """Return desktop_ids in position order."""
        rows = self._fetchall(
            "SELECT desktop_id FROM pinned_apps ORDER BY position ASC"
        )
        return [row["desktop_id"] for row in rows]

    def pin_app(self, desktop_id: str, position: int | None = None) -> None:
        """
        Pin an app at the given position.

        If position is None, appends at the end.
        If the desktop_id is already pinned, updates its position.
        """
        if position is None:
            row = self._fetchone("SELECT COALESCE(MAX(position), -1) + 1 AS pos FROM pinned_apps")
            position = row["pos"] if row else 0

        with self._transaction():
            # Shift existing apps to make room
            self._conn.execute(  # type: ignore[union-attr]
                "UPDATE pinned_apps SET position = position + 1 WHERE position >= ?",
                (position,),
            )
            self._conn.execute(  # type: ignore[union-attr]
                """INSERT INTO pinned_apps (desktop_id, position)
                   VALUES (?, ?)
                   ON CONFLICT(desktop_id) DO UPDATE SET position = excluded.position""",
                (desktop_id, position),
            )
        logger.debug("Pinned %s at position %d", desktop_id, position)

    def unpin_app(self, desktop_id: str) -> None:
        """Remove an app from the dock."""
        row = self._fetchone(
            "SELECT position FROM pinned_apps WHERE desktop_id = ?", (desktop_id,)
        )
        if row is None:
            return

        removed_pos = row["position"]
        with self._transaction():
            self._conn.execute(  # type: ignore[union-attr]
                "DELETE FROM pinned_apps WHERE desktop_id = ?", (desktop_id,)
            )
            # Compact positions
            self._conn.execute(  # type: ignore[union-attr]
                "UPDATE pinned_apps SET position = position - 1 WHERE position > ?",
                (removed_pos,),
            )
        logger.debug("Unpinned %s", desktop_id)

    def move_app(self, desktop_id: str, new_position: int) -> None:
        """
        Move a pinned app to a new position, shifting others as needed.
        """
        row = self._fetchone(
            "SELECT position FROM pinned_apps WHERE desktop_id = ?", (desktop_id,)
        )
        if row is None:
            logger.warning("move_app: %s not in pinned list", desktop_id)
            return

        old_pos = row["position"]
        if old_pos == new_position:
            return

        with self._transaction():
            # Remove from old position
            self._conn.execute(  # type: ignore[union-attr]
                "DELETE FROM pinned_apps WHERE desktop_id = ?", (desktop_id,)
            )
            # Compact
            self._conn.execute(  # type: ignore[union-attr]
                "UPDATE pinned_apps SET position = position - 1 WHERE position > ?",
                (old_pos,),
            )
            # Make room at new position
            self._conn.execute(  # type: ignore[union-attr]
                "UPDATE pinned_apps SET position = position + 1 WHERE position >= ?",
                (new_position,),
            )
            # Re-insert
            self._conn.execute(  # type: ignore[union-attr]
                "INSERT INTO pinned_apps (desktop_id, position) VALUES (?, ?)",
                (desktop_id, new_position),
            )
        logger.debug("Moved %s: %d → %d", desktop_id, old_pos, new_position)

    def is_pinned(self, desktop_id: str) -> bool:
        row = self._fetchone(
            "SELECT 1 FROM pinned_apps WHERE desktop_id = ?", (desktop_id,)
        )
        return row is not None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _apply_schema(self) -> None:
        assert self._conn is not None
        with self._transaction():
            self._conn.executescript(_SCHEMA_SQL)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        assert self._conn is not None
        try:
            yield
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def _fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        assert self._conn is not None
        return self._conn.execute(sql, params).fetchone()

    def _fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        assert self._conn is not None
        return self._conn.execute(sql, params).fetchall()
