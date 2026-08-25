"""Normalise koenvo's per-match Wyscout JSON into one parquet file per match.

Output lands in ``<data dir>/parquet/events_<match_id>.parquet``, which is what
the dbt ``raw.events`` source globs.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

import kloppy

from fis.data.wyscout import DATASET_COMMIT, fetch, match_files
from fis.ingest import kloppy_workarounds
from fis.ingest.kloppy_workarounds import load_match
from fis.paths import ensure, parquet_dir

#: Records what produced the parquet, so a changed pipeline re-ingests itself
#: rather than waiting to be told. Sits beside the output it describes.
INGEST_STAMP = ".fis-ingest.json"


def provenance() -> dict[str, str]:
    """The three things that decide what a parquet file contains.

    Input data, parser version, and our own code -- the last hashed from source,
    since a workaround fix changes the output as surely as a new dataset commit.
    """
    sources = b"".join(
        Path(module.__file__).read_bytes() for module in (sys.modules[__name__], kloppy_workarounds)
    )
    return {
        "dataset_commit": DATASET_COMMIT,
        "kloppy": kloppy.__version__,
        "code": hashlib.sha256(sources).hexdigest()[:16],
    }


def stale(out_dir: Path, current: dict[str, str]) -> list[str]:
    """What differs between the parquet on disk and what we would write now."""
    stamp = out_dir / INGEST_STAMP
    if not stamp.exists():
        # No stamp and no output is a first run, not a stale one.
        if not any(out_dir.glob("events_*.parquet")):
            return []
        return ["produced before provenance was recorded"]
    previous = json.loads(stamp.read_text())
    return [
        f"{key}: {previous.get(key)} -> {value}"
        for key, value in current.items()
        if previous.get(key) != value
    ]


def _qualifiers(event) -> list[str]:
    """Every qualifier as "Type:VALUE".

    to_df's flat columns keep only the last qualifier of each kind; keeping the
    full list defers the flattening to SQL, where it can be chosen.
    """
    out = []
    for q in getattr(event, "qualifiers", None) or []:
        value = getattr(q, "value", None)
        if value is None or value is False:
            continue
        kind = type(q).__name__.removesuffix("Qualifier")
        out.append(f"{kind}:{getattr(value, 'name', value)}")
    return out


def _raw_tags(json_path: Path) -> dict[str, list[int]]:
    """Wyscout tag ids per raw event id.

    kloppy drops every tag but counter-attack; carrying the ids keeps any
    tag-derived fact recoverable in SQL (tags2name.csv labels them).
    """
    events = json.loads(json_path.read_text())["events"]
    return {str(e["id"]): [t["id"] for t in e["tags"]] for e in events}


def ingest_match(match_id: str, json_path: Path, out_dir: Path) -> tuple[Path, list[str]]:
    """Write one match to parquet. Returns the path and any repairs that were needed."""
    ds, applied = load_match(json_path)
    # Do this, or every spatial metric is noise.
    ds = ds.transform(to_orientation="ACTION_EXECUTING_TEAM")
    # kloppy synthesises ids like "interception-88519941" for events it derives;
    # the numeric part is the raw event they came from.
    tags = _raw_tags(json_path)
    df = ds.to_df(
        "*",
        qualifiers=_qualifiers,
        wyscout_tags=lambda e: tags.get(re.sub(r"^[a-z_]+-", "", str(e.event_id)), []),
    )
    # kloppy's frame is ONE match -- it has no match_id column, and everything
    # downstream keys on it.
    df["match_id"] = match_id
    target = out_dir / f"events_{match_id}.parquet"
    df.to_parquet(target, index=False)
    return target, applied


def add_arguments(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-ingest even when the existing parquet matches this pipeline",
    )


def is_ingested(out_dir: Path | None = None) -> bool:
    out_dir = Path(out_dir) if out_dir is not None else parquet_dir()
    return out_dir.exists() and any(out_dir.glob("events_*.parquet"))


def run(args: argparse.Namespace) -> int:
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

    current = provenance()
    reasons = stale(out_dir, current)
    if reasons:
        print("existing parquet does not match this pipeline; re-ingesting all matches:")
        for reason in reasons:
            print(f"  {reason}")

    done, skipped, failed = 0, 0, []
    repairs: collections.Counter[str] = collections.Counter()
    for path in json_files:
        # koenvo names files by Wyscout match id.
        match_id = path.stem
        redo = args.force or bool(reasons)
        if not redo and (out_dir / f"events_{match_id}.parquet").exists():
            skipped += 1
            continue
        try:
            _, applied = ingest_match(match_id, path, out_dir)
            repairs.update(applied)
            done += 1
            if done % 100 == 0:
                print(f"...{done} ingested")
        except Exception as exc:  # deliberate: one bad match must not kill match 300 of 1,941
            failed.append((match_id, repr(exc)))

    # Stamped only when the whole dataset is present and sound; a partial run
    # leaves no claim behind, so the next one cannot mix two pipelines' output.
    if not failed and args.limit is None:
        (out_dir / INGEST_STAMP).write_text(json.dumps(current, indent=2) + "\n")

    print(f"ingested {done}, skipped {skipped}, failed {len(failed)}")
    if repairs:
        # Surfaced, not hidden: these are known kloppy/data defects, and a change
        # in these counts is worth noticing.
        summary = ", ".join(f"{name} {n}" for name, n in sorted(repairs.items()))
        print(f"  workarounds applied: {summary}")
    for match_id, err in failed[:20]:
        print(f"  FAILED {match_id}: {err}")
    return 1 if failed and done == 0 else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fis-ingest-wyscout", description=__doc__.splitlines()[0])
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
