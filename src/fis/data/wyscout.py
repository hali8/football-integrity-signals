"""Fetch the koenvo Wyscout soccer match event dataset.

Downloads a GitHub tarball over HTTPS rather than cloning: no git runtime
dependency, no refs/history machinery, one request.

The commit is pinned so an upstream revision cannot silently change results.
To move to a newer revision, bump ``DATASET_COMMIT`` deliberately -- a changed
pin is visible in the diff, and the stamp file makes existing checkouts
re-download instead of quietly mixing revisions.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

import httpx

from fis.data import figshare
from fis.data.audit import audit, format_report
from fis.paths import ensure, wyscout_dir

REPO = "koenvo/wyscout-soccer-match-event-dataset"

# Pinned: "Add V2 of data compatible with upcoming kloppy 3.14 release" (2023-12-04).
DATASET_COMMIT = "ebc4c54c1093c420a81ce442c69e4186fab33bb4"

# Only this subtree is kept; the repo also carries a v1 tree we do not use.
WANTED_SUBDIR = "processed-v2"

STAMP_NAME = ".fis-dataset.json"
CHUNK = 1 << 20  # 1 MiB


def tarball_url(commit: str = DATASET_COMMIT) -> str:
    return f"https://codeload.github.com/{REPO}/tar.gz/{commit}"


def _read_stamp(dest: Path) -> dict | None:
    try:
        return json.loads((dest / STAMP_NAME).read_text())
    except (OSError, ValueError):
        return None


def _download(url: str, target: Path, *, quiet: bool = False) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        seen = 0
        with target.open("wb") as fh:
            for chunk in response.iter_bytes(CHUNK):
                fh.write(chunk)
                seen += len(chunk)
                if not quiet and total:
                    pct = 100 * seen / total
                    print(f"\r  downloading... {pct:5.1f}%  ({seen >> 20} MiB)", end="")
        if not quiet:
            print(f"\r  downloaded {seen >> 20} MiB{' ' * 20}")


def _extract_subdir(archive: Path, subdir: str, into: Path) -> None:
    """Extract ``<tarball-prefix>/<subdir>`` into ``into``, stripping the prefix."""
    with tarfile.open(archive, "r:gz") as tar:
        members, prefix = [], None
        for member in tar.getmembers():
            head, _, rest = member.name.partition("/")
            prefix = prefix or head
            if rest == subdir or rest.startswith(f"{subdir}/"):
                member.name = rest
                members.append(member)
        if not members:
            raise RuntimeError(f"no '{subdir}/' entries found in {archive.name}")
        # filter="data" blocks absolute paths, ../ traversal, symlinks and device
        # nodes -- we are extracting a third-party archive, so this is not optional.
        tar.extractall(into, members=members, filter="data")


def fetch(
    dest: Path | None = None,
    *,
    commit: str = DATASET_COMMIT,
    force: bool = False,
    quiet: bool = False,
) -> Path:
    """Ensure the dataset is present at ``dest`` and return that path.

    Idempotent: an existing checkout stamped with the same commit is left alone.
    The extraction is staged in a temp directory and swapped in with a rename, so
    an interrupted run can never leave a half-populated directory that a later
    run mistakes for complete.
    """
    dest = Path(dest) if dest is not None else wyscout_dir()

    stamp = _read_stamp(dest)
    if stamp and stamp.get("commit") == commit and not force:
        if not quiet:
            print(f"Already at {commit[:12]}: {dest}")
        return dest

    ensure(dest.parent)
    if not quiet:
        print(f"Fetching {REPO} @ {commit[:12]}")
        print(f"  destination: {dest}")

    staging = Path(tempfile.mkdtemp(prefix=".fis-wyscout-", dir=dest.parent))
    try:
        archive = staging / "dataset.tar.gz"
        _download(tarball_url(commit), archive, quiet=quiet)

        payload = ensure(staging / "payload")
        _extract_subdir(archive, WANTED_SUBDIR, payload)
        archive.unlink()

        (payload / STAMP_NAME).write_text(
            json.dumps({"repo": REPO, "commit": commit, "subdir": WANTED_SUBDIR}, indent=2)
        )

        # Swap in atomically-ish: the new tree is renamed into place, and only
        # then is the old one deleted.
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
        print(f"Done: {len(list(match_files(dest)))} match files.")
    return dest


def match_files(root: Path | None = None):
    """The per-match event JSON files, sorted by name."""
    root = Path(root) if root is not None else wyscout_dir()
    return sorted((root / WANTED_SUBDIR / "files").glob("*.json"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fis-fetch-wyscout", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="target directory (default: <data dir>/download/wyscout)",
    )
    parser.add_argument(
        "--commit",
        default=DATASET_COMMIT,
        help=f"upstream commit to fetch (default: {DATASET_COMMIT[:12]})",
    )
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument("--quiet", action="store_true", help="suppress progress output")
    parser.add_argument(
        "--no-reference",
        action="store_true",
        help="skip the Figshare reference tables (players, teams, referees, ...)",
    )
    parser.add_argument("--no-audit", action="store_true", help="skip the post-download checks")
    parser.add_argument(
        "--audit-verbose", action="store_true", help="list checks that passed, not just findings"
    )
    args = parser.parse_args(argv)

    try:
        fetch(args.dest, commit=args.commit, force=args.force, quiet=args.quiet)
        if not args.no_reference:
            # Different source, different pin, so it keeps its own stamp -- but one
            # command, because a checkout without the dimensions is not much use.
            if not args.quiet:
                print()
            figshare.fetch(force=args.force, quiet=args.quiet)
    except (httpx.HTTPError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Checksums prove the bytes arrived intact; they say nothing about whether the
    # content is usable. Reported, never fatal -- the data is still worth having.
    if not args.no_reference and not args.no_audit:
        findings = audit("wyscout")
        if not args.quiet:
            print()
            print(format_report(findings, verbose=args.audit_verbose))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
