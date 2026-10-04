from collections.abc import Callable
from pathlib import Path

import pytest

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
