"""Single source of truth for where this project reads and writes data.

Every caller imports from here rather than re-deriving paths, so the same code
works in a source checkout, in an editable install, and from a released wheel.

Resolution order for the data root:
  1. ``$FIS_DATA_DIR``                    -- explicit override, always wins
  2. ``<project root>/data``              -- source checkout / editable install,
                                             located by walking up to pyproject.toml
  3. ``<user cache>/football-integrity-signals/data``  -- installed from a wheel

Deliberately does *not* shell out to ``git rev-parse``: that would make git a
runtime dependency and would break in a tarball export or a Docker image where
``.git`` was stripped, both of which still have a pyproject.toml.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

from platformdirs import user_cache_path

APP_NAME = "football-integrity-signals"

#: Modules under this prefix must read marts, not files. See the stage rule in README.
_ANALYSIS_PREFIX = "fis.analysis"


class StageRuleWarning(UserWarning):
    """Analysis code reached past the warehouse to a file on disk.

    Deliberately a warning and not an error: it must never break an exploratory
    session mid-flight. The lint rule in ``src/fis/analysis/ruff.toml`` is what
    stops it reaching a merge.
    """


def _calling_module() -> str:
    """Name of the first module up the stack that is not this one."""
    frame: object = sys._getframe(1)
    while frame is not None:
        name = frame.f_globals.get("__name__", "")  # type: ignore[attr-defined]
        if name != __name__:
            return name
        frame = frame.f_back  # type: ignore[attr-defined]
    return ""


def _guard(accessor: str, holds: str) -> None:
    """Warn -- never raise -- when analysis code asks for a path it should not use."""
    caller = _calling_module()
    if caller != _ANALYSIS_PREFIX and not caller.startswith(_ANALYSIS_PREFIX + "."):
        return
    warnings.warn(
        f"{caller} called fis.paths.{accessor}(), which holds {holds}.\n"
        f"  Analysis reads marts, not files. Use fis.warehouse.mart(<name>) instead.\n"
        f"  If the column you need is missing, that is a missing dbt model: add it to\n"
        f"  warehouse/models/marts/ and run `pixi run build`. Returning the path anyway.",
        StageRuleWarning,
        stacklevel=3,
    )


# Walking up stops here -- a pyproject.toml above an installed package (e.g. a
# stray one at the root of a virtualenv) must never be mistaken for our project.
_STOP_DIRS = frozenset({"site-packages", "dist-packages"})


def project_root() -> Path | None:
    """The source-checkout root, or None when running from an installed wheel."""
    for parent in Path(__file__).resolve().parents:
        if parent.name in _STOP_DIRS:
            return None
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def data_dir() -> Path:
    """Root for all project data. See module docstring for precedence."""
    if env := os.environ.get("FIS_DATA_DIR"):
        return Path(env).expanduser().resolve()
    if root := project_root():
        return root / "data"
    # appauthor=False matters on Windows: left unset it defaults to the appname,
    # giving a duplicated ...\football-integrity-signals\football-integrity-signals\Cache.
    # macOS and Linux ignore it.
    return user_cache_path(APP_NAME, appauthor=False) / "data"


def download_dir() -> Path:
    """Third-party datasets exactly as fetched. Treated as immutable and disposable."""
    _guard("download_dir", "raw upstream JSON")
    return data_dir() / "download"


def json_dir() -> Path:
    """Reference tables as published, read directly by dbt via read_json_auto."""
    _guard("json_dir", "warehouse inputs, one stage upstream of the marts")
    return data_dir() / "json"


def parquet_dir() -> Path:
    """Our own normalised parquet output, the input to dbt."""
    _guard("parquet_dir", "the dbt input, one stage upstream of the marts")
    return data_dir() / "parquet"


def wyscout_dir() -> Path:
    """Root of the extracted koenvo Wyscout dataset."""
    _guard("wyscout_dir", "raw upstream JSON")
    # Not download_dir(), which would fire a second warning for the same call.
    return data_dir() / "download" / "wyscout"


def ensure(path: Path) -> Path:
    """mkdir -p, returning the path so it can be used inline."""
    path.mkdir(parents=True, exist_ok=True)
    return path
