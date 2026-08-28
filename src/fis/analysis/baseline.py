"""Per-player baselines, and how far each match departs from them.

Reads ``fct_player_match_metrics`` via :mod:`fis.warehouse`, scores in pandas,
writes ``fct_player_match_flags``. Residual: z = (observed - median) /
(1.4826 * MAD), leave-current-out per player, with the centre shrunk toward the
position's by an empirical-Bayes weight; an uncomputable or zero MAD falls back
to the position spread or null.
A large residual is a shortlist entry, not evidence. :func:`score` is the one
scoring path every caller (CLI or sensitivity harness) must use.
"""

from __future__ import annotations

import argparse
import sys
import warnings
import zlib

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy import stats

from fis import warehouse

#: Scales MAD to a standard deviation under normality, so z reads conventionally.
MAD_TO_SIGMA = 1.4826

#: Baselines use matches above this cut; ranking uses the mart's eligibility.
BASELINE_MIN_MINUTES = 20

#: Policy floor: matches a player needs (over the baseline cut) to be evaluated
#: at all. His matches still feed the position pools either way.
MIN_PLAYER_MATCHES = 5

#: Share of rows flagged when no rate is given -- see :func:`flag`.
DEFAULT_FLAG_RATE = 0.01

MART = "fct_player_match_metrics"
FLAGS = "fct_player_match_flags"

#: Rates first, then volumes; volumes are per 90 so exposure is comparable.
RATE_METRICS = ["pass_completion_pct", "defensive_action_success_pct", "mean_action_x"]

#: Success/attempt columns for rates that are true proportions (mean_action_x is not).
PROPORTIONS = {
    "pass_completion_pct": ("passes_completed", "passes_with_outcome"),
    "defensive_action_success_pct": (
        "defensive_actions_successful",
        "defensive_actions_with_outcome",
    ),
}

#: crosses is deliberately absent -- see EXCLUDED_METRICS.
VOLUME_METRICS = ["passes", "defensive_actions", "touches_in_defensive_third"]

#: Computed by the mart, left out of the residual vector, with the reason.
EXCLUDED_METRICS = {
    "crosses_per_90": (
        "a MAD z overstates the rarity of large values for a zero-inflated "
        "count, so its scores are not on a comparable surprise scale with the "
        "rest; the correct treatment is an exposure-adjusted count model"
    ),
}
METRICS = RATE_METRICS + [f"{m}_per_90" for m in VOLUME_METRICS]

#: Every mart column prepare() and residuals() read. The raw-data dependency
#: an experiment stamp must cover.
CONSUMED = (
    "player_id",
    "match_id",
    "position_code",
    "minutes_played",
    "regulation_minutes",
    "match_has_missing_substitution",
    "has_mirrored_positions",
    "is_eligible",
    "passes",
    "defensive_actions",
    "touches_in_defensive_third",
    "pass_completion_pct",
    "defensive_action_success_pct",
    "mean_action_x",
    "passes_completed",
    "passes_with_outcome",
    "defensive_actions_successful",
    "defensive_actions_with_outcome",
)

KEY_COLUMNS = ["match_id", "player_id", "team_id", "position_code", "minutes_played"]


def load() -> pd.DataFrame:
    """Read the mart. The only impure function here, and the only I/O."""
    return warehouse.mart(MART)


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Eligible rows only, with volume metrics expressed per 90.

    Exposure is capped at regulation length so stoppage-time differences
    cannot collapse MAD; the zero-MAD path handles the resulting ties.
    """
    frame = frame[frame["minutes_played"] >= BASELINE_MIN_MINUTES].copy()
    # A missing substitution makes someone's minutes window wrong, and we cannot
    # tell whose -- so every per-90 metric in the match is unusable.
    frame = frame[~frame["match_has_missing_substitution"].fillna(False)]
    # Wyscout mirrors some goalkeeper events into the opposing frame: x is wrong
    # rather than missing, and not repairable, so position metrics are nulled.
    mirrored = frame["has_mirrored_positions"].fillna(False)
    frame.loc[mirrored, ["mean_action_x", "touches_in_defensive_third"]] = np.nan
    exposure = np.minimum(frame["minutes_played"], frame["regulation_minutes"])
    per_90 = 90.0 / exposure
    for metric in VOLUME_METRICS:
        frame[f"{metric}_per_90"] = frame[metric] * per_90
    # Counted over the baseline cut, so shape and verdict use the same matches.
    frame["player_baseline_matches"] = frame.groupby("player_id")["match_id"].transform("size")
    frame["is_scoreable"] = frame["is_eligible"].fillna(False) & (
        frame["player_baseline_matches"] >= MIN_PLAYER_MATCHES
    )
    return frame


def informativeness(frame: pd.DataFrame, metric: str) -> float:
    """How much a player's own history says about him, beyond his position.

    Between-player over within-player variance, with the sampling noise of the
    player means (mean(within/n)) subtracted from the numerator.
    """
    per_player = frame.groupby("player_id")[metric]
    counts = per_player.count()
    # Both terms from the same players: a single-match player has no variance,
    # so he cannot enter the correction and must not enter the numerator.
    usable = counts[counts >= 2].index
    if not len(usable):
        return 0.0
    variances = per_player.var(ddof=1).loc[usable]
    within = variances.mean()
    if not within or not np.isfinite(within) or within <= 0:
        return 0.0
    between = per_player.mean().loc[usable].var(ddof=1) - (variances / counts[usable]).mean()
    return float(max(between, 0.0) / within)


#: Bootstrap resamples behind each player's MAD variance.
SCALE_DRAWS = 2000


def _mad(values: np.ndarray) -> float:
    return float(np.median(np.abs(values - np.median(values))))


def scale_ratio(frame: pd.DataFrame, metric: str, draws: int = SCALE_DRAWS) -> float:
    """How much a player's own SPREAD says about him, beyond his position.

    The scale twin of :func:`informativeness`. The within term is bootstrapped
    (a jackknife is inconsistent for median-based statistics). The recovered
    ratio attenuates, so it is a floor, not a measure -- the safe direction
    for a shrinkage weight.
    """
    spreads, variances, sizes = [], [], []
    for player, group in frame.groupby("player_id"):
        # SORTED: the seed fixes the resample INDICES, so an unsorted array
        # makes the draw depend on row order -- and the frame's order is the
        # warehouse's scan order, which no query pins. A bootstrap over a
        # multiset must be a function of the values, not of their presentation.
        values = np.sort(group[metric].dropna().to_numpy(dtype=float))
        if len(values) < 3:
            continue
        rng = np.random.default_rng(zlib.crc32(f"{player}:{metric}".encode()))
        drawn = values[rng.integers(0, len(values), size=(draws, len(values)))]
        replicates = np.median(np.abs(drawn - np.median(drawn, axis=1, keepdims=True)), axis=1)
        spreads.append(_mad(values))
        variances.append(float(replicates.var(ddof=1)))
        sizes.append(len(values))
    if len(spreads) < 2:
        return 0.0
    spreads = np.asarray(spreads)
    variances = np.asarray(variances)
    within = float((np.asarray(sizes, dtype=float) * variances).mean())
    if not within or not np.isfinite(within) or within <= 0:
        return 0.0
    between = float(spreads.var(ddof=1) - variances.mean())
    return float(max(between, 0.0) / within)


def own_weight(n: np.ndarray | int, ratio: float) -> np.ndarray | float:
    """Share of a player's baseline taken from his own matches.

    The empirical-Bayes weight r*n/(r*n+1), r measured per position x metric,
    so how early a player's own history is trusted depends on the metric.
    ratio=inf (no ratio available) is the limit, weight 1, not inf/inf --
    np.where evaluates both branches, so the division is masked, not skipped.
    """
    with np.errstate(invalid="ignore"):
        return np.where(np.isfinite(ratio), ratio * n / (ratio * n + 1.0), 1.0)


def _leave_one_out(
    values: np.ndarray, centre: float = np.nan, ratio: float = np.inf
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Shrunk median, and MAD about it, of every element except each position.

    The MAD is taken around the SHRUNK centre, so it widens in proportion to
    how far the baseline was pulled.
    """
    n = len(values)
    medians = np.full(n, np.nan)
    mads = np.full(n, np.nan)
    weights = np.full(n, np.nan)
    if n < 2:
        return medians, mads, weights

    # Every leave-one-out set at once: row i is `values` without element i.
    # The loop this replaces ran two np.median calls PER ELEMENT, and at
    # 43,993 rows x 6 metrics x a condition it was most of the campaign.
    others = np.broadcast_to(values, (n, n))[~np.eye(n, dtype=bool)].reshape(n, n - 1)
    present = ~np.isnan(others)
    counts = present.sum(axis=1)

    usable = counts > 0
    # nanmedian is several times slower than median, and most players have no
    # missing metric at all -- so pay for it only when something IS missing.
    complete = bool(present.all())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN rows stay NaN
        centres = np.median(others, axis=1) if complete else np.nanmedian(others, axis=1)
        if np.isfinite(centre) and np.isfinite(ratio):
            weight = own_weight(counts, ratio)
            centres = weight * centres + (1.0 - weight) * centre
            weights[usable] = weight[usable]
        medians[usable] = centres[usable]
        deviation = np.abs(others - centres[:, None])
        spread = np.median(deviation, axis=1) if complete else np.nanmedian(deviation, axis=1)
    mads[usable] = spread[usable]
    return medians, mads, weights


def _leave_one_out_sigma(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mean and standard deviation of every element except the one at each position."""
    n = len(values)
    means = np.full(n, np.nan)
    sigmas = np.full(n, np.nan)
    for i in range(n):
        others = np.delete(values, i)
        others = others[~np.isnan(others)]
        if len(others) < 2:
            continue
        means[i] = others.mean()
        sigmas[i] = others.std(ddof=1)
    return means, sigmas


def position_baselines(frame: pd.DataFrame) -> pd.DataFrame:
    """Median and MAD per position, over every eligible match.

    Not leave-one-out: pooled over enough rows that removing one is negligible.
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


def overdispersion(frame: pd.DataFrame, metric: str) -> float:
    """A proportion's excess variance over binomial, as an intra-class correlation.

    WITHIN-player (each player's variance about his own rate), never between --
    between-player spread is the informativeness signal, not overdispersion.
    Pooled as a ratio of sums; only the pooled result is clamped.
    """
    successes, attempts = PROPORTIONS[metric]
    excess = scale = 0.0
    for _, group in frame.groupby("player_id"):
        n = group[attempts].to_numpy(dtype=float)
        k = group[successes].to_numpy(dtype=float)
        keep = n > 0
        n, k = n[keep], k[keep]
        if len(n) < 2:
            continue
        rate = k.sum() / n.sum()
        if not 0 < rate < 1:
            continue
        excess += float((k / n).var(ddof=1) - np.mean(rate * (1 - rate) / n))
        scale += float(np.mean(rate * (1 - rate) * (n - 1) / n))
    if scale <= 0:
        return 0.0
    return float(min(max(excess / scale, 0.0), 0.99))


def _beta_binomial(
    frame: pd.DataFrame,
    metric: str,
    z: np.ndarray,
    rho: np.ndarray,
    pool: np.ndarray,
    ratio: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Replace the MAD residual for a proportion with a beta-binomial tail.

    One estimator at every denominator -- no attempts threshold. The rate is
    EB-shrunk toward the position's, so the location shrinkage survives here.
    """
    successes, attempts = PROPORTIONS[metric]
    k = frame[successes].to_numpy(dtype=float)
    n = frame[attempts].to_numpy(dtype=float)
    totals = frame.assign(_k=k, _n=n).groupby("player_id")[["_k", "_n"]].transform("sum")
    # Leave-current-out, so a match cannot set the rate it is measured against.
    others_n = totals["_n"].to_numpy() - n
    own = (totals["_k"].to_numpy() - k) / np.where(others_n > 0, others_n, np.nan)

    matches = frame.groupby("player_id")["match_id"].transform("size").to_numpy() - 1
    weight = np.where(np.isfinite(ratio), own_weight(matches, ratio), 1.0)
    rate = np.where(np.isfinite(own), weight * own + (1.0 - weight) * pool, pool)

    usable = (n > 0) & np.isfinite(rate) & (rate > 0) & (rate < 1)
    if not usable.any():
        return z, 0
    k, n, rate = k[usable], n[usable], rate[usable]
    lower = np.empty(len(k))
    upper = np.empty(len(k))
    # rho = 0 is the binomial limit, taken as a limit rather than a branch.
    flat = rho[usable] <= 1e-9
    if flat.any():
        lower[flat] = stats.binom.cdf(k[flat], n[flat], rate[flat])
        upper[flat] = stats.binom.sf(k[flat] - 1, n[flat], rate[flat])
    if (~flat).any():
        concentration = 1.0 / rho[usable][~flat] - 1.0
        a = rate[~flat] * concentration
        b = (1.0 - rate[~flat]) * concentration
        lower[~flat] = stats.betabinom.cdf(k[~flat], n[~flat], a, b)
        upper[~flat] = stats.betabinom.sf(k[~flat] - 1, n[~flat], a, b)
    # Two-sided: whichever tail the result sits in, signed to keep the direction.
    tail = np.minimum(lower, upper)
    signed = np.where(lower <= upper, -1.0, 1.0)
    z = z.copy()
    z[usable] = signed * np.abs(stats.norm.ppf(np.clip(tail, 1e-12, 0.5)))
    return z, int(usable.sum())


def hyperparameters(frame: pd.DataFrame, jobs: int = -1) -> dict:
    """Every position-level shrinkage quantity, measured once from one frame.

    All must come from the CLEAN reference, never a frame carrying injections;
    grouping them makes that one decision. Also the expensive step, so a
    harness computes this once and hands it back to :func:`residuals`.
    """
    groups = dict(tuple(frame.groupby("position_code")))
    pairs = [(position, metric) for position in groups for metric in METRICS]
    scales = Parallel(n_jobs=jobs)(
        delayed(scale_ratio)(groups[position], metric) for position, metric in pairs
    )
    rates, spread = {}, {}
    for metric, (successes, attempts) in PROPORTIONS.items():
        for position, group in groups.items():
            total = group[attempts].sum()
            rates[(position, metric)] = group[successes].sum() / total if total > 0 else np.nan
            spread[(position, metric)] = overdispersion(group, metric)
    return {
        "positions": position_baselines(frame),
        "ratios": {(p, m): informativeness(groups[p], m) for p, m in pairs},
        "scales": dict(zip(pairs, scales, strict=True)),
        "rates": rates,
        "overdispersion": spread,
        "codes": tuple(groups),
    }


def residuals(
    frame: pd.DataFrame,
    reference: pd.DataFrame | None = None,
    fitted: dict | None = None,
    only: list[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Attach a z per metric, plus which baseline each row was measured against.

    ``reference`` is the frame the position-level quantities derive from
    (default: ``frame``); an injection harness passes the clean frame so a
    planted row cannot shift its own reference. ``fitted`` accepts them
    precomputed -- see :func:`hyperparameters`. Also returns counts.

    ``only`` restricts the recompute to those metrics, and the caller must
    already carry z, sigma and weight for the rest. Each metric's z depends on
    that metric alone, so an injection that moved one of them cannot change the
    others -- and recomputing all six per condition was most of a campaign.
    """
    fitted = fitted or hyperparameters(frame if reference is None else reference)
    positions = fitted["positions"]
    ratios, scale_ratios = fitted["ratios"], fitted["scales"]
    codes = fitted["codes"]
    frame = frame.sort_values(["player_id", "match_id"]).reset_index(drop=True)

    counts = {
        "own_rows": 0,
        "zero_mad_substituted": 0,
        "position_substituted": 0,
        "unusable": 0,
        "scale_ratios": scale_ratios,
    }
    eligible_per_player = frame.groupby("player_id")["match_id"].transform("size")
    frame["baseline_matches"] = eligible_per_player - 1
    counts["own_rows"] = len(frame)

    for metric in only or METRICS:
        median = np.full(len(frame), np.nan)
        mad = np.full(len(frame), np.nan)
        mean = np.full(len(frame), np.nan)
        sigma = np.full(len(frame), np.nan)
        weight = np.full(len(frame), np.nan)

        for index in frame.groupby("player_id").groups.values():
            at = frame.index.get_indexer(index)
            values = frame.loc[index, metric].to_numpy()
            position = frame.loc[index[0], "position_code"]
            own_median, own_mad, own_w = _leave_one_out(
                values,
                centre=positions[f"{metric}__median"].get(position, np.nan),
                ratio=ratios.get((position, metric), np.inf),
            )
            median[at] = own_median
            mad[at] = own_mad
            weight[at] = own_w
            own_mean, own_sd = _leave_one_out_sigma(values)
            mean[at] = own_mean
            sigma[at] = own_sd

        position_median = frame["position_code"].map(positions[f"{metric}__median"]).to_numpy()
        position_mad = frame["position_code"].map(positions[f"{metric}__mad"]).to_numpy()

        # Scale shrinkage: MAD blended toward the position spread, applied
        # before substitution and before the zero-MAD path.
        scale_weight = own_weight(
            (eligible_per_player - 1).to_numpy(dtype=float),
            frame["position_code"]
            .map({position: scale_ratios[(position, metric)] for position in codes})
            .to_numpy(dtype=float),
        )
        mad = np.where(np.isnan(mad), mad, scale_weight * mad + (1.0 - scale_weight) * position_mad)
        # Substitute where the personal quantity is uncomputable, never by
        # gate membership.
        counts["position_substituted"] += int(np.isnan(median).sum())
        median = np.where(np.isnan(median), position_median, median)
        mad = np.where(np.isnan(mad), position_mad, mad)

        # A metric that never varies gives MAD 0 and an infinite z. Fall back to
        # the position spread; where that is 0 too, say nothing.
        flat = (mad == 0) & ~np.isnan(mad)
        counts["zero_mad_substituted"] += int(flat.sum())
        mad = np.where(flat, position_mad, mad)
        mad = np.where((mad == 0) | np.isnan(mad), np.nan, mad)

        observed = frame[metric].to_numpy()
        z = (observed - median) / (MAD_TO_SIGMA * mad)

        if metric in PROPORTIONS:

            def per_position(table: dict, default: float = np.nan, metric=metric) -> np.ndarray:
                return (
                    frame["position_code"]
                    .map({p: table.get((p, metric), default) for p in codes})
                    .to_numpy(dtype=float)
                )

            z, swapped = _beta_binomial(
                frame,
                metric,
                z,
                rho=per_position(fitted["overdispersion"], 0.0),
                pool=per_position(fitted["rates"]),
                ratio=per_position(ratios, np.inf),
            )
            counts["binomial_rows"] = counts.get("binomial_rows", 0) + swapped

        counts["unusable"] += int((np.isnan(z) & ~np.isnan(observed)).sum())
        frame[f"z_{metric}"] = z
        # Position spread corroborates where the LOO sigma is uncomputable.
        sigma = np.where(np.isnan(sigma), position_mad * MAD_TO_SIGMA, sigma)
        mean = np.where(np.isnan(mean), position_median, mean)
        frame[f"sigma_{metric}"] = (observed - mean) / np.where(sigma > 0, sigma, np.nan)
        # EB weight of this row's baseline: continuous provenance.
        frame[f"weight_{metric}"] = weight

    absolute = frame[[f"z_{m}" for m in METRICS]].abs()
    frame["max_abs_z"] = absolute.max(axis=1)
    frame["mean_abs_z"] = absolute.mean(axis=1)
    frame["metrics_scored"] = absolute.notna().sum(axis=1)
    return frame, counts


def flag(frame: pd.DataFrame, rate: float = DEFAULT_FLAG_RATE) -> pd.DataFrame:
    """Flag ``rate`` of scoreable rows: the highest ``max_abs_z``, plain quantile."""
    if not 0 < rate < 1:
        raise ValueError(f"flag rate must be between 0 and 1, got {rate}")
    frame = frame.copy()
    # Sigma on the metric that drove max_abs_z, not whichever metric is widest.
    z_columns = [f"z_{m}" for m in METRICS]
    driver = frame[z_columns].abs().idxmax(axis=1).str.removeprefix("z_")
    frame["driving_metric"] = driver
    frame["baseline_weight"] = [
        frame.at[i, f"weight_{m}"] if isinstance(m, str) else np.nan for i, m in driver.items()
    ]
    scoreable = frame["max_abs_z"].dropna()
    threshold = float(np.nanquantile(scoreable, 1 - rate)) if len(scoreable) else float("nan")
    frame["flag_threshold"] = threshold
    frame["is_flagged"] = frame["max_abs_z"] >= threshold
    return frame


def evidence(frame: pd.DataFrame) -> pd.DataFrame:
    """The published columns: keys, which baseline, the evidence, the verdict."""
    baseline = ["baseline_matches", "baseline_weight", "metrics_scored"]
    per_metric = [c for metric in METRICS for c in (metric, f"z_{metric}", f"sigma_{metric}")]
    verdict = [
        "max_abs_z",
        "mean_abs_z",
        "driving_metric",
        "flag_threshold",
        "is_flagged",
    ]
    return frame[KEY_COLUMNS + baseline + per_metric + verdict]


def score(frame: pd.DataFrame, rate: float = DEFAULT_FLAG_RATE) -> tuple[pd.DataFrame, dict]:
    """Mart-shaped frame in, flagged rows out. The path every caller must use.

    Baselines are built from every match above BASELINE_MIN_MINUTES; only
    eligible rows are published and ranked.
    """
    scored, counts = residuals(prepare(frame))
    counts["baseline_rows"] = len(scored)
    scored = scored[scored["is_scoreable"]]
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
        f"  baselines: {counts['own_rows']:,} rows, own-weight median "
        f"{flagged['baseline_weight'].median():.2f}"
    )
    print(
        f"  position-substituted: {counts['position_substituted']:,}; "
        f"zero-MAD substitutions: {counts['zero_mad_substituted']:,}; "
        f"residuals left null: {counts['unusable']:,}"
    )
    print(
        f"  flagged at {args.rate:.1%}: {int(flagged['is_flagged'].sum()):,} rows, "
        f"|z| >= {flagged['flag_threshold'].iloc[0]:.2f}"
    )

    if not args.dry_run:
        warehouse.publish(FLAGS, flagged)
        print(f"  wrote {FLAGS}: {len(flagged):,} rows, {len(flagged.columns)} columns")

    # The review list: the flagged rows, ranked by the z that flagged them.
    top = (
        flagged[flagged["is_flagged"]]
        .sort_values("max_abs_z", ascending=False)
        .head(args.top)
        .copy()
    )
    top["observed"] = [top.at[i, m] for i, m in top["driving_metric"].items()]
    top["metric"] = top["driving_metric"].str.replace("_per_90", "/90", regex=False)
    columns = [
        "match_id",
        "player_id",
        "position_code",
        "minutes_played",
        "metric",
        "observed",
        "max_abs_z",
        "is_flagged",
    ]
    print(f"\nTop {args.top} by |z|:")
    print(top[columns].to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
