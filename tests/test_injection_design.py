"""The two injection designs, and the census guards that protect them.

Detection is design-invariant: a target's leave-one-out fit excludes the
target and the position pools are pinned to the clean frame, so an injection
cannot move its own score. The designs differ only in whether the rest of the
player's history is rescored -- which is what makes collateral measurable
under ``persistent`` and impossible under ``heldout``.

That distinction is worth pinning, because the failure mode it replaced was
not a crash: scoring a partial set of non-target rows produced a *plausible*
collateral number drawn from a near-median subset, which reads as measured
when it is not.
"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from fis.analysis import baseline, heldout, injection_test


def _census(rows: int = 12, players: int = 6) -> pd.DataFrame:
    """A census shaped like score_all's output, with every forest column."""
    rng = np.random.default_rng(4)
    frame = pd.DataFrame(
        {
            "player_id": np.repeat(np.arange(players), rows),
            "match_id": np.tile(np.arange(rows), players),
            "position_code": "DF",
            "fit_source": "shrunk",
        }
    )
    for column in (
        "mahalanobis",
        "mahalanobis_z",
        "forest",
        "forest_norm",
        "forest_own_fraction",
        "forest_res",
        "forest_res_norm",
        "forest_res_own_fraction",
    ):
        frame[column] = rng.normal(size=len(frame))
    return frame


def _scored(census: pd.DataFrame) -> pd.DataFrame:
    """Enough of a residual frame for flag() to calibrate against."""
    rng = np.random.default_rng(5)
    frame = census[["player_id", "match_id", "position_code"]].copy()
    frame["max_abs_z"] = np.abs(rng.normal(size=len(frame)))
    for metric in baseline.METRICS:
        frame[f"z_{metric}"] = rng.normal(size=len(frame))
        frame[f"sigma_{metric}"] = rng.normal(size=len(frame)) * 4.0
        frame[f"weight_{metric}"] = rng.uniform(size=len(frame))
    return frame


def test_designs_are_the_only_two_accepted():
    """A typo in the design name must fail loudly, not pick a default."""
    with pytest.raises(ValueError, match="persistent or heldout"):
        injection_test.run(None, None, None, design="held-out")


def test_forest_scorers_are_opt_in():
    """The default costs no forest fits, so a committed result cannot move."""
    import inspect

    parameters = inspect.signature(injection_test.run).parameters
    assert parameters["forest"].default is False
    assert parameters["design"].default == "persistent"


def test_select_targets_gives_every_scorer_its_own_row():
    """Per-scorer selection is what stops one scorer's hard case becoming
    every other scorer's easy one."""
    census = _census()
    scored = _scored(census)
    scorers = ("max", "mahalanobis", "forest", "forest_res")
    targets = injection_test.select_targets(scored, census, scorers=scorers)
    chosen = {s: {p: m for p, m, sc in targets if sc == s} for s in scorers}
    for scorer in scorers:
        assert len(chosen[scorer]) == census["player_id"].nunique()
    # The scorers disagree about which match is typical, or selection is not
    # per-scorer at all.
    assert any(chosen["mahalanobis"][p] != chosen["forest"][p] for p in chosen["max"])


def test_production_bars_rejects_a_renamed_census():
    """SOME forest columns present means the names moved underneath -- the
    stale-cache case, which must say so rather than reach a bare KeyError."""
    census = _census()
    stale = census.rename(columns={"forest_norm": "forest_z"}).drop(
        columns=["forest_res", "forest_res_norm"]
    )
    with pytest.raises(KeyError, match="predates a column rename"):
        heldout.production_bars(_scored(census), stale, 0.01)


def test_production_bars_accepts_a_census_built_without_forests():
    """ALL forest columns absent is a legitimate no-forest census, not a
    stale one, so it must pass rather than raise."""
    census = _census()
    without = census[[c for c in census.columns if not c.startswith("forest")]]
    bars = heldout.production_bars(_scored(census), without, 0.01)
    assert set(bars) == {
        "max",
        "max_ungated",
        "max_delivered",
        "mahalanobis",
        "mahalanobis_z",
    }


def test_run_names_the_remedy_when_the_census_lacks_forests():
    """forest=True against a forest-free census is a stale-cache mistake, and
    the message has to name the rebuild rather than the missing column."""
    census = _census()
    without = census[[c for c in census.columns if not c.startswith("forest")]]
    with pytest.raises(KeyError, match="rebuild it"):
        injection_test.run(_scored(census), None, without, forest=True)


def _results(shift_is_nan: bool) -> pd.DataFrame:
    """One composed cell, per-DOF columns, for the summary renderer."""
    rng = np.random.default_rng(9)
    n = 8
    return pd.DataFrame(
        {
            "player_id": np.arange(n),
            "match_id": np.arange(n),
            "scorer": "max",
            "mechanism": "a+b",
            "severity": 3.0,
            "is_target": True,
            "clean": rng.normal(size=n),
            "after": rng.normal(size=n),
            "sigma_clean": rng.normal(size=n) * 5,
            "sigma_after": rng.normal(size=n) * 5,
            "achieved": np.nan,
            "achieved_z": np.nan,
            "achieved_a": -1.0,
            "achieved_z_a": np.nan if shift_is_nan else -0.8,
        }
    )


def test_unmeasurable_per_dof_shift_reads_as_not_applicable():
    """A metric dropped from the feature set has no z column, so its shift is
    unmeasurable in that arm -- which must not render as '+nan', a string that
    reads as a defect rather than as an honest gap."""
    text = injection_test.summary_persistent(_results(True), {"max": 1.0})
    assert "achieved_z" not in text
    assert "a -1.00sd/n/a" in text
    assert "nan" not in text.split("per-DOF")[1].split("\n")[0]


def test_measurable_per_dof_shift_still_prints_the_number():
    """The n/a path must not swallow a real value."""
    text = injection_test.summary_persistent(_results(False), {"max": 1.0})
    assert "a -1.00sd/-0.80z" in text


def test_fingerprint_ignores_prose_but_not_behaviour():
    """Dimension 3: a changed borrowing rule or shrinkage weight alters values
    without moving a column, so the column guard cannot see it. Comments never
    reach the AST and docstrings are stripped, so prose is free."""
    import ast

    source = inspect.getsource(heldout)
    base = ast.dump(ast.parse(source))
    commented = ast.dump(ast.parse("# a remark\n" + source))
    behaviour = ast.dump(
        ast.parse(source.replace("POOL_BORROW_CAP = 256", "POOL_BORROW_CAP = 128"))
    )
    assert base == commented, "a comment must not invalidate a cached census"
    assert base != behaviour, "a changed borrowing rule must invalidate it"


def test_cached_census_is_refused_when_the_data_moved(tmp_path):
    """Dimension 4, the silent one: two sessions share a warehouse, so a dbt
    build moves the marts under every cached census."""
    census = _census()
    scored = _scored(census)
    path = tmp_path / "census.parquet"
    heldout.write_census(path, census, scored)
    assert len(heldout.read_census(path, scored)) == len(census)

    moved = scored.copy()
    moved.loc[moved.index[0], f"z_{baseline.METRICS[0]}"] += 1.0
    with pytest.raises(ValueError, match="moved under it"):
        heldout.read_census(path, moved)


def test_fingerprint_round_trips_through_parquet_metadata(tmp_path):
    """The stamp has to survive the write, or every read is a false alarm."""
    census = _census()
    scored = _scored(census)
    path = tmp_path / "census.parquet"
    heldout.write_census(path, census, scored)
    reloaded = heldout.read_census(path, scored)
    pd.testing.assert_frame_equal(reloaded, census)


def test_delivered_rate_comes_from_the_clean_population():
    """The asterisk must fire on the gate's ceiling, not on target selection.

    Injected rows are median-selected and fire the sigma gate far less often
    than the population (1.5% against 4.9%), so a delivered rate computed over
    result rows measures selection and would asterisk every row, including the
    1% rows the rule reaches perfectly well.
    """
    frame = baseline.prepare(baseline.load())
    scored, _ = baseline.residuals(frame)
    scored = scored[scored["is_scoreable"]]
    census = scored.assign(mahalanobis=0.0, mahalanobis_z=0.0)

    at_one = heldout.production_bars(scored, census, 0.01)["max_delivered"]
    at_five = heldout.production_bars(scored, census, 0.05)["max_delivered"]
    assert at_one == pytest.approx(0.01, abs=1e-3), "1% is reachable, so no asterisk"
    assert at_five < 0.05, "5% is above the gate ceiling, so it must asterisk"


def test_ungated_bar_is_not_the_gated_one():
    """The gated bar is LOWER, because the gate removes rows after the cut.
    Inheriting it for the ungated tally would look right and be wrong."""
    frame = baseline.prepare(baseline.load())
    scored, _ = baseline.residuals(frame)
    scored = scored[scored["is_scoreable"]]
    bars = heldout.production_bars(scored, scored.assign(mahalanobis=0.0, mahalanobis_z=0.0), 0.01)
    assert bars["max"] < bars["max_ungated"]


def test_ungated_bar_delivers_its_nominal_rate():
    """Ordering is the weak property: a bar that is too high or too low still
    sits above the gated one. What the tally claims is that the bar flags the
    rate on its label, so assert THAT -- otherwise a joint-bar leak reads as a
    plausible percentage that a human has to catch."""
    frame = baseline.prepare(baseline.load())
    scored, _ = baseline.residuals(frame)
    scored = scored[scored["is_scoreable"]]
    census = scored.assign(mahalanobis=0.0, mahalanobis_z=0.0)
    top = scored["max_abs_z"].to_numpy()

    one = heldout.production_bars(scored, census, 0.01)
    five = heldout.production_bars(scored, census, 0.05)
    for bars, rate in ((one, 0.01), (five, 0.05)):
        delivered = float((top >= bars["max_ungated"]).mean())
        assert delivered == pytest.approx(rate, abs=5e-4), (rate, delivered)

    # The two rates must be two rates. A 5% arm silently inheriting the 1%
    # bar would satisfy every ordering check and print two identical rows.
    assert five["max_ungated"] < one["max_ungated"]
    assert five["max"] < one["max"]


def test_persistent_with_forests_stays_available():
    """Deferred is not deleted. This path is the only one that can answer the
    collateral question, and 'no current caller' is exactly what justified
    deleting _auc a day before the sweep needed it back."""
    import inspect

    source = inspect.getsource(injection_test.run)
    assert '"persistent"' in source and '"heldout"' in source
    parameters = inspect.signature(injection_test.run).parameters
    assert parameters["design"].default == "persistent"
    assert parameters["forest"].default is False


def test_auc_treats_missing_scores_as_unflaggable():
    """-inf is a real gated score; NaN cannot be flagged, so it sinks rather
    than being dropped, which would flatter a scorer by shrinking its base."""
    reference = np.array([0.0, 1.0, 2.0, 3.0])
    assert injection_test._auc(reference, np.array([4.0])) == pytest.approx(1.0)
    assert injection_test._auc(reference, np.array([-np.inf])) == pytest.approx(0.0)
    # NaN must score as the bottom, not vanish.
    assert injection_test._auc(reference, np.array([np.nan])) == pytest.approx(0.0)
    # A NaN in the reference is dropped, matching how the bars are set.
    assert injection_test._auc(np.array([0.0, np.nan, 2.0]), np.array([1.0])) == pytest.approx(0.5)


def test_borrowed_rows_differ_between_players():
    """A single global seed handed every thin player the SAME borrowed rows,
    so their forest scores carried one shared draw error instead of independent
    ones -- correlated across the population, so it never averaged out."""
    rng = np.random.default_rng(11)
    pool = rng.normal(size=(400, 3))
    own = rng.normal(size=(4, 3))
    drawn = [
        heldout._Fit(own, pool=pool, seed=heldout.borrow_seed(p))._training_rows(3)[4:]
        for p in range(6)
    ]
    for i in range(1, len(drawn)):
        assert not np.array_equal(drawn[0], drawn[i]), "players share a borrow draw"
    # Same player, same draw: a score must not move between runs or workers.
    repeat = heldout._Fit(own, pool=pool, seed=heldout.borrow_seed(0))._training_rows(3)[4:]
    assert np.array_equal(drawn[0], repeat)


def test_borrow_seed_survives_a_fresh_interpreter():
    """``hash`` is salted per process, so a seed built from it would differ
    between joblib workers and silently make a census unreproducible."""
    import pathlib
    import subprocess
    import sys

    import fis

    root = str(pathlib.Path(fis.__file__).resolve().parents[1])
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "from fis.analysis.heldout import borrow_seed; print(borrow_seed('p1'), borrow_seed(7))",
        ],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": root, "PYTHONHASHSEED": "random", "PATH": "/usr/bin:/bin"},
    )
    assert out.stdout.split() == [str(heldout.borrow_seed("p1")), str(heldout.borrow_seed(7))]


@pytest.mark.slow
def test_a_row_scores_the_same_through_the_census_and_through_run():
    """The bar comes from the census and the score comes from run(), so the two
    must fit a given player identically or the table compares a score against a
    threshold derived from a differently-fitted population.

    This is what a half-applied seed change breaks, and it breaks it invisibly:
    both sides stay internally consistent and only the comparison is wrong.
    """
    mart = baseline.load()
    frame = baseline.prepare(mart)
    scored, _ = baseline.residuals(frame)
    scored = scored[scored["is_scoreable"]]
    keep = scored["player_id"].drop_duplicates().head(10)
    scored = scored[scored["player_id"].isin(set(keep))]

    census = heldout.score_all(scored, forest=True, jobs=1)
    results = injection_test.run(
        scored,
        mart,
        census,
        # Any dose does: `clean` is scored once before injection, so the
        # invariant is dose-free. k=1 only because k=0 emits no rows.
        severities=(1.0,),
        mechanisms={"defensive_success": injection_test.MECHANISMS["defensive_success"]},
        forest=True,
        design="heldout",
        jobs=1,
    )
    by_key = census.set_index(["player_id", "match_id"])
    for scorer in ("forest", "forest_res", "mahalanobis"):
        part = results[(results["scorer"] == scorer) & results["is_target"]]
        assert not part.empty, scorer
        keys = list(zip(part["player_id"], part["match_id"]))
        np.testing.assert_array_equal(
            by_key.loc[keys, scorer].to_numpy(),
            part["clean"].to_numpy(),
            err_msg=f"{scorer}: census and run fit the same row differently",
        )


def _cells() -> pd.DataFrame:
    """Four targets: already-above, genuinely recovered, missed, unscoreable."""
    return pd.DataFrame(
        {
            "player_id": [1, 2, 3, 4],
            "match_id": [1, 2, 3, 4],
            "position_code": "DF",
            "scorer": "mahalanobis",
            "mechanism": "m",
            "severity": 3.0,
            "is_target": True,
            "bit": True,
            "clipped": [False, False, True, False],
            "achieved": 1.0,
            "achieved_z": 1.0,
            "clean": [9.0, 0.0, 0.0, 0.0],
            "after": [9.5, 9.0, 0.5, np.nan],
            "sigma_clean": 5.0,
            "sigma_after": 5.0,
        }
    )


def test_recovery_excludes_rows_already_over_the_bar():
    """'Caught' counts a row that was flagged before anything was injected.
    Recovery must not: nothing recovered it, and counting it lifts every
    scorer by the same amount, which hides the differences the table exists
    to show."""
    stats = injection_test.cell_statistics(_cells(), {"mahalanobis": 5.0})
    row = stats.iloc[0]
    assert row["caught"] == pytest.approx(0.50), "2 of 4 sit above the bar after"
    assert row["recovery"] == pytest.approx(0.25), "only one CROSSED because of it"
    # Agresti-Coull: (0.25*4+2)/8 = 0.375, se = sqrt(0.375*0.625/8).
    assert row["recovery_se"] == pytest.approx(np.sqrt(0.375 * 0.625 / 8))
    assert row["clipped"] == pytest.approx(0.25)


def test_an_empty_recovery_cell_does_not_claim_zero_uncertainty():
    """sqrt(p(1-p)/n) is exactly 0 at p=0, so an untouched cell prints
    '0.0% +-0.0%' -- which reads as measured-to-be-zero when it means no events
    were seen. Where the zero is STRUCTURAL (k=0, after IS clean) it is exact."""
    missed = _cells()
    missed["after"] = 0.0  # nothing crosses a bar of 5
    stats = injection_test.cell_statistics(missed, {"mahalanobis": 5.0})
    assert stats.iloc[0]["recovery"] == pytest.approx(0.0)
    assert stats.iloc[0]["recovery_se"] > 0.05, "no events seen is not zero uncertainty"

    null = _cells()
    null["after"] = null["clean"]
    exact = injection_test.cell_statistics(null, {"mahalanobis": 5.0})
    assert exact.iloc[0]["recovery"] == pytest.approx(0.0)
    assert exact.iloc[0]["recovery_se"] == 0.0, "k=0 is exact, not estimated"


def test_the_dose_limiting_clamps_are_the_instrumented_ones():
    """The unit clamp on mean_action_x is a 4dp rounding guard that binds on 2
    rows in the whole mart. The clamps that actually truncate a dose are the
    count ones -- running out of successes, actions or touches -- and those are
    what the report's 'clipped' column has to mean."""
    row = pd.Series(
        {
            "defensive_actions": 4.0,
            "defensive_action_successes": 1.0,
            "minutes_played": 90.0,
            "regulation_minutes": 90,
        }
    )
    # Asking to relabel far more successes than exist truncates the dose.
    out = injection_test._relabel(
        row,
        sd=5.0,
        k=3.0,
        rng=np.random.default_rng(0),
        success_col="defensive_action_successes",
        denom_col="defensive_actions",
        metric="defensive_action_success_pct",
    )
    assert out["defensive_action_successes"] == 0, "floored, so the dose was cut"
    assert out[injection_test.CLIPPED] is True


def test_auc_does_not_move_with_the_bar():
    """AUC is threshold-free. If it moved with the bar it would be reported
    per rate, and two identical columns would read as agreement between
    thresholds rather than as one number printed twice."""
    reference = {"mahalanobis": np.array([0.0, 1.0, 2.0, 9.2])}
    cells = _cells()
    tight = injection_test.cell_statistics(cells, {"mahalanobis": 9.0}, reference=reference)
    loose = injection_test.cell_statistics(cells, {"mahalanobis": 0.5}, reference=reference)
    assert tight.iloc[0]["auc"] == pytest.approx(loose.iloc[0]["auc"])
    assert tight.iloc[0]["recovery"] != loose.iloc[0]["recovery"], "the bar must matter"


def test_reference_population_is_the_census_not_the_results():
    """A results-frame reference inflates every AUC and is invisible in the
    output -- nothing in the table shows what it compared against."""
    census = _census()
    scored = _scored(census)
    reference = injection_test.reference_scores(scored, census)
    assert set(reference) >= {"max", "max_ungated", "mahalanobis", "mahalanobis_z"}
    for name in ("mahalanobis", "forest", "forest_res"):
        assert len(reference[name]) == len(census), name
    np.testing.assert_array_equal(reference["mahalanobis"], census["mahalanobis"].to_numpy())
    # The gated reference masks below-gate rows to -inf rather than dropping
    # them: they are real rows the rule declines to flag.
    assert np.isneginf(reference["max"]).any()


def test_clip_unit_records_that_the_dose_was_truncated():
    """A clamped row got less than was asked for, so a miss there is delivery,
    not detection. Discarding that silently reads as a detector failure."""
    out: dict = {}
    assert injection_test.clip_unit(0.5, out) == pytest.approx(0.5)
    assert injection_test.CLIPPED not in out
    assert injection_test.clip_unit(1.4, out) == pytest.approx(1.0)
    assert out[injection_test.CLIPPED] is True


def test_target_choices_separates_a_scorers_own_pick_from_the_fallback():
    """select_targets hands a scorer the shipped rule's row when it cannot
    score a player. The agreement matrix must be able to tell that apart, or a
    blind scorer reads as perfectly aligned with the shipped rule."""
    census = _census()
    scored = _scored(census)
    blind = census["player_id"].unique()[:2]
    census.loc[census["player_id"].isin(blind), "mahalanobis"] = np.nan
    default, choices = injection_test.target_choices(
        scored, census, scorers=("mahalanobis", "forest")
    )
    assert set(default) == set(census["player_id"].unique())
    assert not set(blind) & set(choices["mahalanobis"]), "no opinion must not be an opinion"
    assert set(blind) <= set(choices["forest"]), "only the blind scorer loses them"


def test_report_reports_auc_once_and_recovery_per_rate():
    """AUC is threshold-free and recovery is not. Rendering AUC per rate would
    print one number twice and invite reading it as agreement between the two
    thresholds; rendering recovery once would hide the bar's whole effect."""
    from fis.analysis import report

    cells = _cells()
    per_rate = {
        0.01: injection_test.cell_statistics(cells, {"mahalanobis": 9.0}),
        0.05: injection_test.cell_statistics(cells, {"mahalanobis": 0.5}),
    }
    text = report.detection_table(per_rate, ("mahalanobis",), "t")
    assert text.count("recovery @1%") == 1 and text.count("recovery @5%") == 1
    body = [ln for ln in text.splitlines() if ln.startswith("| **mahalanobis**")]
    assert len(body) == 1
    # The two recovery cells must differ: the loose bar recovers a row the
    # tight one does not. No reference was passed, so auc has to say so rather
    # than print "nan", which reads as a defect.
    assert "25.0%" in body[0] and "50.0%" in body[0], body[0]
    assert "nan" not in body[0] and "| n/a |" in body[0]


def test_matrix_cell_says_nothing_rather_than_zero_when_a_scorer_caught_none():
    """|A and B|/|A| has no denominator when A caught nobody. Printing 0% there
    would read as disagreement rather than as an absent opinion."""
    from fis.analysis import report

    rendered = report._matrix(["a", "b"], lambda x, y: "-" if x == "a" else "50%/50%")
    assert rendered.splitlines()[2].startswith("| **a** | - |")


def _total(shares: list[float]) -> float:
    """Displacement of an allocation, which composes in quadrature."""
    return float(np.sqrt(sum(s * s for s in shares)))


def test_allocation_preserves_the_requested_sigma():
    """The composed row is LABELLED k sigma. An equal k/sqrt(n) split silently
    under-delivers whenever a channel is short of substrate, which makes the
    label false; water-filling keeps the total."""
    assert _total(injection_test.allocate(3.0, [9, 9, 9, 9])) == pytest.approx(3.0)
    # A thin channel is pinned at its ceiling and the rest absorb its share.
    thin = injection_test.allocate(3.0, [9, 9, 0.4, 9])
    assert thin[2] == pytest.approx(0.4)
    assert _total(thin) == pytest.approx(3.0)
    assert thin[0] == thin[1] == thin[3] > 1.5, "survivors must take MORE than an equal share"


def test_a_dead_channel_gives_its_whole_share_to_the_survivors():
    """Zero capacity must be excluded, not handed a share. A NaN or infinite
    cap would pass the comparison and waste budget on a channel that cannot
    move -- reintroducing exactly the shortfall this fixes."""
    shares = injection_test.allocate(3.0, [9, 9, 0.0, 9])
    assert shares[2] == 0.0
    assert _total(shares) == pytest.approx(3.0)
    # Three survivors sharing the whole budget is k/sqrt(3), not k/sqrt(4).
    assert shares[0] == pytest.approx(3.0 / np.sqrt(3))


def test_allocation_falls_short_only_when_every_channel_is_capped():
    """A row with nowhere to put the displacement cannot reach k at any
    allocation. That is a property of the player and must be reported, so the
    allocator returns the shortfall rather than looping or over-allocating."""
    capped = injection_test.allocate(3.0, [0.5, 0.5, 0.5, 0.5])
    assert capped == [0.5, 0.5, 0.5, 0.5]
    assert _total(capped) == pytest.approx(1.0)
    assert injection_test.allocate(3.0, [0.0, 0.0]) == [0.0, 0.0]


def test_a_channel_pinned_at_its_ceiling_does_not_clip():
    """The allocator caps each channel at what it can deliver, so the clamp
    inside the mechanism should never bind. The boundary case is exact
    saturation, where the product lands on an integer give or take an ulp --
    either side rounds back to that integer, so nothing is truncated."""
    row = pd.Series(
        {
            "defensive_actions_successful": 10.0,
            "defensive_actions_with_outcome": 20.0,
            "defensive_action_success_pct": 50.0,
        }
    )
    sd = 0.5
    cap = injection_test._relabel_capacity(
        row, sd, "defensive_actions_successful", "defensive_actions_with_outcome"
    )
    assert cap == pytest.approx(1.0), "10 successes / (0.5 * 20)"
    for seed in range(50):
        out = injection_test._relabel(
            row,
            sd,
            cap,
            np.random.default_rng(seed),
            "defensive_actions_successful",
            "defensive_actions_with_outcome",
            "defensive_action_success_pct",
        )
        assert out["defensive_actions_successful"] == 0, "saturated exactly"
        assert injection_test.CLIPPED not in out, "saturation is not truncation"


def test_the_detection_vector_holds_no_raw_count():
    """Injection moves COUNTS and leaves ``minutes_played`` untouched, so a raw
    count in the detection vector would carry an exposure signal — the detector
    would be reading how long a player was on the pitch as if it were how he
    played. That is what the per-90 forms exist to remove.

    The SUFFIX rule is the load-bearing half. Disjointness against the named
    counts is the weaker one and nearly vacuous today, because ``METRICS`` is
    CONSTRUCTED as ``RATE_METRICS + [f"{m}_per_90" for m in VOLUME_METRICS]``
    and so cannot contain a bare volume name. It earns its place only if that
    construction is ever replaced by an explicit list -- which is exactly when
    a naming convention stops being a check. Kept for that, not relied on.
    """
    # Every count named anywhere: the volume metrics AND the numerators and
    # denominators behind the proportions, which VOLUME_METRICS does not cover.
    raw = set(baseline.VOLUME_METRICS)
    for numerator, denominator in baseline.PROPORTIONS.values():
        raw |= {numerator, denominator}
    assert len(raw) >= len(baseline.VOLUME_METRICS), "counts must be named to be checkable"
    assert not (set(baseline.METRICS) & raw), (
        f"raw count(s) in the detection vector: {sorted(set(baseline.METRICS) & raw)}"
    )
    for metric in baseline.METRICS:
        assert metric.endswith("_pct") or metric.endswith("_per_90") or metric == "mean_action_x", (
            f"{metric} is neither a ratio, a per-90 rate, nor a mean over events"
        )


def test_injection_never_moves_a_player_exposure():
    """The per-90 defence above only holds while exposure is held fixed. If a
    mechanism wrote minutes_played, the normalisation would move with the
    numerator and the metric would stop being exposure-free."""
    rng = np.random.default_rng(3)
    row = pd.Series(
        {
            "defensive_actions": 40.0,
            "defensive_actions_with_outcome": 30.0,
            "defensive_actions_successful": 20.0,
            "defensive_action_success_pct": 66.67,
            "defensive_actions_in_defensive_third": 15.0,
            "actions": 200.0,
            "touches_in_defensive_third": 25.0,
            "sum_start_x_in_defensive_third": 5.0,
            "mean_action_x": 0.4,
            "attempts_with_position": 120.0,
            "passes": 90.0,
            "passes_completed": 70.0,
            "passes_with_outcome": 85.0,
            "pass_completion_pct": 82.35,
            "minutes_played": 90.0,
            "regulation_minutes": 90,
        }
    )
    sds = {
        "defensive_actions": 3.0,
        "touches_in_defensive_third": 3.0,
        "defensive_success": 0.05,
        "pass_completion": 0.05,
    }
    exposure = {"minutes_played", "regulation_minutes"}
    for name, mechanism in injection_test.MECHANISMS.items():
        updates = mechanism(row, sds, 2.0, rng)
        assert not (set(updates) & exposure), f"{name} moved the player's exposure"


def test_gated_score_reproduces_the_shipped_flag_at_any_bar():
    """One bar-independent ranking: thresholding it IS the shipped rule."""
    z = np.array([5.0, 4.0, 3.0, 2.0])
    sigma = np.array([4.0, 1.0, 4.0, 4.0])
    masked = injection_test.gated_score(z, sigma, 3.0)
    for bar in (2.5, 3.5, 4.5):
        expected = (z >= bar) & (np.abs(sigma) >= 3.0)
        assert np.array_equal(masked >= bar, expected), bar
