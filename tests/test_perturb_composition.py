"""Composition of perturbation mechanisms, against rows whose answer is built in.

Two invariants make composed severities readable. A single mechanism through
compose() must be BIT-identical to calling it directly, or every historical
single-mechanism number silently changes meaning; and each composed mechanism
must see the row as the previous ones left it, or a relabelling is sized
against a denominator that no longer exists. Both are checkable on planted
rows: all-in-third compositions make the hypergeometric draws deterministic,
so a stale-state implementation produces a provably different row.
"""

from __future__ import annotations

import math
import zlib

import numpy as np
import pandas as pd
import pytest

from fis.analysis import injection_test

SDS = {
    "defensive_actions": 3.0,
    "touches_in_defensive_third": 5.0,
    "defensive_actions_successful": 2.0,
    "passes_completed": 6.0,
    "defensive_success": 0.10,
    "pass_completion": 0.05,
}

ALL_FOUR = injection_test.COMPOSITION_ORDER


def _rng_for(name: str, scaled: float, tag: str = "p|s") -> np.random.Generator:
    """The production stream: seeded exactly as run() seeds it."""
    return np.random.default_rng(
        [injection_test.SEED, zlib.crc32(f"{tag}|{name}|{scaled}".encode())]
    )


def _row(**overrides) -> pd.Series:
    base = dict(
        player_id=1,
        match_id=1,
        minutes_played=90.0,
        regulation_minutes=90.0,
        actions=60.0,
        defensive_actions=12,
        defensive_actions_with_outcome=10,
        defensive_actions_successful=7,
        defensive_actions_in_defensive_third=8,
        touches_in_defensive_third=20.0,
        sum_start_x_in_defensive_third=4.0,
        attempts_with_position=50.0,
        mean_action_x=0.35,
        passes_completed=30,
        passes_with_outcome=40,
        pass_completion_pct=75.0,
        defensive_action_success_pct=70.0,
        defensive_actions_per_90=12.0,
        touches_in_defensive_third_per_90=20.0,
    )
    base.update(overrides)
    return pd.Series(base)


def _random_row(rng: np.random.Generator) -> pd.Series:
    """A consistent random row: children never exceed parents, means in range."""
    defensive = int(rng.integers(1, 25))
    with_outcome = int(rng.integers(0, defensive + 1))
    successful = int(rng.integers(0, with_outcome + 1))
    in_third_def = int(rng.integers(0, defensive + 1))
    touches = int(rng.integers(in_third_def, in_third_def + 30))
    n_pos = touches + int(rng.integers(0, 40))
    mean_third = rng.uniform(0.0, injection_test.DEFENSIVE_THIRD_MAX_X)
    mean_out = rng.uniform(injection_test.DEFENSIVE_THIRD_MAX_X, 1.0)
    total_x = touches * mean_third + (n_pos - touches) * mean_out
    passes_with = int(rng.integers(0, 60))
    passes_done = int(rng.integers(0, passes_with + 1))
    return _row(
        defensive_actions=defensive,
        defensive_actions_with_outcome=with_outcome,
        defensive_actions_successful=successful,
        defensive_actions_in_defensive_third=in_third_def,
        touches_in_defensive_third=float(touches),
        sum_start_x_in_defensive_third=touches * mean_third,
        attempts_with_position=float(n_pos),
        mean_action_x=injection_test.round_half_up(total_x / n_pos, 4) if n_pos else 0.0,
        passes_with_outcome=passes_with,
        passes_completed=passes_done,
        pass_completion_pct=(
            injection_test.round_half_up(100.0 * passes_done / passes_with, 2)
            if passes_with
            else np.nan
        ),
        defensive_action_success_pct=(
            injection_test.round_half_up(100.0 * successful / with_outcome, 2)
            if with_outcome
            else np.nan
        ),
        defensive_actions_per_90=float(defensive),
        touches_in_defensive_third_per_90=float(touches),
        actions=float(defensive + passes_with + int(rng.integers(0, 40))),
    )


def _same(a, b) -> bool:
    return (a != a and b != b) or a == b


def test_single_mechanism_through_compose_is_bit_identical():
    """compose([m]) at any k draws, computes and returns exactly what m does.

    The stream key uses the SCALED severity, which for n=1 is k/sqrt(1) -- the
    same float bit for bit -- so the draws are the same draws, not statistical
    twins. Checked value-for-value over random rows, every mechanism, the
    whole severity ladder, including the fraction-laddered throttle.
    """
    rng = np.random.default_rng(11)
    ladders = {"throttle_defensive": (0.0, 0.10, 0.25, 0.50)}
    for name in list(ALL_FOUR) + ["throttle_defensive"]:
        for k in ladders.get(name, injection_test.SEVERITIES):
            for trial in range(10):
                row = _random_row(rng)
                tag = f"{trial}|s"
                direct = injection_test.MECHANISMS[name](row, SDS, k, _rng_for(name, k, tag))
                merged, steps = injection_test.compose(
                    row,
                    SDS,
                    k,
                    (name,),
                    lambda m, s, tag=tag: _rng_for(m, s, tag),
                )
                # compose() strips the truncation marker before it can reach the
                # frame as a column, so it is never in `merged`.
                direct = {c: v for c, v in direct.items() if c != injection_test.CLIPPED}
                assert set(merged) == set(direct)
                for column, value in direct.items():
                    assert _same(merged[column], value), (name, k, column)
                # Achieved through the step record equals the inline formula
                # run() used before composition existed.
                spread = SDS.get(injection_test.CONTROLS[name])
                if name in injection_test.RATE_CONTROLS:
                    denom = float(row[injection_test.RATE_CONTROLS[name][1]])
                    spread = SDS[name] * denom if denom > 0 else None
                control = injection_test.CONTROLS[name]
                expected = (
                    (float(direct[control]) - float(row[control])) / spread
                    if control in direct and spread and np.isfinite(spread)
                    else 0.0
                )
                assert injection_test.step_achieved(name, steps[name], SDS) == expected


def test_composing_the_fraction_mechanism_raises():
    """k/sqrt(n) has no meaning on a fraction axis, so pairing it is an error."""
    with pytest.raises(ValueError):
        injection_test.compose(
            _row(), SDS, 1.0, ("throttle_defensive", "remove_defensive"), _rng_for
        )


def test_null_composition_changes_nothing():
    """k=0 through all four mechanisms leaves every written value unmoved."""
    rng = np.random.default_rng(23)
    for _ in range(20):
        row = _random_row(rng)
        merged, _ = injection_test.compose(row, SDS, 0.0, ALL_FOUR, _rng_for)
        for column, value in merged.items():
            assert np.isclose(float(row[column]), value, equal_nan=True), column


def test_components_are_scaled_to_k_over_sqrt_n():
    """Each DOF delivers k/sqrt(4) of its own sigma in expectation.

    Large planted counts keep every draw far from its cap, so the only thing
    between requested and delivered is stochastic rounding -- which must
    average out, not bias. A harness that forgot the sqrt would deliver k and
    fail by a factor of two.
    """
    row = _row(
        defensive_actions=400,
        defensive_actions_with_outcome=380,
        defensive_actions_successful=300,
        defensive_actions_in_defensive_third=200,
        touches_in_defensive_third=500.0,
        sum_start_x_in_defensive_third=100.0,
        attempts_with_position=2000.0,
        mean_action_x=0.35,
        passes_completed=600,
        passes_with_outcome=800,
        pass_completion_pct=75.0,
        defensive_action_success_pct=78.95,
        actions=2000.0,
        defensive_actions_per_90=400.0,
        touches_in_defensive_third_per_90=500.0,
    )
    sds = dict(SDS, defensive_actions=20.5, touches_in_defensive_third=30.5)
    k = 2.0
    sums = {name: 0.0 for name in ALL_FOUR}
    draws = 300
    for trial in range(draws):
        _, steps = injection_test.compose(
            row, sds, k, ALL_FOUR, lambda m, s, trial=trial: _rng_for(m, s, f"{trial}|s")
        )
        for name in ALL_FOUR:
            sums[name] += injection_test.step_achieved(name, steps[name], sds)
    for name in ALL_FOUR:
        mean = sums[name] / draws
        assert mean == pytest.approx(-k / math.sqrt(len(ALL_FOUR)), abs=0.05), name


def test_later_mechanisms_see_the_thinned_row():
    """State threads between mechanisms; a stale-row implementation fails here.

    Planted so every draw is forced: all defensive actions sit in the third,
    all carry outcomes, all succeeded, and the third holds nothing else -- so
    removing all six of them (k*sd exactly 6) deterministically empties the
    third and the outcome denominator. Relocation must then find nothing to
    move, and the relabelling must find no denominator; against the ORIGINAL
    row both would act.
    """
    row = _row(
        defensive_actions=6,
        defensive_actions_with_outcome=6,
        defensive_actions_successful=6,
        defensive_actions_in_defensive_third=6,
        touches_in_defensive_third=6.0,
        sum_start_x_in_defensive_third=1.2,
        attempts_with_position=30.0,
        mean_action_x=injection_test.round_half_up((1.2 + 24 * 0.5) / 30.0, 4),
        defensive_action_success_pct=100.0,
        defensive_actions_per_90=6.0,
        touches_in_defensive_third_per_90=6.0,
    )
    sds = dict(SDS, defensive_actions=6.0)
    parts = ("remove_defensive", "relocate_upfield", "defensive_success")
    scaled = 3.0 / math.sqrt(len(parts))  # times sd 6.0: n = sqrt(3)*6 > 6, capped
    merged, steps = injection_test.compose(row, sds, 3.0, parts, _rng_for)

    assert merged["defensive_actions"] == 0
    assert merged["touches_in_defensive_third"] == 0.0
    # Relocation saw the emptied third and did not move.
    assert not steps["relocate_upfield"]["moved"]
    assert steps["relocate_upfield"]["before"] == 0.0
    # The relabelling was sized against the THINNED denominator (now zero),
    # not the original six.
    assert steps["defensive_success"]["denominator"] == 0.0
    assert not steps["defensive_success"]["moved"]
    # The stale row would have relocated and relabelled: that is the bug this
    # test plants for.
    stale_relocate = injection_test.relocate_upfield(row, sds, scaled, _rng_for("x", 1.0))
    stale_relabel = injection_test.defensive_success(row, sds, scaled, _rng_for("y", 1.0))
    assert stale_relocate and stale_relabel


def test_region_means_are_refreshed_between_mechanisms():
    """Partial removal updates the row before relocation reads it.

    All defensive actions in the third makes every hypergeometric draw
    deterministic (all three removals leave the third), and the sds are sized
    so k/sqrt(2) times each is exactly integral -- no stochastic rounding. The
    surviving state is then computable by hand: relocation must act on nine
    touches, not twelve, and must rebuild mean_action_x from the mean the
    removal wrote, not the original row's. The stale-row value is computed too
    and must differ, so a compose() that forgot to thread state fails loudly.
    """
    row = _row(
        defensive_actions=3,
        defensive_actions_with_outcome=3,
        defensive_actions_successful=3,
        defensive_actions_in_defensive_third=3,
        touches_in_defensive_third=12.0,
        sum_start_x_in_defensive_third=2.4,
        attempts_with_position=40.0,
        mean_action_x=injection_test.round_half_up((2.4 + 28 * 0.5) / 40.0, 4),
        defensive_action_success_pct=100.0,
        defensive_actions_per_90=3.0,
        touches_in_defensive_third_per_90=12.0,
    )
    scale = 2.0 / math.sqrt(2.0)
    sds = dict(SDS, defensive_actions=3.0 / scale, touches_in_defensive_third=4.0 / scale)
    parts = ("remove_defensive", "relocate_upfield")
    merged, steps = injection_test.compose(row, sds, 2.0, parts, _rng_for)

    # Removal takes all three defensive actions, all from the third.
    assert merged["defensive_actions"] == 0
    assert steps["relocate_upfield"]["before"] == 9.0
    # Relocation then moves four of the NINE survivors, not four of twelve.
    assert merged["touches_in_defensive_third"] == 5.0
    thinned_mean = (2.4 - 3 * 0.2) / 9.0
    assert merged["sum_start_x_in_defensive_third"] == pytest.approx(5.0 * thinned_mean)
    # mean_action_x is rebuilt from the state the removal wrote: 37 positioned
    # actions and the 4dp-rounded intermediate mean, whose reconstruction the
    # relocation re-reads. The same arithmetic against the ORIGINAL row gives
    # a different number, so state-threading is what this asserts.
    assert merged["attempts_with_position"] == 37.0
    total_x0 = float(row["mean_action_x"]) * 40.0
    mean1 = injection_test.round_half_up((total_x0 - 3 * 0.2) / 37.0, 4)
    total_x1 = mean1 * 37.0
    mean_out1 = (total_x1 - 1.8) / 28.0
    fresh = injection_test.round_half_up((total_x1 + 4 * (mean_out1 - 0.2)) / 37.0, 4)
    stale = injection_test.round_half_up((total_x0 + 4 * ((total_x0 - 2.4) / 28.0 - 0.2)) / 40.0, 4)
    assert fresh != stale
    assert merged["mean_action_x"] == fresh


def test_composition_keeps_means_inside_the_unit_interval():
    """4dp reconstruction error cannot push a written mean off the pitch.

    Planted so the stored (rounded) mean_action_x implies more x-mass outside
    the third than one action can carry: the reconstructed out-of-third mean
    exceeds 1 before clamping. Every composed output must still be a
    coordinate.
    """
    row = _row(
        touches_in_defensive_third=10.0,
        sum_start_x_in_defensive_third=3.0,
        attempts_with_position=11.0,
        mean_action_x=0.3637,
        defensive_actions=8,
        defensive_actions_with_outcome=8,
        defensive_actions_successful=6,
        defensive_actions_in_defensive_third=8,
        defensive_action_success_pct=75.0,
        defensive_actions_per_90=8.0,
        touches_in_defensive_third_per_90=10.0,
    )
    for trial in range(50):
        for k in (1.0, 2.0, 3.0):
            merged, _ = injection_test.compose(
                row, SDS, k, ALL_FOUR, lambda m, s, trial=trial: _rng_for(m, s, f"{trial}|u")
            )
            mean_x = merged.get("mean_action_x", float(row["mean_action_x"]))
            if np.isfinite(mean_x):
                assert 0.0 <= mean_x <= 1.0, (trial, k, mean_x)
            assert merged.get("sum_start_x_in_defensive_third", 0.0) >= 0.0
            touches = merged.get("touches_in_defensive_third", row["touches_in_defensive_third"])
            sum_x = merged.get(
                "sum_start_x_in_defensive_third", row["sum_start_x_in_defensive_third"]
            )
            if touches > 0:
                assert 0.0 <= sum_x / touches <= 1.0, (trial, k)


def test_target_selection_follows_the_feature_set():
    """A scorer's target moves with the census it scored, per feature set.

    The same player under two censuses -- as score_all would produce with and
    without a z-dominating metric -- must select different matches for the
    multivariate scorer while the shipped rule's target stays put. One shared
    target would hand the selecting scorer its hardest case and every other
    scorer an easier-than-typical row.
    """
    scored = pd.DataFrame(
        {
            "player_id": [1] * 5 + [2] * 3,
            "match_id": [1, 2, 3, 4, 5, 1, 2, 3],
            "max_abs_z": [1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0, 3.0],
        }
    )
    full = pd.DataFrame(
        {
            "player_id": [1] * 5 + [2] * 3,
            "match_id": [1, 2, 3, 4, 5, 1, 2, 3],
            "mahalanobis": [5.0, 4.0, 3.0, 2.0, 1.0, np.nan, np.nan, np.nan],
            "mahalanobis_z": [5.0, 4.0, 3.0, 2.0, 1.0, np.nan, np.nan, np.nan],
        }
    )
    reduced = full.assign(
        mahalanobis=[1.0, 5.0, 2.0, 4.0, 3.0, np.nan, np.nan, np.nan],
        mahalanobis_z=[1.0, 5.0, 2.0, 4.0, 3.0, np.nan, np.nan, np.nan],
    )
    with_metric = injection_test.select_targets(scored, full)
    without_metric = injection_test.select_targets(scored, reduced)
    # The shipped rule's median match is 3 either way.
    assert (1, 3, "max") in with_metric and (1, 3, "max") in without_metric
    # The multivariate scorer's median match moves with its scores.
    assert (1, 3, "mahalanobis") in with_metric
    assert (1, 5, "mahalanobis") in without_metric
    # A player the scorer cannot score is still tested, on the default target.
    assert (2, 2, "mahalanobis") in with_metric
