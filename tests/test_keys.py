import base64
import sqlite3

import keyring
import pytest
from keyring.backends import fail
from keyring.errors import KeyringError

from tests.conftest import MemoryKeyring
from unlisted import crypto, db, keys

PASSPHRASE = "fake passphrase for tests"


def test_keyring_mode_roundtrip(conn: sqlite3.Connection, memory_keyring: MemoryKeyring) -> None:
    key = keys.create_key(conn, keys.KeyMode.KEYRING)
    assert keys.key_mode(conn) is keys.KeyMode.KEYRING
    assert len(memory_keyring.entries) == 1
    assert keys.unlock(conn, _no_prompt) == key


def test_keyring_mode_never_stores_key_in_db(conn: sqlite3.Connection) -> None:
    key = keys.create_key(conn, keys.KeyMode.KEYRING)
    for (value,) in conn.execute("SELECT value FROM meta"):
        assert key not in value
        assert base64.b64encode(key) not in value


def test_missing_keyring_entry(conn: sqlite3.Connection, memory_keyring: MemoryKeyring) -> None:
    keys.create_key(conn, keys.KeyMode.KEYRING)
    memory_keyring.entries.clear()
    with pytest.raises(keys.UnlockError, match="missing from the system keyring"):
        keys.unlock(conn, _no_prompt)


def test_keyring_entry_for_other_db_rejected(
    conn: sqlite3.Connection, memory_keyring: MemoryKeyring
) -> None:
    keys.create_key(conn, keys.KeyMode.KEYRING)
    (entry,) = memory_keyring.entries
    memory_keyring.entries[entry] = base64.b64encode(crypto.new_key()).decode()
    with pytest.raises(keys.UnlockError, match="doesn't match"):
        keys.unlock(conn, _no_prompt)


def test_passphrase_mode_roundtrip(conn: sqlite3.Connection, memory_keyring: MemoryKeyring) -> None:
    key = keys.create_key(conn, keys.KeyMode.PASSPHRASE, PASSPHRASE)
    assert memory_keyring.entries == {}
    assert keys.unlock(conn, lambda: PASSPHRASE) == key


def test_passphrase_mode_wrong_passphrase(conn: sqlite3.Connection) -> None:
    keys.create_key(conn, keys.KeyMode.PASSPHRASE, PASSPHRASE)
    with pytest.raises(keys.UnlockError, match="wrong passphrase"):
        keys.unlock(conn, lambda: "not the passphrase")


def test_passphrase_mode_requires_passphrase(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError):
        keys.create_key(conn, keys.KeyMode.PASSPHRASE, "")


def test_kdf_params_recorded_so_defaults_can_change(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = keys.create_key(conn, keys.KeyMode.PASSPHRASE, PASSPHRASE)
    monkeypatch.setattr(keys, "DEFAULT_SCRYPT", crypto.ScryptParams(n=2**11, r=8, p=1))
    assert keys.unlock(conn, lambda: PASSPHRASE) == key


def test_second_key_refused(conn: sqlite3.Connection) -> None:
    keys.create_key(conn, keys.KeyMode.KEYRING)
    with pytest.raises(RuntimeError):
        keys.create_key(conn, keys.KeyMode.KEYRING)


def test_unlock_without_key(conn: sqlite3.Connection) -> None:
    with pytest.raises(keys.UnlockError):
        keys.unlock(conn, _no_prompt)


def test_keyring_entry_removed_if_db_write_fails(
    conn: sqlite3.Connection, memory_keyring: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_: object) -> None:
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(keys, "set_meta", explode)
    with pytest.raises(sqlite3.OperationalError):
        keys.create_key(conn, keys.KeyMode.KEYRING)
    assert memory_keyring.entries == {}
    assert db.get_meta(conn, "key_mode") is None


def test_keyring_write_failure_is_user_facing(
    conn: sqlite3.Connection, memory_keyring: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_: object) -> None:
        raise KeyringError("locked")

    monkeypatch.setattr(memory_keyring, "set_password", refuse)
    with pytest.raises(keys.UnlockError, match="could not save"):
        keys.create_key(conn, keys.KeyMode.KEYRING)


class _PlaintextishKeyring(MemoryKeyring):
    priority = 0.5  # type: ignore[assignment]


def test_secure_keyring_detection() -> None:
    assert keys.secure_keyring_available()

    keyring.set_keyring(fail.Keyring())  # type: ignore[no-untyped-call]
    assert not keys.secure_keyring_available()

    keyring.set_keyring(_PlaintextishKeyring())
    assert not keys.secure_keyring_available()


def _no_prompt() -> str:
    raise AssertionError("keyring mode must not ask for a passphrase")
