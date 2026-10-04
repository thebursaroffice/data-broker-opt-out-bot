from pathlib import Path

import pytest

from tests.conftest import VALID_YAML, WriteBroker
from unlisted.brokers.loader import BrokerFileError, Issue, load_broker, load_registry


def issues_for(path: Path) -> list[Issue]:
    with pytest.raises(BrokerFileError) as exc:
        load_broker(path)
    return exc.value.issues


def only_issue(path: Path) -> Issue:
    issues = issues_for(path)
    assert len(issues) == 1, [str(i) for i in issues]
    return issues[0]


def test_valid_file_loads(write_broker: WriteBroker) -> None:
    loaded = load_broker(write_broker())
    assert loaded.id == "fake-broker"
    assert loaded.broker.name == "Fake Broker"
    assert loaded.todos == []


def test_yaml_syntax_error_has_line(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("name: Fake Broker", "name: Fake: Broker"))
    issue = only_issue(path)
    assert issue.line == 2
    assert "mapping values are not allowed" in issue.message


def test_tab_indentation_has_line(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("  method: web_form", "\tmethod: web_form"))
    issue = only_issue(path)
    assert issue.line == 5
    assert issue.message.startswith("invalid YAML")


def test_wrong_enum_points_at_value(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("method: web_form", "method: webform"))
    issue = only_issue(path)
    assert (issue.line, issue.column) == (5, 11)
    assert issue.loc == "opt_out.method"
    assert "'web_form'" in issue.message and "'webform'" in issue.message


def test_unknown_key_points_at_key_and_suggests(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("verification: email", "verificaton: email"))
    issues = issues_for(path)
    unknown = next(i for i in issues if "unknown field" in i.message)
    assert (unknown.line, unknown.column) == (10, 1)
    assert "did you mean 'verification'" in unknown.message


def test_unknown_nested_key_suggests_from_nested_model(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("  url: https", "  ur1: https"))
    unknown = next(i for i in issues_for(path) if "unknown field" in i.message)
    assert (unknown.line, unknown.column) == (6, 3)
    assert "did you mean 'url'" in unknown.message


def test_missing_top_level_field(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("verification: email\n", ""))
    issue = only_issue(path)
    assert issue.line == 1
    assert issue.message == "missing required field 'verification'"


def test_missing_nested_field_points_at_parent(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("  method: web_form\n", ""))
    issue = only_issue(path)
    assert issue.line == 4
    assert issue.loc == "opt_out"
    assert "'method'" in issue.message


def test_cross_field_rule_points_at_parent_key(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("  url: https://broker.example/opt-out\n", ""))
    issue = only_issue(path)
    assert issue.line == 4
    assert "'url' is required" in issue.message


def test_duplicate_key_reported(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML + "name: Another Fake Broker\n")
    issue = only_issue(path)
    assert issue.line == 13
    assert "duplicate key 'name'" in issue.message
    assert "line 2" in issue.message


def test_invalid_date_has_line(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("2025-01-15", "2025-13-01"))
    issue = only_issue(path)
    assert issue.line == 12
    assert "YYYY-MM-DD" in issue.message


def test_bad_list_item_points_at_item(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("  - last_name", "  - phone_number"))
    issue = only_issue(path)
    assert (issue.line, issue.column) == (9, 5)
    assert issue.loc == "required_fields[1]"


def test_quoted_int_rejected_with_line(write_broker: WriteBroker) -> None:
    text = VALID_YAML.replace("relist_interval_days: 30", 'relist_interval_days: "30"')
    path = write_broker(text)
    issue = only_issue(path)
    assert issue.line == 11


def test_top_level_must_be_mapping(write_broker: WriteBroker) -> None:
    issue = only_issue(write_broker("- one\n- two\n"))
    assert issue.line == 1
    assert "mapping" in issue.message


def test_empty_file(write_broker: WriteBroker) -> None:
    assert only_issue(write_broker("# nothing here\n")).message == "file is empty"


def test_bad_filename_reported_alongside_content_errors(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("method: web_form", "method: nope"), "Bad_Name.yaml")
    messages = [i.message for i in issues_for(path)]
    assert any("filename 'Bad_Name.yaml'" in m for m in messages)
    assert any("must be one of" in m for m in messages)


def test_multiple_errors_all_reported_in_line_order(write_broker: WriteBroker) -> None:
    text = VALID_YAML.replace("method: web_form", "method: nope").replace(
        "verification: email", "verification: carrier_pigeon"
    )
    lines = [i.line for i in issues_for(write_broker(text))]
    assert lines == [5, 10]


def test_todo_markers_become_located_warnings(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("site: https://broker.example", "site: TODO_VERIFY"))
    todos = load_broker(path).todos
    assert len(todos) == 1
    assert (todos[0].line, todos[0].loc, todos[0].severity) == (3, "site", "warning")


def test_issue_string_format(write_broker: WriteBroker) -> None:
    path = write_broker(VALID_YAML.replace("method: web_form", "method: webform"))
    assert str(only_issue(path)).startswith(f"{path}:5:11: error: opt_out.method: must be one of")


def test_registry_collects_errors_from_every_file(write_broker: WriteBroker) -> None:
    good = write_broker(name="good-broker.yaml")
    write_broker(VALID_YAML.replace("method: web_form", "method: nope"), "bad-one.yaml")
    write_broker("name: [unclosed\n", "bad-two.yaml")
    loaded, issues = load_registry(good.parent)
    assert [b.id for b in loaded] == ["good-broker"]
    assert {i.path.name for i in issues} == {"bad-one.yaml", "bad-two.yaml"}


def test_registry_rejects_same_id_with_different_extensions(write_broker: WriteBroker) -> None:
    path = write_broker(name="fake-broker.yaml")
    write_broker(name="fake-broker.yml")
    loaded, issues = load_registry(path.parent)
    assert len(loaded) == 1
    assert "already defined" in issues[0].message


def test_registry_missing_directory(tmp_path: Path) -> None:
    loaded, issues = load_registry(tmp_path / "nope")
    assert loaded == []
    assert issues[0].message == "broker directory not found"
