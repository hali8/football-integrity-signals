"""Registry of the datasets this project knows how to fetch and ingest."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    description: str
    approx_download_gb: float
    add_fetch_arguments: Callable[[argparse.ArgumentParser], None]
    run_fetch: Callable[[argparse.Namespace], int]
    add_ingest_arguments: Callable[[argparse.ArgumentParser], None]
    run_ingest: Callable[[argparse.Namespace], int]
    is_fetched: Callable[[], bool]
    is_ingested: Callable[[], bool]


def _wyscout() -> Source:
    from fis.data import wyscout as data_wyscout
    from fis.ingest import wyscout as ingest_wyscout

    return Source(
        name="wyscout",
        description="koenvo's Wyscout event dataset, 1941 matches (default)",
        approx_download_gb=0.3,
        add_fetch_arguments=data_wyscout.add_arguments,
        run_fetch=data_wyscout.run,
        add_ingest_arguments=ingest_wyscout.add_arguments,
        run_ingest=ingest_wyscout.run,
        is_fetched=data_wyscout.is_fetched,
        is_ingested=ingest_wyscout.is_ingested,
    )


# Built lazily so importing this module never requires kloppy/httpx.
_BUILDERS: dict[str, Callable[[], Source]] = {
    "wyscout": _wyscout,
}

DEFAULT: tuple[str, ...] = ("wyscout",)


def known() -> list[str]:
    return sorted(_BUILDERS)


def get(name: str) -> Source:
    try:
        builder = _BUILDERS[name]
    except KeyError:
        raise KeyError(f"unknown source {name!r}; known: {', '.join(known())}") from None
    return builder()


def resolve(selected: str | None, *, all_: bool = False) -> list[str]:
    if all_:
        return known()
    if selected is None:
        return list(DEFAULT)
    if selected not in _BUILDERS:
        raise KeyError(f"unknown source {selected!r}; known: {', '.join(known())}")
    return [selected]


def installed(stage: str = "ingested") -> list[str]:
    if stage not in ("fetched", "ingested"):
        raise ValueError(f"stage must be 'fetched' or 'ingested', got {stage!r}")
    check = "is_fetched" if stage == "fetched" else "is_ingested"
    return sorted(name for name in known() if getattr(get(name), check)())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fis-sources", description=__doc__ or "")
    parser.add_argument(
        "--fetched",
        action="store_true",
        help="list sources that have been fetched, not (necessarily) ingested",
    )
    args = parser.parse_args(argv)
    print(",".join(installed("fetched" if args.fetched else "ingested")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
