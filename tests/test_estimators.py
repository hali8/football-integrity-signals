"""Every hyperparameter estimator, against data whose answer is built in.

r (location), r_s (scale), nu (covariance) and rho (overdispersion) each
replace an asserted constant, so each must recover a planted truth and return
nothing on a planted null.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fis.analysis import baseline, heldout

DRAWS = 400


def _frame(rows: list[tuple], column: str = "v") -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["player_id", "match_id", column])


def _players(
    spread: float, scale_spread: float, seed: int, matches: int = 20, players: int = 400
) -> pd.DataFrame:
    """Players differing in location by ``spread`` and in scale by ``scale_spread``."""
    rng = np.random.default_rng(seed)
    rows = []
    for player in range(players):
        centre = rng.normal(0.0, spread)
        sd = np.exp(rng.normal(0.0, scale_spread))
        for match in range(matches):
            rows.append((player, match, centre + rng.normal(0.0, sd)))
    return _frame(rows)


def test_informativeness_recovers_planted_location_spread():
    """r rises with real between-player differences and is ~0 without them."""
    null = baseline.informativeness(_players(0.0, 0.0, seed=1), "v")
    signal = baseline.informativeness(_players(1.0, 0.0, seed=1), "v")
    assert null < 0.05, f"planted null returned r={null}"
    # Between/within of 1.0 planted against unit within: recover the order.
    assert 0.5 < signal < 2.0, f"planted r=1 returned {signal}"


def test_informativeness_is_not_fooled_by_thin_histories():
    """A one-match player has no variance and must not inflate the numerator."""
    rng = np.random.default_rng(7)
    rows = [(p, m, rng.normal()) for p in range(200) for m in range(20)]
    rows += [(1000 + p, 0, rng.normal(0, 5)) for p in range(200)]
    assert baseline.informativeness(_frame(rows), "v") < 0.05


def test_scale_ratio_recovers_planted_scale_spread():
    """r_s rises with real between-player spread differences, ~0 without.

    The jackknife version returned exactly 0.0 for the signal case. Anything
    that cannot separate these two lines is not measuring scale.
    """
    null = baseline.scale_ratio(_players(1.0, 0.0, seed=2), "v", draws=DRAWS)
    signal = baseline.scale_ratio(_players(1.0, 0.6, seed=2), "v", draws=DRAWS)
    assert null < 0.01, f"planted null returned r_s={null}"
    assert signal > 3 * max(null, 1e-4), f"planted spread returned r_s={signal}"


def test_scale_ratio_attenuates_rather_than_overstating():
    """The recovered ratio is a floor. Guard the direction, not the value."""
    signal = baseline.scale_ratio(_players(1.0, 0.6, seed=3), "v", draws=DRAWS)
    assert 0.0 < signal < 0.6, f"r_s={signal} is not the attenuated floor expected"


def test_covariance_nu_falls_as_players_differ_more():
    """nu is the prior's weight: more real between-player structure, less prior."""
    rng = np.random.default_rng(4)

    def build(scale_spread: float) -> tuple[np.ndarray, np.ndarray]:
        rows, ids = [], []
        for player in range(300):
            sd = np.exp(rng.normal(0.0, scale_spread, size=3))
            own = rng.normal(0.0, sd, size=(20, 3))
            rows.append(own)
            ids.append(np.full(20, player))
        return np.vstack(rows), np.concatenate(ids)

    alike = heldout.covariance_nu(*build(0.0))
    varied = heldout.covariance_nu(*build(0.7))
    assert varied < alike, f"nu did not fall when players differed more: {varied} vs {alike}"
    assert varied > 0


def test_covariance_nu_is_infinite_without_players():
    """Nothing to estimate from shrinks fully to the position, not to a guess."""
    rows = np.random.default_rng(5).normal(size=(10, 3))
    assert heldout.covariance_nu(rows, np.zeros(10)) == float("inf")


@pytest.mark.parametrize("planted", [0.0, 0.05, 0.2])
def test_overdispersion_recovers_planted_rho(planted: float):
    """rho comes back near what beta-binomial data was drawn with."""
    rng = np.random.default_rng(6)
    rows = []
    for player in range(400):
        rate = rng.uniform(0.4, 0.8)
        for match in range(20):
            attempts = int(rng.integers(4, 30))
            if planted <= 0:
                successes = rng.binomial(attempts, rate)
            else:
                concentration = 1.0 / planted - 1.0
                drawn = rng.beta(rate * concentration, (1 - rate) * concentration)
                successes = rng.binomial(attempts, drawn)
            rows.append((player, match, successes, attempts))
    frame = pd.DataFrame(rows, columns=["player_id", "match_id", "k", "n"])
    original = baseline.PROPORTIONS.get("v")
    baseline.PROPORTIONS["v"] = ("k", "n")
    try:
        estimated = baseline.overdispersion(frame, "v")
    finally:
        if original is None:
            del baseline.PROPORTIONS["v"]
        else:
            baseline.PROPORTIONS["v"] = original
    assert abs(estimated - planted) < 0.03, f"planted rho={planted}, got {estimated}"


def test_overdispersion_is_within_player_not_between():
    """Players with very different rates but no own excess must give rho ~ 0.

    The between-player version of this estimator would return the spread of
    player rates here, widening every tail by the informativeness signal.
    """
    rng = np.random.default_rng(8)
    rows = []
    for player in range(400):
        rate = rng.uniform(0.1, 0.9)  # players differ enormously
        for match in range(20):  # but each is pure binomial
            attempts = int(rng.integers(4, 30))
            rows.append((player, match, rng.binomial(attempts, rate), attempts))
    frame = pd.DataFrame(rows, columns=["player_id", "match_id", "k", "n"])
    baseline.PROPORTIONS["v"] = ("k", "n")
    try:
        assert baseline.overdispersion(frame, "v") < 0.02
    finally:
        del baseline.PROPORTIONS["v"]


def test_beta_binomial_scores_the_all_success_player_via_shrinkage():
    """A degenerate own rate is smoothed by the EB blend, not skipped or scored
    against a p=1 tail. The blend IS the smoothing: pseudo-counts from the
    position with measured weight, so the scored rate sits strictly inside
    (0, 1) whenever the location ratio is finite."""
    rows = []
    for match in range(6):
        rows.append((1, match, "GK", 8, 8))  # all successes, every match
    for player in range(2, 30):
        for match in range(6):
            rows.append((player, match, "GK", 5 + match % 3, 8))
    frame = pd.DataFrame(rows, columns=["player_id", "match_id", "position_code", "k", "n"])
    z = np.full(len(frame), 99.0)  # sentinel: replaced means scored
    baseline.PROPORTIONS["v"] = ("k", "n")
    try:
        scored, swapped = baseline._beta_binomial(
            frame,
            "v",
            z,
            rho=np.full(len(frame), 0.05),
            pool=np.full(len(frame), 0.7),
            ratio=np.full(len(frame), 0.5),  # finite -> weight < 1
        )
        assert swapped == len(frame)
        assert np.isfinite(scored).all()
        assert (scored != 99.0).all(), "some row kept its sentinel: not scored"
        # And with weight forced to 1 (infinite ratio), the degenerate player
        # falls back to the incoming z rather than a degenerate tail.
        kept, swapped = baseline._beta_binomial(
            frame,
            "v",
            z,
            rho=np.full(len(frame), 0.05),
            pool=np.full(len(frame), 0.7),
            ratio=np.full(len(frame), np.inf),
        )
        assert (kept[:6] == 99.0).all(), "p=1 row was scored against a degenerate tail"
    finally:
        del baseline.PROPORTIONS["v"]


def test_scale_ratio_holds_at_small_histories():
    """Bootstrap MAD variance is lumpy at n~6; lumpiness must not manufacture
    structure from a null nor swallow a real signal."""
    null = baseline.scale_ratio(_players(1.0, 0.0, seed=11, matches=6), "v", draws=DRAWS)
    signal = baseline.scale_ratio(_players(1.0, 0.6, seed=11, matches=6), "v", draws=DRAWS)
    assert null < 0.01, f"n=6 null returned r_s={null}"
    assert signal > 0.03, f"n=6 planted spread returned r_s={signal}"
