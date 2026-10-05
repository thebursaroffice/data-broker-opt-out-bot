# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `unlisted profile init`, `show` and `edit`: an encrypted local profile with
  names, aliases, current and past addresses, phone numbers, emails and date of
  birth. Every field is optional. Editing is prompt-by-prompt, so the profile is
  never written to a temporary file in plaintext.
- `profile show` masks values by default (`T**** M*********`); `--reveal`
  prints them in full.
- Local SQLite database with schema migrations. A database created by a newer
  version of unlisted is refused rather than misread.
- `--data-dir` option and `UNLISTED_DATA_DIR` to choose where data is stored;
  defaults to the OS's per-user data folder.
- `-v` / `-vv` for info and debug logging to stderr.
- Project scaffold: `unlisted` CLI entry point (Typer), `--version`, uv-managed
  environment pinned to Python 3.12, ruff, strict mypy and pytest configuration.
- Broker definition schema (`schema_version: 1`): name, site, opt-out method
  (`web_form`, `email`, `legal_request`, `manual`) with its URL or email, required
  profile fields, verification type (`none`, `email`, `phone`, `id_upload`),
  search URL pattern, relist interval, notes and last-verified date.
- `TODO_VERIFY` placeholder for values not yet confirmed against a live site.
- `unlisted brokers validate`: reports every problem in every file with its
  line and column, including YAML syntax errors, unknown fields (with
  "did you mean" suggestions), duplicate keys, missing fields and invalid
  values. `--strict` treats leftover `TODO_VERIFY` placeholders as errors.
- `unlisted brokers list`: table of all valid broker definitions.
- Broker directory selectable with `--dir` or `UNLISTED_BROKERS_DIR`.
- Three fictional example brokers, one per common opt-out method.

### Security
- The profile is encrypted at rest with AES-256-GCM. The data key is kept in the
  OS keyring, or wrapped with a scrypt-derived key from a passphrase
  (`profile init --passphrase`, or automatically when no secure keyring is
  available). Plaintext-file keyring backends are not trusted.
- The data directory is created `0700` and the database `0600`.
- Profile objects redact themselves in `repr`/`str` and validation errors, and
  tests run every profile command at full verbosity to check that no personal
  data reaches the logs.
- Broker URLs must use `https://`, since they will receive personal data.
- Search URL patterns may only use the `{first_name}`, `{last_name}`, `{city}`
  and `{state}` placeholders, so no other profile data ends up in URLs.
