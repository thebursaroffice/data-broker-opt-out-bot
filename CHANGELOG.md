# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
- Broker URLs must use `https://`, since they will receive personal data.
- Search URL patterns may only use the `{first_name}`, `{last_name}`, `{city}`
  and `{state}` placeholders, so no other profile data ends up in URLs.
