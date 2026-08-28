"""Count-level perturbation mechanisms, calibrated in per-player sigma.

Moves underlying counts and re-derives every metric, so a perturbed row is one
real events could produce. Four mechanisms: defensive_success, pass_completion,
remove_defensive, relocate_upfield. Severity ``k`` is in sd of the calibrated
metric (player sd, or the position pool's where his cannot be computed); the
per-90 mechanisms convert through the row's exposure. ``k = 0`` must change
nothing (:func:`run` asserts it); achieved severity is reported vs requested.

Mechanisms can be COMPOSED: several applied to the same match in a fixed causal
order, each seeing the row as the previous ones left it. The requested ``k`` is
allocated across them in QUADRATURE, channels short of substrate pinned at
their ceiling and the remainder re-split, so the total displacement honours the
label rather than under-delivering. A single mechanism through
:func:`compose` is bit-identical to calling it directly.
"""

from __future__ import annotations

import argparse
import itertools
import math
import os
import sys
import time
import warnings
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from fis.analysis import baseline, heldout

#: k = 0 is the null check. 1.5 rather than 2.0 is the ruled ladder: k feeds
#: the rng key, so runs on different ladders share no draws and cannot pool.
SEVERITIES = (0.0, 1.0, 1.5, 3.0)

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
    out = {
        success_col: new,
        metric: round_half_up(100.0 * new / denom, RATE_DECIMALS),
    }
    # Running out of successes to relabel truncates the dose. This is the clamp
    # that actually binds -- defensive_success delivers about a third of what is
    # asked at k=3 -- so it is the one the report must count.
    if successes - moved < 0 or successes - moved > denom:
        out[CLIPPED] = True
    return out


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


#: Marks an update whose dose was truncated for want of substrate. Stripped in
#: compose(), so it never reaches the frame as a column.
CLIPPED = "_clipped"


def clip_unit(value: float, out: dict) -> float:
    """Clamp a reconstructed mean to [0, 1], recording whether it bound.

    A bound clamp means the row received LESS than the requested dose, so the
    achieved figure understates by an unmeasured amount. Silently discarding
    that reads as a detector miss when it is a delivery shortfall.
    """
    clipped = float(np.clip(value, 0.0, 1.0))
    if not np.isclose(clipped, value, equal_nan=True):
        out[CLIPPED] = True
    return clipped


def remove_defensive(row, sds, k, rng):
    sd = sds["defensive_actions"]
    total = int(row["defensive_actions"])
    if total <= 0 or not np.isfinite(sd) or sd <= 0:
        return {}
    exposure = _exposure(row)
    wanted = stochastic_round(k * sd, rng)
    n = min(wanted, total)
    if n == 0:
        return {}
    truncated = wanted > total

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
    if truncated:
        out[CLIPPED] = True

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
            clip_unit((total_x - removed_x) / (n_pos - n), out), MEAN_X_DECIMALS
        )
        out["attempts_with_position"] = n_pos - n
    return out


def relocate_upfield(row, sds, k, rng):
    sd = sds["touches_in_defensive_third"]
    touches = int(row["touches_in_defensive_third"])
    if touches <= 0 or not np.isfinite(sd) or sd <= 0:
        return {}
    exposure = _exposure(row)
    wanted = stochastic_round(k * sd, rng)
    n = min(wanted, touches)
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
    if wanted > touches:
        out[CLIPPED] = True
    if n_pos > 0:
        # Same clamp as remove_defensive's write.
        out["mean_action_x"] = round_half_up(
            clip_unit((total_x + n * (x_dest - x_from)) / n_pos, out),
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

#: Identity fields every mechanism's view carries.
COMMON_MECHANISM_INPUTS = ("player_id", "match_id")

#: What each mechanism CONSUMES. compose() restricts the row to these plus the
#: common set, so an undeclared read raises; raw_fingerprint() hashes them.
MECHANISM_INPUTS = {
    "defensive_success": (
        "defensive_actions_successful",
        "defensive_actions_with_outcome",
    ),
    "pass_completion": (
        "passes_completed",
        "passes_with_outcome",
    ),
    "remove_defensive": (
        "defensive_actions",
        "defensive_actions_with_outcome",
        "defensive_actions_successful",
        "defensive_actions_in_defensive_third",
        "actions",
        "touches_in_defensive_third",
        "mean_action_x",
        "attempts_with_position",
        "sum_start_x_in_defensive_third",
        "minutes_played",
        "regulation_minutes",
    ),
    "relocate_upfield": (
        "touches_in_defensive_third",
        "defensive_actions_in_defensive_third",
        "mean_action_x",
        "attempts_with_position",
        "sum_start_x_in_defensive_third",
        "minutes_played",
        "regulation_minutes",
    ),
    "throttle_defensive": (
        "defensive_actions_successful",
        "defensive_actions_with_outcome",
    ),
}


def mechanism_view(name: str, row: pd.Series) -> pd.Series:
    """``row`` restricted to what ``name`` declares, plus identity fields.

    Identity is optional; a missing DECLARED input raises.
    """
    common = [c for c in COMMON_MECHANISM_INPUTS if c in row.index]
    return row[common + list(MECHANISM_INPUTS[name])]


#: Severity ladder per mechanism. throttle_defensive is a fraction of successes
#: lost, not a sigma count; achieved is reported in count sd either way.
LADDERS = {"throttle_defensive": (0.0, 0.20, 0.50)}

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


def batch_size(players: int, jobs: int) -> int:
    """Players per dispatch, scaled to the machine rather than pinned to it.

    One at a time left the workers idle waiting on the parent. Too coarse and
    the last worker runs alone while the rest sit finished, so aim at a few
    batches each. A resource knob must never move a number -- joblib returns
    batches in order, so this changes only how the work is handed out.
    """
    workers = os.cpu_count() or 1 if jobs in (-1, None) else abs(jobs)
    return max(1, min(64, players // max(1, workers * 4)))


#: Rows a player needs before his OWN spread sizes his injection rather than
#: his position pool's; an sd from two points is too noisy to define "k sigma"
#: against. Decides only how hard a player is hit, never whether he is scored.
MIN_SPREAD_ROWS = 4


#: The single count each mechanism moves directly and calibrates its severity
#: against -- one degree of freedom each, so "k sigma" stays well defined; the
#: other columns follow from that one draw.
def _count_capacity(row: pd.Series, sd: float, column: str) -> float:
    """Largest k a count-removal mechanism can deliver: it cannot remove more
    events than exist, so the ceiling is the count itself in sigma units."""
    if not np.isfinite(sd) or sd <= 0:
        return 0.0
    return max(float(row[column]), 0.0) / sd


def _relabel_capacity(row: pd.Series, sd: float, success_col: str, denom_col: str) -> float:
    """Largest k a relabelling can deliver: it floors at zero successes, and
    moves ``k * sd * denominator`` of them, so the ceiling is the successes
    divided by that product."""
    denom = float(row[denom_col])
    if denom <= 0 or not np.isfinite(sd) or sd <= 0:
        return 0.0
    return max(float(row[success_col]), 0.0) / (sd * denom)


#: Per-mechanism ceiling in sigma, mirroring the clamp inside each mechanism.
#: Lets a composed budget be allocated across channels of unequal headroom.
CAPACITIES = {
    "remove_defensive": lambda row, sds: _count_capacity(
        row, sds["defensive_actions"], "defensive_actions"
    ),
    "relocate_upfield": lambda row, sds: _count_capacity(
        row, sds["touches_in_defensive_third"], "touches_in_defensive_third"
    ),
    "defensive_success": lambda row, sds: _relabel_capacity(
        row,
        sds["defensive_success"],
        "defensive_actions_successful",
        "defensive_actions_with_outcome",
    ),
    "pass_completion": lambda row, sds: _relabel_capacity(
        row,
        sds["pass_completion"],
        "passes_completed",
        "passes_with_outcome",
    ),
}


def allocate(budget: float, caps: list[float]) -> list[float]:
    """Split ``budget`` sigma across channels in QUADRATURE, respecting caps.

    Water-filling: share equally, pin any channel that cannot take its share at
    its ceiling, re-split what is left across the rest. Preserves the total --
    sum(k_i**2) == budget**2 -- unless every channel is capped, which is a row
    that cannot reach the requested sigma at any allocation.
    """
    out = [0.0] * len(caps)
    free = [i for i, c in enumerate(caps) if c > 0]
    left = budget**2
    while free:
        share = math.sqrt(left / len(free))
        over = [i for i in free if caps[i] < share]
        if not over:
            for i in free:
                out[i] = share
            return out
        for i in over:
            out[i] = caps[i]
            left -= caps[i] ** 2
            free.remove(i)
    return out


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
    """Apply ``names`` jointly, splitting ``k`` across them IN QUADRATURE.

    The claim on a composed row is a k-sigma deviation, so the budget is
    allocated to honour it: channels that cannot take an equal share are pinned
    at their ceiling and the remainder is re-split across those with headroom,
    preserving sum(k_i**2) == k**2. An equal k/sqrt(n) split would silently
    under-deliver whenever any channel is short of substrate.

    That makes the composed manipulation more CONCENTRATED when a channel is
    thin -- the same total displacement through fewer directions -- which is a
    property of the mechanism rather than of the result.

    Mechanisms run in :data:`COMPOSITION_ORDER`, each seeing the row as the
    previous ones left it, so a relabelling is sized by its THINNED
    denominator, and capacities are recomputed at each step for the same
    reason. ``rng_for(name, scaled_k)`` supplies each mechanism's stream.
    Returns the merged updates against the ORIGINAL row and one record per
    mechanism for per-DOF achieved reporting.
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
    working = row.copy()
    merged: dict[str, float] = {}
    steps: dict[str, dict] = {}
    budget = k**2
    for position, name in enumerate(ordered):
        if len(ordered) == 1:
            # k / sqrt(1) is k bit-exactly, and a single channel has nowhere to
            # redistribute to -- its clamp is the whole story.
            scaled = k
        else:
            # Re-plan each step against the row as the earlier channels left
            # it: removal succeeding is precisely what collapses a later
            # relabelling's capacity, so the horizon cannot be costed up front.
            horizon = ordered[position:]
            caps = [CAPACITIES[n](mechanism_view(n, working), sds) for n in horizon]
            scaled = allocate(math.sqrt(max(budget, 0.0)), caps)[0]
            budget -= scaled**2
        control = CONTROLS[name]
        before = float(working[control])
        denominator = float(working[RATE_CONTROLS[name][1]]) if name in RATE_CONTROLS else np.nan
        # The view is the enforcement: an undeclared read raises here.
        updates = MECHANISMS[name](
            mechanism_view(name, working), sds, scaled, rng_for(name, scaled)
        )
        # Strip the clamp marker before it can be written as a column.
        was_clipped = bool(updates.pop(CLIPPED, False))
        for column, value in updates.items():
            working[column] = value
        merged.update(updates)
        steps[name] = {
            "clipped": was_clipped,
            "allocated": scaled,
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
            usable = g[g[denom] > 0].assign(_r=lambda d, s=success, n=denom: d[s] / d[n])
            spreads[name] = float(np.sqrt(usable.groupby("player_id")["_r"].var(ddof=1).mean()))
        out[position] = spreads
    return out


#: Scorers needing a per-row forest fit. Kept out of SCORERS so the
#: default run costs no fits; run(forest=True) opts them in.
FOREST_SCORERS = ("forest", "forest_norm", "forest_res", "forest_res_norm")

#: Scorers compared, each picking its own target row -- raw and residual
#: space disagree about which match is a player's most typical.
SCORERS = ("max", "mahalanobis", "mahalanobis_res")


def select_targets(
    scored: pd.DataFrame, census: pd.DataFrame, scorers: tuple[str, ...] = SCORERS
) -> set[tuple]:
    """One (player, match) per scorer: the match closest to his median CLEAN
    score under that scorer, chosen before anything is perturbed.

    The player universe is max|z|'s by convention; mahalanobis and forest score
    every row too. Selection is per scorer AND per feature set -- the census carries scores
    computed under whatever metric set the caller ran. One shared target would
    hand the selecting scorer its hardest case and every other scorer an
    easier-than-typical row. A scorer that cannot score a player is still
    tested on him -- max|z|'s target, NaN score, counted as a miss -- so
    narrow coverage is paid for rather than flattered.
    """
    default, choices = target_choices(scored, census, scorers)
    targets = set()
    for scorer in scorers:
        chosen = choices[scorer]
        blind = [p for p in default if p not in chosen]
        if blind:
            # Never silent: the scorer is tested on a row it cannot score, so it
            # takes a miss it did not earn on the merits.
            warnings.warn(
                f"{scorer} cannot score {len(blind)} of {len(default)} players; "
                "they are tested on max|z|'s row and count as misses, so its "
                "detection rate is understated",
                stacklevel=2,
            )
        for player, match in default.items():
            targets.add((player, chosen.get(player, match), scorer))
    return targets


def target_choices(
    scored: pd.DataFrame, census: pd.DataFrame, scorers: tuple[str, ...] = SCORERS
) -> tuple[dict, dict[str, dict]]:
    """max|z|'s pick per player, and each scorer's OWN pick.

    Kept separate from :func:`select_targets` because the agreement matrix must
    be able to tell a scorer's own choice from the fallback it inherits when it
    cannot score a player. Counting a fallback as agreement would make a thin
    scorer look most aligned with max|z| exactly where it is blind.
    """
    keys = ["player_id", "match_id"]
    clean_scores = census.merge(scored[keys + ["max_abs_z"]], on=keys, how="left").rename(
        columns={"max_abs_z": "max"}
    )

    def median_row(frame: pd.DataFrame, column: str) -> dict:
        usable = frame.dropna(subset=[column])
        typical = usable.groupby("player_id")[column].transform("median")
        # match_id breaks equal-distance ties, which frame order otherwise decides.
        pick = usable.assign(_d=(usable[column] - typical).abs()).sort_values(["_d", "match_id"])
        pick = pick.groupby("player_id").head(1)
        return dict(zip(pick["player_id"], pick["match_id"]))

    default = median_row(clean_scores, "max")
    return default, {s: median_row(clean_scores, s) for s in scorers}


def draw_rng(seed: int, player_id, match_id, mechanism_name: str, scaled_k: float):
    """The stream for one (row, mechanism, dose).

    ``match_id`` keeps a changed target off another row's stream; no scorer, so
    two scorers on one target draw identically.
    """
    return np.random.default_rng(
        [seed, zlib.crc32(f"{player_id}|{match_id}|{mechanism_name}|{scaled_k}".encode())]
    )


def canonical_recipe(
    *,
    forest: bool = False,
    design: str = "persistent",
    seed: int = SEED,
    metrics: list[str] | None = None,
    scorers: tuple[str, ...] | None = None,
    severities: tuple[float, ...] | None = None,
    mechanisms: dict | None = None,
    compositions: dict[str, tuple[str, ...]] | None = None,
) -> dict:
    """Every default resolved ONCE, order preserved.

    :func:`run` and :func:`campaign_config` both read this, so the runner and
    the stamp cannot resolve a default differently.
    """
    return {
        "forest": bool(forest),
        "design": design,
        "seed": seed,
        "metrics": list(metrics) if metrics is not None else list(baseline.METRICS),
        "scorers": tuple(scorers)
        if scorers is not None
        else SCORERS + (FOREST_SCORERS if forest else ()),
        "severities": tuple(severities) if severities is not None else SEVERITIES,
        # {} means "no single-mechanism conditions", so it is not a default.
        "mechanisms": dict(mechanisms) if mechanisms is not None else dict(MECHANISMS),
        "compositions": {k: tuple(v) for k, v in (compositions or {}).items()},
    }


def consumed_columns() -> list[str]:
    """Every raw column the experiment reads. Order-stable, deduplicated."""
    seen = dict.fromkeys(baseline.CONSUMED)
    for inputs in MECHANISM_INPUTS.values():
        seen.update(dict.fromkeys(inputs))
    return list(seen)


def raw_fingerprint(raw: pd.DataFrame) -> str:
    """Content hash of the FULL raw dependency, in canonical row order.

    Non-target rows reach the position-level fits, so a raw edit outside the
    scored subset can move target scores with the scored hash unmoved. Covers
    the consumed columns only: an unconsumed edit must not invalidate a run.
    """
    import hashlib

    columns = consumed_columns()
    keyed = raw.loc[:, columns].sort_values(["player_id", "match_id"], kind="mergesort")
    doubled = keyed.duplicated(["player_id", "match_id"])
    if doubled.any():
        pairs = keyed.loc[doubled, ["player_id", "match_id"]].head(3).to_records(index=False)
        raise ValueError(f"raw frame has duplicate (player_id, match_id) keys, e.g. {list(pairs)}")
    rows = pd.util.hash_pandas_object(keyed, index=False)
    digest = hashlib.sha256()
    digest.update("|".join(["raw-v1", str(len(keyed)), *columns]).encode())
    digest.update(rows.to_numpy().tobytes())
    return digest.hexdigest()[:16]


def campaign_config(scoring: str, recipe: dict, raw: pd.DataFrame) -> str:
    """The one stamp string for an injection campaign.

    Adds what :func:`heldout.results_config` cannot see: the resolved recipe,
    order preserved, and the full-raw fingerprint. Mechanisms stamp by
    REGISTERED NAME -- a callable repr can carry a process address, so an
    unregistered one is refused rather than given an unstable identity.
    """
    strangers = [n for n, fn in recipe["mechanisms"].items() if MECHANISMS.get(n) is not fn]
    if strangers:
        raise ValueError(
            f"cannot stamp unregistered mechanisms {strangers}; register them in "
            "MECHANISMS (and MECHANISM_INPUTS) or run unstamped"
        )
    core = heldout.results_config(scoring, recipe["seed"], recipe["design"])
    composed = ";".join(f"{n}={'+'.join(p)}" for n, p in recipe["compositions"].items())
    return (
        f"{core}|scorers={','.join(recipe['scorers'])}"
        f"|severities={','.join(f'{s:g}' for s in recipe['severities'])}"
        f"|mechanisms={','.join(recipe['mechanisms'])}"
        f"|compositions={composed}"
        f"|raw={raw_fingerprint(raw)}"
    )


def run(
    scored: pd.DataFrame,
    raw: pd.DataFrame,
    census: pd.DataFrame,
    severities: tuple[float, ...] = SEVERITIES,
    mechanisms: dict | None = None,
    compositions: dict[str, tuple[str, ...]] | None = None,
    metrics: list[str] | None = None,
    seed: int = SEED,
    jobs: int = 1,
    forest: bool = False,
    design: str = "persistent",
    progress: bool = False,
    scorers: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """One match per player perturbed by every mechanism at every severity.

        A manipulator fixes a match, not a career, so exactly one row per player is
        injected. Each scorer picks its own target -- the match nearest that
        player's median score under that scorer. The perturbed row is always the
        held-out one; ``census`` supplies the clean scores targets are chosen from.

        ``compositions`` maps a name to mechanism names injected JOINTLY, with
        ``k`` allocated across them in quadrature against each channel's capacity;
        those rows carry per-DOF achieved columns. ``metrics``
        narrows the multivariate scorers' feature set (the census must have been
        scored under the same set); injection sizing always uses the full set,
        so the perturbation is identical across feature-set arms.

    ``design`` selects the experiment, and the two answer different questions:

        ``persistent``
            The fixed match stays in the player's history, so every OTHER row of
            his is rescored against a baseline that now contains it. That is what
            makes collateral measurable, and it costs a fit per row per frame.
        ``heldout``
            Only each scorer's own targets are scored, against criteria fixed on
            the clean census -- as if the fixed match were a new event arriving
            after the detector was built. No collateral by construction, and cheap
            enough to afford forests.

        A target's own raw-metric fit is identical under both: leave-one-out
        excludes the target, and the position pools are pinned to the clean
        frame. The RESIDUAL fits differ by design: heldout trains them on the
        clean frame's residuals -- the same cohort the census fitted, as if the
        target arrived after the detector was built -- while persistent trains
        on residuals whose baselines contain the perturbed target, because a
        manipulation sitting in the history is the thing it measures.
    """
    if design not in ("persistent", "heldout"):
        raise ValueError(f"design must be persistent or heldout; got {design!r}")
    absent = [
        s for s in SCORERS + (FOREST_SCORERS if forest else ()) if s != "max" and s not in census
    ]
    if absent:
        # Checked before any fitting, so a stale cache costs nothing to find.
        # A bare KeyError from select_targets' dropna would name the column
        # but not the remedy.
        raise KeyError(
            f"census lacks {absent}; rebuild it with score_all(..., forest=True) "
            "-- a census cached before a rename or without forests is stale"
        )
    warnings.filterwarnings("ignore")
    # One resolution path for runner and stamp, so defaults cannot diverge.
    recipe = canonical_recipe(
        forest=forest,
        design=design,
        seed=seed,
        metrics=metrics,
        scorers=scorers,
        severities=severities,
        mechanisms=mechanisms,
        compositions=compositions,
    )
    mechanisms = recipe["mechanisms"]
    compositions = recipe["compositions"]
    metrics = recipe["metrics"]
    severities = recipe["severities"]
    pos_sds = position_spreads(scored)
    # Hyperparameters from the clean frame, computed once.
    fitted = baseline.hyperparameters(baseline.prepare(raw), jobs=jobs)

    zcols = heldout.residual_columns(metrics)
    floor = len(metrics) + 2
    position_fits, position_z, position_rows = {}, {}, {}
    position_nu, position_nu_z, position_z_rows = {}, {}, {}
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
        position_z_rows[position] = pz
        position_z[position] = heldout._Fit(pz) if len(pz) >= floor else None
        position_nu_z[position] = heldout.covariance_nu(pz, frame_z["player_id"].to_numpy())

    keys = ["player_id", "match_id"]
    # A targeted run asks for a subset -- the collateral question needs the two
    # forests on the coordinated condition, not all seven on all six recipes.
    scorers = recipe["scorers"]
    targets = select_targets(scored, census, scorers=scorers)
    target_rows = {(p, m) for p, m, _ in targets}

    #: The clean pass's residual frame, kept so a condition can carry the
    #: metrics its injection did not move instead of recomputing them.
    unmoved: dict = {}
    #: (raw fit, residual fit) by (player, match), built ONCE by the clean pass.
    #: Heldout must train on CLEAN rows or the injection leaks into its own bar.
    held_fits: dict | None = {} if design == "heldout" else None

    def score_frame(
        frame: pd.DataFrame, wanted: set | None = None, remember: bool = False
    ) -> pd.DataFrame:
        """Every row scored through the residual path, position
        reference pinned to the clean frame. The player's own history is left
        contaminated on purpose -- that is what the collateral columns measure.

        ``wanted`` restricts scoring to those (player, match) rows. Under the
        heldout design it is the scorer's OWN targets, so no fit is built for
        a row nobody reads -- and, more importantly, a row belonging to some
        other scorer's target set cannot leak into this scorer's collateral,
        where it would be a near-median subset masquerading as the population.
        """
        prepared = baseline.prepare(frame)
        only = None
        was = unmoved.get("frame")
        if was is not None:
            # Which metrics moved, read off the data. Each z depends on its
            # own metric, so the rest are carried rather than recomputed.
            pair = ["player_id", "match_id"]
            lined = prepared[pair + list(baseline.METRICS)].merge(
                was[pair + list(baseline.METRICS)], on=pair, suffixes=("", "_was")
            )
            only = [
                m
                for m in baseline.METRICS
                if not np.allclose(lined[m], lined[f"{m}_was"], equal_nan=True)
            ]
            carried = [
                c
                for m in baseline.METRICS
                if m not in only
                for c in (f"z_{m}", f"sigma_{m}", f"weight_{m}")
            ]
            prepared = prepared.merge(was[pair + carried], on=pair, how="left")
        rescored, _ = baseline.residuals(prepared, fitted=fitted, only=only)
        if remember:
            unmoved["frame"] = rescored.copy()
        rescored = rescored[rescored["is_scoreable"]]
        flagged = baseline.flag(rescored, baseline.DEFAULT_FLAG_RATE)

        # The clean pass builds the fits; later passes look them up.
        collect = held_fits is not None and not held_fits

        def one_player(lo: int, hi: int) -> tuple[list[dict], list[tuple]]:
            out: list[dict] = []
            built: list[tuple] = []
            position = every_pos[lo]
            if position not in position_fits:
                return out, built
            pool_fit, pool_z = position_fits[position], position_z.get(position)
            player_id = every_pid[lo]
            mine_x, mine_z = every_x[lo:hi], every_z[lo:hi]
            mine_mid, mine_top = every_mid[lo:hi], every_top[lo:hi]
            whole = ~np.isnan(mine_x).any(axis=1)  # == dropna(subset=metrics)
            cx, cz, cids = mine_x[whole], mine_z[whole], mine_mid[whole]
            for x, zrow, mid, top in zip(mine_x, mine_z, mine_mid, mine_top, strict=True):
                if wanted is not None and (player_id, mid) not in wanted:
                    continue
                if held_fits:
                    # Raises on a missing key: no fit is a design violation.
                    fit, zfit = held_fits[(player_id, mid)]
                else:
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
                            seed=heldout.borrow_seed(player_id),
                        )
                    ztrain = cz[keep]
                    ztrain = ztrain[~np.isnan(ztrain).any(axis=1)]
                    # The SAME fallback the census uses, or the score and the
                    # bar come from differently fitted populations.
                    zfit = pool_z
                    if len(ztrain) >= 2:
                        zfit = heldout._Fit(
                            ztrain,
                            target=pool_z.cov if pool_z is not None else None,
                            weight=heldout.shrinkage_weight(
                                len(ztrain), position_nu_z.get(position, np.inf)
                            ),
                            pool=position_z_rows.get(position) if forest else None,
                            seed=heldout.borrow_seed(player_id),
                        )
                zdist = zfit.distance(zrow) if zfit is not None else np.nan
                fres = fres_norm = np.nan
                if forest and zfit is not None:
                    _, fres, fres_norm = zfit.score(zrow)
                record = {
                    "player_id": player_id,
                    "match_id": mid,
                    "position_code": position,
                    "max": top,
                    "mahalanobis": fit.distance(x),
                    "mahalanobis_res": zdist,
                }
                if forest:
                    _, fraw, fnorm = fit.score(x)
                    record["forest"] = fraw
                    record["forest_norm"] = fnorm
                    record["forest_res"] = fres
                    record["forest_res_norm"] = fres_norm
                record.update(dict(zip(zcols, zrow)))
                out.append(record)
                if collect:
                    # Scoring warmed the lazy forests, so these return fitted.
                    built.append(((player_id, mid), (fit, zfit)))
            return out, built

        # Same shape as heldout.score_all's loop, and parallelised the same
        # way: each player is independent, the closed-over fits are read-only,
        # and joblib returns batches in order so the frame is draw-for-draw
        # identical to the serial path.
        # Hoisted ONCE and closed over, not sliced per task: joblib memmaps
        # arrays this size, so ten workers share one copy instead of unpickling
        # a frame slice each. Tasks carry two integers.
        ordered = flagged.sort_values("player_id", kind="stable")
        every_x = ordered[metrics].to_numpy(dtype=float)
        every_z = ordered[zcols].to_numpy(dtype=float)
        every_mid = ordered["match_id"].to_numpy()
        every_top = ordered["max_abs_z"].to_numpy()
        every_pid = ordered["player_id"].to_numpy()
        every_pos = ordered["position_code"].to_numpy()
        edges = np.flatnonzero(np.r_[True, every_pid[1:] != every_pid[:-1], True])
        histories = list(itertools.pairwise(edges))
        # Lookup passes stay serial: dispatching would pickle the fit map to
        # every worker for scoring that is already cheap.
        if jobs and jobs != 1 and not (held_fits is not None and held_fits):
            from joblib import Parallel, delayed

            # A player is a small task and the frame slice is pickled per
            # call, so one-per-dispatch left the workers waiting on the parent.
            batches = Parallel(n_jobs=jobs, batch_size=batch_size(len(histories), jobs))(
                delayed(one_player)(lo, hi) for lo, hi in histories
            )
        else:
            batches = [one_player(lo, hi) for lo, hi in histories]
        if collect:
            for _, built in batches:
                held_fits.update(built)
        return pd.DataFrame([r for records, _ in batches for r in records])

    # Every player's spread, computed once from clean data -- always over the
    # FULL metric set, so the injection does not change with ``metrics``.
    spreads = {
        pid: calibration_sds(g.dropna(subset=baseline.METRICS), pos_sds, g["position_code"].iloc[0])
        for pid, g in scored.groupby("player_id")
    }
    by_key = raw.set_index(keys)
    # Heldout scores only targets, so the clean pass needs the union across
    # scorers (each scorer reads its own targets' clean values from it).
    clean = score_frame(raw, wanted=target_rows if design == "heldout" else None, remember=True)
    if held_fits is not None:
        # Empty here means the workers built nothing: KeyError on every row.
        assert held_fits, "heldout clean pass returned no fits to the parent"
    clean = clean.set_index(keys)

    # Singles are one-mechanism recipes through the same compose() path.
    recipes = [(name, (name,)) for name in mechanisms]
    recipes += [(name, tuple(parts)) for name, parts in compositions.items()]

    rows = []
    done, opened = 0, time.monotonic()
    for scorer in scorers:
        chosen = {p: m for p, m, sc in targets if sc == scorer}
        for name, parts in recipes:
            composed = len(parts) > 1
            zobs = f"z_{OBSERVABLES[name]}" if name in OBSERVABLES else None
            ladder = severities if composed else LADDERS.get(name, severities)
            for k in ladder:
                # Every target is fixed at once, then the WHOLE frame is
                # re-scored, so the position-level knock-on is included.
                patch, achieved, details, noop = {}, {}, {}, set()
                clamped: dict = {}
                allocated: dict = {}
                for player_id, match_id in chosen.items():
                    if (player_id, match_id) not in by_key.index:
                        continue
                    test = by_key.loc[(player_id, match_id)]

                    def rng_for(mechanism_name, scaled_k, player_id=player_id, match_id=match_id):
                        return draw_rng(seed, player_id, match_id, mechanism_name, scaled_k)

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
                    # Per DOF as well as per row: delivery is already reported
                    # per DOF, so collapsing truncation to one boolean leaves a
                    # reader unable to attribute the shortfall.
                    clamped[player_id] = {p: bool(steps[p].get("clipped")) for p in parts}
                    # Did the allocation reach the k this row is labelled with?
                    # It cannot when every channel is at its ceiling, which is a
                    # property of the player, not a failure to hide.
                    allocated[player_id] = math.sqrt(
                        sum(float(steps[p].get("allocated", 0.0)) ** 2 for p in parts)
                    )
                    # A composed row has no single sigma unit; its scalar is
                    # NaN and the per-DOF achieved_* columns carry the shift.
                    achieved[player_id] = per[name] if not composed else np.nan
                mine = {(p, m) for p, m in chosen.items()}
                if k == 0:
                    # The null row costs no scoring pass: nothing was injected,
                    # so `after` IS `clean`. Every rate and AUC needs it as a
                    # baseline, and the masked gate's no-skill floor is 0.483
                    # rather than 0.5, so it cannot be assumed.
                    # Restricted to the same rows a dosed block scores, or k=0
                    # would carry other scorers' targets and print a collateral
                    # figure the dosed rows never measure.
                    after = clean[clean.index.isin(mine)] if design == "heldout" else clean
                elif not patch:
                    continue
                else:
                    fixed = raw.copy()
                    for (player_id, match_id), updates in patch.items():
                        mask = (fixed["player_id"] == player_id) & (fixed["match_id"] == match_id)
                        for column, value in updates.items():
                            fixed.loc[mask, column] = value
                    began = time.monotonic()
                    after = score_frame(fixed, wanted=mine if design == "heldout" else None)
                    after = after.set_index(keys)
                    # A campaign is over an hour of silence otherwise, with no
                    # way to tell progress from a hang.
                    if progress:
                        done += 1
                        print(
                            f"  [{done:>3}] {scorer:<16}{name:<20}k={k:<5}"
                            f"{time.monotonic() - began:6.1f}s"
                            f"  ({time.monotonic() - opened:5.0f}s total)",
                            flush=True,
                        )

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
                        "clipped": any(clamped.get(player_id, {}).values()),
                        # Short of the label's k: no allocation could reach it.
                        "short": bool(
                            k > 0 and player_id in allocated and allocated[player_id] < k - 1e-9
                        ),
                        "allocated": allocated.get(player_id, np.nan),
                        "achieved": achieved[player_id],
                        "achieved_z": (
                            after.at[key, zobs] - clean.at[key, zobs]
                            if is_target and zobs is not None and zobs in after.columns
                            else np.nan
                        ),
                        "clean": clean.at[key, scorer],
                        "after": after.at[key, scorer],
                    }
                    if composed:
                        for p in parts:
                            p_obs = f"z_{OBSERVABLES[p]}"
                            record[f"achieved_{p}"] = details[player_id][p]
                            record[f"clipped_{p}"] = bool(clamped.get(player_id, {}).get(p, False))
                            record[f"achieved_z_{p}"] = (
                                after.at[key, p_obs] - clean.at[key, p_obs]
                                if is_target and p_obs in after.columns
                                else np.nan
                            )
                    rows.append(record)
    return pd.DataFrame(rows)


def _auc(reference: np.ndarray, hot: np.ndarray) -> float:
    """Cohort-referenced two-sample Mann-Whitney AUC, ties counted half.

    P(a row from ``hot`` outranks one from ``reference``): two distributions,
    NOT per-row pairs. Threshold-free at the specified dose, so it separates
    "cannot see the perturbation" from "sees it but the bar is too far out".

    NaN is dropped from the reference. A NaN score cannot be flagged, matching
    flag(), so in the perturbed set it sinks to -inf rather than being
    discarded, which would flatter the scorer by shrinking its denominator.
    """
    clean = np.sort(reference[~np.isnan(reference)])
    perturbed = np.where(np.isnan(hot), -np.inf, hot)
    if not len(clean) or not len(perturbed):
        return float("nan")
    lo = np.searchsorted(clean, perturbed, side="left")
    hi = np.searchsorted(clean, perturbed, side="right")
    return float(np.mean((lo + hi) / (2 * len(clean))))


def tallies_for(present: set, bars: dict[str, float]) -> list[str]:
    """The scorers to tally, in report order."""
    return [s for s in SCORERS + FOREST_SCORERS if s in present]


def cell_statistics(
    results: pd.DataFrame,
    bars: dict[str, float],
) -> pd.DataFrame:
    """One row per (mechanism, severity, tally) -- every number a table needs.

    Computed once so the text summary and the report tables cannot drift.
    Two faithful renderings of one wrong number agree with each other, which
    is exactly how the jackknife estimator survived as long as it did.
    """
    present = set(results["scorer"].unique())
    rows = []
    for name in results["mechanism"].unique():
        for k in sorted(results.loc[results.mechanism == name, "severity"].unique()):
            block = results[(results.mechanism == name) & (results.severity == k)]
            for tally in tallies_for(present, bars):
                r = block[block.scorer == tally]
                if r.empty:
                    continue
                cut = bars[tally]
                hit, was = r["after"] >= cut, r["clean"] >= cut
                t, o = r.is_target, ~r.is_target
                n = int(t.sum())
                # Recovery is crossing the bar BECAUSE OF the injection. A row
                # already above it when clean was recovered by nothing, and
                # counting it inflates every scorer equally.
                gained = float((~was & hit)[t].mean()) if n else np.nan
                # Second denominator: rows the injection actually CHANGED. The
                # numerator is identical -- a row where nothing moved has
                # after == clean, so it cannot cross the bar -- so the two rates
                # differ only by how many un-moved rows share the credit.
                # Row-level, so it means "any channel fired" -- true on nearly
                # every COMPOSED row even when a channel is dead on three
                # quarters of them. There the concept is per-channel, not
                # per-row, so the column says n/a and the per-DOF acted shares
                # carry it instead.
                composed_block = any(
                    c.startswith("achieved_")
                    and c != "achieved_z"
                    and not c.startswith("achieved_z_")
                    and r[c].notna().any()
                    for c in r.columns
                )
                dosed = (t & r["bit"]) if "bit" in r.columns else t
                n_dosed = 0 if composed_block else int(dosed.sum())
                gained_dosed = (
                    float((~was & hit)[dosed].mean()) if n_dosed and not composed_block else np.nan
                )
                # Cohort clean vs after: two samples, not per-row pairs, and
                # not the population, which floors each scorer differently.
                auc = np.nan
                paired = t & r["clean"].notna()
                if paired.any():
                    auc = _auc(
                        r.loc[paired, "clean"].to_numpy(dtype=float),
                        r.loc[paired, "after"].to_numpy(dtype=float),
                    )
                measurable = bool(o.any()) and r.loc[o, "after"].notna().sum() > 0
                middle = spread = np.nan
                stirred = 0
                if measurable:
                    # Bar crossings are too rare to measure collateral on, so
                    # report the signed score shift of the player's OTHER
                    # matches; rows whose fit never held the target cannot move.
                    shift = r.loc[o, "after"] - r.loc[o, "clean"]
                    moved = shift[shift.abs() > 1e-9]
                    stirred = len(moved)
                    spread = r.loc[o, "clean"].std()
                    middle = float(moved.median()) if stirred else np.nan
                rows.append(
                    {
                        "mechanism": name,
                        "severity": k,
                        "tally": tally,
                        "bar": cut,
                        "n": n,
                        "caught": float(hit[t].mean()) if n else np.nan,
                        "recovery": gained,
                        "recovered": int((~was & hit)[t].sum()) if n else 0,
                        "n_short": (
                            int(r.loc[t, "short"].sum()) if n and "short" in r.columns else 0
                        ),
                        "allocated": (
                            float(r.loc[t, "allocated"].mean())
                            if n and "allocated" in r.columns
                            else np.nan
                        ),
                        "n_dosed": n_dosed,
                        "recovery_dosed": gained_dosed,
                        "recovered_dosed": int((~was & hit)[dosed].sum()) if n_dosed else 0,
                        "auc": auc,
                        # Delivered dose belongs beside detection: mechanisms differ
                        # in how much of the requested sigma they can actually apply,
                        # so a row-to-row comparison reads delivery as detectability
                        # unless both are visible.
                        # Composed rows mix NaN (dosed) with 0.0 (no-op) in
                        # `achieved`, so a NaN-skipping mean prints "+0.00 sd" for a
                        # delivered dose. Per-DOF columns carry delivery there.
                        "achieved": (
                            float(r.loc[t, "achieved"].mean())
                            if n and "achieved" in r.columns and not composed_block
                            else np.nan
                        ),
                        # One currency across mechanisms, and the check that
                        # different scorers' targets took comparable doses.
                        "delivered_z": (
                            float(r.loc[t, "achieved_z"].mean())
                            if n
                            and "achieved_z" in r.columns
                            and r.loc[t, "achieved_z"].notna().any()
                            else np.nan
                        ),
                        "clipped": (
                            float(r.loc[t, "clipped"].mean())
                            if n and "clipped" in r.columns
                            else np.nan
                        ),
                        "collateral_measurable": measurable,
                        "others_before": float(was[o].mean()) if measurable else np.nan,
                        "others_after": float(hit[o].mean()) if measurable else np.nan,
                        "contaminated": stirred,
                        "n_other": int(o.sum()),
                        "shift": middle,
                        "shift_sd": (
                            middle / spread
                            if measurable and spread and np.isfinite(spread)
                            else np.nan
                        ),
                    }
                )
    return pd.DataFrame(rows)


def clipped_note(block: pd.DataFrame) -> str:
    """Share of injected targets whose dose was TRUNCATED by a mechanism
    running out of substrate -- successes to relabel, actions to remove or
    touches to relocate.

    Sits beside the achieved dose because it qualifies it: a truncated row got
    less than was asked for, so a miss there is delivery, not detection. On
    composed rows this should be near zero, because the allocator caps each
    channel at its capacity and so pre-empts the clamp.
    """
    on_target = block[block.is_target]
    if "clipped" not in block.columns or not len(on_target):
        return ""
    share = float(on_target["clipped"].mean())
    return f"  clipped {share:.1%}" if share else ""


def census_rates(
    scored: pd.DataFrame,
    census: pd.DataFrame,
    bars: dict[str, float],
    rate: float = baseline.DEFAULT_FLAG_RATE,
) -> str:
    """Share of the CENSUS each bar actually flags, which must equal ``rate``
    -- a bug check, and the anchor every other rate is read against."""
    flagged = baseline.flag(scored, rate)
    parts = [f"max {flagged['is_flagged'].mean():.4%}"]
    for name in SCORERS + FOREST_SCORERS:
        if name == "max" or name not in census:
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
    rate: float = baseline.DEFAULT_FLAG_RATE,
) -> str:
    """Detection on the fixed match, and what it did to the player's others."""
    lines = []
    stats = cell_statistics(results, bars)
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

                def dof(part: str, on_target=on_target) -> str:
                    # A dropped metric has no z column in this feature set, so
                    # its shift is unmeasurable here -- say so rather than
                    # printing "+nan", which reads as a defect.
                    shift = on_target[f"achieved_z_{part}"].mean()
                    scale = f"{on_target[f'achieved_{part}'].mean():+.2f}sd"
                    # Truncation per DOF, beside delivery per DOF: composing
                    # runs removal first, so a relabelling meets a denominator
                    # that removal has already eaten and its floor binds harder.
                    # A channel that never fired has exactly zero achieved, so
                    # its firing rate needs no extra plumbing -- and without it
                    # a dead channel reads as a weak one.
                    marks = []
                    acted = float((on_target[f"achieved_{part}"].abs() > 1e-9).mean())
                    if acted < 1.0:
                        marks.append(f"acted {acted:.0%}")
                    if f"clipped_{part}" in on_target.columns:
                        share = float(on_target[f"clipped_{part}"].mean())
                        if share:
                            marks.append(f"clip {share:.0%}")
                    tail = f"[{', '.join(marks)}]" if marks else ""
                    return (
                        f"{part} {scale}/" + ("n/a" if pd.isna(shift) else f"{shift:+.2f}z") + tail
                    )

                delivered = "  ".join(dof(p) for p in per_dof)
                # The k on the label is a claim. Say when it was not met, and
                # by how much, rather than leaving the label to stand alone.
                short = ""
                on = block[block.is_target]
                if "short" in block.columns and on["short"].any():
                    mean_k = on.loc[on["short"], "allocated"].mean()
                    short = (
                        f"\n   !! {int(on['short'].sum()):,}/{len(on):,} rows could not reach "
                        f"k={k:g}; those rows averaged {mean_k:.2f} sigma"
                    )
                lines.append(
                    f"\n-- {name}  k={k:g}  per-DOF {delivered}{clipped_note(block)}{short}"
                )
            else:
                lines.append(
                    f"\n-- {name}  k={k:g}  "
                    f"achieved {block.loc[block.is_target, 'achieved'].mean():+.2f} sd"
                    f"  ({block.loc[block.is_target, 'achieved_z'].mean():+.2f} z)"
                    f"{clipped_note(block)}"
                )
            cells = stats[(stats.mechanism == name) & (stats.severity == k)]
            for row in cells.itertuples():
                label = row.tally
                auc = f" | auc {row.auc:.3f}" if np.isfinite(row.auc) else ""
                dosed = (
                    f" -> {row.recovered_dosed:,}/{row.n_dosed:,} dosed ({row.recovery_dosed:.1%})"
                    if np.isfinite(row.recovery_dosed)
                    else ""
                )
                head = (
                    f"  {label:12} bar {row.bar:6.2f}"
                    f" | caught {row.caught:5.1%}"
                    f" | recovered {row.recovered:,}/{row.n:,}"
                    f" ({row.recovery:5.1%}){dosed}{auc}"
                )
                if not row.collateral_measurable:
                    lines.append(f"{head} | collateral not measured (heldout)")
                    continue
                lines.append(
                    f"{head}"
                    f" | others {row.others_before:5.1%} -> {row.others_after:5.1%}"
                    f" | of {row.contaminated:,}/{row.n_other:,} contaminated:"
                    f" shift {row.shift:+.4f} ({row.shift_sd:+.3f} sd)"
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
        help="mechanisms injected JOINTLY on the same match, k allocated across "
        "them in quadrature against each channel's capacity; "
        "repeatable. Given alone it replaces the singles; add --mechanism "
        "to run singles alongside.",
    )
    parser.add_argument(
        "--drop-metric",
        choices=list(baseline.METRICS),
        action="append",
        help="remove a metric from the multivariate feature set; repeatable. "
        "max|z| and the injection keep the full set; census, "
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
        help="score the isolation forests too. One fit per scored row, so pair "
        "it with --jobs and prefer --design heldout; a cached --census built "
        "without forests has no forest columns.",
    )
    parser.add_argument(
        "--design",
        choices=("persistent", "heldout"),
        default="persistent",
        help="persistent leaves the fixed match in the player's history and "
        "measures what it does to his other matches (collateral), at a fit "
        "per row per frame. heldout scores only each scorer's own targets "
        "against criteria fixed on the clean census -- no collateral, cheap "
        "enough for forests. Target scores are identical either way.",
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
    if cache:
        total = scored["player_id"].nunique()
        players = min(args.n, total) if args.n else total
        suffix = f".drop-{'-'.join(dropped)}" if dropped else ""
        # Population in the key: otherwise a --n pilot and the full run share
        # a filename, and the pilot is reloaded and reported as the full set.
        cache = cache.with_name(f"{cache.stem}{suffix}.n{players}{cache.suffix}")
    settings = heldout.scoring_config(metrics=metrics, forest=args.forest, limit_players=args.n)
    if cache and cache.exists():
        census = heldout.read_census(cache, scored, config=settings)
    else:
        census = heldout.score_all(
            scored,
            metrics=metrics,
            limit_players=args.n,
            jobs=args.jobs,
            forest=args.forest,
        )
        if cache:
            heldout.write_census(cache, census, scored, config=settings)
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
        seed=args.seed,
        jobs=args.jobs,
        forest=args.forest,
        design=args.design,
    )
    if args.out:
        results.to_parquet(args.out, index=False)
    print(census_rates(scored, census, bars, args.rate))
    print(summary_persistent(results, bars))
    return 0


if __name__ == "__main__":
    sys.exit(main())
