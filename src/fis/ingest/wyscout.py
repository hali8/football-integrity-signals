"""Normalise koenvo's per-match Wyscout JSON into one parquet file per match.

Output lands in ``<data dir>/parquet/events_<match_id>.parquet``, which is what
the dbt ``raw.events`` source globs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kloppy import wyscout

from fis.data.wyscout import fetch, match_files
from fis.paths import ensure, parquet_dir


def ingest_match(match_id: str, json_path: Path, out_dir: Path) -> Path:
    ds = wyscout.load(event_data=str(json_path), data_version="V2")
    # Do this, or every spatial metric is noise.
    ds = ds.transform(to_orientation="ACTION_EXECUTING_TEAM")
    df = ds.to_df()
    # kloppy's frame is ONE match -- it has no match_id column, and everything
    # downstream keys on it.
    df["match_id"] = match_id
    target = out_dir / f"events_{match_id}.parquet"
    df.to_parquet(target, index=False)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fis-ingest-wyscout", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: <data dir>/parquet)",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="download the dataset first if it is missing",
    )
    parser.add_argument("--limit", type=int, default=None, help="ingest at most N matches")
    parser.add_argument("--force", action="store_true", help="re-ingest matches already done")
    args = parser.parse_args(argv)

    if args.fetch:
        fetch(quiet=True)

    out_dir = ensure(args.out if args.out is not None else parquet_dir())

    json_files = match_files()
    if not json_files:
        print(
            "error: no match files found -- run fis-fetch-wyscout first (or pass --fetch).",
            file=sys.stderr,
        )
        return 1
    if args.limit is not None:
        json_files = json_files[: args.limit]

    done, skipped, failed = 0, 0, []
    for path in json_files:
        # koenvo names files by Wyscout match id.
        match_id = path.stem
        if not args.force and (out_dir / f"events_{match_id}.parquet").exists():
            skipped += 1
            continue
        try:
            ingest_match(match_id, path, out_dir)
            done += 1
            if done % 100 == 0:
                print(f"...{done} ingested")
        except Exception as exc:  # deliberate: one bad match must not kill match 300 of 1,941
            failed.append((match_id, repr(exc)))

    print(f"ingested {done}, skipped {skipped}, failed {len(failed)}")
    for match_id, err in failed[:20]:
        print(f"  FAILED {match_id}: {err}")
    return 1 if failed and done == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
