from typing import Annotated

import typer

from unlisted import __version__
from unlisted.brokers.cli import app as brokers_app

app = typer.Typer(
    name="unlisted",
    help="Remove your personal info from data broker sites. Everything stays on this machine.",
    no_args_is_help=True,
)
app.add_typer(brokers_app, name="brokers")


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"unlisted {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_print_version, is_eager=True, help="Show version and exit."
        ),
    ] = False,
) -> None:
    pass
