"""Logging setup.

The rule for every log call in this codebase: log events, counts and ids,
never values that came from the profile. tests/test_no_pii_leaks.py runs the
profile commands at full verbosity to hold us to that.
"""

import logging
import sys

_LEVELS = {0: logging.WARNING, 1: logging.INFO}


def configure(verbosity: int) -> None:
    level = _LEVELS.get(verbosity, logging.DEBUG)
    root = logging.getLogger("unlisted")
    root.setLevel(level)
    # Replace rather than add, so repeated invocations in one process
    # (tests, mostly) don't stack handlers and duplicate every line.
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
