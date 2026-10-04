from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Column, Table
from rich.text import Text

from unlisted.brokers.loader import Issue, default_brokers_dir, load_registry

app = typer.Typer(help="Inspect and validate broker definitions.", no_args_is_help=True)

DirOption = Annotated[
    Path | None,
    typer.Option(
        "--dir",
        help="Broker definitions directory. Defaults to $UNLISTED_BROKERS_DIR, then ./brokers.",
        file_okay=False,
    ),
]


@app.command("validate")
def validate(
    files: Annotated[
        list[Path] | None,
        typer.Argument(help="Specific broker files to check. Defaults to every file in --dir."),
    ] = None,
    directory: DirOption = None,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Treat leftover TODO_VERIFY placeholders as errors."),
    ] = False,
) -> None:
    """Check broker files against the schema and report every problem with its line."""
    out = Console(highlight=False, soft_wrap=True)
    loaded, errors = load_registry(directory or default_brokers_dir(), files or None)

    warnings: list[Issue] = []
    for item in loaded:
        if strict:
            errors.extend(replace(todo, severity="error") for todo in item.todos)
        else:
            warnings.extend(item.todos)

    for issue in sorted([*errors, *warnings], key=lambda i: (str(i.path), i.line or 0)):
        style = "red" if issue.severity == "error" else "yellow"
        out.print(str(issue), style=style, markup=False)

    files_with_errors = {i.path for i in errors}
    ok = sum(1 for item in loaded if item.path not in files_with_errors)
    summary = f"{ok} valid, {len(files_with_errors)} invalid"
    if warnings:
        summary += f", {len(warnings)} warning(s)"
    out.print(summary, style="red" if errors else "green", markup=False)
    if errors:
        raise typer.Exit(code=1)


@app.command("list")
def list_brokers(directory: DirOption = None) -> None:
    """Show every valid broker definition."""
    out = Console(highlight=False)
    loaded, errors = load_registry(directory or default_brokers_dir())
    ids = [item.id for item in loaded]

    table = Table("name", "method", "verification", "relist (days)", "last verified")
    # Ids get typed back into other commands, so they must never be truncated.
    table.columns.insert(
        0, Column("id", no_wrap=True, min_width=len(max(ids, key=len, default="")))
    )
    for item in sorted(loaded, key=lambda b: b.id):
        b = item.broker
        # Text() so a bracket in a contributor-written name isn't parsed as Rich markup.
        table.add_row(
            Text(item.id),
            Text(b.name),
            b.opt_out.method.value,
            b.verification.value,
            str(b.relist_interval_days),
            b.last_verified.isoformat() if b.last_verified else "unverified",
        )
    out.print(table)

    if errors:
        bad = len({i.path for i in errors})
        out.print(
            f"{bad} file(s) skipped due to errors; run `unlisted brokers validate` for details.",
            style="yellow",
            markup=False,
        )
