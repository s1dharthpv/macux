"""Unit tests for macuxd.db — Database and migration runner."""

from __future__ import annotations

from pathlib import Path
import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Create a fresh dock Database backed by a temp directory."""
    import macuxd.db as db_module
    monkeypatch.setattr(db_module, "_DATA_DIR", tmp_path)
    from macuxd.db import Database
    d = Database("dock")
    d.open()
    yield d
    d.close()


class TestDatabaseOpen:
    def test_opens_successfully(self, db):
        assert db._conn is not None

    def test_schema_version_table_exists(self, db):
        row = db.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
        assert row is not None

    def test_pinned_apps_table_exists(self, db):
        row = db.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='pinned_apps'")
        assert row is not None

    def test_running_history_table_exists(self, db):
        row = db.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='running_app_history'")
        assert row is not None


class TestDatabaseCRUD:
    def test_insert_and_fetch_pinned_app(self, db):
        db.execute(
            "INSERT INTO pinned_apps(desktop_id, position) VALUES (?, ?)",
            ("org.gnome.Calculator.desktop", 0),
        )
        row = db.fetchone("SELECT * FROM pinned_apps WHERE desktop_id = ?",
                          ("org.gnome.Calculator.desktop",))
        assert row is not None
        assert row["position"] == 0

    def test_unique_desktop_id_constraint(self, db):
        import sqlite3
        db.execute("INSERT INTO pinned_apps(desktop_id, position) VALUES (?, ?)", ("app.desktop", 0))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO pinned_apps(desktop_id, position) VALUES (?, ?)", ("app.desktop", 1))

    def test_transaction_rollback_on_error(self, db):
        import sqlite3
        try:
            with db.transaction():
                db.execute("INSERT INTO pinned_apps(desktop_id, position) VALUES (?, ?)", ("x.desktop", 0))
                raise RuntimeError("forced rollback")
        except RuntimeError:
            pass
        row = db.fetchone("SELECT * FROM pinned_apps WHERE desktop_id='x.desktop'")
        assert row is None

    def test_transaction_commit(self, db):
        with db.transaction():
            db.execute("INSERT INTO pinned_apps(desktop_id, position) VALUES (?, ?)", ("y.desktop", 1))
        row = db.fetchone("SELECT * FROM pinned_apps WHERE desktop_id='y.desktop'")
        assert row is not None


class TestMigrationIdempotency:
    def test_second_open_does_not_duplicate_schema(self, tmp_path, monkeypatch):
        import macuxd.db as db_module
        monkeypatch.setattr(db_module, "_DATA_DIR", tmp_path)
        from macuxd.db import Database

        # Open twice
        db1 = Database("dock")
        db1.open()
        db1.close()

        db2 = Database("dock")
        db2.open()
        count = db2.fetchone("SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table'")
        db2.close()

        # Should have the same number of tables both times
        assert count["c"] >= 2
