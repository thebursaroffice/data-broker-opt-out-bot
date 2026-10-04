"""Schema for broker definition files in brokers/*.yaml.

These files are written by contributors who may never touch the Python code, so
validation errors need to be specific and the format needs to stay boring.
"""

import re
import string
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

# Marks a value nobody has confirmed against the live site yet. Kept as a plain
# string so it survives round-trips through any YAML tooling a contributor uses.
TODO_VERIFY = "TODO_VERIFY"

# Only values a search page could plausibly need. Anything broader (DOB, phone)
# would put more of the profile into URLs than a relist check justifies.
SEARCH_PLACEHOLDERS = frozenset({"first_name", "last_name", "city", "state"})

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OptOutMethod(StrEnum):
    WEB_FORM = "web_form"
    EMAIL = "email"
    LEGAL_REQUEST = "legal_request"
    MANUAL = "manual"


class Verification(StrEnum):
    NONE = "none"
    EMAIL = "email"
    PHONE = "phone"
    ID_UPLOAD = "id_upload"


class ProfileField(StrEnum):
    # These names double as profile keys, so renaming one is a breaking change
    # for every broker file that references it.
    FULL_NAME = "full_name"
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    ALIASES = "aliases"
    CURRENT_ADDRESS = "current_address"
    PAST_ADDRESSES = "past_addresses"
    CITY = "city"
    STATE = "state"
    ZIP = "zip"
    PHONE = "phone"
    EMAIL = "email"
    DOB = "dob"
    LISTING_URL = "listing_url"


def _check_https_url(value: str) -> str:
    if value == TODO_VERIFY:
        return value
    parts = urlsplit(value)
    # Plain http is rejected outright: these URLs receive the user's personal info.
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError(f"must be an https:// URL or {TODO_VERIFY}")
    return value


def _check_email(value: str) -> str:
    if value == TODO_VERIFY or _EMAIL_RE.match(value):
        return value
    raise ValueError(f"must be an email address or {TODO_VERIFY}")


def _check_search_pattern(value: str) -> str:
    if value == TODO_VERIFY:
        return value
    try:
        names = {name for _, name, _, _ in string.Formatter().parse(value) if name is not None}
    except ValueError as exc:
        raise ValueError(f"has unbalanced braces ({exc})") from None
    unknown = sorted(names - SEARCH_PLACEHOLDERS)
    if unknown:
        allowed = ", ".join("{" + p + "}" for p in sorted(SEARCH_PLACEHOLDERS))
        found = ", ".join("{" + p + "}" for p in unknown)
        raise ValueError(f"uses unknown placeholder(s) {found}; allowed: {allowed}")
    return _check_https_url(value)


def _check_unique(values: list[ProfileField]) -> list[ProfileField]:
    seen: set[ProfileField] = set()
    dupes: set[str] = set()
    for v in values:
        if v in seen:
            dupes.add(v.value)
        seen.add(v)
    if dupes:
        raise ValueError(f"lists {', '.join(sorted(dupes))} more than once")
    return values


def _check_not_future(value: date | None) -> date | None:
    if value is not None and value > date.today():
        raise ValueError("is in the future")
    return value


HttpsUrl = Annotated[str, AfterValidator(_check_https_url)]
EmailAddress = Annotated[str, AfterValidator(_check_email)]
NonEmptyStr = Annotated[str, Field(min_length=1)]


class OptOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: OptOutMethod
    url: HttpsUrl | None = None
    email: EmailAddress | None = None

    @model_validator(mode="after")
    def _method_has_target(self) -> Self:
        if self.method is OptOutMethod.WEB_FORM and self.url is None:
            raise ValueError("'url' is required when method is web_form")
        if self.method is OptOutMethod.EMAIL and self.email is None:
            raise ValueError("'email' is required when method is email")
        return self


class Broker(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    name: NonEmptyStr
    site: HttpsUrl
    opt_out: OptOut
    required_fields: Annotated[list[ProfileField], AfterValidator(_check_unique)]
    verification: Verification
    search_url_pattern: Annotated[str, AfterValidator(_check_search_pattern)] | None = None
    # strict so YAML like `relist_interval_days: true` doesn't quietly become 1.
    relist_interval_days: Annotated[int, Field(strict=True, ge=1, le=3650)]
    notes: str | None = None
    last_verified: Annotated[date | None, AfterValidator(_check_not_future)] = None
