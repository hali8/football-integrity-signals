"""Per-player baselines, and how far each match departs from them.

The first stage that is not SQL. Everything upstream is dbt; this reads
``fct_player_match_metrics`` through :mod:`fis.warehouse`, does the statistics in
pandas, and writes ``fct_player_match_flags`` back.

**A large residual is not evidence of anything.** It says a player's match looked
unlike their other matches on one measure. Injury, a tactical change, a role
switch, a red card, an unusual opponent and plain variance all produce the same
signal. The output is a shortlist to look at, and the evidence columns exist so
that looking is possible.

One scoring path, two callers
-----------------------------
:func:`score` is the whole pipeline from a mart-shaped frame to flagged rows.
The CLI calls it; so must anything that measures this detector by perturbing
data and re-scoring. If a caller re-implemented any step, a sensitivity figure
would be measuring the gap between two implementations rather than the
detector. Everything except :func:`load` is pure, so a caller can substitute its
own frame.

Method
------
For each player and metric, the baseline is the **median and MAD of that
player's other eligible matches** -- leave-current-out, so a match cannot pull
the line it is measured against. The residual is

    z = (observed - median) / (1.4826 * MAD)

where 1.4826 makes MAD estimate the standard deviation of a normal
distribution, so z reads on the familiar scale.

Two things the data forces:

* **Small samples pool.** Under ``MIN_OWN_MATCHES`` eligible matches a player's
  own median is too noisy to test against, so the baseline comes from every
  eligible player in the same registered position instead. ``baseline_source``
  records which was used, per row.
* **Zero MAD.** A player whose metric never varies gives MAD 0 and an infinite
  z. The position MAD is substituted; where that is also 0 the residual is null
  rather than invented, and both counts are reported.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from fis import warehouse

#: Scales MAD to a standard deviation under normality, so z reads conventionally.
MAD_TO_SIGMA = 1.4826

#: Below this many eligible matches, a player's own baseline is too noisy to use
#: and the position baseline is substituted. Decided up front rather than tuned.
MIN_OWN_MATCHES = 10

#: Share of rows flagged when no rate is given. Not a false-positive rate in the
#: usual sense -- see :func:`flag`.
DEFAULT_FLAG_RATE = 0.01

MART = "fct_player_match_metrics"
FLAGS = "fct_player_match_flags"

#: Rates first, then volumes. Volumes are per 90 so a substitute's twenty
#: minutes are comparable with a starter's ninety -- otherwise every residual
#: would be a minutes residual wearing another name.
RATE_METRICS = ["pass_completion_pct", "defensive_action_success_pct", "mean_action_x"]
VOLUME_METRICS = ["passes", "defensive_actions", "crosses", "touches_in_defensive_third"]
METRICS = RATE_METRICS + [f"{m}_per_90" for m in VOLUME_METRICS]

KEY_COLUMNS = ["match_id", "player_id", "team_id", "position_code", "minutes_played"]


def load() -> pd.DataFrame:
    """Read the mart. The only impure function here, and the only I/O."""
    return warehouse.mart(MART)


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Eligible rows only, with volume metrics expressed per 90.

    Exposure is capped at regulation length. Uncapped, two matches with the same
    count differ only by stoppage time, and MAD settles on that difference --
    reporting a spread orders of magnitude too small. Capped, they are identical
    and the zero-MAD path handles them.
    """
    frame = frame[frame["is_eligible"].fillna(False)].copy()
    exposure = np.minimum(frame["minutes_played"], frame["regulation_minutes"])
    per_90 = 90.0 / exposure
    for metric in VOLUME_METRICS:
        frame[f"{metric}_per_90"] = frame[metric] * per_90
    return frame


def _leave_one_out(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Median and MAD of every element except the one at each position."""
    n = len(values)
    medians = np.full(n, np.nan)
    mads = np.full(n, np.nan)
    for i in range(n):
        others = np.delete(values, i)
        others = others[~np.isnan(others)]
        if len(others) == 0:
            continue
        median = np.median(others)
        medians[i] = median
        mads[i] = np.median(np.abs(others - median))
    return medians, mads


def position_baselines(frame: pd.DataFrame) -> pd.DataFrame:
    """Median and MAD per position, over every eligible match.

    Not leave-one-out: these pool thousands of rows, so removing one moves the
    median by less than the rounding in the metric itself.
    """
    rows = []
    for position, group in frame.groupby("position_code"):
        row = {"position_code": position}
        for metric in METRICS:
            values = group[metric].dropna().to_numpy()
            median = np.median(values) if len(values) else np.nan
            row[f"{metric}__median"] = median
            row[f"{metric}__mad"] = np.median(np.abs(values - median)) if len(values) else np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("position_code")


def residuals(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Attach a z per metric, plus which baseline each row was measured against.

    Returns the frame and the counts worth reporting: how many rows were pooled,
    how often a zero MAD forced a substitution, and how many residuals could not
    be computed at all.
    """
    positions = position_baselines(frame)
    frame = frame.sort_values(["player_id", "match_id"]).reset_index(drop=True)

    counts = {"own_rows": 0, "pooled_rows": 0, "zero_mad_substituted": 0, "unusable": 0}
    eligible_per_player = frame.groupby("player_id")["match_id"].transform("size")
    use_own = eligible_per_player >= MIN_OWN_MATCHES
    frame["baseline_source"] = np.where(use_own, "player", "position")
    frame["baseline_matches"] = np.where(use_own, eligible_per_player - 1, np.nan)
    counts["own_rows"] = int(use_own.sum())
    counts["pooled_rows"] = int((~use_own).sum())

    pooled = ~use_own.to_numpy()
    for metric in METRICS:
        median = np.full(len(frame), np.nan)
        mad = np.full(len(frame), np.nan)

        for index in frame.loc[use_own].groupby("player_id").groups.values():
            at = frame.index.get_indexer(index)
            own_median, own_mad = _leave_one_out(frame.loc[index, metric].to_numpy())
            median[at] = own_median
            mad[at] = own_mad

        position_median = frame["position_code"].map(positions[f"{metric}__median"]).to_numpy()
        position_mad = frame["position_code"].map(positions[f"{metric}__mad"]).to_numpy()
        median[pooled] = position_median[pooled]
        mad[pooled] = position_mad[pooled]

        # A metric that never varies gives MAD 0 and an infinite z. Fall back to
        # the position spread; where that is 0 too, say nothing.
        flat = (mad == 0) & ~np.isnan(mad)
        counts["zero_mad_substituted"] += int(flat.sum())
        mad = np.where(flat, position_mad, mad)
        mad = np.where((mad == 0) | np.isnan(mad), np.nan, mad)

        observed = frame[metric].to_numpy()
        z = (observed - median) / (MAD_TO_SIGMA * mad)
        counts["unusable"] += int((np.isnan(z) & ~np.isnan(observed)).sum())
        frame[f"z_{metric}"] = z

    absolute = frame[[f"z_{m}" for m in METRICS]].abs()
    frame["max_abs_z"] = absolute.max(axis=1)
    frame["mean_abs_z"] = absolute.mean(axis=1)
    frame["metrics_scored"] = absolute.notna().sum(axis=1)
    return frame, counts


def flag(frame: pd.DataFrame, rate: float = DEFAULT_FLAG_RATE) -> pd.DataFrame:
    """Mark the top ``rate`` share of rows by ``max_abs_z``.

    Called a false-positive rate loosely, and it is not one. With no labelled
    cases there is nothing to be false against, so what this fixes is the
    **flag rate**: the share of rows sent for review. Whether those are false
    can only be settled by review, or by injecting known perturbations and
    measuring how many are recovered.

    The threshold is empirical rather than a fixed z, because the residual
    distribution is not normal -- pooled rows and heavy tails both push a fixed
    cutoff around. Taking a quantile fixes the review workload instead, which is
    the quantity anyone actually has to plan for.
    """
    if not 0 < rate < 1:
        raise ValueError(f"flag rate must be between 0 and 1, got {rate}")
    frame = frame.copy()
    scored = frame["max_abs_z"].dropna()
    threshold = float(np.quantile(scored, 1 - rate)) if len(scored) else np.nan
    frame["flag_threshold"] = threshold
    frame["is_flagged"] = frame["max_abs_z"] >= threshold
    return frame


def evidence(frame: pd.DataFrame) -> pd.DataFrame:
    """The published columns: keys, which baseline, the evidence, the verdict."""
    baseline = ["baseline_source", "baseline_matches", "metrics_scored"]
    per_metric = [c for metric in METRICS for c in (metric, f"z_{metric}")]
    verdict = ["max_abs_z", "mean_abs_z", "flag_threshold", "is_flagged"]
    return frame[KEY_COLUMNS + baseline + per_metric + verdict]


def score(frame: pd.DataFrame, rate: float = DEFAULT_FLAG_RATE) -> tuple[pd.DataFrame, dict]:
    """Mart-shaped frame in, flagged rows out. The path every caller must use."""
    scored, counts = residuals(prepare(frame))
    return evidence(flag(scored, rate)), counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fis-baseline", description=__doc__.splitlines()[0])
    parser.add_argument("--top", type=int, default=20, help="how many rows to print")
    parser.add_argument(
        "--rate", type=float, default=DEFAULT_FLAG_RATE, help="share of rows to flag"
    )
    parser.add_argument("--dry-run", action="store_true", help="compute but do not publish")
    args = parser.parse_args(argv)

    frame = load()
    flagged, counts = score(frame, args.rate)

    print(f"{len(flagged):,} eligible player-matches, {flagged['player_id'].nunique():,} players")
    print(
        f"  baselines: {counts['own_rows']:,} from the player's own matches, "
        f"{counts['pooled_rows']:,} pooled to position (<{MIN_OWN_MATCHES} eligible)"
    )
    print(
        f"  zero-MAD substitutions: {counts['zero_mad_substituted']:,}; "
        f"residuals left null: {counts['unusable']:,}"
    )
    print(
        f"  flagged at {args.rate:.1%}: {int(flagged['is_flagged'].sum()):,} rows, "
        f"|z| >= {flagged['flag_threshold'].iloc[0]:.2f}"
    )

    if not args.dry_run:
        warehouse.publish(FLAGS, flagged)
        print(f"  wrote {FLAGS}: {len(flagged):,} rows, {len(flagged.columns)} columns")

    top = flagged.sort_values("max_abs_z", ascending=False).head(args.top)
    columns = [
        "match_id",
        "player_id",
        "position_code",
        "minutes_played",
        "baseline_source",
        "max_abs_z",
        "mean_abs_z",
    ]
    print(f"\nTop {args.top} by |z|:")
    print(top[columns].to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
