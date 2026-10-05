"""Interactive field-by-field profile entry.

Prompting in the terminal instead of opening $EDITOR is deliberate: an editor
needs the plaintext profile in a temp file, which can outlive the process in
swap files, backups or editor history.
"""

from collections.abc import Callable
from datetime import date

import typer

from unlisted.profile.model import Address, Profile, check_dob, check_email, check_phone

CLEAR = "-"
LIST_SEPARATOR = ";"

Validator = Callable[[str], str]


def collect_profile(existing: Profile | None) -> Profile:
    p = existing or Profile()
    typer.echo(
        "Every field is optional. Press Enter to keep the value in [brackets] "
        f"or skip an empty field; enter {CLEAR} to clear a value."
    )
    typer.echo(f"For lists, separate entries with '{LIST_SEPARATOR}'.\n")

    first_name = ask_text("First name", p.first_name)
    middle_name = ask_text("Middle name", p.middle_name)
    last_name = ask_text("Last name", p.last_name)
    aliases = ask_list("Other names or aliases", p.aliases)
    current_address = ask_address("Current address", p.current_address)
    past_addresses = ask_past_addresses(p.past_addresses)
    phones = ask_list("Phone numbers", p.phones, check_phone)
    emails = ask_list("Email addresses", p.emails, check_email)
    dob = ask_date("Date of birth (YYYY-MM-DD)", p.dob)

    return Profile(
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        aliases=aliases,
        current_address=current_address,
        past_addresses=past_addresses,
        phones=phones,
        emails=emails,
        dob=dob,
    )


def ask_text(label: str, current: str | None, validate: Validator | None = None) -> str | None:
    while True:
        raw: str = typer.prompt(label, default=current or "", show_default=bool(current))
        raw = raw.strip()
        if not raw or raw == CLEAR:
            return None
        if validate is None:
            return raw
        try:
            return validate(raw)
        except ValueError as exc:
            typer.echo(f"  That {exc}. Try again.")


def ask_list(label: str, current: list[str], validate: Validator | None = None) -> list[str]:
    default = f"{LIST_SEPARATOR} ".join(current)
    while True:
        raw: str = typer.prompt(label, default=default, show_default=bool(default))
        raw = raw.strip()
        if not raw or raw == CLEAR:
            return []
        items = [item.strip() for item in raw.split(LIST_SEPARATOR) if item.strip()]
        if validate is None:
            return items
        try:
            return [validate(item) for item in items]
        except ValueError as exc:
            # Don't echo the rejected entry back; just say which list it was in.
            typer.echo(f"  One of the {label.lower()} {exc}. Try again.")


def ask_date(label: str, current: date | None) -> date | None:
    def parse(raw: str) -> str:
        try:
            value = date.fromisoformat(raw)
        except ValueError:
            raise ValueError("is not a date in YYYY-MM-DD form") from None
        check_dob(value)
        return raw

    raw = ask_text(label, current.isoformat() if current else None, parse)
    return date.fromisoformat(raw) if raw else None


def ask_address(title: str, current: Address | None) -> Address | None:
    typer.echo(f"{title}:")
    c = current or Address()
    address = Address(
        street=ask_text("  Street", c.street),
        city=ask_text("  City", c.city),
        state=ask_text("  State/region", c.state),
        zip=ask_text("  ZIP/postal code", c.zip),
        country=ask_text("  Country", c.country),
    )
    return None if address.is_empty() else address


def ask_past_addresses(current: list[Address]) -> list[Address]:
    kept: list[Address] = []
    if current and typer.confirm(f"Keep the {len(current)} saved past address(es)?", default=True):
        kept = list(current)
    while typer.confirm("Add a past address?", default=False):
        address = ask_address("Past address", None)
        if address is not None:
            kept.append(address)
    return kept
