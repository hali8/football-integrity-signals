"""Normalise koenvo's per-match Wyscout JSON into one parquet file per match.

Output lands in ``<data dir>/parquet/events_<match_id>.parquet``, which is what
the dbt ``raw.events`` source globs.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import json
import re
import shutil
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
    try:
        previous = json.loads(stamp.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        # Fail CLOSED: a marker that cannot be read vouches for nothing, so the
        # output it sits beside is stale rather than trusted.
        return ["the version marker is unreadable"]
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


def _raw_fields(json_path: Path) -> dict[str, tuple[list[int], int | None, int]]:
    """Wyscout tag ids, subEventId and source position per raw event id.

    kloppy drops all three. Tags keep any tag-derived fact recoverable in SQL
    (tags2name.csv labels them); subEventId is the only place attacking and
    defending ground duels are told apart (eventid2name.csv labels them); the
    position is where the event sits in the source array, which is the only
    authority on order when two events share a timestamp.
    """
    events = json.loads(json_path.read_text())["events"]
    out = {}
    for position, e in enumerate(events):
        sub = e.get("subEventId")
        sub = int(sub) if str(sub).strip().lstrip("-").isdigit() else None
        out[str(e["id"])] = ([t["id"] for t in e["tags"]], sub, position)
    return out


def ingest_match(match_id: str, json_path: Path, out_dir: Path) -> tuple[Path, list[str]]:
    """Write one match to parquet. Returns the path and any repairs that were needed."""
    ds, applied = load_match(json_path)
    # Do this, or every spatial metric is noise.
    ds = ds.transform(to_orientation="ACTION_EXECUTING_TEAM")
    # kloppy synthesises ids like "interception-88519941" for events it derives;
    # the numeric part is the raw event they came from.
    raw = _raw_fields(json_path)

    def _raw(event, index):
        return raw.get(re.sub(r"^[a-z_]+-", "", str(event.event_id)), ([], None, None))[index]

    df = ds.to_df(
        "*",
        qualifiers=_qualifiers,
        wyscout_tags=lambda e: _raw(e, 0),
        wyscout_subevent=lambda e: _raw(e, 1),
        wyscout_index=lambda e: _raw(e, 2),
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


def _staged_problem(staged: Path, expected: list[Path], current: dict[str, str]) -> str | None:
    """Why a staged rebuild must not go live, or None if it may."""
    import pyarrow.parquet as pq

    want = {p.stem for p in expected}
    have = {f.stem.removeprefix("events_") for f in staged.glob("events_*.parquet")}
    if want - have:
        return f"{len(want - have)} of {len(expected)} matches missing"
    # Extras matter as much as absences: a file left by an earlier attempt would
    # otherwise ride the swap into the live set.
    if have - want:
        return f"{len(have - want)} unexpected matches present"
    for parquet in staged.glob("events_*.parquet"):
        try:
            pq.ParquetFile(parquet)
        except Exception as exc:  # noqa: BLE001 -- fail closed: ANY reader error blocks the swap
            return f"{parquet.name} is unreadable: {exc!r}"
    stamp = staged / INGEST_STAMP
    try:
        marked = json.loads(stamp.read_text()) if stamp.exists() else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        marked = None  # unreadable is not current, and must not raise
    if marked != current:
        return "the staged version marker is missing, unreadable or from another pipeline"
    return None


class Busy(RuntimeError):
    """Another ingest already holds the rebuild guard."""


class Unresolved(RuntimeError):
    """Leftover state from an interrupted replacement needs a decision."""


@contextlib.contextmanager
def _single_writer(live: Path):
    """Only one process may rebuild or recover at a time.

    ``.staging`` and ``.previous`` are fixed paths, so a second run would
    validate, promote or delete state belonging to the first. An OS lock rather
    than a lock FILE: the kernel drops it when the process dies, so a killed run
    leaves no stale lock blocking the recovery it just made necessary.
    """
    live.parent.mkdir(parents=True, exist_ok=True)
    handle = (live.parent / f"{live.name}.lock").open("w")
    busy = Busy(
        f"another ingest is working on {live}; wait for it rather than running "
        "two, which would corrupt each other's staging"
    )
    try:
        try:
            import fcntl
        except ImportError:
            # Windows equivalent, also released when the process dies.
            # Untested -- no runner for that platform.
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise busy from exc
        else:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise busy from exc
        yield
    finally:
        handle.close()


def _recover(live: Path, current: dict[str, str], expected: list[Path]) -> str | None:
    """Resolve a replacement that was interrupted, before anything else runs.

    :func:`_swap` renames twice, so a kill leaves one of two states, and BOTH
    are handled here -- checking only for a missing live directory would let the
    second one survive an entire expensive rebuild before failing in the swap.
    Must be called BEFORE the live directory is created, or an empty one hides
    the first state.
    """
    previous = live.with_name(live.name + ".previous")
    staged = live.with_name(live.name + ".staging")

    if live.exists():
        if not previous.exists():
            return None
        if staged.exists():
            raise Unresolved(
                f"{live}, {previous.name} and {staged.name} all exist; which is current "
                "cannot be decided here. Resolve them by hand before rebuilding."
            )
        # Both renames completed and only the cleanup was interrupted, so live
        # IS the new set -- provided it describes this pipeline.
        if stale(live, current):
            raise Unresolved(
                f"{previous.name} exists beside a live set that does not match this "
                f"pipeline. One of them is wanted and this cannot tell which; move or "
                "remove one deliberately."
            )
        _discard(previous)
        return f"finished an interrupted replacement: removed the superseded {previous.name}"

    # Live is absent, so a swap died between its two renames. Staging, if it is
    # there, is the newer set -- revalidated rather than trusted, so a malformed
    # one falls through to restoring the old set instead of blocking it.
    if staged.exists() and _staged_problem(staged, expected, current) is None:
        staged.rename(live)
        _discard(previous)
        return f"recovered an interrupted replacement: promoted {staged.name}"
    if previous.exists():
        previous.rename(live)
        return f"recovered an interrupted replacement: restored from {previous.name}"
    return None


def _discard(superseded: Path) -> None:
    """Remove a set the replacement has superseded, and refuse to pretend.

    ``ignore_errors`` alone reports success while leaving the directory behind,
    which blocks the NEXT replacement for a reason the message denied.
    """
    shutil.rmtree(superseded, ignore_errors=True)
    if superseded.exists():
        raise Unresolved(
            f"{superseded} could not be removed. The live set is correct, but this "
            "will block the next replacement -- remove it by hand."
        )


def _swap(live: Path, staged: Path) -> None:
    """Replace ``live`` with ``staged`` by directory rename.

    NOT a single atomic operation: a kill between the two renames leaves the
    live path absent. What that buys is that a complete set always exists under
    SOME name, which _recover puts back on the next run.
    """
    previous = live.with_name(live.name + ".previous")
    if previous.exists():
        # It may be the only complete surviving set. Deleting it to make room
        # was the original defect here.
        raise RuntimeError(
            f"{previous} exists: an earlier replacement was interrupted and has not "
            "been resolved. Move or remove it deliberately before rebuilding."
        )
    if live.exists():
        live.rename(previous)
    try:
        staged.rename(live)
    except Exception:
        if previous.exists() and not live.exists():
            previous.rename(live)
        raise
    _discard(previous)


def run(args: argparse.Namespace) -> int:
    if args.fetch:
        fetch(quiet=True)
    target = Path(args.out) if args.out is not None else parquet_dir()
    try:
        with _single_writer(target):
            return _ingest(args, target)
    except (Busy, Unresolved) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _ingest(args: argparse.Namespace, target: Path) -> int:
    current = provenance()
    every_match = match_files()
    # Before ensure(): an interrupted replacement leaves the live path ABSENT,
    # and creating it empty would hide that from recovery.
    recovered = _recover(target, current, every_match)
    if recovered:
        print(recovered)
    out_dir = ensure(target)

    json_files = every_match
    if not json_files:
        print(
            "error: no match files found -- run fis-fetch-wyscout first (or pass --fetch).",
            file=sys.stderr,
        )
        return 1
    if args.limit is not None:
        json_files = json_files[: args.limit]

    reasons = stale(out_dir, current)
    if reasons:
        print("existing parquet does not match this pipeline; re-ingesting all matches:")
        for reason in reasons:
            print(f"  {reason}")
        if args.limit is not None:
            # A limited run would rewrite PART of a set already written by a
            # different parser, leaving two versions side by side in one mart.
            print(
                "error: --limit cannot be combined with a stale parquet set -- it would "
                "leave a mix of parser versions. Re-run without --limit.",
                file=sys.stderr,
            )
            return 1

    # A full rebuild writes to a SIBLING directory and replaces the live one by
    # rename. Rewriting in place would leave a failed match's file from the
    # PREVIOUS parser next to freshly written ones -- one mart, two pipelines.
    rebuilding = (args.force or bool(reasons)) and args.limit is None
    write_dir = out_dir.with_name(out_dir.name + ".staging") if rebuilding else out_dir
    if rebuilding:
        # Cleared loudly: a survivor would mix a previous attempt's files into
        # this one, and only the ones this run rewrites would be current.
        _discard(write_dir)
        write_dir.mkdir(parents=True, exist_ok=True)

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
            _, applied = ingest_match(match_id, path, write_dir)
            repairs.update(applied)
            done += 1
            if done % 100 == 0:
                print(f"...{done} ingested")
        except Exception as exc:  # noqa: BLE001 -- one bad match must not kill match 300 of 1,941
            failed.append((match_id, repr(exc)))

    if rebuilding:
        # The marker goes in the staged set and travels with it, so the live
        # directory is never stamped for a rebuild that did not land.
        (write_dir / INGEST_STAMP).write_text(json.dumps(current, indent=2) + "\n")
        problem = (
            f"{len(failed)} matches failed"
            if failed
            else _staged_problem(write_dir, json_files, current)
        )
        if problem:
            print(
                f"  rebuild incomplete ({problem}); the live parquet is untouched "
                f"and the partial set is in {write_dir}"
            )
        else:
            _swap(out_dir, write_dir)
            print(f"  staged rebuild validated and swapped into {out_dir}")
    elif not failed and args.limit is None:
        # Incremental top-up: stamp only when the whole dataset is present and
        # sound, so a partial run leaves no claim behind.
        (out_dir / INGEST_STAMP).write_text(json.dumps(current, indent=2) + "\n")

    print(f"ingested {done}, skipped {skipped}, failed {len(failed)}")
    if repairs:
        # Surfaced, not hidden: these are known kloppy/data defects, and a change
        # in these counts is worth noticing.
        summary = ", ".join(f"{name} {n}" for name, n in sorted(repairs.items()))
        print(f"  workarounds applied: {summary}")
    for match_id, err in failed[:20]:
        print(f"  FAILED {match_id}: {err}")
    # ANY failure fails the command: 1 bad match in 1,941 still leaves the mart
    # short, and exiting 0 lets `pixi run build` proceed on an incomplete set.
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fis-ingest-wyscout", description=__doc__.splitlines()[0])
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
