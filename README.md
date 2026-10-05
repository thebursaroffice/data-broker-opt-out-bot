# unlisted

A local-first CLI for getting your personal info removed from data broker sites,
tracking each request, and catching it when you get relisted.

**Status:** early development. The broker registry and encrypted profile work so far.

## Privacy

- Your personal data never leaves your machine, except when it's sent to a broker
  you explicitly run a request against.
- No telemetry, analytics, or update checks.
- Profile data is encrypted at rest and never written to logs.
- Anything that needs a human (CAPTCHAs, ID checks) is handed back to you, never bypassed.

## Your profile

```
unlisted profile init               # prompts for each field; all optional
unlisted profile init --passphrase  # use a passphrase instead of the OS keyring
unlisted profile show               # masked; add --reveal to see values
unlisted profile edit
```

The profile is encrypted before it touches disk. By default the key lives in
your OS keyring (Keychain on macOS). If no secure keyring is available, or you
pass `--passphrase`, you'll be asked for a passphrase instead. **There is no
recovery**: lose the keyring entry or the passphrase and the profile has to be
re-entered.

Data is stored in your OS's per-user data folder. Use `--data-dir` or
`UNLISTED_DATA_DIR` to put it somewhere else.

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
