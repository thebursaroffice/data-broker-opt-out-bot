import sqlite3
from contextlib import closing
from pathlib import Path

import keyring
import pytest
from keyring.backends import fail
from typer.testing import CliRunner, Result

from tests.conftest import FAKE_PROFILE
from unlisted import db, keys
from unlisted.cli import app
from unlisted.profile.cli import mask
from unlisted.profile.model import Profile
from unlisted.profile.store import load_profile

runner = CliRunner(env={"COLUMNS": "200"})

PASSPHRASE = "fake passphrase for tests"

# Answers to `profile init`, in prompt order, that produce FAKE_PROFILE.
INIT_ANSWERS = [
    "Testy",
    "Quux",
    "McFakeface",
    "Fakey McTestson",
    "123 Fakeway Lane",
    "Faketown",
    "ZZ",
    "00000",
    "Testlandia",
    "y",  # add a past address
    "456 Pretend Avenue",
    "Mocksville",
    "",
    "",
    "",
    "n",  # no more past addresses
    "+1 555-0100",
    "testy.mcfakeface@example.com",
    "1970-01-02",
]

# Accept every default in `profile edit`: 3 names, aliases, 5 address parts,
# keep past addresses, don't add one, phones, emails, dob.
KEEP_EVERYTHING = [""] * 14


def invoke(*args: str, answers: list[str] | None = None) -> Result:
    text = "\n".join(answers) + "\n" if answers is not None else None
    return runner.invoke(app, list(args), input=text)


def stored_profile(data_dir: Path, passphrase: str = "") -> Profile:
    with closing(db.connect(data_dir / "unlisted.db")) as conn:
        profile = load_profile(conn, keys.unlock(conn, lambda: passphrase))
    assert profile is not None
    return profile


def test_init_with_keyring(isolated_data_dir: Path) -> None:
    result = invoke("profile", "init", answers=INIT_ANSWERS)
    assert result.exit_code == 0, result.output
    assert "system keyring" in result.stdout
    assert stored_profile(isolated_data_dir) == FAKE_PROFILE


def test_init_with_passphrase(isolated_data_dir: Path) -> None:
    answers = [*INIT_ANSWERS, "too short", "too short", PASSPHRASE, PASSPHRASE]
    result = invoke("profile", "init", "--passphrase", answers=answers)
    assert result.exit_code == 0, result.output
    assert "at least 10 characters" in result.stdout
    assert stored_profile(isolated_data_dir, PASSPHRASE) == FAKE_PROFILE


def test_init_falls_back_to_passphrase_without_secure_keyring(isolated_data_dir: Path) -> None:
    keyring.set_keyring(fail.Keyring())  # type: ignore[no-untyped-call]
    result = invoke("profile", "init", answers=[*INIT_ANSWERS, PASSPHRASE, PASSPHRASE])
    assert result.exit_code == 0, result.output
    assert "No secure system keyring" in result.stdout
    assert stored_profile(isolated_data_dir, PASSPHRASE) == FAKE_PROFILE


def test_init_twice_refused() -> None:
    invoke("profile", "init", answers=INIT_ANSWERS)
    result = invoke("profile", "init", answers=INIT_ANSWERS)
    assert result.exit_code == 1
    assert "already exists" in result.stderr


def test_init_reuses_key_left_by_interrupted_init(isolated_data_dir: Path) -> None:
    with closing(db.connect(isolated_data_dir / "unlisted.db")) as conn:
        keys.create_key(conn, keys.KeyMode.KEYRING)
    result = invoke("profile", "init", answers=INIT_ANSWERS)
    assert result.exit_code == 0, result.output
    assert stored_profile(isolated_data_dir) == FAKE_PROFILE


def test_all_fields_optional(isolated_data_dir: Path) -> None:
    # Every text prompt blank, and decline the past-address prompt.
    answers = [""] * 9 + ["n"] + [""] * 3
    result = invoke("profile", "init", answers=answers)
    assert result.exit_code == 0, result.output
    assert stored_profile(isolated_data_dir) == Profile()


def test_invalid_entry_reprompts(isolated_data_dir: Path) -> None:
    answers = [*INIT_ANSWERS]
    answers[-2:-1] = ["not-an-email", "testy.mcfakeface@example.com"]
    answers[-1:] = ["1970-13-45", "1970-01-02"]
    result = invoke("profile", "init", answers=answers)
    assert result.exit_code == 0, result.output
    assert result.stdout.count("Try again") == 2
    assert stored_profile(isolated_data_dir) == FAKE_PROFILE


def test_show_masks_by_default() -> None:
    invoke("profile", "init", answers=INIT_ANSWERS)
    result = invoke("profile", "show")
    assert result.exit_code == 0, result.output
    assert "T**** Q*** M*********" in result.stdout
    assert "McFakeface" not in result.stdout
    assert "--reveal" in result.stdout


def test_show_reveal() -> None:
    invoke("profile", "init", answers=INIT_ANSWERS)
    result = invoke("profile", "show", "--reveal")
    assert result.exit_code == 0, result.output
    assert "Testy Quux McFakeface" in result.stdout
    assert "123 Fakeway Lane, Faketown, ZZ, 00000, Testlandia" in result.stdout
    assert "456 Pretend Avenue, Mocksville" in result.stdout


def test_show_before_init() -> None:
    result = invoke("profile", "show")
    assert result.exit_code == 1
    assert "profile init" in result.stderr


def test_show_wrong_passphrase() -> None:
    invoke("profile", "init", "--passphrase", answers=[*INIT_ANSWERS, PASSPHRASE, PASSPHRASE])
    result = invoke("profile", "show", answers=["not the passphrase"])
    assert result.exit_code == 1
    assert "wrong passphrase" in result.stderr
    assert "Traceback" not in result.output


def test_show_with_missing_keyring_entry(memory_keyring: object) -> None:
    invoke("profile", "init", answers=INIT_ANSWERS)
    keyring.get_keyring().entries.clear()  # type: ignore[attr-defined]
    result = invoke("profile", "show")
    assert result.exit_code == 1
    assert "missing from the system keyring" in result.stderr


def test_edit_without_changes(isolated_data_dir: Path) -> None:
    invoke("profile", "init", answers=INIT_ANSWERS)
    result = invoke("profile", "edit", answers=KEEP_EVERYTHING)
    assert result.exit_code == 0, result.output
    assert "No changes." in result.stdout
    assert stored_profile(isolated_data_dir) == FAKE_PROFILE


def test_edit_changes_and_clears_fields(isolated_data_dir: Path) -> None:
    invoke("profile", "init", answers=INIT_ANSWERS)
    answers = [*KEEP_EVERYTHING]
    answers[1] = "-"  # clear middle name
    answers[9] = "n"  # drop saved past addresses
    answers[12] = "fakey@example.com; testy.mcfakeface@example.com"
    result = invoke("profile", "edit", answers=answers)
    assert result.exit_code == 0, result.output
    assert "Profile updated." in result.stdout

    profile = stored_profile(isolated_data_dir)
    assert profile.middle_name is None
    assert profile.past_addresses == []
    assert profile.emails == ["fakey@example.com", "testy.mcfakeface@example.com"]
    assert profile.first_name == "Testy"


def test_data_dir_option(tmp_path: Path) -> None:
    custom = tmp_path / "elsewhere"
    result = invoke("--data-dir", str(custom), "profile", "init", answers=INIT_ANSWERS)
    assert result.exit_code == 0, result.output
    assert stored_profile(custom) == FAKE_PROFILE


def test_newer_database_refused(isolated_data_dir: Path) -> None:
    with closing(db.connect(isolated_data_dir / "unlisted.db")) as conn:
        conn.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + 1}")
    result = invoke("profile", "show")
    assert result.exit_code == 1
    assert "upgrade unlisted" in result.stderr


@pytest.mark.parametrize(
    ("value", "masked"),
    [
        ("Testy McFakeface", "T**** M*********"),
        ("testy.mcfakeface@example.com", "t****.m*********@e******.c**"),
        ("+1 555-0100", "+1 5**-0***"),
        ("1970-01-02", "1***-0*-0*"),
        ("Zoë Ångström", "Z** Å*******"),
    ],
)
def test_mask(value: str, masked: str) -> None:
    assert mask(value) == masked


def test_db_never_created_outside_data_dir(isolated_data_dir: Path, tmp_path: Path) -> None:
    invoke("profile", "init", answers=INIT_ANSWERS)
    created = {p.name for p in tmp_path.iterdir()}
    assert created == {isolated_data_dir.name}
    with closing(sqlite3.connect(isolated_data_dir / "unlisted.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 1
