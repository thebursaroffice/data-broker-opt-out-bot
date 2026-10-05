import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from rich.console import Console

from tests.conftest import FAKE_PROFILE, FAKE_SECRETS
from unlisted import crypto, keys
from unlisted.profile.model import Profile
from unlisted.profile.store import has_profile, load_profile, save_profile


def test_roundtrip(conn: sqlite3.Connection) -> None:
    key = keys.create_key(conn, keys.KeyMode.KEYRING)
    assert not has_profile(conn)
    save_profile(conn, key, FAKE_PROFILE)
    assert has_profile(conn)
    assert load_profile(conn, key) == FAKE_PROFILE


def test_overwrite_keeps_single_row(conn: sqlite3.Connection) -> None:
    key = keys.create_key(conn, keys.KeyMode.KEYRING)
    save_profile(conn, key, FAKE_PROFILE)
    save_profile(conn, key, FAKE_PROFILE.model_copy(update={"middle_name": None}))
    assert conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 1
    loaded = load_profile(conn, key)
    assert loaded is not None and loaded.middle_name is None


def test_wrong_key_cannot_read(conn: sqlite3.Connection) -> None:
    key = keys.create_key(conn, keys.KeyMode.KEYRING)
    save_profile(conn, key, FAKE_PROFILE)
    with pytest.raises(crypto.DecryptionError):
        load_profile(conn, crypto.new_key())


@pytest.mark.parametrize("mode", list(keys.KeyMode))
def test_database_file_contains_no_plaintext(
    conn: sqlite3.Connection, isolated_data_dir: Path, mode: keys.KeyMode
) -> None:
    key = keys.create_key(conn, mode, "fake passphrase for tests")
    save_profile(conn, key, FAKE_PROFILE)
    # Save twice so any page SQLite rewrote still contains only ciphertext.
    save_profile(conn, key, FAKE_PROFILE.model_copy(update={"aliases": ["Other Fakename"]}))
    conn.close()

    files = list(isolated_data_dir.iterdir())
    assert files, "expected database files on disk"
    for path in files:
        raw = path.read_bytes()
        for secret in [*FAKE_SECRETS, "Other Fakename"]:
            assert secret.encode() not in raw, f"{secret!r} found in {path.name}"
            assert secret.encode("utf-16-le") not in raw


def test_repr_and_str_are_redacted() -> None:
    rendered = [repr(FAKE_PROFILE), str(FAKE_PROFILE), f"{FAKE_PROFILE}"]
    rendered.append(repr(FAKE_PROFILE.current_address))
    console = Console(record=True, width=200)
    console.print(FAKE_PROFILE)
    rendered.append(console.export_text())
    for text in rendered:
        for secret in FAKE_SECRETS:
            assert secret not in text


def test_validation_errors_do_not_echo_input() -> None:
    with pytest.raises(ValidationError) as exc:
        Profile(emails=["testy.mcfakeface-at-example.com"], phones=["Faketown"])
    assert "testy.mcfakeface" not in str(exc.value)
    assert "Faketown" not in str(exc.value)


def test_future_dob_rejected() -> None:
    with pytest.raises(ValidationError):
        Profile(dob=date.today() + timedelta(days=1))


def test_full_name() -> None:
    assert FAKE_PROFILE.full_name == "Testy Quux McFakeface"
    assert Profile().full_name is None
