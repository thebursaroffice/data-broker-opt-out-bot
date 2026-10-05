from pathlib import Path
from typing import Annotated

import typer

from unlisted import __version__, logs
from unlisted.brokers.cli import app as brokers_app
from unlisted.paths import DATA_DIR_ENV, AppContext, resolve_data_dir
from unlisted.profile.cli import app as profile_app

app = typer.Typer(
    name="unlisted",
    help="Remove your personal info from data broker sites. Everything stays on this machine.",
    no_args_is_help=True,
)
app.add_typer(brokers_app, name="brokers")
app.add_typer(profile_app, name="profile")


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"unlisted {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    data_dir: Annotated[
        Path | None,
        typer.Option(
            "--data-dir",
            help=f"Where your encrypted data lives. Defaults to ${DATA_DIR_ENV}, "
            "then your OS's per-user data folder.",
            file_okay=False,
        ),
    ] = None,
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="More log output (-v info, -vv debug)."),
    ] = 0,
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_print_version, is_eager=True, help="Show version and exit."
        ),
    ] = False,
) -> None:
    logs.configure(verbose)
    ctx.obj = AppContext(data_dir=resolve_data_dir(data_dir))
