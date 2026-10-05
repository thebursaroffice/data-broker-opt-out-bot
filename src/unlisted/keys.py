"""Data key management.

One random data key encrypts everything. It never touches disk in the clear:
either the OS keyring holds it, or it's stored in the database wrapped by a
key derived from the user's passphrase. Wrapping (rather than encrypting
data directly with the passphrase-derived key) means a passphrase change
only rewrites one small blob.
"""

import base64
import json
import logging
import sqlite3
import uuid
from collections.abc import Callable
from enum import StrEnum

import keyring
import keyring.errors
from keyring.backend import KeyringBackend
from keyring.backends import fail
from keyring.backends.chainer import ChainerBackend

from unlisted import crypto
from unlisted.db import get_meta, set_meta, transaction

log = logging.getLogger(__name__)

KEYRING_SERVICE = "unlisted"
# Overridable so tests can use cheap parameters; real stores record whatever
# was used at creation time, so changing this never breaks existing data.
DEFAULT_SCRYPT = crypto.ScryptParams()

_KEY_CHECK = b"unlisted-key-check"


class KeyMode(StrEnum):
    KEYRING = "keyring"
    PASSPHRASE = "passphrase"


class UnlockError(Exception):
    """The data key exists but couldn't be recovered. Message is user-facing."""


def secure_keyring_available() -> bool:
    backend = keyring.get_keyring()
    backends = backend.backends if isinstance(backend, ChainerBackend) else [backend]
    return any(_is_secure(b) for b in backends)


def _is_secure(backend: KeyringBackend) -> bool:
    # keyring rates its plaintext-file fallbacks below 1, and the fail backend
    # at 0. Storing the data key in a plaintext file would defeat the point.
    if isinstance(backend, fail.Keyring):
        return False
    return float(backend.priority) >= 1


def key_mode(conn: sqlite3.Connection) -> KeyMode | None:
    raw = get_meta(conn, "key_mode")
    return KeyMode(raw.decode()) if raw is not None else None


def create_key(conn: sqlite3.Connection, mode: KeyMode, passphrase: str | None = None) -> bytes:
    if key_mode(conn) is not None:
        raise RuntimeError("a data key already exists for this database")
    if mode is KeyMode.PASSPHRASE and not passphrase:
        raise ValueError("passphrase mode requires a passphrase")

    key = crypto.new_key()
    store_id = uuid.uuid4().hex

    if mode is KeyMode.KEYRING:
        try:
            keyring.set_password(KEYRING_SERVICE, _keyring_username(store_id), _b64(key))
        except keyring.errors.KeyringError as exc:
            raise UnlockError(
                f"could not save the encryption key to the system keyring: {exc}"
            ) from None

    try:
        with transaction(conn):
            set_meta(conn, "store_id", store_id.encode())
            set_meta(conn, "key_mode", mode.value.encode())
            set_meta(conn, "key_check", crypto.encrypt(key, _KEY_CHECK, "key-check"))
            if mode is KeyMode.PASSPHRASE:
                assert passphrase is not None
                salt = crypto.new_salt()
                params = DEFAULT_SCRYPT
                kek = crypto.derive_key(passphrase, salt, params)
                kdf = {
                    "name": "scrypt",
                    "n": params.n,
                    "r": params.r,
                    "p": params.p,
                    "salt": _b64(salt),
                }
                set_meta(conn, "kdf", json.dumps(kdf).encode())
                set_meta(conn, "wrapped_key", crypto.encrypt(kek, key, "wrapped-key"))
    except BaseException:
        # Don't leave an orphaned key in the keyring for a store that doesn't exist.
        if mode is KeyMode.KEYRING:
            _delete_keyring_entry(store_id)
        raise

    log.debug("created data key (mode=%s)", mode.value)
    return key


def unlock(conn: sqlite3.Connection, get_passphrase: Callable[[], str]) -> bytes:
    mode = key_mode(conn)
    store_id = _require_meta(conn, "store_id").decode()

    if mode is KeyMode.KEYRING:
        try:
            encoded = keyring.get_password(KEYRING_SERVICE, _keyring_username(store_id))
        except keyring.errors.KeyringError as exc:
            raise UnlockError(f"could not read the system keyring: {exc}") from None
        if encoded is None:
            raise UnlockError(
                "the encryption key for this profile is missing from the system keyring; "
                "without it the stored data can't be decrypted"
            )
        key = base64.b64decode(encoded)
    elif mode is KeyMode.PASSPHRASE:
        kdf = json.loads(_require_meta(conn, "kdf"))
        params = crypto.ScryptParams(n=kdf["n"], r=kdf["r"], p=kdf["p"])
        kek = crypto.derive_key(get_passphrase(), base64.b64decode(kdf["salt"]), params)
        try:
            key = crypto.decrypt(kek, _require_meta(conn, "wrapped_key"), "wrapped-key")
        except crypto.DecryptionError:
            raise UnlockError("wrong passphrase") from None
    else:
        raise UnlockError("no encryption key has been set up; run `unlisted profile init`")

    try:
        crypto.decrypt(key, _require_meta(conn, "key_check"), "key-check")
    except crypto.DecryptionError:
        raise UnlockError("the stored encryption key doesn't match this database") from None

    log.debug("unlocked data key (mode=%s)", mode.value)
    return key


def _require_meta(conn: sqlite3.Connection, name: str) -> bytes:
    value = get_meta(conn, name)
    if value is None:
        raise UnlockError(f"database is missing key metadata ({name}); it may be corrupted")
    return value


def _keyring_username(store_id: str) -> str:
    # Keyed per database so separate data dirs don't clobber each other's keys.
    return f"data-key:{store_id}"


def _delete_keyring_entry(store_id: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, _keyring_username(store_id))
    except keyring.errors.KeyringError:
        log.warning("could not remove an unused key from the system keyring")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
