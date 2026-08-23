"""Read access to the dbt marts. This is the only sanctioned input for analysis.

Every error raised here names the remedy, because the remedy is almost never
"read the parquet instead" -- it is "add a column to a dbt model and rebuild".
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd

from fis.paths import project_root

#: dbt writes custom-schema models as ``<target schema>_<custom schema>``.
MARTS_SCHEMA = os.environ.get("FIS_MARTS_SCHEMA", "main_marts")

BUILD_HINT = "pixi run ingest && pixi run build"


class WarehouseError(RuntimeError):
    """Raised with an actionable message when the warehouse cannot satisfy a read."""


def db_path() -> Path:
    """Location of the duckdb file."""
    if env := os.environ.get("FIS_WAREHOUSE_DB"):
        return Path(env).expanduser().resolve()
    root = project_root()
    if root is None:
        raise WarehouseError(
            "No project checkout found, so the warehouse location is unknown.\n"
            "  Fix: set FIS_WAREHOUSE_DB to the duckdb file you want to read."
        )
    return root / "warehouse" / "integrity.duckdb"


def connect(*, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Open the warehouse. Read-only by default -- analysis never writes."""
    path = db_path()
    if not path.exists():
        raise WarehouseError(f"No warehouse at {path}.\n  Fix: build it with `{BUILD_HINT}`.")
    return duckdb.connect(str(path), read_only=read_only)


def mart_names() -> list[str]:
    """Every mart currently built, sorted."""
    with connect() as con:
        rows = con.execute(
            "select table_name from information_schema.tables "
            "where table_schema = ? order by table_name",
            [MARTS_SCHEMA],
        ).fetchall()
    return [r[0] for r in rows]


def mart(name: str, columns: list[str] | None = None) -> pd.DataFrame:
    """Read one mart.

    A missing mart or a missing column is a missing dbt model, never a reason to
    read ``data/parquet/`` -- so both raise with the model to edit, not a stack
    trace from duckdb.
    """
    available = mart_names()
    if name not in available:
        listed = ", ".join(available) if available else "(none built yet)"
        raise WarehouseError(
            f"No mart {name!r} in schema {MARTS_SCHEMA!r}.\n"
            f"  Available: {listed}\n"
            f"  Fix: a missing mart is a missing dbt model. Add\n"
            f"       warehouse/models/marts/{name}.sql, then run `{BUILD_HINT}`.\n"
            f"  Do NOT read data/parquet/ from analysis -- see the stage rule in README."
        )

    with connect() as con:
        table = f'"{MARTS_SCHEMA}"."{name}"'
        present = [r[0] for r in con.execute(f"describe {table}").fetchall()]
        if columns is not None:
            missing = [c for c in columns if c not in present]
            if missing:
                raise WarehouseError(
                    f"Mart {name!r} has no column(s): {', '.join(missing)}.\n"
                    f"  Available: {', '.join(present)}\n"
                    f"  Fix: a missing column is a missing dbt model, not a backwards\n"
                    f"       reach. Add it to warehouse/models/marts/{name}.sql and\n"
                    f"       run `{BUILD_HINT}`."
                )
            selection = ", ".join(f'"{c}"' for c in columns)
        else:
            selection = "*"
        return con.execute(f"select {selection} from {table}").df()


def publish(name: str, frame: pd.DataFrame) -> int:
    """Write an analysis result back into the marts schema. Returns the row count.

    This is the one write analysis is allowed, and it is not a way around the
    stage rule: the input still has to come from a mart. It exists because a
    statistical result is a table, and a table belongs where the tables are --
    readable through :func:`mart` like anything else.

    The caveat is ownership, so it is stated rather than hidden in a schema
    name: **dbt does not build this table**. ``dbt build`` will not refresh it
    and ``dbt clean`` will not remove it, so it goes stale the moment the mart
    under it is rebuilt. Re-run the analysis, not dbt.
    """
    with connect(read_only=False) as con:
        con.register("_publishing", frame)
        con.execute(f'create schema if not exists "{MARTS_SCHEMA}"')
        con.execute(
            f'create or replace table "{MARTS_SCHEMA}"."{name}" as select * from _publishing'
        )
        con.unregister("_publishing")
    return len(frame)


def query(sql: str) -> pd.DataFrame:
    """Escape hatch for ad-hoc SQL against the marts schema.

    Still read-only, and still pointed at the warehouse rather than the parquet.
    """
    with connect() as con:
        con.execute(f'set search_path = "{MARTS_SCHEMA}"')
        return con.execute(sql).df()
