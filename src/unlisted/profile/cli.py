import re
import sqlite3
from contextlib import closing
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from unlisted import crypto, db, keys
from unlisted.paths import AppContext
from unlisted.profile.model import Profile
from unlisted.profile.prompts import collect_profile
from unlisted.profile.store import has_profile, load_profile, save_profile

app = typer.Typer(help="Manage your encrypted local profile.", no_args_is_help=True)

MIN_PASSPHRASE_LENGTH = 10
_EMPTY = "—"


@app.command("init")
def init(
    ctx: typer.Context,
    passphrase: Annotated[
        bool,
        typer.Option(
            "--passphrase",
            help="Protect the profile with a passphrase instead of the system keyring.",
        ),
    ] = False,
) -> None:
    """Create your profile. Everything is encrypted before it's written to disk."""
    with closing(_open(ctx)) as conn:
        if has_profile(conn):
            _fail("A profile already exists. Use `unlisted profile edit` to change it.")

        mode = keys.key_mode(conn)
        if mode is None:
            if passphrase:
                mode = keys.KeyMode.PASSPHRASE
            elif keys.secure_keyring_available():
                mode = keys.KeyMode.KEYRING
            else:
                mode = keys.KeyMode.PASSPHRASE
                typer.echo("No secure system keyring found; your profile will need a passphrase.")
            profile = collect_profile(None)
            secret = _new_passphrase() if mode is keys.KeyMode.PASSPHRASE else None
            try:
                key = keys.create_key(conn, mode, secret)
            except keys.UnlockError as exc:
                _fail(str(exc))
        else:
            # A previous init got as far as creating the key but not saving
            # the profile; reuse the key rather than orphaning it.
            key = _unlock(conn)
            profile = collect_profile(None)

        save_profile(conn, key, profile)
    where = "system keyring" if mode is keys.KeyMode.KEYRING else "your passphrase"
    typer.echo(f"Profile saved. It's encrypted with a key protected by {where}.")


@app.command("show")
def show(
    ctx: typer.Context,
    reveal: Annotated[
        bool, typer.Option("--reveal", help="Show values in full instead of masked.")
    ] = False,
) -> None:
    """Display your profile. Values are masked unless --reveal is given."""
    with closing(_open(ctx)) as conn:
        profile = _load(conn)

    out = Console(highlight=False)
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    for label, values in _rows(profile):
        shown = [v if reveal else mask(v) for v in values]
        table.add_row(label, Text("\n".join(shown) if shown else _EMPTY))
    out.print(table)
    if not reveal:
        out.print("\nValues are masked. Use --reveal to show them in full.", style="dim")


@app.command("edit")
def edit(ctx: typer.Context) -> None:
    """Change your profile, one field at a time."""
    with closing(_open(ctx)) as conn:
        key, profile = _unlock_and_load(conn)
        updated = collect_profile(profile)
        if updated == profile:
            typer.echo("No changes.")
            return
        save_profile(conn, key, updated)
    typer.echo("Profile updated.")


def mask(value: str) -> str:
    """Keep the first character of each word, star the rest.

    Enough to recognize your own data at a glance, not enough for someone
    reading over your shoulder or a screen share.
    """
    return re.sub(r"[^\W_]+", lambda m: m.group()[0] + "*" * (len(m.group()) - 1), value)


def _rows(profile: Profile) -> list[tuple[str, list[str]]]:
    current = profile.current_address
    return [
        ("Name", [profile.full_name] if profile.full_name else []),
        ("Aliases", profile.aliases),
        ("Current address", [current.one_line()] if current else []),
        ("Past addresses", [a.one_line() for a in profile.past_addresses]),
        ("Phones", profile.phones),
        ("Emails", profile.emails),
        ("Date of birth", [profile.dob.isoformat()] if profile.dob else []),
    ]


def _open(ctx: typer.Context) -> sqlite3.Connection:
    app_ctx = ctx.obj
    if not isinstance(app_ctx, AppContext):
        raise RuntimeError("profile commands must run under the root unlisted command")
    try:
        return db.connect(app_ctx.db_path)
    except db.SchemaTooNewError as exc:
        _fail(str(exc))


def _load(conn: sqlite3.Connection) -> Profile:
    return _unlock_and_load(conn)[1]


def _unlock_and_load(conn: sqlite3.Connection) -> tuple[bytes, Profile]:
    if not has_profile(conn):
        _fail("No profile yet. Run `unlisted profile init` first.")
    key = _unlock(conn)
    try:
        profile = load_profile(conn, key)
    except crypto.DecryptionError:
        _fail("The stored profile could not be decrypted; the database may be corrupted.")
    assert profile is not None
    return key, profile


def _unlock(conn: sqlite3.Connection) -> bytes:
    try:
        return keys.unlock(conn, lambda: typer.prompt("Passphrase", hide_input=True))
    except keys.UnlockError as exc:
        _fail(str(exc))


def _new_passphrase() -> str:
    while True:
        value: str = typer.prompt("Choose a passphrase", hide_input=True, confirmation_prompt=True)
        if len(value) >= MIN_PASSPHRASE_LENGTH:
            return value
        typer.echo(f"Use at least {MIN_PASSPHRASE_LENGTH} characters.")


def _fail(message: str) -> NoReturn:
    Console(stderr=True, highlight=False).print(message, style="red", markup=False)
    raise typer.Exit(code=1)
