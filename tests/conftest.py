import sqlite3
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from unlisted import db, keys
from unlisted.crypto import ScryptParams
from unlisted.profile.model import Address, Profile

# Line numbers below are asserted in tests; edit with care.
VALID_YAML = """\
schema_version: 1
name: Fake Broker
site: https://broker.example
opt_out:
  method: web_form
  url: https://broker.example/opt-out
required_fields:
  - first_name
  - last_name
verification: email
relist_interval_days: 30
last_verified: 2025-01-15
"""

WriteBroker = Callable[..., Path]


@pytest.fixture
def write_broker(tmp_path: Path) -> WriteBroker:
    def _write(text: str = VALID_YAML, name: str = "fake-broker.yaml") -> Path:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    return _write


class MemoryKeyring(KeyringBackend):
    """Stands in for the OS keyring so tests never read or write the real one."""

    priority = 10

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.entries: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.entries.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.entries[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.entries.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def memory_keyring() -> Iterator[MemoryKeyring]:
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Belt and braces: even a test that forgets --data-dir can't touch real user data.
    data_dir = tmp_path / "data"
    monkeypatch.setenv("UNLISTED_DATA_DIR", str(data_dir))
    return data_dir


@pytest.fixture(autouse=True)
def fast_scrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keys, "DEFAULT_SCRYPT", ScryptParams(n=2**10, r=8, p=1))


@pytest.fixture
def conn(isolated_data_dir: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(isolated_data_dir / "unlisted.db")
    yield connection
    connection.close()


# An obviously fictional identity. Every value is distinctive enough that
# finding it in a byte dump or log line can only mean a leak.
FAKE_PROFILE = Profile(
    first_name="Testy",
    middle_name="Quux",
    last_name="McFakeface",
    aliases=["Fakey McTestson"],
    current_address=Address(
        street="123 Fakeway Lane",
        city="Faketown",
        state="ZZ",
        zip="00000",
        country="Testlandia",
    ),
    past_addresses=[Address(street="456 Pretend Avenue", city="Mocksville")],
    phones=["+1 555-0100"],
    emails=["testy.mcfakeface@example.com"],
    dob=date(1970, 1, 2),
)

# Values long or odd enough not to appear by coincidence in binary data or output.
FAKE_SECRETS = [
    "Testy",
    "Quux",
    "McFakeface",
    "Fakey McTestson",
    "123 Fakeway Lane",
    "Faketown",
    "Testlandia",
    "456 Pretend Avenue",
    "Mocksville",
    "555-0100",
    "testy.mcfakeface@example.com",
    "1970-01-02",
]
