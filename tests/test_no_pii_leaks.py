"""Done-when check for Increment 2: nothing personal reaches logs at any level.

Runs every profile command at maximum verbosity and inspects everything that
isn't the command's own deliberate stdout output.
"""

import logging

import pytest
from typer.testing import CliRunner

from tests.conftest import FAKE_SECRETS
from tests.test_profile_cli import INIT_ANSWERS, KEEP_EVERYTHING, PASSPHRASE
from unlisted.cli import app

runner = CliRunner(env={"COLUMNS": "200"})


def _assert_clean(text: str, where: str) -> None:
    for secret in [*FAKE_SECRETS, PASSPHRASE]:
        assert secret not in text, f"{secret!r} leaked into {where}"


@pytest.mark.parametrize("verbosity", ["-v", "-vv", "-vvv"])
@pytest.mark.parametrize("passphrase", [False, True])
def test_profile_commands_log_nothing_personal(
    caplog: pytest.LogCaptureFixture, verbosity: str, passphrase: bool
) -> None:
    caplog.set_level(logging.DEBUG)
    init_args = ["profile", "init", *(["--passphrase"] if passphrase else [])]
    init_answers = [*INIT_ANSWERS, *([PASSPHRASE, PASSPHRASE] if passphrase else [])]
    unlock = [PASSPHRASE] if passphrase else []

    steps = [
        (init_args, init_answers),
        (["profile", "show"], unlock),
        (["profile", "show", "--reveal"], unlock),
        (["profile", "edit"], [*unlock, *KEEP_EVERYTHING]),
    ]
    for args, answers in steps:
        result = runner.invoke(app, [verbosity, *args], input="\n".join(answers) + "\n")
        assert result.exit_code == 0, result.output
        _assert_clean(result.stderr, f"stderr of {' '.join(args)}")

    # Guard against this test passing vacuously because logging was off.
    assert caplog.records
    if verbosity != "-v":
        assert any(r.levelno == logging.DEBUG for r in caplog.records)
    _assert_clean(caplog.text, "log records")
    for record in caplog.records:
        _assert_clean(repr(record.args), "log record args")


def test_masked_show_output_is_clean() -> None:
    runner.invoke(app, ["profile", "init"], input="\n".join(INIT_ANSWERS) + "\n")
    result = runner.invoke(app, ["profile", "show"])
    assert result.exit_code == 0, result.output
    _assert_clean(result.stdout, "masked show output")
