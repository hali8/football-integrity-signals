#!/usr/bin/env python
"""Pre-commit guard: the published report must match the code it claims to describe.

Auto-fixes what is cheap (a re-render, seconds against the saved results) and
refuses what is not (an estimator change invalidates those results and needs the
whole campaign). Classification reads no data, so it works in CI; the fix needs
the warehouse, so it only runs where one exists.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
from pathlib import Path

REPORT = Path("results/phase2.md")


def _reexec_in_project_env() -> None:
    """Re-run under an interpreter that can import fis, if this one cannot.

    A push can come from any shell. pre-commit resolves `python` on PATH, which
    outside a pixi shell is either absent or a system interpreter without the
    project's dependencies -- so locate the project environment rather than
    assume the caller is in one.
    """
    sys.path.insert(0, "src")
    try:
        import fis.analysis.report  # noqa: F401

        return
    except ImportError:
        pass
    for candidate in sorted(glob.glob(".pixi/envs/*/bin/python")):
        if os.path.realpath(candidate) != os.path.realpath(sys.executable):
            os.execv(candidate, [candidate, __file__])
    print("cannot import fis and found no project environment; skipping the check")
    raise SystemExit(0)


def main() -> int:
    if not REPORT.exists():
        return 0
    _reexec_in_project_env()
    from fis import paths
    from fis.analysis.report import COLLATERAL_ARMS, STALE_MARKER, freshness

    text = REPORT.read_text(encoding="utf-8")
    # Only where the warehouse exists: CI cannot tell deleted from never-fetched.
    state, detail = freshness(
        text, results=paths.report_dir() / "phase2.parquet", arms=set(COLLATERAL_ARMS)
    )
    if state == "fresh":
        return 0

    if STALE_MARKER in text:
        # Labelled and deferred rather than silently wrong -- that is the
        # condition the guard exists to prevent, so it is satisfied.
        print(f"{REPORT}: {state}, but banded as stale -- allowed")
        return 0

    if state == "render":
        print(f"{REPORT}: {detail}\n  re-rendering...")
        done = subprocess.run(
            # --publish IS the recipe: census, results and both collateral arms.
            # Spelling it out here once cost a re-render that could not find the
            # cached payload and started a whole campaign instead.
            [sys.executable, "-m", "fis.analysis.report", "--publish"],
            env={**__import__("os").environ, "PYTHONPATH": "src"},
            check=False,  # the returncode is inspected below, both ways
        )
        if done.returncode == 0:
            print(f"  {REPORT} regenerated -- stage it and commit again")
            return 1
        print("  re-render failed (no warehouse?); commit refused")
        return 1

    print(
        f"{REPORT}: {detail}\n"
        "  This cannot be fixed by re-rendering. Either:\n"
        "    fis-report --publish --jobs -1    re-run the campaign (long), or\n"
        "    fis-report --mark-stale           label the published numbers stale\n"
        "  then stage the result. To commit anyway: SKIP=report-freshness git commit"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
