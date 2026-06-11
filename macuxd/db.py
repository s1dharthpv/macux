"""MacUX SQLite database layer — schema creation and migration runner."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_DIR = Path("~/.local/share/macux").expanduser()

# Schema version → migration SQL mapping.
# Each entry is (version, sql_statements).
# version 0 = initial schema creation.
_MIGRATIONS: dict[str, list[tuple[int, list[str]]]] = {
    "dock": [
        (0, [
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                db_name TEXT PRIMARY KEY,
                version INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pinned_apps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                desktop_id  TEXT    NOT NULL UNIQUE,
                position    INTEGER NOT NULL,
                added_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS running_app_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                desktop_id  TEXT    NOT NULL,
                last_used   DATETIME DEFAULT CURRENT_TIMESTAMP,
                use_count   INTEGER DEFAULT 1,
                UNIQUE(desktop_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_running_history_desktop ON running_app_history(desktop_id)",
            "CREATE INDEX IF NOT EXISTS idx_pinned_position ON pinned_apps(position)",
        ]),
    ],
    "launchpad": [
        (0, [
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                db_name TEXT PRIMARY KEY,
                version INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS folders (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT    NOT NULL,
                page    INTEGER NOT NULL DEFAULT 0,
                row     INTEGER NOT NULL DEFAULT 0,
                col     INTEGER NOT NULL DEFAULT 0,
                color   TEXT    DEFAULT '#808080'
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS app_layout (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                desktop_id  TEXT    NOT NULL UNIQUE,
                page        INTEGER NOT NULL DEFAULT 0,
                row         INTEGER NOT NULL DEFAULT 0,
                col         INTEGER NOT NULL DEFAULT 0,
                folder_id   INTEGER REFERENCES folders(id) ON DELETE SET NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_layout_page ON app_layout(page, row, col)",
        ]),
    ],
    "notifications": [
        (0, [
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                db_name TEXT PRIMARY KEY,
                version INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name    TEXT    NOT NULL,
                app_icon    TEXT,
                summary     TEXT    NOT NULL,
                body        TEXT,
                actions     TEXT,
                hints       TEXT,
                replaces_id INTEGER,
                received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                read_at     DATETIME,
                dismissed   BOOLEAN DEFAULT 0,
                urgency     INTEGER DEFAULT 1
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS do_not_disturb_schedule (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled     BOOLEAN DEFAULT 0,
                start_time  TEXT DEFAULT '22:00',
                end_time    TEXT DEFAULT '07:00',
                days        TEXT DEFAULT '0,1,2,3,4,5,6'
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_notifications_app ON notifications(app_name)",
            "CREATE INDEX IF NOT EXISTS idx_notifications_received ON notifications(received_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(read_at) WHERE read_at IS NULL",
        ]),
    ],
    "finder": [
        (0, [
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                db_name TEXT PRIMARY KEY,
                version INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS favorites (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                path        TEXT    NOT NULL UNIQUE,
                label       TEXT,
                icon        TEXT,
                position    INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tags (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT    NOT NULL UNIQUE,
                color   TEXT    NOT NULL DEFAULT '#808080'
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS file_tags (
                file_path   TEXT    NOT NULL,
                tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (file_path, tag_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS recent_locations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                path        TEXT    NOT NULL UNIQUE,
                visited_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "INSERT OR IGNORE INTO tags(name, color) VALUES ('Red', '#ff3b30')",
            "INSERT OR IGNORE INTO tags(name, color) VALUES ('Orange', '#ff9500')",
            "INSERT OR IGNORE INTO tags(name, color) VALUES ('Yellow', '#ffcc00')",
            "INSERT OR IGNORE INTO tags(name, color) VALUES ('Green', '#34c759')",
            "INSERT OR IGNORE INTO tags(name, color) VALUES ('Blue', '#007aff')",
            "INSERT OR IGNORE INTO tags(name, color) VALUES ('Purple', '#af52de')",
            "INSERT OR IGNORE INTO tags(name, color) VALUES ('Gray', '#8e8e93')",
            "CREATE INDEX IF NOT EXISTS idx_file_tags_path ON file_tags(file_path)",
            "CREATE INDEX IF NOT EXISTS idx_recent_locations_visited ON recent_locations(visited_at DESC)",
        ]),
    ],
}


class Database:
    """Thread-safe SQLite connection wrapper with migration support."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._path = _DATA_DIR / f"{name}.db"
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self._path,
            check_same_thread=False,
            isolation_level=None,  # autocommit; use explicit BEGIN
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._run_migrations()
        logger.info("Database %s opened at %s", self.name, self._path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _get_version(self) -> int:
        try:
            row = self._conn.execute(
                "SELECT version FROM schema_version WHERE db_name = ?", (self.name,)
            ).fetchone()
            return row["version"] if row else -1
        except sqlite3.OperationalError:
            return -1

    def _set_version(self, version: int) -> None:
        self._conn.execute(
            "INSERT INTO schema_version(db_name, version) VALUES (?,?) "
            "ON CONFLICT(db_name) DO UPDATE SET version=excluded.version",
            (self.name, version),
        )

    def _run_migrations(self) -> None:
        migrations = _MIGRATIONS.get(self.name, [])
        current = self._get_version()
        for version, statements in migrations:
            if version > current:
                logger.info("Applying migration v%d to %s", version, self.name)
                with self.transaction():
                    for sql in statements:
                        self._conn.execute(sql)
                    self._set_version(version)
                logger.info("Migration v%d applied to %s", version, self.name)

    def transaction(self):
        return _Transaction(self._conn)

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        assert self._conn is not None, "Database not open"
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params_seq: list[tuple]) -> sqlite3.Cursor:
        assert self._conn is not None, "Database not open"
        return self._conn.executemany(sql, params_seq)

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def lastrowid(self, sql: str, params: tuple = ()) -> int | None:
        return self.execute(sql, params).lastrowid


class _Transaction:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self):
        self._conn.execute("BEGIN")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.execute("ROLLBACK")
            return False
        self._conn.execute("COMMIT")
        return False


def open_all_databases() -> dict[str, Database]:
    """Open and migrate all MacUX databases. Returns name → Database map."""
    dbs: dict[str, Database] = {}
    for name in _MIGRATIONS:
        db = Database(name)
        db.open()
        dbs[name] = db
    return dbs
