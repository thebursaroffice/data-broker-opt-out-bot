import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

DATA_DIR_ENV = "UNLISTED_DATA_DIR"
DB_FILENAME = "unlisted.db"


@dataclass(frozen=True)
class AppContext:
    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / DB_FILENAME


def resolve_data_dir(override: Path | None = None) -> Path:
    if override is not None:
        return override
    env = os.environ.get(DATA_DIR_ENV)
    if env:
        return Path(env)
    return Path(user_data_dir("unlisted", appauthor=False))


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    # mkdir's mode is masked by umask and ignored for existing dirs, so set it explicitly.
    path.chmod(0o700)
    return path
