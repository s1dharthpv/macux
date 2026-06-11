"""MacUX Launchpad — SQLite persistence for app positions and folders.

Schema
------
  app_positions(desktop_id PK, page, row, col, folder_id FK→folders)
  folders(folder_id PK AUTOINCREMENT, name, page, row, col)

Apps inside a folder have folder_id set; their page/row/col reflect their
position *within* the folder (0-indexed), not their grid position.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from launchpad.grid import GridCell

logger = logging.getLogger(__name__)

_DB_PATH = Path("~/.local/share/macux/launchpad/layout.db").expanduser()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
    folder_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL DEFAULT 'Folder',
    page       INTEGER NOT NULL DEFAULT 0,
    row        INTEGER NOT NULL DEFAULT 0,
    col        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_positions (
    desktop_id TEXT    PRIMARY KEY,
    page       INTEGER NOT NULL DEFAULT 0,
    row        INTEGER NOT NULL DEFAULT 0,
    col        INTEGER NOT NULL DEFAULT 0,
    folder_id  INTEGER REFERENCES folders(folder_id) ON DELETE SET NULL
);
"""


@dataclass
class FolderData:
    """A Launchpad folder with its grid position and member list."""

    folder_id: int
    name: str
    page: int = 0
    row: int = 0
    col: int = 0
    members: list[str] = field(default_factory=list)

    @property
    def cell(self) -> GridCell:
        return GridCell(page=self.page, row=self.row, col=self.col)


class LaunchpadPersistence:
    """
    Stores Launchpad app positions and folder membership in a WAL SQLite
    database.

    Usage::

        db = LaunchpadPersistence()
        db.open()
        db.set_app_position("firefox", GridCell(page=0, row=0, col=0))
        positions = db.get_app_positions()
        db.close()
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or _DB_PATH
        self._conn: sqlite3.Connection | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.debug("Launchpad DB opened: %s", self._path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── App positions ─────────────────────────────────────────────────────────

    def get_app_positions(self) -> dict[str, GridCell]:
        """Return grid positions for all apps that are NOT inside a folder."""
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT desktop_id, page, row, col FROM app_positions WHERE folder_id IS NULL"
        ).fetchall()
        return {
            desktop_id: GridCell(page=page, row=row, col=col)
            for desktop_id, page, row, col in rows
        }

    def set_app_position(self, desktop_id: str, cell: GridCell) -> None:
        assert self._conn is not None
        self._conn.execute(
            """INSERT INTO app_positions(desktop_id, page, row, col)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(desktop_id) DO UPDATE SET
                 page=excluded.page, row=excluded.row, col=excluded.col,
                 folder_id=NULL""",
            (desktop_id, cell.page, cell.row, cell.col),
        )
        self._conn.commit()

    def set_app_positions_bulk(self, positions: dict[str, GridCell]) -> None:
        """Write many positions in a single transaction (fast initial layout)."""
        assert self._conn is not None
        self._conn.executemany(
            """INSERT INTO app_positions(desktop_id, page, row, col)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(desktop_id) DO UPDATE SET
                 page=excluded.page, row=excluded.row, col=excluded.col""",
            [(k, v.page, v.row, v.col) for k, v in positions.items()],
        )
        self._conn.commit()

    def remove_app(self, desktop_id: str) -> None:
        assert self._conn is not None
        self._conn.execute(
            "DELETE FROM app_positions WHERE desktop_id=?", (desktop_id,)
        )
        self._conn.commit()

    def has_any_positions(self) -> bool:
        assert self._conn is not None
        count = self._conn.execute("SELECT COUNT(*) FROM app_positions").fetchone()[0]
        return count > 0

    # ── Folders ───────────────────────────────────────────────────────────────

    def get_folders(self) -> list[FolderData]:
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT folder_id, name, page, row, col FROM folders ORDER BY folder_id"
        ).fetchall()
        result: list[FolderData] = []
        for folder_id, name, page, row, col in rows:
            members = self._conn.execute(
                """SELECT desktop_id FROM app_positions
                   WHERE folder_id=? ORDER BY rowid""",
                (folder_id,),
            ).fetchall()
            result.append(FolderData(
                folder_id=folder_id,
                name=name,
                page=page,
                row=row,
                col=col,
                members=[m[0] for m in members],
            ))
        return result

    def create_folder(self, name: str, page: int, row: int, col: int) -> int:
        assert self._conn is not None
        cursor = self._conn.execute(
            "INSERT INTO folders(name, page, row, col) VALUES (?, ?, ?, ?)",
            (name, page, row, col),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def rename_folder(self, folder_id: int, name: str) -> None:
        assert self._conn is not None
        self._conn.execute(
            "UPDATE folders SET name=? WHERE folder_id=?", (name, folder_id)
        )
        self._conn.commit()

    def delete_folder(self, folder_id: int) -> None:
        """Delete a folder; its member apps have folder_id set to NULL."""
        assert self._conn is not None
        self._conn.execute(
            "UPDATE app_positions SET folder_id=NULL WHERE folder_id=?",
            (folder_id,),
        )
        self._conn.execute("DELETE FROM folders WHERE folder_id=?", (folder_id,))
        self._conn.commit()

    def add_to_folder(self, folder_id: int, desktop_id: str) -> None:
        assert self._conn is not None
        self._conn.execute(
            "UPDATE app_positions SET folder_id=? WHERE desktop_id=?",
            (folder_id, desktop_id),
        )
        self._conn.commit()

    def remove_from_folder(self, desktop_id: str, cell: GridCell) -> None:
        """Remove app from its folder, placing it at the given grid cell."""
        assert self._conn is not None
        self._conn.execute(
            """UPDATE app_positions
               SET folder_id=NULL, page=?, row=?, col=?
               WHERE desktop_id=?""",
            (cell.page, cell.row, cell.col, desktop_id),
        )
        self._conn.commit()

    def set_folder_position(self, folder_id: int, cell: GridCell) -> None:
        assert self._conn is not None
        self._conn.execute(
            "UPDATE folders SET page=?, row=?, col=? WHERE folder_id=?",
            (cell.page, cell.row, cell.col, folder_id),
        )
        self._conn.commit()
