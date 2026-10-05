import sqlite3
import stat
from pathlib import Path

import pytest

from unlisted import db


def test_migrations_bring_schema_to_current(conn: sqlite3.Connection) -> None:
    assert db.schema_version(conn) == db.SCHEMA_VERSION
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "profile"} <= tables


def test_connect_is_idempotent(isolated_data_dir: Path) -> None:
    path = isolated_data_dir / "unlisted.db"
    db.connect(path).close()
    conn = db.connect(path)
    assert db.schema_version(conn) == db.SCHEMA_VERSION
    conn.close()


def test_newer_schema_refused(isolated_data_dir: Path) -> None:
    path = isolated_data_dir / "unlisted.db"
    conn = db.connect(path)
    conn.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(db.SchemaTooNewError, match="upgrade unlisted"):
        db.connect(path)


def test_failed_migration_rolls_back(
    isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = isolated_data_dir / "unlisted.db"
    db.connect(path).close()
    broken = [*db.MIGRATIONS, "CREATE TABLE half_done (x INTEGER); THIS IS NOT SQL;"]
    monkeypatch.setattr(db, "MIGRATIONS", broken)
    monkeypatch.setattr(db, "SCHEMA_VERSION", len(broken))

    with pytest.raises(sqlite3.Error):
        db.connect(path)

    conn = sqlite3.connect(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "half_done" not in tables
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(broken) - 1
    conn.close()


def test_files_are_private(isolated_data_dir: Path) -> None:
    path = isolated_data_dir / "unlisted.db"
    db.connect(path).close()
    assert stat.S_IMODE(isolated_data_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_transaction_rolls_back_on_error(conn: sqlite3.Connection) -> None:
    with pytest.raises(RuntimeError), db.transaction(conn):
        db.set_meta(conn, "probe", b"1")
        raise RuntimeError
    assert db.get_meta(conn, "probe") is None


def test_meta_upsert(conn: sqlite3.Connection) -> None:
    db.set_meta(conn, "probe", b"1")
    db.set_meta(conn, "probe", b"2")
    assert db.get_meta(conn, "probe") == b"2"
