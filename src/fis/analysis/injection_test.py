"""Count-level perturbation mechanisms, calibrated in per-player sigma.

Moves underlying counts and re-derives every metric, so a perturbed row is one
real events could produce. Four mechanisms: defensive_success, pass_completion,
remove_defensive, relocate_upfield. Severity ``k`` is in sd of the calibrated
metric (player sd, or the position pool's where his cannot be computed); the
per-90 mechanisms convert through the row's exposure. ``k = 0`` must change
nothing (:func:`run` asserts it); achieved severity is reported vs requested.

Mechanisms can be COMPOSED: several applied to the same match at ``k/sqrt(n)``
each, in a fixed causal order, each seeing the row as the previous ones left
it. A single mechanism through :func:`compose` is bit-identical to calling it
directly.
"""

from __future__ import annotations

import argparse
import math
import sys
import warnings
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from fis.analysis import baseline, heldout

#: k = 0 is the null check.
SEVERITIES = (0.0, 1.0, 2.0, 3.0)

SEED = 20260823

#: The mart rounds rates to 2 decimals and mean_action_x to 4.
RATE_DECIMALS = 2
MEAN_X_DECIMALS = 4

DEFENSIVE_THIRD_MAX_X = 1.0 / 3.0


def round_half_up(value: float, decimals: int) -> float:
    """Round ties away from zero, as duckdb does; Python rounds half to even."""
    if not np.isfinite(value):
        return value
    scale = 10.0**decimals
    return float(np.floor(abs(value) * scale + 0.5) / scale * np.sign(value))


def stochastic_round(value: float, rng: np.random.Generator) -> int:
    """Round to an integer with expectation equal to ``value``."""
    if not np.isfinite(value) or value <= 0:
        return 0
    floor = np.floor(value)
    return int(floor + (rng.random() < value - floor))


def _exposure(row: pd.Series) -> float:
    return float(min(row["minutes_played"], row["regulation_minutes"]))


def _relabel(
    row: pd.Series,
    sd: float,
    k: float,
    rng: np.random.Generator,
    success_col: str,
    denom_col: str,
    metric: str,
) -> dict[str, float]:
    denom = float(row[denom_col])
    successes = float(row[success_col])
    if denom <= 0 or not np.isfinite(sd) or sd <= 0:
        return {}
    moved = stochastic_round(k * sd * denom, rng)
    new = int(min(max(successes - moved, 0), denom))
    return {
        success_col: new,
        metric: round_half_up(100.0 * new / denom, RATE_DECIMALS),
    }


def defensive_success(row, sds, k, rng):
    return _relabel(
        row,
        sds["defensive_success"],
        k,
        rng,
        "defensive_actions_successful",
        "defensive_actions_with_outcome",
        "defensive_action_success_pct",
    )


def pass_completion(row, sds, k, rng):
    return _relabel(
        row,
        sds["pass_completion"],
        k,
        rng,
        "passes_completed",
        "passes_with_outcome",
        "pass_completion_pct",
    )


def _hypergeom(good: int, total: int, drawn: int, rng: np.random.Generator) -> int:
    """How many of ``drawn`` removals hit the ``good`` subgroup of ``total``."""
    good, total, drawn = int(good), int(total), int(drawn)
    if drawn <= 0 or total <= 0 or good <= 0:
        return 0
    return int(rng.hypergeometric(good, max(total - good, 0), min(drawn, total)))


def _x_means(row: pd.Series) -> tuple[float, float, float, float]:
    """(sum x, positioned count, mean x in the third, mean x outside it).

    total_x is reconstructed from the mart's 4dp-rounded mean_action_x, so the
    region means can leave [0, 1] on small counts; clamped.
    """
    n_pos = float(row["attempts_with_position"])
    total_x = float(row["mean_action_x"]) * n_pos
    in_third = float(row["touches_in_defensive_third"])
    sum_third = float(row["sum_start_x_in_defensive_third"])
    mean_third = sum_third / in_third if in_third > 0 else np.nan
    outside = n_pos - in_third
    mean_out = (total_x - sum_third) / outside if outside > 0 else np.nan
    return total_x, n_pos, np.clip(mean_third, 0.0, 1.0), np.clip(mean_out, 0.0, 1.0)


def remove_defensive(row, sds, k, rng):
    sd = sds["defensive_actions"]
    total = int(row["defensive_actions"])
    if total <= 0 or not np.isfinite(sd) or sd <= 0:
        return {}
    exposure = _exposure(row)
    n = min(stochastic_round(k * sd, rng), total)
    if n == 0:
        return {}

    with_outcome = int(row["defensive_actions_with_outcome"])
    successful = int(row["defensive_actions_successful"])
    in_third = int(row["defensive_actions_in_defensive_third"])
    gone_outcome = _hypergeom(with_outcome, total, n, rng)
    gone_success = _hypergeom(successful, with_outcome, gone_outcome, rng)
    gone_third = _hypergeom(in_third, total, n, rng)

    out = {
        "defensive_actions": total - n,
        "defensive_actions_with_outcome": with_outcome - gone_outcome,
        "defensive_actions_successful": successful - gone_success,
        "defensive_actions_in_defensive_third": in_third - gone_third,
        "actions": float(row["actions"]) - n,
        "defensive_actions_per_90": (total - n) * 90.0 / exposure,
    }
    if with_outcome - gone_outcome > 0:
        out["defensive_action_success_pct"] = round_half_up(
            100.0 * (successful - gone_success) / (with_outcome - gone_outcome), RATE_DECIMALS
        )
    else:
        out["defensive_action_success_pct"] = np.nan

    touches = float(row["touches_in_defensive_third"])
    out["touches_in_defensive_third"] = touches - gone_third
    out["touches_in_defensive_third_per_90"] = (touches - gone_third) * 90.0 / exposure

    # Deleted actions carry the group-mean x of the region they left; the
    # exact composition is unknowable at mart level.
    total_x, n_pos, mean_third, mean_out = _x_means(row)
    fallback = float(row["mean_action_x"])
    x_third = mean_third if np.isfinite(mean_third) else fallback
    x_out = mean_out if np.isfinite(mean_out) else fallback
    # The third's x-mass leaves with its actions, so a composed mechanism
    # running after this one reads region means consistent with the thinning.
    out["sum_start_x_in_defensive_third"] = max(
        float(row["sum_start_x_in_defensive_third"]) - gone_third * x_third, 0.0
    )
    removed_x = gone_third * x_third + (n - gone_third) * x_out
    if n_pos - n > 0:
        # Clamped like the region means: the reconstruction carries the mart's
        # 4dp rounding residual.
        out["mean_action_x"] = round_half_up(
            float(np.clip((total_x - removed_x) / (n_pos - n), 0.0, 1.0)), MEAN_X_DECIMALS
        )
        out["attempts_with_position"] = n_pos - n
    return out


def relocate_upfield(row, sds, k, rng):
    sd = sds["touches_in_defensive_third"]
    touches = int(row["touches_in_defensive_third"])
    if touches <= 0 or not np.isfinite(sd) or sd <= 0:
        return {}
    exposure = _exposure(row)
    n = min(stochastic_round(k * sd, rng), touches)
    if n == 0:
        return {}

    total_x, n_pos, mean_third, mean_out = _x_means(row)
    # Destination: the player's own out-of-third mean, or the boundary when
    # every positioned action was in the third.
    x_dest = mean_out if np.isfinite(mean_out) else DEFENSIVE_THIRD_MAX_X
    x_from = mean_third if np.isfinite(mean_third) else DEFENSIVE_THIRD_MAX_X

    out = {
        "touches_in_defensive_third": touches - n,
        "touches_in_defensive_third_per_90": (touches - n) * 90.0 / exposure,
        "defensive_actions_in_defensive_third": float(row["defensive_actions_in_defensive_third"])
        - _hypergeom(int(row["defensive_actions_in_defensive_third"]), touches, n, rng),
        "sum_start_x_in_defensive_third": (touches - n) * x_from,
    }
    if n_pos > 0:
        # Same clamp as remove_defensive's write.
        out["mean_action_x"] = round_half_up(
            float(np.clip((total_x + n * (x_dest - x_from)) / n_pos, 0.0, 1.0)),
            MEAN_X_DECIMALS,
        )
    return out


def throttle_defensive(row, sds, k, rng):
    """Lose a FRACTION k of successful defensive actions, not k sigma.

    Each success survives with probability 1-k, drawn rather than rounded.
    Reported like the others in sd of the controlled count.
    """
    denom = float(row["defensive_actions_with_outcome"])
    successes = int(row["defensive_actions_successful"])
    if denom <= 0 or successes <= 0 or not 0 < k <= 1:
        return {}
    kept = int(rng.binomial(successes, 1.0 - k))
    return {
        "defensive_actions_successful": kept,
        "defensive_action_success_pct": round_half_up(100.0 * kept / denom, RATE_DECIMALS),
    }


MECHANISMS = {
    "defensive_success": defensive_success,
    "pass_completion": pass_completion,
    "remove_defensive": remove_defensive,
    "relocate_upfield": relocate_upfield,
    "throttle_defensive": throttle_defensive,
}

#: Severity ladder per mechanism. throttle_defensive is a fraction of successes
#: lost, not a sigma count; achieved is reported in count sd either way.
LADDERS = {"throttle_defensive": (0.0, 0.10, 0.25, 0.50)}

#: Application order under composition, and the set that CAN compose: removal
#: first so relabellings are sized against surviving denominators, relocation
#: against the thinned positional state, relabellings last. throttle_defensive
#: is absent because its severity is a fraction, so k/sqrt(n) has no meaning.
COMPOSITION_ORDER = (
    "remove_defensive",
    "relocate_upfield",
    "defensive_success",
    "pass_completion",
)

#: Rows a player needs before his OWN spread sizes his injection rather than
#: his position pool's; an sd from two points is too noisy to define "k sigma"
#: against. Decides only how hard a player is hit, never whether he is scored.
MIN_SPREAD_ROWS = 4

#: The single count each mechanism moves directly and calibrates its severity
#: against -- one degree of freedom each, so "k sigma" stays well defined; the
#: other columns follow from that one draw.
CONTROLS = {
    "throttle_defensive": "defensive_actions_successful",
    "defensive_success": "defensive_actions_successful",
    "pass_completion": "passes_completed",
    "remove_defensive": "defensive_actions",
    "relocate_upfield": "touches_in_defensive_third",
}

#: The metric each mechanism primarily moves; the delivered shift is also
#: reported in the detector's z on it, one currency across mechanisms.
OBSERVABLES = {
    "defensive_success": "defensive_action_success_pct",
    "throttle_defensive": "defensive_action_success_pct",
    "pass_completion": "pass_completion_pct",
    "remove_defensive": "defensive_actions_per_90",
    "relocate_upfield": "touches_in_defensive_third_per_90",
}

#: Mechanisms that relabel outcomes inside a frozen denominator. Their DOF is
#: successes GIVEN attempts, so k is sized by the CONDITIONAL spread (sd of the
#: rate times this match's denominator), not the marginal count sd.
RATE_CONTROLS = {
    "defensive_success": ("defensive_actions_successful", "defensive_actions_with_outcome"),
    "pass_completion": ("passes_completed", "passes_with_outcome"),
}


def compose(
    row: pd.Series,
    sds: dict[str, float],
    k: float,
    names: tuple[str, ...],
    rng_for,
) -> tuple[dict[str, float], dict[str, dict]]:
    """Apply ``names`` jointly, each at ``k / sqrt(n)`` of its own sigma.

    Mechanisms run in :data:`COMPOSITION_ORDER`, each seeing the row as the
    previous ones left it, so a relabelling is sized by its THINNED
    denominator. ``rng_for(name, scaled_k)`` supplies each mechanism's stream,
    keyed so a single mechanism through here draws exactly what it draws
    directly. Returns the merged updates against the ORIGINAL row and one
    record per mechanism for per-DOF achieved reporting.
    """
    if len(names) == 1:
        # k / sqrt(1) is k bit-exactly; no sigma axis needed, none assumed.
        ordered = list(names)
    else:
        strangers = [n for n in names if n not in COMPOSITION_ORDER]
        if strangers:
            raise ValueError(
                f"cannot compose {strangers}: severity is not on the sigma axis, "
                "so k/sqrt(n) has no meaning"
            )
        ordered = [n for n in COMPOSITION_ORDER if n in names]
    scaled = k / math.sqrt(len(ordered))
    working = row.copy()
    merged: dict[str, float] = {}
    steps: dict[str, dict] = {}
    for name in ordered:
        control = CONTROLS[name]
        before = float(working[control])
        denominator = float(working[RATE_CONTROLS[name][1]]) if name in RATE_CONTROLS else np.nan
        updates = MECHANISMS[name](working, sds, scaled, rng_for(name, scaled))
        for column, value in updates.items():
            working[column] = value
        merged.update(updates)
        steps[name] = {
            "control": control,
            "before": before,
            "after": float(updates[control]) if control in updates else before,
            "moved": control in updates,
            "denominator": denominator,
        }
    return merged, steps


def step_achieved(name: str, step: dict, spreads: dict[str, float]) -> float:
    """One mechanism's delivered shift, in the sigma its severity was sized in:
    marginal count sd for volume, conditional (rate sd times the denominator it
    actually moved within -- thinned, under composition) for relabellings."""
    spread = spreads.get(step["control"])
    if name in RATE_CONTROLS:
        denom = step["denominator"]
        rate_sd = spreads.get(name)
        spread = rate_sd * denom if rate_sd and denom > 0 else None
    return (
        (step["after"] - step["before"]) / spread
        if step["moved"] and spread and np.isfinite(spread)
        else 0.0
    )


def calibration_sds(
    train: pd.DataFrame, position_sds: dict[str, dict[str, float]], position: str
) -> dict[str, float]:
    """Sd of each controlled COUNT over the player's other matches, falling
    back to the position pool's spread on a thin history."""
    out = {}
    for column in CONTROLS.values():
        values = train[column].dropna()
        if len(values) >= MIN_SPREAD_ROWS:
            out[column] = float(values.std(ddof=1))
        else:
            out[column] = position_sds.get(position, {}).get(column, np.nan)
    # Conditional spread for the relabelling mechanisms.
    for name, (success, denom) in RATE_CONTROLS.items():
        usable = train[train[denom] > 0]
        rates = (usable[success] / usable[denom]).dropna()
        out[name] = (
            float(rates.std(ddof=1))
            if len(rates) >= MIN_SPREAD_ROWS
            else position_sds.get(position, {}).get(name, np.nan)
        )
    return out


def position_spreads(scored: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Fallback spread of each controlled count: WITHIN-player, pooled by
    position -- the pooled-rows spread would mix in between-player differences
    a single player's match-to-match variation does not contain."""
    out = {}
    for position, g in scored.groupby("position_code"):
        spreads = {
            c: float(np.sqrt(g.groupby("player_id")[c].var(ddof=1).mean()))
            for c in CONTROLS.values()
        }
        for name, (success, denom) in RATE_CONTROLS.items():
            usable = g[g[denom] > 0].assign(_r=lambda d: d[success] / d[denom])
            spreads[name] = float(np.sqrt(usable.groupby("player_id")["_r"].var(ddof=1).mean()))
        out[position] = spreads
    return out


#: Scorers compared, each picking its own target row -- raw and residual
#: space disagree about which match is a player's most typical.
SCORERS = ("max", "mahalanobis", "mahalanobis_z")


def select_targets(
    scored: pd.DataFrame, census: pd.DataFrame, scorers: tuple[str, ...] = SCORERS
) -> set[tuple]:
    """One (player, match) per scorer: the match closest to his median CLEAN
    score under that scorer, chosen before anything is perturbed.

    Selection is per scorer AND per feature set -- the census carries scores
    computed under whatever metric set the caller ran. One shared target would
    hand the selecting scorer its hardest case and every other scorer an
    easier-than-typical row. A scorer that cannot score a player is still
    tested on him -- shipped rule's target, NaN score, counted as a miss -- so
    narrow coverage is paid for rather than flattered.
    """
    keys = ["player_id", "match_id"]
    clean_scores = census.merge(scored[keys + ["max_abs_z"]], on=keys, how="left").rename(
        columns={"max_abs_z": "max"}
    )

    def median_row(frame: pd.DataFrame, column: str) -> dict:
        usable = frame.dropna(subset=[column])
        typical = usable.groupby("player_id")[column].transform("median")
        pick = usable.assign(_d=(usable[column] - typical).abs()).sort_values("_d")
        pick = pick.groupby("player_id").head(1)
        return dict(zip(pick["player_id"], pick["match_id"]))

    default = median_row(clean_scores, "max")
    targets = set()
    for scorer in scorers:
        chosen = median_row(clean_scores, scorer)
        for player, match in default.items():
            targets.add((player, chosen.get(player, match), scorer))
    return targets


def run(
    scored: pd.DataFrame,
    raw: pd.DataFrame,
    census: pd.DataFrame,
    severities: tuple[float, ...] = SEVERITIES,
    mechanisms: dict | None = None,
    compositions: dict[str, tuple[str, ...]] | None = None,
    metrics: list[str] | None = None,
    limit_players: int | None = None,
    seed: int = SEED,
    jobs: int = 1,
) -> pd.DataFrame:
    """One match per player perturbed by every mechanism at every severity.

    A manipulator fixes a match, not a career, so exactly one row per player is
    injected. Each scorer picks its own target -- the match nearest that
    player's median score under that scorer. The perturbed row is always the
    held-out one; ``census`` supplies the clean scores targets are chosen from.

    ``compositions`` maps a name to mechanism names injected JOINTLY at
    ``k/sqrt(n)`` each; those rows carry per-DOF achieved columns. ``metrics``
    narrows the multivariate scorers' feature set (the census must have been
    scored under the same set); injection sizing always uses the shipped set,
    so the perturbation is identical across feature-set arms.
    """
    warnings.filterwarnings("ignore")
    mechanisms = MECHANISMS if mechanisms is None else mechanisms
    compositions = compositions or {}
    metrics = list(metrics) if metrics is not None else list(baseline.METRICS)
    pos_sds = position_spreads(scored)
    # Hyperparameters from the clean frame, computed once.
    fitted = baseline.hyperparameters(baseline.prepare(raw), jobs=jobs)

    zcols = heldout.residual_columns(metrics)
    floor = len(metrics) + 2
    position_fits, position_z, position_rows = {}, {}, {}
    position_nu, position_nu_z = {}, {}
    for position in heldout.POSITIONS:
        pool = scored[scored["position_code"] == position].dropna(subset=metrics)
        if len(pool) < floor:
            continue
        position_rows[position] = pool[metrics].to_numpy(dtype=float)
        position_fits[position] = heldout._Fit(position_rows[position])
        ids = pool["player_id"].to_numpy()
        position_nu[position] = heldout.covariance_nu(position_rows[position], ids)
        frame_z = pool[zcols + ["player_id"]].dropna()
        pz = frame_z[zcols].to_numpy(dtype=float)
        position_z[position] = heldout._Fit(pz) if len(pz) >= floor else None
        position_nu_z[position] = heldout.covariance_nu(pz, frame_z["player_id"].to_numpy())

    keys = ["player_id", "match_id"]
    targets = select_targets(scored, census)

    def score_frame(frame: pd.DataFrame) -> pd.DataFrame:
        """Every row scored through the shipped residual path, position
        reference pinned to the clean frame. The player's own history is left
        contaminated on purpose -- that is what the collateral columns measure.
        """
        rescored, _ = baseline.residuals(baseline.prepare(frame), fitted=fitted)
        rescored = rescored[rescored["is_scoreable"]]
        flagged = baseline.flag(rescored, baseline.DEFAULT_FLAG_RATE)
        out = []
        for _, g in flagged.groupby("player_id"):
            position = g["position_code"].iloc[0]
            if position not in position_fits:
                continue
            pool_fit, pool_z = position_fits[position], position_z.get(position)
            complete = g.dropna(subset=metrics)
            cx = complete[metrics].to_numpy(dtype=float)
            cz = complete[zcols].to_numpy(dtype=float)
            cids = complete["match_id"].to_numpy()
            for x, zrow, mid, top, gate in zip(
                g[metrics].to_numpy(dtype=float),
                g[zcols].to_numpy(dtype=float),
                g["match_id"].to_numpy(),
                g["max_abs_z"].to_numpy(),
                g["sd_from_mean"].to_numpy(),
            ):
                keep = cids != mid
                fit = pool_fit
                if keep.sum() >= 2:
                    fit = heldout._Fit(
                        cx[keep],
                        target=pool_fit.cov,
                        weight=heldout.shrinkage_weight(
                            int(keep.sum()), position_nu.get(position, np.inf)
                        ),
                        pool=position_rows.get(position),
                    )
                ztrain = cz[keep]
                ztrain = ztrain[~np.isnan(ztrain).any(axis=1)]
                zdist = np.nan
                if len(ztrain) >= 2:
                    zfit = heldout._Fit(
                        ztrain,
                        target=pool_z.cov if pool_z is not None else None,
                        weight=heldout.shrinkage_weight(
                            len(ztrain), position_nu_z.get(position, np.inf)
                        ),
                    )
                    zdist = zfit.distance(zrow)
                record = {
                    "player_id": g["player_id"].iloc[0],
                    "match_id": mid,
                    "position_code": position,
                    "max": top,
                    "sigma": gate,
                    "mahalanobis": fit.distance(x),
                    "mahalanobis_z": zdist,
                }
                record.update(dict(zip(zcols, zrow)))
                out.append(record)
        return pd.DataFrame(out)

    # Every player's spread, computed once from clean data -- always over the
    # SHIPPED metric set, so the injection does not change with ``metrics``.
    spreads = {
        pid: calibration_sds(g.dropna(subset=baseline.METRICS), pos_sds, g["position_code"].iloc[0])
        for pid, g in scored.groupby("player_id")
    }
    by_key = raw.set_index(keys)
    clean = score_frame(raw).set_index(keys)

    # Singles are one-mechanism recipes through the same compose() path.
    recipes = [(name, (name,)) for name in mechanisms]
    recipes += [(name, tuple(parts)) for name, parts in compositions.items()]

    rows = []
    for scorer in SCORERS:
        chosen = {p: m for p, m, sc in targets if sc == scorer}
        for name, parts in recipes:
            composed = len(parts) > 1
            zobs = f"z_{OBSERVABLES[name]}" if name in OBSERVABLES else None
            ladder = severities if composed else LADDERS.get(name, severities)
            for k in ladder:
                # Every target is fixed at once, then the WHOLE frame is
                # re-scored, so the position-level knock-on is included.
                patch, achieved, details, noop = {}, {}, {}, set()
                for player_id, match_id in chosen.items():
                    if (player_id, match_id) not in by_key.index:
                        continue
                    test = by_key.loc[(player_id, match_id)]

                    def rng_for(mechanism_name, scaled_k):
                        return np.random.default_rng(
                            [
                                seed,
                                zlib.crc32(
                                    f"{player_id}|{scorer}|{mechanism_name}|{scaled_k}".encode()
                                ),
                            ]
                        )

                    updates, steps = compose(test, spreads.get(player_id, {}), k, parts, rng_for)
                    if not updates or all(
                        np.isclose(float(test[c]), v, equal_nan=True) for c, v in updates.items()
                    ):
                        # A no-op draw is recorded, not skipped: for a fraction
                        # mechanism that IS the result.
                        noop.add(player_id)
                        achieved[player_id] = 0.0
                        details[player_id] = {p: 0.0 for p in parts}
                        continue
                    if k == 0:
                        moved = {
                            c: (float(test[c]), v)
                            for c, v in updates.items()
                            if not np.isclose(float(test[c]), v, equal_nan=True)
                        }
                        if moved:
                            raise AssertionError(f"null perturbation moved {name}: {moved}")
                        continue
                    patch[(player_id, match_id)] = updates
                    per = {p: step_achieved(p, steps[p], spreads.get(player_id, {})) for p in parts}
                    details[player_id] = per
                    # A composed row has no single sigma unit; its scalar is
                    # NaN and the per-DOF achieved_* columns carry the shift.
                    achieved[player_id] = per[name] if not composed else np.nan
                if k == 0 or not patch:
                    continue

                fixed = raw.copy()
                for (player_id, match_id), updates in patch.items():
                    mask = (fixed["player_id"] == player_id) & (fixed["match_id"] == match_id)
                    for column, value in updates.items():
                        fixed.loc[mask, column] = value
                after = score_frame(fixed).set_index(keys)

                shared = clean.index.intersection(after.index)
                for key in shared:
                    player_id, match_id = key
                    if player_id not in achieved:
                        continue
                    bit = player_id not in noop
                    is_target = chosen.get(player_id) == match_id
                    record = {
                        "player_id": player_id,
                        "match_id": match_id,
                        "position_code": clean.at[key, "position_code"],
                        "scorer": scorer,
                        "mechanism": name,
                        "severity": k,
                        "is_target": is_target,
                        "bit": bit,
                        "achieved": achieved[player_id],
                        "achieved_z": (
                            after.at[key, zobs] - clean.at[key, zobs]
                            if is_target and zobs is not None and zobs in after.columns
                            else np.nan
                        ),
                        "clean": clean.at[key, scorer],
                        "after": after.at[key, scorer],
                        "sigma_clean": clean.at[key, "sigma"],
                        "sigma_after": after.at[key, "sigma"],
                    }
                    if composed:
                        for p in parts:
                            p_obs = f"z_{OBSERVABLES[p]}"
                            record[f"achieved_{p}"] = details[player_id][p]
                            record[f"achieved_z_{p}"] = (
                                after.at[key, p_obs] - clean.at[key, p_obs]
                                if is_target and p_obs in after.columns
                                else np.nan
                            )
                    rows.append(record)
    return pd.DataFrame(rows)


def census_rates(
    scored: pd.DataFrame,
    census: pd.DataFrame,
    bars: dict[str, float],
    rate: float = baseline.DEFAULT_FLAG_RATE,
    sigma_gate: float = baseline.CORROBORATING_SIGMA,
) -> str:
    """Share of the CENSUS each bar actually flags, which must equal ``rate``
    -- a bug check, and the anchor every other rate is read against."""
    flagged = baseline.flag(scored, rate)
    parts = [f"max {flagged['is_flagged'].mean():.4%}"]
    for name in SCORERS:
        if name == "max":
            continue
        column = census[name].dropna()
        if not len(column) or not np.isfinite(bars[name]):
            parts.append(f"{name} n/a")
        else:
            parts.append(f"{name} {(column >= bars[name]).mean():.4%}")
    return f"census flags (target {rate:.4%}): " + "  ".join(parts)


def summary_persistent(
    results: pd.DataFrame,
    bars: dict[str, float],
    sigma_gate: float = baseline.CORROBORATING_SIGMA,
) -> str:
    """Detection on the fixed match, and what it did to the player's others."""
    lines = []
    for name in results["mechanism"].unique():
        for k in sorted(results.loc[results.mechanism == name, "severity"].unique()):
            block = results[(results.mechanism == name) & (results.severity == k)]
            # Composed blocks report per DOF; a scalar mean would mix units.
            per_dof = [
                c.removeprefix("achieved_")
                for c in block.columns
                if c.startswith("achieved_")
                and c != "achieved_z"
                and not c.startswith("achieved_z_")
                and block[c].notna().any()
            ]
            if per_dof:
                on_target = block[block.is_target]
                delivered = "  ".join(
                    f"{p} {on_target[f'achieved_{p}'].mean():+.2f}sd"
                    f"/{on_target[f'achieved_z_{p}'].mean():+.2f}z"
                    for p in per_dof
                )
                lines.append(f"\n-- {name}  k={k:g}  per-DOF {delivered}")
            else:
                lines.append(
                    f"\n-- {name}  k={k:g}  "
                    f"achieved {block.loc[block.is_target, 'achieved'].mean():+.2f} sd"
                    f"  ({block.loc[block.is_target, 'achieved_z'].mean():+.2f} z)"
                )
            for scorer in SCORERS:
                r = block[block.scorer == scorer]
                if r.empty:
                    continue
                cut = bars[scorer]
                gate_after = r["sigma_after"].abs() >= sigma_gate
                gate_clean = r["sigma_clean"].abs() >= sigma_gate
                hit = r["after"] >= cut
                was = r["clean"] >= cut
                if scorer == "max":
                    hit, was = hit & gate_after, was & gate_clean
                t, o = r.is_target, ~r.is_target
                # Bar crossings are too rare to measure collateral on, so
                # report the signed score shift of the player's OTHER matches;
                # rows whose fit never contained the target cannot move, so
                # they are excluded from the median.
                shift = r.loc[o, "after"] - r.loc[o, "clean"]
                spread = r.loc[o, "clean"].std()
                stirred = shift[shift.abs() > 1e-9]
                middle = stirred.median() if len(stirred) else np.nan
                lines.append(
                    f"  {scorer:12} bar {cut:6.2f}"
                    f" | target caught {hit[t].mean():5.1%} (n={int(t.sum()):,})"
                    f" | others {was[o].mean():5.1%} -> {hit[o].mean():5.1%}"
                    f" | of {len(stirred):,}/{int(o.sum()):,} contaminated:"
                    f" shift {middle:+.4f}"
                    f" ({middle / spread if spread else np.nan:+.3f} sd)"
                )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fis-injection-test", description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=None, help="cap the number of players")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--mechanism",
        choices=sorted(MECHANISMS),
        action="append",
        help="restrict to one or more mechanisms (default: all, unless --compose is given)",
    )
    parser.add_argument(
        "--compose",
        action="append",
        metavar="M1,M2,...",
        help="mechanisms injected JOINTLY on the same match at k/sqrt(n) each; "
        "repeatable. Given alone it replaces the singles; add --mechanism "
        "to run singles alongside.",
    )
    parser.add_argument(
        "--drop-metric",
        choices=list(baseline.METRICS),
        action="append",
        help="remove a metric from the multivariate feature set; repeatable. "
        "The shipped rule and the injection keep the full set; census, "
        "bars and target selection follow the reduced one.",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=baseline.DEFAULT_FLAG_RATE,
        help="share of clean rows each tagger flags",
    )
    parser.add_argument("--out", type=str, default=None, help="write per-row results as parquet")
    parser.add_argument(
        "--census",
        type=str,
        default=None,
        help="parquet to cache the clean census in; reused if it exists. "
        "Per feature set: --drop-metric adds a suffix.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="players scored in parallel; -1 uses every core. Results do not depend on it.",
    )
    parser.add_argument(
        "--forest",
        action="store_true",
        help="also score the isolation forest in the census. One fit per row, so "
        "pair it with --jobs; a cached --census built without it has no forest column.",
    )
    args = parser.parse_args(argv)

    dropped = sorted(set(args.drop_metric or []))
    metrics = [m for m in baseline.METRICS if m not in dropped]
    compositions = {}
    for spec in args.compose or []:
        parts = tuple(p.strip() for p in spec.split(",") if p.strip())
        unknown = [p for p in parts if p not in MECHANISMS]
        if unknown:
            parser.error(f"unknown mechanism(s) in --compose: {unknown}")
        if len(parts) < 2:
            parser.error("--compose needs at least two mechanisms; use --mechanism for one")
        compositions["+".join(parts)] = parts

    mart = baseline.load()
    frame = baseline.prepare(mart)
    # No pre-filter: baselines come from every match above the baseline cut,
    # as baseline.score does.
    scored, _ = baseline.residuals(frame)
    scored = scored[scored["is_scoreable"]]

    # Every eligible row scored clean: the population the bars come from and
    # the pool each scorer picks its target out of.
    cache = Path(args.census) if args.census else None
    if cache and dropped:
        cache = cache.with_name(f"{cache.stem}.drop-{'-'.join(dropped)}{cache.suffix}")
    if cache and cache.exists():
        census = pd.read_parquet(cache)
    else:
        census = heldout.score_all(
            scored,
            metrics=metrics,
            limit_players=args.n,
            jobs=args.jobs,
            forest=args.forest,
        )
        if cache:
            census.to_parquet(cache, index=False)
    bars = heldout.production_bars(scored, census, args.rate)
    if args.mechanism:
        chosen = {m: MECHANISMS[m] for m in args.mechanism}
    elif compositions:
        chosen = {}
    else:
        chosen = None
    results = run(
        scored,
        mart,
        census,
        mechanisms=chosen,
        compositions=compositions,
        metrics=metrics,
        limit_players=args.n,
        seed=args.seed,
        jobs=args.jobs,
    )
    if args.out:
        results.to_parquet(args.out, index=False)
    print(census_rates(scored, census, bars, args.rate))
    print(summary_persistent(results, bars))
    return 0


if __name__ == "__main__":
    sys.exit(main())
