"""SQLite storage and schema migrations.

Migrations are append-only: never edit one that has shipped, add a new one.
The applied version lives in PRAGMA user_version so there's no bookkeeping
table to get out of sync.
"""

import logging
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from unlisted.paths import ensure_private_dir

log = logging.getLogger(__name__)

MIGRATIONS: list[str] = [
    # 1: key material and the encrypted profile.
    """
    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value BLOB NOT NULL
    );
    CREATE TABLE profile (
        id         INTEGER PRIMARY KEY CHECK (id = 1),
        ciphertext BLOB NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
]

SCHEMA_VERSION = len(MIGRATIONS)


class SchemaTooNewError(Exception):
    pass


def connect(path: Path) -> sqlite3.Connection:
    ensure_private_dir(path.parent)
    # Create the file ourselves so it's 0600 from the first byte. SQLite would
    # otherwise create it with the umask default, typically world-readable.
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.close(fd)
    path.chmod(0o600)

    # isolation_level=None: transactions are explicit via transaction() below
    # rather than opened implicitly by the sqlite3 module.
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def migrate(conn: sqlite3.Connection) -> None:
    current = schema_version(conn)
    if current > SCHEMA_VERSION:
        raise SchemaTooNewError(
            f"database schema is version {current}, but this version of unlisted only "
            f"understands up to {SCHEMA_VERSION}; upgrade unlisted"
        )
    for version in range(current + 1, SCHEMA_VERSION + 1):
        log.debug("applying migration %d", version)
        # executescript() commits any open transaction first, so the
        # BEGIN/COMMIT live in the script to keep each migration atomic.
        script = MIGRATIONS[version - 1]
        try:
            conn.executescript(
                f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version = {version};\nCOMMIT;"
            )
        except sqlite3.Error:
            # executescript stops at the failing statement and leaves the
            # transaction open; without this the half-applied DDL would stick.
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise


def get_meta(conn: sqlite3.Connection, key: str) -> bytes | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    value = row[0]
    return value if isinstance(value, bytes) else str(value).encode()


def set_meta(conn: sqlite3.Connection, key: str, value: bytes) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
