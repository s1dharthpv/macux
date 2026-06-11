"""MacUX Notification Center — SQLite WAL persistence.

Stores the last *max_count* notifications.  Oldest are evicted automatically
after each save to stay under the cap.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Sequence

from notification_center.notification import Notification, Urgency

_CREATE = """
CREATE TABLE IF NOT EXISTS notifications (
    id            INTEGER PRIMARY KEY,
    app_name      TEXT    NOT NULL DEFAULT '',
    app_icon      TEXT    NOT NULL DEFAULT '',
    summary       TEXT    NOT NULL DEFAULT '',
    body          TEXT    NOT NULL DEFAULT '',
    urgency       INTEGER NOT NULL DEFAULT 1,
    expire_timeout INTEGER NOT NULL DEFAULT -1,
    timestamp     REAL    NOT NULL,
    dismissed     INTEGER NOT NULL DEFAULT 0
) STRICT
"""


class NotificationPersistence:
    """
    SQLite-backed notification store.

    Args:
        db_path:   Path to the SQLite database file.
        max_count: Maximum number of notifications to retain (default 100).
    """

    def __init__(self, db_path: Path, max_count: int = 100) -> None:
        self._max_count = max_count
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute(_CREATE)
        self._conn.commit()

    # ── Write ─────────────────────────────────────────────────────────────────

    def save(self, notif: Notification) -> None:
        """Insert or replace a notification, then evict oldest if over cap."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO notifications
                (id, app_name, app_icon, summary, body, urgency, expire_timeout, timestamp, dismissed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                notif.notif_id,
                notif.app_name,
                notif.app_icon,
                notif.summary,
                notif.body,
                int(notif.urgency),
                notif.expire_timeout,
                notif.timestamp,
                int(notif.dismissed),
            ),
        )
        self._evict()
        self._conn.commit()

    def dismiss(self, notif_id: int) -> None:
        self._conn.execute(
            "UPDATE notifications SET dismissed=1 WHERE id=?", (notif_id,)
        )
        self._conn.commit()

    def undismiss(self, notif_id: int) -> None:
        self._conn.execute(
            "UPDATE notifications SET dismissed=0 WHERE id=?", (notif_id,)
        )
        self._conn.commit()

    def clear_all(self) -> None:
        """Mark every notification as dismissed (does not delete rows)."""
        self._conn.execute("UPDATE notifications SET dismissed=1")
        self._conn.commit()

    def delete(self, notif_id: int) -> None:
        self._conn.execute("DELETE FROM notifications WHERE id=?", (notif_id,))
        self._conn.commit()

    def delete_all(self) -> None:
        self._conn.execute("DELETE FROM notifications")
        self._conn.commit()

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_all(self, include_dismissed: bool = True) -> list[Notification]:
        """Return notifications ordered newest-first."""
        if include_dismissed:
            rows = self._conn.execute(
                "SELECT * FROM notifications ORDER BY timestamp DESC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM notifications WHERE dismissed=0 ORDER BY timestamp DESC"
            ).fetchall()
        return [self._row_to_notif(r) for r in rows]

    def get_count(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM notifications"
        ).fetchone()[0]

    def get_undismissed_count(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE dismissed=0"
        ).fetchone()[0]

    def exists(self, notif_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM notifications WHERE id=?", (notif_id,)
        ).fetchone()
        return row is not None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _evict(self) -> None:
        """Delete oldest rows that exceed max_count."""
        self._conn.execute(
            """
            DELETE FROM notifications
            WHERE id IN (
                SELECT id FROM notifications
                ORDER BY timestamp DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self._max_count,),
        )

    @staticmethod
    def _row_to_notif(row: sqlite3.Row) -> Notification:
        return Notification(
            notif_id=row["id"],
            app_name=row["app_name"],
            app_icon=row["app_icon"],
            summary=row["summary"],
            body=row["body"],
            actions=[],
            hints={},
            urgency=row["urgency"],
            expire_timeout=row["expire_timeout"],
            timestamp=row["timestamp"],
            dismissed=bool(row["dismissed"]),
        )
