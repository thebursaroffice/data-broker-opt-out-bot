from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.conftest import VALID_YAML, WriteBroker
from unlisted import __version__
from unlisted.cli import app

REPO_BROKERS = Path(__file__).resolve().parent.parent / "brokers"

# Wide enough that Rich never wraps table cells and breaks substring checks.
runner = CliRunner(env={"COLUMNS": "200"})


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_validate_passes_on_valid_dir(write_broker: WriteBroker) -> None:
    path = write_broker()
    result = runner.invoke(app, ["brokers", "validate", "--dir", str(path.parent)])
    assert result.exit_code == 0, result.output
    assert "1 valid, 0 invalid" in result.output


def test_validate_fails_with_line_specific_error(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("method: web_form", "method: webform"))
    result = runner.invoke(app, ["brokers", "validate", str(path)])
    assert result.exit_code == 1
    assert f"{path}:5:11: error: opt_out.method" in result.output
    assert "0 valid, 1 invalid" in result.output


def test_todo_is_warning_unless_strict(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("site: https://broker.example", "site: TODO_VERIFY"))

    lenient = runner.invoke(app, ["brokers", "validate", str(path)])
    assert lenient.exit_code == 0
    assert "warning: site: TODO_VERIFY" in lenient.output

    strict = runner.invoke(app, ["brokers", "validate", "--strict", str(path)])
    assert strict.exit_code == 1
    assert "error: site: TODO_VERIFY" in strict.output


def test_dir_from_env(write_broker: WriteBroker, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write_broker()
    monkeypatch.setenv("UNLISTED_BROKERS_DIR", str(path.parent))
    result = runner.invoke(app, ["brokers", "list"])
    assert result.exit_code == 0
    assert "fake-broker" in result.output


def test_list_shows_brokers_and_flags_skipped(write_broker: WriteBroker) -> None:
    path = write_broker()
    write_broker("name: [unclosed\n", "broken.yaml")
    result = runner.invoke(app, ["brokers", "list", "--dir", str(path.parent)])
    assert result.exit_code == 0
    assert "fake-broker" in result.output
    assert "web_form" in result.output
    assert "1 file(s) skipped" in result.output


def test_shipped_brokers_are_valid() -> None:
    result = runner.invoke(app, ["brokers", "validate", "--dir", str(REPO_BROKERS)])
    assert result.exit_code == 0, result.output
