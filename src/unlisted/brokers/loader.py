"""Load broker YAML files and report problems against the exact line they came from.

PyYAML's safe_load throws away source positions, so we compose the node tree
ourselves, keep it around, and walk it to translate Pydantic error locations
back into line/column numbers.
"""

import difflib
import os
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

from unlisted.brokers.schema import TODO_VERIFY, Broker

BROKERS_DIR_ENV = "UNLISTED_BROKERS_DIR"

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    path: Path
    message: str
    line: int | None = None
    column: int | None = None
    loc: str = ""
    severity: Severity = "error"

    def __str__(self) -> str:
        where = str(self.path)
        if self.line is not None:
            where += f":{self.line}"
            if self.column is not None:
                where += f":{self.column}"
        field_part = f"{self.loc}: " if self.loc else ""
        return f"{where}: {self.severity}: {field_part}{self.message}"


@dataclass(frozen=True)
class LoadedBroker:
    id: str
    path: Path
    broker: Broker
    todos: list[Issue] = field(default_factory=list)


class BrokerFileError(Exception):
    def __init__(self, issues: list[Issue]) -> None:
        super().__init__("\n".join(str(i) for i in issues))
        self.issues = issues


class _Loader(yaml.SafeLoader):
    """SafeLoader that leaves dates as strings.

    The stock loader converts `2025-13-01` into a date during construction and
    raises a bare ValueError with no position. Leaving it as a string lets
    Pydantic reject it, and that error we can place on a line.
    """

    yaml_implicit_resolvers = {
        first: [(tag, regexp) for tag, regexp in resolvers if tag != _TIMESTAMP_TAG]
        for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }


def default_brokers_dir() -> Path:
    env = os.environ.get(BROKERS_DIR_ENV)
    return Path(env) if env else Path("brokers")


def load_broker(path: Path) -> LoadedBroker:
    issues: list[Issue] = []
    broker_id = path.stem
    if not _SLUG_RE.match(broker_id):
        issues.append(
            Issue(
                path,
                f"filename '{path.name}' must be lowercase letters, digits and single "
                "hyphens (e.g. acme-people-search.yaml); it becomes the broker id",
            )
        )

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise BrokerFileError([*issues, Issue(path, "file is not valid UTF-8")]) from None

    loader = _Loader(text)
    try:
        root = loader.get_single_node()
        data = loader.construct_document(root) if root is not None else None
    except yaml.MarkedYAMLError as exc:
        raise BrokerFileError([*issues, _yaml_error_issue(path, exc)]) from None
    finally:
        loader.dispose()

    if root is None:
        raise BrokerFileError([*issues, Issue(path, "file is empty")])
    if not isinstance(root, yaml.MappingNode) or not isinstance(data, dict):
        issues.append(
            Issue(
                path,
                "top level must be a mapping of `field: value` lines",
                *_position(root.start_mark),
            )
        )
        raise BrokerFileError(issues)

    issues.extend(_duplicate_keys(path, root))

    broker: Broker | None = None
    try:
        broker = Broker.model_validate(data)
    except ValidationError as exc:
        issues.extend(_validation_issue(path, root, err) for err in exc.errors())

    if issues or broker is None:
        raise BrokerFileError(sorted(issues, key=_sort_key))
    return LoadedBroker(id=broker_id, path=path, broker=broker, todos=_todo_markers(path, root))


def load_registry(
    directory: Path, files: Sequence[Path] | None = None
) -> tuple[list[LoadedBroker], list[Issue]]:
    """Load every broker file, collecting all problems rather than stopping at the first."""
    if files is None:
        if not directory.is_dir():
            return [], [Issue(directory, "broker directory not found")]
        files = sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")])

    loaded: list[LoadedBroker] = []
    issues: list[Issue] = []
    seen: dict[str, Path] = {}
    for path in files:
        if path.stem in seen:
            issues.append(
                Issue(path, f"broker id '{path.stem}' is already defined by {seen[path.stem]}")
            )
            continue
        seen[path.stem] = path
        try:
            loaded.append(load_broker(path))
        except BrokerFileError as exc:
            issues.extend(exc.issues)
        except OSError as exc:
            issues.append(Issue(path, f"cannot read file ({exc.strerror})"))
    return loaded, issues


def _position(mark: yaml.Mark | None) -> tuple[int | None, int | None]:
    if mark is None:
        return None, None
    return mark.line + 1, mark.column + 1


def _sort_key(issue: Issue) -> tuple[int, int]:
    return issue.line or 0, issue.column or 0


def _yaml_error_issue(path: Path, exc: yaml.MarkedYAMLError) -> Issue:
    problem = exc.problem or "invalid YAML"
    if exc.context:
        problem = f"{exc.context}, {problem}"
    mark = exc.problem_mark or exc.context_mark
    return Issue(path, f"invalid YAML: {problem}", *_position(mark))


def _iter_mapping(node: yaml.MappingNode) -> Iterator[tuple[str, yaml.Node, yaml.Node]]:
    for key_node, value_node in node.value:
        key = key_node.value if isinstance(key_node, yaml.ScalarNode) else str(key_node.value)
        yield key, key_node, value_node


def _children(node: yaml.Node) -> Iterator[tuple[str | int, yaml.Node]]:
    if isinstance(node, yaml.MappingNode):
        for key, _, value in _iter_mapping(node):
            yield key, value
    elif isinstance(node, yaml.SequenceNode):
        yield from enumerate(node.value)


def _duplicate_keys(path: Path, node: yaml.Node, prefix: str = "") -> list[Issue]:
    # PyYAML keeps the last value for a repeated key without complaint, which
    # would silently drop whatever the contributor wrote first.
    issues: list[Issue] = []
    if isinstance(node, yaml.MappingNode):
        first_line: dict[str, int] = {}
        for key, key_node, _ in _iter_mapping(node):
            line, col = _position(key_node.start_mark)
            if key in first_line:
                issues.append(
                    Issue(
                        path,
                        f"duplicate key '{key}' (first defined on line {first_line[key]})",
                        line,
                        col,
                        loc=_join(prefix, key),
                    )
                )
            else:
                first_line[key] = line or 0
    for child_key, child in _children(node):
        issues.extend(_duplicate_keys(path, child, _join(prefix, child_key)))
    return issues


def _todo_markers(path: Path, node: yaml.Node, prefix: str = "") -> list[Issue]:
    if isinstance(node, yaml.ScalarNode):
        if isinstance(node.value, str) and TODO_VERIFY in node.value:
            return [
                Issue(
                    path,
                    f"{TODO_VERIFY} placeholder still present",
                    *_position(node.start_mark),
                    loc=prefix,
                    severity="warning",
                )
            ]
        return []
    found: list[Issue] = []
    for key, child in _children(node):
        found.extend(_todo_markers(path, child, _join(prefix, key)))
    return found


def _join(prefix: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{prefix}[{key}]"
    return f"{prefix}.{key}" if prefix else key


def _locate(root: yaml.Node, loc: Sequence[str | int]) -> tuple[yaml.Node, yaml.Node | None]:
    """Follow a Pydantic loc into the node tree as far as it goes.

    Returns the deepest value node reached and, if the last step was a mapping
    key, that key's node. Stopping early is fine: pointing at the parent is
    still more useful than no line number at all.
    """
    node, key_node = root, None
    for part in loc:
        next_node: yaml.Node | None = None
        if isinstance(node, yaml.MappingNode):
            for key, kn, vn in _iter_mapping(node):
                if key == str(part):
                    next_node, key_node = vn, kn
                    break
        elif (
            isinstance(node, yaml.SequenceNode)
            and isinstance(part, int)
            and 0 <= part < len(node.value)
        ):
            next_node, key_node = node.value[part], None
        if next_node is None:
            break
        node = next_node
    return node, key_node


def _validation_issue(path: Path, root: yaml.Node, err: ErrorDetails) -> Issue:
    loc = tuple(err["loc"])
    kind = err["type"]

    if kind == "missing":
        # Point at the `parent:` line for nested fields. Top-level fields have
        # no natural home, so they go to the start of the document.
        mark = root.start_mark
        if loc[:-1]:
            parent, parent_key = _locate(root, loc[:-1])
            mark = (parent_key or parent).start_mark
        return Issue(
            path,
            f"missing required field '{loc[-1]}'",
            *_position(mark),
            loc=_loc_str(loc[:-1]),
        )

    node, key_node = _locate(root, loc)
    if kind == "extra_forbidden":
        target = key_node or node
        return Issue(
            path,
            _unknown_field_message(str(loc[-1]), loc[:-1]),
            *_position(target.start_mark),
            loc=_loc_str(loc),
        )

    # A block mapping's own mark is its first child's line, which reads as if
    # that child were at fault. The key line is what the contributor expects.
    target = key_node if key_node is not None and not isinstance(node, yaml.ScalarNode) else node
    return Issue(path, _friendly_message(err), *_position(target.start_mark), loc=_loc_str(loc))


def _loc_str(loc: Sequence[str | int]) -> str:
    out = ""
    for part in loc:
        out = _join(out, part)
    return out


def _model_at(loc: Sequence[str | int]) -> type[BaseModel] | None:
    model: type[BaseModel] = Broker
    for part in loc:
        info = model.model_fields.get(str(part))
        annotation = info.annotation if info else None
        if not (isinstance(annotation, type) and issubclass(annotation, BaseModel)):
            return None
        model = annotation
    return model


def _unknown_field_message(name: str, parent_loc: Sequence[str | int]) -> str:
    message = f"unknown field '{name}'"
    model = _model_at(parent_loc)
    if model is not None:
        close = difflib.get_close_matches(name, list(model.model_fields), n=1)
        if close:
            message += f" (did you mean '{close[0]}'?)"
    return message


def _friendly_message(err: ErrorDetails) -> str:
    kind = err["type"]
    ctx: dict[str, Any] = dict(err.get("ctx") or {})
    got = err.get("input")
    if kind in ("enum", "literal_error"):
        return f"must be one of {ctx.get('expected', '?')} (got {got!r})"
    if kind.startswith("date_"):
        return f"must be a date written as YYYY-MM-DD (got {got!r})"
    if kind == "value_error":
        error = ctx.get("error")
        return str(error) if error is not None else err["msg"]
    if kind in ("int_type", "string_type", "list_type", "model_type", "dict_type"):
        return f"{err['msg'].lower()} (got {got!r})"
    return str(err["msg"])
