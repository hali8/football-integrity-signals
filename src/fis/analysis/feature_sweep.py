"""Leave-one-variable-out sweep: every metric dropped from the feature set in turn.

Arms are the full metric set plus one per metric removed. The sweep owns arm
definition, per-arm census caching and the table -- nothing else. Every score
comes from :func:`injection_test.run` under the heldout design, so no fit,
target selection or borrowing rule lives here; a second implementation of
those is exactly what this module exists to avoid.

Injection is identical across arms by construction: sizing uses the FULL
metric set whatever the arm scores, and the rng key carries no arm, so the
same (player, scorer, mechanism, severity) draws the same counts everywhere.
Only the scoring differs, which is the point of an ablation.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from fis.analysis import baseline, heldout, injection_test


#: Doses for the sweep, now identical to injection_test's ruled ladder.
SEVERITIES = injection_test.SEVERITIES


def arms(metrics: list[str] | None = None) -> dict[str, list[str]]:
    """The full feature set, then each metric dropped in turn.

    Cross-arm RATES are not comparable: a dropped metric lowers d by one, so
    the forest's 2**d borrow target halves and the fit becomes ~1.9x more
    player-specific (own_fraction median 0.375 -> 0.75 on 99.4% of rows). Pin
    the target to compare rates. Within one arm there is no artifact, and the
    cross-SCORER ordering is clean in every arm.
    """
    metrics = list(metrics or baseline.METRICS)
    out = {"all": metrics}
    for metric in metrics:
        out[f"drop:{metric}"] = [m for m in metrics if m != metric]
    return out


def sweep(
    scored: pd.DataFrame,
    raw: pd.DataFrame,
    chosen: dict[str, list[str]],
    severities: tuple[float, ...] = SEVERITIES,
    compositions: dict[str, tuple[str, ...]] | None = None,
    mechanisms: dict | None = None,
    rate: float = baseline.DEFAULT_FLAG_RATE,
    seed: int = injection_test.SEED,
    jobs: int = 1,
    cache: Path | None = None,
) -> str:
    """One block per arm: its census rates, then detection for every scorer."""
    blocks = []
    # The caveat travels with the numbers: a docstring is further from the
    # reader than a footnote, and these blocks print rates side by side.
    if any(name != "all" for name in chosen):
        blocks.append(
            "\n!! CROSS-ARM RATES ARE NOT COMPARABLE: dropping a metric halves the\n"
            "!! forest's 2**d borrow target, making the fit ~1.9x more player-specific\n"
            "!! (own_fraction median 0.375 -> 0.75 on 99.4% of rows). Read the SCORER\n"
            "!! ORDERING within each arm; do not compare detection rates between arms."
        )
    players = scored["player_id"].nunique()
    for name, metrics in chosen.items():
        started = time.time()
        # The population is part of the cache key: a --n pilot writing the
        # same filename as the full campaign would otherwise be read back
        # silently and reported as the full population.
        path = cache / f"{name.replace(':', '-')}.n{players}.parquet" if cache else None
        if path is not None and path.exists():
            census = heldout.read_census(path, scored)
        else:
            census = heldout.score_all(scored, metrics=metrics, forest=True, jobs=jobs)
            if path is not None:
                heldout.write_census(path, census, scored)
        bars = heldout.production_bars(scored, census, rate)
        results = injection_test.run(
            scored,
            raw,
            census,
            severities=severities,
            mechanisms=mechanisms,
            compositions=compositions,
            metrics=metrics,
            seed=seed,
            jobs=jobs,
            forest=True,
            design="heldout",
        )
        blocks.append(
            f"\n=== {name}  ({len(metrics)} metrics, {players:,} players, "
            f"{time.time() - started:.0f}s) ===\n"
            + injection_test.census_rates(scored, census, bars, rate)
            + injection_test.summary_persistent(
                results,
                bars,
                rate=rate,
                reference=injection_test.reference_scores(scored, census),
            )
        )
    return "\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fis-feature-sweep", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--arm",
        action="append",
        help="arms to run, e.g. 'all' or 'drop:mean_action_x' (default: 'all' "
        "alone; drop arms are opt-in because cross-arm rates are not "
        "comparable)",
    )
    parser.add_argument("--n", type=int, default=None, help="cap the number of players")
    parser.add_argument("--seed", type=int, default=injection_test.SEED)
    parser.add_argument(
        "--rate",
        type=float,
        default=baseline.DEFAULT_FLAG_RATE,
        help="share of clean rows each tagger flags",
    )
    parser.add_argument(
        "--compose",
        action="append",
        metavar="M1,M2,...",
        help="mechanisms injected JOINTLY, k allocated in quadrature across "
        "them; repeatable. Given "
        "alone it replaces the singles.",
    )
    parser.add_argument(
        "--census-dir",
        type=str,
        default=None,
        help="directory to cache each arm's census in. Censuses fit a forest "
        "per row and dominate the runtime, so caching is worth it.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=-1,
        help="players scored in parallel; -1 uses every core.",
    )
    args = parser.parse_args(argv)

    compositions = {}
    for spec in args.compose or []:
        parts = tuple(p.strip() for p in spec.split(",") if p.strip())
        unknown = [p for p in parts if p not in injection_test.MECHANISMS]
        if unknown:
            parser.error(f"unknown mechanism(s) in --compose: {unknown}")
        if len(parts) < 2:
            parser.error("--compose needs at least two mechanisms")
        compositions["+".join(parts)] = parts

    every = arms()
    if args.arm:
        unknown = [a for a in args.arm if a not in every]
        if unknown:
            parser.error(f"unknown arm(s): {unknown}; have {sorted(every)}")
        every = {a: every[a] for a in args.arm}
    else:
        # Drop arms are opt-in: their rates are not comparable to 'all', and a
        # bare command should not print a table that invites that reading.
        every = {"all": every["all"]}

    mart = baseline.load()
    frame = baseline.prepare(mart)
    scored, _ = baseline.residuals(frame)
    scored = scored[scored["is_scoreable"]]
    if args.n:
        keep = scored["player_id"].drop_duplicates().head(args.n)
        scored = scored[scored["player_id"].isin(set(keep))]

    print(
        sweep(
            scored,
            mart,
            every,
            compositions=compositions,
            mechanisms={} if compositions else None,
            rate=args.rate,
            seed=args.seed,
            jobs=args.jobs,
            cache=Path(args.census_dir) if args.census_dir else None,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
