"""Fetch the reference tables behind the Wyscout open dataset.

koenvo's repo gives us per-match events; these are the dimensions that give them
meaning -- who played, for which team, in which competition, and who officiated.
They come from the original Figshare collection published alongside
Pappalardo et al. (2019), which is the canonical source. koenvo mirrors four of
them but not competitions, referees or coaches, so all of it is taken from
Figshare rather than splitting provenance across two sources.

    https://figshare.com/collections/Soccer_match_event_dataset/4415000

Every file is pinned by Figshare file id *and* md5. The id fixes the article
version, and the checksum is verified after download, so a silently republished
file fails loudly instead of changing your results.

Left as JSON on purpose. Flattening the nested ``teamsData`` in matches belongs
in a dbt staging model, not in Python -- see the README.

``events.zip`` is deliberately not fetched: it holds the same events as the
1941 per-match files already ingested via kloppy, and expands past 1 GB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from fis.paths import ensure, json_dir

COLLECTION_URL = "https://figshare.com/collections/Soccer_match_event_dataset/4415000"
DOWNLOAD_URL = "https://ndownloader.figshare.com/files/{file_id}"

STAMP_NAME = ".fis-figshare.json"
CHUNK = 1 << 20


@dataclass(frozen=True)
class Asset:
    """One pinned Figshare file."""

    name: str
    article: int
    version: int
    file_id: int
    md5: str
    size: int
    note: str
    unzip: bool = False


#: Pinned 2026-08. Verified against the Figshare API: article version, file id,
#: byte size and md5 all agree with what is published.
ASSETS: tuple[Asset, ...] = (
    Asset(
        "matches.zip",
        7770422,
        1,
        14464622,
        "51d80beb17480919f69a53a0152c2d71",
        645097,
        "per-league matches: dates, teams, scores, referee assignments",
        unzip=True,
    ),
    Asset(
        "players.json",
        7765196,
        3,
        15073721,
        "f28ddf6326281efeda6488b2169f5609",
        1737347,
        "player identities, roles and positions",
    ),
    Asset(
        "teams.json", 7765310, 3, 15073697, "1381ff9449f21105090729cf0e086b5b", 27404, "team lookup"
    ),
    Asset(
        "competitions.json",
        7765316,
        4,
        15073685,
        "3dc210a4805dda5337b0ff9f7eaa407a",
        1209,
        "competition lookup",
    ),
    Asset(
        "referees.json",
        8082665,
        1,
        15074030,
        "6b5b5612e128238f0f28a355cc13796a",
        196709,
        "referee identities",
    ),
    Asset(
        "coaches.json",
        8082650,
        1,
        15073868,
        "ee8afad14b5be622b1d3560d15248778",
        70664,
        "coach identities",
    ),
    Asset(
        "eventid2name.csv",
        11743836,
        1,
        21385245,
        "46daf16100ece0c743eedc9adcfea162",
        1001,
        "event id -> name, for decoding eventId/subEventId",
    ),
    Asset(
        "tags2name.csv",
        11743818,
        1,
        21385239,
        "e7acb14918d00e40c80a898b1da8fc39",
        1754,
        "tag id -> name, e.g. 1802 = not accurate",
    ),
)

TOTAL_BYTES = sum(a.size for a in ASSETS)


def _salvage_trailing_object(fragment: str) -> dict | None:
    """Close a JSON object truncated mid-key, keeping every complete field.

    Tries closing the object at each trailing comma, outermost first. Candidates
    that split a nested object simply fail to parse and are skipped.
    """
    for cut in range(len(fragment), 0, -1):
        if fragment[cut - 1] != ",":
            continue
        try:
            return json.loads(fragment[: cut - 1] + "}")
        except ValueError:
            continue
    return None


def repair_truncated_array(raw: str) -> tuple[list, bool] | None:
    """Recover records from a JSON array cut off mid-record.

    Returns ``(records, salvaged_partial)``, or None if the text parses cleanly
    and needs no repair. Applied lazily: an upstream fix makes this unreachable.
    """
    try:
        json.loads(raw)
        return None
    except ValueError:
        pass

    decoder = json.JSONDecoder()
    records: list = []
    i = raw.index("[") + 1
    while True:
        while i < len(raw) and raw[i] in " ,\n\r\t":
            i += 1
        if i >= len(raw) or raw[i] == "]":
            break
        try:
            obj, i = decoder.raw_decode(raw, i)
        except ValueError:
            break
        records.append(obj)

    # Whatever follows the last complete record is a partial one. Keep its
    # complete fields rather than losing the whole record.
    salvaged = _salvage_trailing_object(raw[i:].lstrip(" ,\n\r\t"))
    if salvaged is not None:
        records.append(salvaged)
    return records, salvaged is not None


def _read_stamp(dest: Path) -> dict | None:
    try:
        return json.loads((dest / STAMP_NAME).read_text())
    except (OSError, ValueError):
        return None


def _expected_stamp() -> dict:
    return {
        "collection": COLLECTION_URL,
        "files": {a.name: {"file_id": a.file_id, "md5": a.md5} for a in ASSETS},
    }


def _download(asset: Asset, target: Path, *, quiet: bool) -> None:
    """Download one asset and verify its checksum before it is trusted."""
    digest = hashlib.md5()
    with httpx.stream(
        "GET", DOWNLOAD_URL.format(file_id=asset.file_id), follow_redirects=True, timeout=60.0
    ) as response:
        response.raise_for_status()
        with target.open("wb") as fh:
            for chunk in response.iter_bytes(CHUNK):
                fh.write(chunk)
                digest.update(chunk)

    if digest.hexdigest() != asset.md5:
        raise RuntimeError(
            f"{asset.name}: checksum mismatch.\n"
            f"  expected {asset.md5}\n"
            f"  got      {digest.hexdigest()}\n"
            f"  The pinned file may have been republished. Verify at {COLLECTION_URL} "
            f"before updating the pin."
        )
    if not quiet:
        print(f"  {asset.name:<20} {asset.size / 1e6:6.2f} MB  md5 ok")


def fetch(dest: Path | None = None, *, force: bool = False, quiet: bool = False) -> Path:
    """Ensure every pinned reference file is present at ``dest``.

    Idempotent: a directory already stamped with these exact file ids and
    checksums is left alone. Files are staged in a temp directory and swapped in
    only once every checksum has passed, so an interrupted run cannot leave a
    half-populated directory a later run mistakes for complete.
    """
    dest = Path(dest) if dest is not None else json_dir()

    stamp = _read_stamp(dest)
    expected = _expected_stamp()
    # Compare only the pinned fields; the stamp may also record repairs.
    if not force and stamp and all(stamp.get(k) == v for k, v in expected.items()):
        if not quiet:
            print(f"Already have {len(ASSETS)} pinned reference files: {dest}")
            for name, why in (stamp.get("repaired") or {}).items():
                print(f"  note: {name} was {why}")
        return dest

    ensure(dest.parent)
    if not quiet:
        print(f"Fetching {len(ASSETS)} reference files ({TOTAL_BYTES / 1e6:.1f} MB) from Figshare")
        print(f"  destination: {dest}")

    staging = Path(tempfile.mkdtemp(prefix=".fis-figshare-", dir=dest.parent))
    try:
        payload = ensure(staging / "payload")
        for asset in ASSETS:
            blob = staging / asset.name
            _download(asset, blob, quiet=quiet)
            if asset.unzip:
                with zipfile.ZipFile(blob) as zf:
                    # Flatten: the archive nests its members under a directory we
                    # do not want, and every member is a plain .json.
                    for member in zf.infolist():
                        if member.is_dir():
                            continue
                        name = Path(member.filename).name
                        if name.startswith(".") or not name.endswith(".json"):
                            continue
                        (payload / name).write_bytes(zf.read(member))
                blob.unlink()
            else:
                blob.rename(payload / asset.name)

        # Some published files are malformed. Checked lazily: a file that parses
        # is left exactly as downloaded, so an upstream fix makes this a no-op.
        repaired: dict[str, str] = {}
        for path in sorted(payload.glob("*.json")):
            outcome = repair_truncated_array(path.read_text(encoding="utf8"))
            if outcome is None:
                continue
            records, salvaged_partial = outcome
            # Keep the published bytes next to the repair so the damage stays
            # auditable and the md5 in the stamp still refers to something real.
            path.rename(payload / f"{path.stem}.as-published{path.suffix}")
            path.write_text(json.dumps(records))
            repaired[path.name] = f"truncated upstream; recovered {len(records)} records" + (
                ", last one salvaged without its final field" if salvaged_partial else ""
            )
            if not quiet:
                print(f"  REPAIRED {path.name}: {repaired[path.name]}")

        stamp = _expected_stamp()
        if repaired:
            stamp["repaired"] = repaired
        (payload / STAMP_NAME).write_text(json.dumps(stamp, indent=2))

        previous = dest.with_name(dest.name + ".previous") if dest.exists() else None
        if previous is not None:
            shutil.rmtree(previous, ignore_errors=True)
            os.rename(dest, previous)
        os.rename(payload, dest)
        if previous is not None:
            shutil.rmtree(previous, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    if not quiet:
        print(f"Done: {len(list(dest.glob('*.json')))} json, {len(list(dest.glob('*.csv')))} csv.")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fis-fetch-reference", description=__doc__.splitlines()[0]
    )
    parser.add_argument("--dest", type=Path, default=None, help="target (default: <data dir>/json)")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument("--quiet", action="store_true", help="suppress progress output")
    args = parser.parse_args(argv)

    try:
        fetch(args.dest, force=args.force, quiet=args.quiet)
    except (httpx.HTTPError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
