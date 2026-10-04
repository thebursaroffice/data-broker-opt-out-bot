from datetime import date, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from unlisted.brokers.schema import TODO_VERIFY, Broker, OptOutMethod


def broker_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": 1,
        "name": "Fake Broker",
        "site": "https://broker.example",
        "opt_out": {"method": "web_form", "url": "https://broker.example/opt-out"},
        "required_fields": ["first_name", "last_name"],
        "verification": "email",
        "relist_interval_days": 30,
    }
    data.update(overrides)
    return data


def error_messages(exc: pytest.ExceptionInfo[ValidationError]) -> str:
    return " | ".join(e["msg"] for e in exc.value.errors())


def test_valid_broker() -> None:
    broker = Broker.model_validate(broker_data())
    assert broker.opt_out.method is OptOutMethod.WEB_FORM
    assert broker.last_verified is None


def test_todo_verify_accepted_for_urls_and_email() -> None:
    broker = Broker.model_validate(
        broker_data(
            site=TODO_VERIFY,
            opt_out={"method": "email", "email": TODO_VERIFY},
            search_url_pattern=TODO_VERIFY,
        )
    )
    assert broker.site == TODO_VERIFY


def test_web_form_requires_url() -> None:
    with pytest.raises(ValidationError) as exc:
        Broker.model_validate(broker_data(opt_out={"method": "web_form"}))
    assert "'url' is required" in error_messages(exc)


def test_email_method_requires_email() -> None:
    with pytest.raises(ValidationError) as exc:
        Broker.model_validate(broker_data(opt_out={"method": "email"}))
    assert "'email' is required" in error_messages(exc)


def test_http_url_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        Broker.model_validate(broker_data(site="http://broker.example"))
    assert "https://" in error_messages(exc)


def test_search_pattern_rejects_unknown_placeholder() -> None:
    with pytest.raises(ValidationError) as exc:
        Broker.model_validate(
            broker_data(search_url_pattern="https://broker.example/s?q={first_name}&d={dob}")
        )
    assert "{dob}" in error_messages(exc)


def test_search_pattern_accepts_known_placeholders() -> None:
    pattern = "https://broker.example/{first_name}-{last_name}/{state}/{city}"
    assert Broker.model_validate(broker_data(search_url_pattern=pattern)).search_url_pattern


def test_search_pattern_rejects_unbalanced_braces() -> None:
    with pytest.raises(ValidationError) as exc:
        Broker.model_validate(broker_data(search_url_pattern="https://broker.example/{first_name"))
    assert "unbalanced" in error_messages(exc)


def test_duplicate_required_fields_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        Broker.model_validate(broker_data(required_fields=["phone", "email", "phone"]))
    assert "phone more than once" in error_messages(exc)


def test_extra_key_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        Broker.model_validate(broker_data(website="https://broker.example"))
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_relist_interval_must_be_real_int() -> None:
    for bad in (True, "30", 0, 5000):
        with pytest.raises(ValidationError):
            Broker.model_validate(broker_data(relist_interval_days=bad))


def test_last_verified_cannot_be_future() -> None:
    tomorrow = date.today() + timedelta(days=1)
    with pytest.raises(ValidationError) as exc:
        Broker.model_validate(broker_data(last_verified=tomorrow))
    assert "future" in error_messages(exc)


def test_unknown_schema_version_rejected() -> None:
    with pytest.raises(ValidationError):
        Broker.model_validate(broker_data(schema_version=2))
