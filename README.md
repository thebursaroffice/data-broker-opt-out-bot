# unlisted

A local-first CLI for getting your personal info removed from data broker sites,
tracking each request, and catching it when you get relisted.

**Status:** early development. Only the broker registry works so far.

## Privacy

- Your personal data never leaves your machine, except when it's sent to a broker
  you explicitly run a request against.
- No telemetry, analytics, or update checks.
- Profile data is encrypted at rest and never written to logs.
- Anything that needs a human (CAPTCHAs, ID checks) is handed back to you, never bypassed.

## Brokers

Each broker is a YAML file in [`brokers/`](brokers/). The filename is the broker's id.
The three `example-*.yaml` files are fictional templates, one per common opt-out
method. Values marked `TODO_VERIFY` haven't been confirmed against the live site.

```
unlisted brokers list
unlisted brokers validate                 # every file in ./brokers
unlisted brokers validate brokers/x.yaml  # specific files
unlisted brokers validate --strict        # TODO_VERIFY counts as an error
```

Set `UNLISTED_BROKERS_DIR` or pass `--dir` to use a different directory.

## Development

Requires [uv](https://docs.astral.sh/uv/). It will install Python 3.12 if needed.

```
uv sync
uv run unlisted --help
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
```
