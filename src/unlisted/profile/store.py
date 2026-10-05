import logging
import sqlite3
from datetime import UTC, datetime

from unlisted import crypto
from unlisted.db import transaction
from unlisted.profile.model import Profile

log = logging.getLogger(__name__)

_PURPOSE = "profile"


def has_profile(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM profile WHERE id = 1").fetchone() is not None


def load_profile(conn: sqlite3.Connection, key: bytes) -> Profile | None:
    row = conn.execute("SELECT ciphertext FROM profile WHERE id = 1").fetchone()
    if row is None:
        return None
    plaintext = crypto.decrypt(key, row[0], _PURPOSE)
    return Profile.model_validate_json(plaintext)


def save_profile(conn: sqlite3.Connection, key: bytes, profile: Profile) -> None:
    blob = crypto.encrypt(key, profile.model_dump_json().encode("utf-8"), _PURPOSE)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with transaction(conn):
        conn.execute(
            "INSERT INTO profile (id, ciphertext, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET "
            "ciphertext = excluded.ciphertext, updated_at = excluded.updated_at",
            (blob, now),
        )
    log.info("saved profile (%d bytes encrypted)", len(blob))
