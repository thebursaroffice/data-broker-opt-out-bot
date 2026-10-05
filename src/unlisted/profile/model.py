"""The user's identity: what we search brokers for and submit in opt-outs.

Every model here redacts itself in repr/str and hides input in validation
errors. That's the backstop for the most likely leak: someone adding
`log.debug("saving %s", profile)` or an exception message that echoes input.
"""

import re
from collections.abc import Iterator
from datetime import date
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Deliberately loose: brokers list numbers in every format, and international
# numbers vary too much for a stricter check to be worth the false rejections.
_PHONE_RE = re.compile(r"^\+?[0-9][0-9 ().\-]{5,}[0-9]$")


class _Private(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"

    def __str__(self) -> str:
        return repr(self)

    def __repr_args__(self) -> Iterator[tuple[str | None, Any]]:
        # Pydantic builds __rich_repr__ and pretty-printing from this.
        return iter(())


def check_email(value: str) -> str:
    if not _EMAIL_RE.match(value):
        raise ValueError("is not a valid email address")
    return value


def check_phone(value: str) -> str:
    if not _PHONE_RE.match(value):
        raise ValueError("is not a valid phone number")
    return value


def check_dob(value: date | None) -> date | None:
    if value is not None and not date(1900, 1, 1) <= value <= date.today():
        raise ValueError("must be between 1900-01-01 and today")
    return value


Text = Annotated[str, Field(min_length=1)]
Email = Annotated[str, AfterValidator(check_email)]
Phone = Annotated[str, AfterValidator(check_phone)]


class Address(_Private):
    street: Text | None = None
    city: Text | None = None
    state: Text | None = None
    zip: Text | None = None
    country: Text | None = None

    def is_empty(self) -> bool:
        return all(v is None for v in self.model_dump().values())

    def one_line(self) -> str:
        return ", ".join(v for v in self.model_dump().values() if v)


class Profile(_Private):
    first_name: Text | None = None
    middle_name: Text | None = None
    last_name: Text | None = None
    aliases: list[Text] = []
    current_address: Address | None = None
    past_addresses: list[Address] = []
    phones: list[Phone] = []
    emails: list[Email] = []
    dob: Annotated[date | None, AfterValidator(check_dob)] = None

    @property
    def full_name(self) -> str | None:
        parts = [p for p in (self.first_name, self.middle_name, self.last_name) if p]
        return " ".join(parts) or None
