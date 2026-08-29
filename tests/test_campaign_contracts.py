"""The contracts a campaign runs under: draw identity, target ties, the
mechanism-input boundary, the full-raw fingerprint, the resolved recipe, the
publication gate, and freshness over payload and runtime.

Each pins a remedy's property rather than its implementation.
"""

from __future__ import annotations

import argparse
import inspect
import pathlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fis.analysis import baseline, heldout, injection_test, report

# ---------------------------------------------------------------- draws (A2) --


def test_the_same_row_and_dose_draw_the_same_stream():
    one = injection_test.draw_rng(7, "p1", "m1", "remove_defensive", 1.5)
    two = injection_test.draw_rng(7, "p1", "m1", "remove_defensive", 1.5)
    assert one.random() == two.random()


def test_a_changed_target_match_gets_a_fresh_stream():
    """Without match_id a re-selected target reuses another row's stream."""
    one = injection_test.draw_rng(7, "p1", "m1", "remove_defensive", 1.5)
    two = injection_test.draw_rng(7, "p1", "m2", "remove_defensive", 1.5)
    assert one.random() != two.random()


def test_the_stream_is_scorer_free_by_signature():
    """Two scorers on one target must draw identically."""
    assert "scorer" not in inspect.signature(injection_test.draw_rng).parameters


# ------------------------------------------------------------ target ties (A3) --


def _tied_pair(order: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One player, two matches equidistant from his median score."""
    frame = pd.DataFrame(
        {
            "player_id": [1, 1],
            "match_id": ["m-late", "m-early"],
            "max_abs_z": [1.0, 3.0],
        }
    ).iloc[order]
    census = frame[["player_id", "match_id"]].assign(mahalanobis=frame["max_abs_z"].to_numpy())
    return frame, census


def test_equidistant_targets_resolve_on_match_id_not_frame_order():
    picks = []
    for order in ([0, 1], [1, 0]):
        scored, census = _tied_pair(order)
        default, chosen = injection_test.target_choices(scored, census, scorers=("mahalanobis",))
        picks.append((default[1], chosen["mahalanobis"][1]))
    assert picks[0] == picks[1] == ("m-early", "m-early"), (
        "an equal-distance tie must fall to the canonical match_id, not to "
        "whichever row arrived first"
    )


# ------------------------------------------------- mechanism boundary (B1) --


def test_every_registered_mechanism_declares_its_inputs():
    assert set(injection_test.MECHANISM_INPUTS) == set(injection_test.MECHANISMS)
    for name, control in injection_test.CONTROLS.items():
        assert control in injection_test.MECHANISM_INPUTS[name], f"{name} control undeclared"
    for name, (success, denom) in injection_test.RATE_CONTROLS.items():
        declared = set(injection_test.MECHANISM_INPUTS[name])
        assert {success, denom} <= declared, f"{name} rate columns undeclared"


def _full_row() -> pd.Series:
    return pd.Series(
        {
            "minutes_played": 90.0,
            "regulation_minutes": 90.0,
            "actions": 60.0,
            "defensive_actions": 12,
            "defensive_actions_with_outcome": 10,
            "defensive_actions_successful": 7,
            "defensive_actions_in_defensive_third": 8,
            "touches_in_defensive_third": 20.0,
            "sum_start_x_in_defensive_third": 4.0,
            "attempts_with_position": 50.0,
            "mean_action_x": 0.35,
            "passes_completed": 30,
            "passes_with_outcome": 40,
            "pass_completion_pct": 75.0,
            "defensive_action_success_pct": 70.0,
            "defensive_actions_per_90": 12.0,
            "touches_in_defensive_third_per_90": 20.0,
        }
    )


_SDS = {
    "defensive_actions": 3.0,
    "touches_in_defensive_third": 5.0,
    "defensive_actions_successful": 2.0,
    "passes_completed": 6.0,
    "defensive_success": 0.10,
    "pass_completion": 0.05,
}


def _rng_for(name, scaled):
    return injection_test.draw_rng(0, "p", "m", name, scaled)


def test_declared_views_satisfy_every_registered_mechanism():
    """Declarations must be SUFFICIENT: every mechanism runs on its own view."""
    for name in injection_test.MECHANISMS:
        k = 0.5 if name == "throttle_defensive" else 1.0
        updates, _ = injection_test.compose(_full_row(), _SDS, k, (name,), _rng_for)
        assert updates, f"{name} produced nothing on a well-stocked row"


def test_an_undeclared_read_raises_through_the_restricted_view(monkeypatch):
    """Enforced in production: reading past the declaration fails on the view."""

    def nosy(row, sds, k, rng):
        return {"defensive_actions": float(row["passes_completed"])}

    monkeypatch.setitem(injection_test.MECHANISMS, "nosy", nosy)
    monkeypatch.setitem(injection_test.MECHANISM_INPUTS, "nosy", ("defensive_actions",))
    monkeypatch.setitem(injection_test.CONTROLS, "nosy", "defensive_actions")
    with pytest.raises(KeyError, match="passes_completed"):
        injection_test.compose(_full_row(), _SDS, 1.0, ("nosy",), _rng_for)


# ------------------------------------------------- full-raw fingerprint (B1) --


def _raw(n: int = 8) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    frame = pd.DataFrame({c: rng.random(n) for c in injection_test.consumed_columns()})
    frame["player_id"] = np.arange(n) % 4
    frame["match_id"] = [f"m{i}" for i in range(n)]
    frame["position_code"] = "DF"
    frame["unconsumed_note"] = rng.random(n)
    return frame


def test_a_consumed_column_edit_on_a_nontarget_row_moves_the_raw_fingerprint():
    """Non-target rows reach the position-level fits, so their consumed columns
    are part of result identity."""
    raw = _raw()
    base = injection_test.raw_fingerprint(raw)
    moved = raw.copy()
    moved.loc[moved.index[-1], "passes"] += 1.0
    assert injection_test.raw_fingerprint(moved) != base


def test_an_unconsumed_column_edit_leaves_the_raw_fingerprint_alone():
    """Hashing past the dependency would invalidate a campaign on any edit."""
    raw = _raw()
    base = injection_test.raw_fingerprint(raw)
    moved = raw.copy()
    moved["unconsumed_note"] += 1.0
    assert injection_test.raw_fingerprint(moved) == base


def test_row_order_does_not_move_the_raw_fingerprint():
    raw = _raw()
    shuffled = raw.sample(frac=1.0, random_state=5)
    assert injection_test.raw_fingerprint(shuffled) == injection_test.raw_fingerprint(raw)


def test_duplicate_experiment_keys_are_rejected():
    raw = _raw()
    doubled = pd.concat([raw, raw.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        injection_test.raw_fingerprint(doubled)


# ------------------------------------------------- canonical recipe (B2) --


def test_every_resolved_recipe_field_reaches_the_stamp():
    """Each field, varied alone against a fixed raw frame, must move the stamp."""
    raw = _raw()
    base_recipe = injection_test.canonical_recipe(
        forest=True, design="heldout", compositions={"correlated": ("remove_defensive",)}
    )
    base = injection_test.campaign_config("s", base_recipe, raw)
    varied = {
        "seed": {"seed": 99},
        "design": {"design": "persistent"},
        "scorers": {"scorers": ("max",)},
        "severities": {"severities": (0.0, 2.0)},
        "mechanisms": {"mechanisms": {}},
        "compositions": {"compositions": {}},
    }
    for what, override in varied.items():
        kwargs = {
            "forest": True,
            "design": "heldout",
            "compositions": {"correlated": ("remove_defensive",)},
            **override,
        }
        recipe = injection_test.canonical_recipe(**kwargs)
        assert injection_test.campaign_config("s", recipe, raw) != base, f"{what} left it unmoved"
    moved = raw.copy()
    moved.loc[moved.index[0], "passes"] += 1.0
    assert injection_test.campaign_config("s", base_recipe, moved) != base, "raw left it unmoved"


def test_an_unregistered_mechanism_is_refused_from_the_stamped_path():
    recipe = injection_test.canonical_recipe(mechanisms={"custom": lambda r, s, k, g: {}})
    with pytest.raises(ValueError, match="unregistered"):
        injection_test.campaign_config("s", recipe, _raw())


def test_the_report_call_site_feeds_one_recipe_to_both_runner_and_stamp():
    """main() must build one recipe, stamp from it, and hand run() the resolved
    values rather than re-resolving."""
    src = inspect.getsource(report.main)
    assert "canonical_recipe(" in src
    assert "campaign_config(settings, recipe, mart)" in src
    for field in ("severities", "mechanisms", "compositions", "scorers", "metrics", "seed"):
        assert f'{field}=recipe["{field}"]' in src, f"run() is not fed the resolved {field}"


def test_run_resolves_through_the_canonical_recipe():
    src = inspect.getsource(injection_test.run)
    assert "canonical_recipe(" in src, "run() resolving its own defaults is the divergence bug"


# ------------------------------------------------- publication gate (B3) --


def test_the_readme_write_is_guarded_by_the_gate():
    src = inspect.getsource(report.main)
    assert "if canonical and not args.stale_ok" in src, (
        "a non-canonical run must never rewrite the README summary block"
    )


# ------------------------------------------------- freshness (B4) --


def _report_text(**overrides) -> str:
    stamps = report._stamps(results_stamp=overrides.pop("results_stamp", "abc"))
    stamps.update(overrides)
    return "\n".join(f"<!-- {k}={v} -->" for k, v in stamps.items()) + "\n# Injection sensitivity\n"


def _payload(path, fingerprint: str) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.Table.from_pandas(pd.DataFrame({"x": [1]}), preserve_index=False)
    meta = {**(table.schema.metadata or {}), b"fis_fingerprint": fingerprint.encode()}
    pq.write_table(table.replace_schema_metadata(meta), path)


def test_a_missing_stamped_payload_is_not_fresh(tmp_path):
    """A report whose parquet is gone must not certify itself as fresh."""
    state, detail = report.freshness(_report_text(), results=tmp_path / "phase2.parquet")
    assert state == "payload" and "missing" in detail


def test_a_swapped_payload_is_not_fresh(tmp_path):
    _payload(tmp_path / "phase2.parquet", "someone-elses-results")
    state, _ = report.freshness(_report_text(), results=tmp_path / "phase2.parquet")
    assert state == "payload"


def test_a_matching_payload_is_fresh(tmp_path):
    _payload(tmp_path / "phase2.parquet", "abc")
    state, _ = report.freshness(_report_text(), results=tmp_path / "phase2.parquet")
    assert state == "fresh"


def test_the_payload_check_stands_down_without_a_warehouse(tmp_path):
    """No data directory: code stamps only, since CI cannot tell deleted from
    never-fetched."""
    state, _ = report.freshness(_report_text(), results=tmp_path / "no-dir" / "phase2.parquet")
    assert state == "fresh"


def test_a_runtime_change_is_its_own_state():
    text = _report_text(**{report.RUNTIME_STAMP: "python=0.0.0,numpy=0"})
    state, detail = report.freshness(text)
    assert state == "runtime" and "environment" in detail


def test_the_reworded_banner_still_clears():
    body = report.STALE_BANNER + "\nReal prose.\n"
    cleared = report._clear_banner(body)
    assert report.STALE_MARKER not in cleared and "Real prose." in cleared


def test_the_banner_states_the_antecedent_not_the_conclusion():
    """A source hash knows the code changed, not that a number moved."""
    assert "may no longer describe" in report.STALE_BANNER
    assert "They do not describe" not in report.STALE_BANNER


# ------------------------------------------------- AUC wording (B5) --


def test_the_withdrawn_auc_claims_stay_withdrawn():
    """The statistic is a cohort two-sample comparison, threshold-free at a
    specified dose: never "paired", never "dose-free"."""
    for module in (injection_test, report):
        src = inspect.getsource(module)
        for banned in ("It is paired", "PAIRED against", "dose-free"):
            assert banned not in src, f"{module.__name__} still says {banned!r}"
    assert "two-sample" in inspect.getsource(injection_test._auc)


# ------------------------------------------------- clean-trained fits (A1) --


def _mart_like(n_players: int = 4, n_matches: int = 8) -> pd.DataFrame:
    """A synthetic mart slice that survives prepare() and residuals(): one
    position, every player over the appearance floor, counts self-consistent."""
    rng = np.random.default_rng(11)
    rows = []
    for p in range(n_players):
        for m in range(n_matches):
            passes_with = int(rng.integers(20, 40))
            completed = int(rng.integers(10, passes_with + 1))
            defensive = int(rng.integers(6, 18))
            with_outcome = int(rng.integers(4, defensive + 1))
            successful = int(rng.integers(1, with_outcome + 1))
            touches = int(rng.integers(3, 15))
            rows.append(
                {
                    "player_id": p,
                    "match_id": f"match-{p}-{m}",
                    "position_code": "DF",
                    "minutes_played": 90.0,
                    "regulation_minutes": 90.0,
                    "match_has_missing_substitution": False,
                    "has_mirrored_positions": False,
                    "is_eligible": True,
                    "passes": passes_with + 2,
                    "passes_with_outcome": passes_with,
                    "passes_completed": completed,
                    "pass_completion_pct": round(100.0 * completed / passes_with, 2),
                    "defensive_actions": defensive,
                    "defensive_actions_with_outcome": with_outcome,
                    "defensive_actions_successful": successful,
                    "defensive_action_success_pct": round(100.0 * successful / with_outcome, 2),
                    "defensive_actions_in_defensive_third": min(defensive, touches),
                    "touches_in_defensive_third": touches,
                    "sum_start_x_in_defensive_third": touches * 0.2,
                    "attempts_with_position": passes_with + touches,
                    "mean_action_x": round(float(rng.uniform(0.3, 0.6)), 4),
                    "actions": passes_with + defensive + 5,
                }
            )
    return pd.DataFrame(rows)


def test_heldout_target_scores_ignore_sibling_residuals_of_perturbed_passes(monkeypatch):
    """Heldout residual fits must train on the CLEAN frame, so poisoning every
    sibling row in the perturbed passes must change no target score."""
    raw = _mart_like()
    frame = baseline.prepare(raw)
    scored, _ = baseline.residuals(frame)
    scored = scored[scored["is_scoreable"]]
    census = heldout.score_all(scored, jobs=1)
    mechanisms = {"defensive_success": injection_test.MECHANISMS["defensive_success"]}

    def campaign():
        return injection_test.run(
            scored,
            raw,
            census,
            severities=(1.0,),
            mechanisms=mechanisms,
            design="heldout",
            jobs=1,
        )

    honest = campaign()

    real = baseline.residuals
    calls = {"n": 0}
    targets = {(p, m) for p, m, _ in injection_test.select_targets(scored, census)}

    def poisoned(frame, **kwargs):
        out, fitted = real(frame, **kwargs)
        calls["n"] += 1
        if calls["n"] > 1:  # every pass after the clean one
            keyed = list(zip(out["player_id"], out["match_id"]))
            sibling = ~pd.Series([k in targets for k in keyed], index=out.index)
            out.loc[sibling, [f"z_{m}" for m in baseline.METRICS]] += 100.0
        return out, fitted

    monkeypatch.setattr(injection_test.baseline, "residuals", poisoned)
    blind = campaign()
    assert calls["n"] > 1, "the poison never ran, so this test checked nothing"
    for column in ("clean", "after"):
        pd.testing.assert_series_equal(honest[column], blind[column], check_exact=True)


def test_the_clean_pass_returns_fits_to_the_parent():
    """Worker mutations die with the worker, so the clean pass must RETURN the
    map. Pinned at source: the map is a closure a test cannot reach."""
    src = inspect.getsource(injection_test.run)
    assert "held_fits.update(built)" in src, "fits must come back via return values"
    assert "held_fits[(player_id, mid)]" in src, "later passes must look up, not rebuild"
    assert 'assert held_fits, "heldout clean pass returned no fits' in src


# ------------------------------------------------- feature_sweep repair (C1) --


def test_feature_sweep_assembles_its_block_through_the_real_call_site(monkeypatch):
    """Scoring is stubbed, the call site is not, so a wrong signature fails
    here -- which is what no test reached when the call was broken."""
    from fis.analysis import feature_sweep

    raw = _mart_like()
    frame = baseline.prepare(raw)
    scored, _ = baseline.residuals(frame)
    scored = scored[scored["is_scoreable"]]

    census = pd.DataFrame(
        {
            "player_id": scored["player_id"].to_numpy(),
            "match_id": scored["match_id"].to_numpy(),
            "mahalanobis": 1.0,
            "mahalanobis_res": 1.0,
            "forest": 1.0,
            "forest_norm": 1.0,
            "forest_res": 1.0,
            "forest_res_norm": 1.0,
        }
    )
    results = pd.DataFrame(
        {
            "player_id": [0],
            "match_id": ["match-0-0"],
            "position_code": ["DF"],
            "scorer": ["mahalanobis"],
            "mechanism": ["defensive_success"],
            "severity": [1.0],
            "is_target": [True],
            "bit": [True],
            "clipped": [False],
            "achieved": [1.0],
            "achieved_z": [1.0],
            "clean": [0.0],
            "after": [9.0],
        }
    )
    monkeypatch.setattr(feature_sweep.heldout, "score_all", lambda *a, **k: census)
    monkeypatch.setattr(feature_sweep.injection_test, "run", lambda *a, **k: results)

    out = feature_sweep.sweep(scored, raw, {"all": list(baseline.METRICS)}, severities=(1.0,))
    assert "=== all" in out and "Calibration" not in out
    assert "defensive_success" in out, "the per-mechanism block never assembled"


def test_the_headline_makes_no_forest_claim_without_forest_rows():
    """A forest-free run must not claim a forest result, and the AUC sentence
    must not dangle off the claim it followed."""
    cells = pd.DataFrame(
        {
            "mechanism": ["pass_completion", "correlated"] * 2,
            "severity": [3.0] * 4,
            "tally": ["max", "max", "mahalanobis", "mahalanobis"],
            "n": [25] * 4,
            "recovered": [3, 3, 1, 6],
            "recovery": [0.12, 0.12, 0.04, 0.24],
            "auc": [0.946, 0.915, 0.878, 0.850],
        }
    )
    out = report.headline_summary(cells, 0.01, ("correlated", 3.0))
    assert "forest" not in out.lower(), "no forest row, so no forest claim"
    assert "statement about the bar" not in out, "the clause dangles without its antecedent"
    assert "AUC ranks the whole distribution" in out, "the disagreement still has to be reported"


def test_the_experiment_note_maps_five_hidden_variables_over_four_channels():
    """Five, not four: relocate_upfield moves the defensive-third touch count
    and the action x-mass together, and neither can move alone."""
    note = report.experiment_note()
    assert "Five hidden variables over four channels" in note
    assert "only move together" in note
    for variable in (
        "defensive_actions",
        "touches_in_defensive_third",
        "sum_start_x_in_defensive_third",
        "defensive_actions_successful",
        "passes_completed",
    ):
        assert variable in note, f"{variable} missing from the map"
    assert note.count("| `relocate_upfield` |") == 1, "the pair belongs to ONE channel"


# ------------------------------------------------- collateral section --


def _collateral_stats(**over):
    return {
        "collateral_measurable": True,
        "severity": 3.0,
        "mechanism": "correlated",
        "others_before": 0.0105,
        "others_after": 0.0097,
        "n_other": 41853,
        "contaminated": 41000,
        "shift_sd": -0.0147,
        **over,
    }


def test_every_scorer_is_labelled_not_just_the_first_row():
    """Labelling on row index blanked every scorer after the first, so a
    24-row table named one of seven."""
    stats = pd.DataFrame(
        [_collateral_stats(tally="forest", severity=k) for k in (1.0, 3.0)]
        + [_collateral_stats(tally="max", severity=k) for k in (1.0, 3.0)]
    )
    out = report.collateral_section(stats, 0.01)
    assert "**forest**" in out and "**max**" in out, "each scorer must be named once"
    assert out.count("**forest**") == 1, "and only on its first row"


def test_the_direction_claim_counts_cells_rather_than_naming_scorers():
    """The claim is about how many conditions move down, not which scorers are
    exceptions -- the earlier wording listed 5 of 7 as exceptions to 'every'."""
    stats = pd.DataFrame(
        [
            _collateral_stats(tally="max", severity=1.0, shift_sd=+0.002),
            _collateral_stats(tally="max", severity=3.0, shift_sd=-0.01),
            _collateral_stats(tally="forest", severity=1.0, shift_sd=-0.02),
        ]
    )
    out = report.collateral_section(stats, 0.01)
    assert "downward in 2 of 3 conditions" in out
    assert "every scorer but" not in out


def test_an_empty_collateral_frame_says_so_rather_than_rendering_a_table():
    stats = pd.DataFrame([_collateral_stats(collateral_measurable=False)])
    assert "No collateral measured" in report.collateral_section(stats, 0.01)


def test_a_valueless_fis_marker_does_not_break_freshness():
    """HEADLINE_END shares the fis- prefix but carries no "=", and the stamp
    parser unpacked every such line into a pair."""
    text = _report_text() + f"\n{report.HEADLINE_END}\n\nprose\n"
    state, _ = report.freshness(text)
    assert state in {"fresh", "render", "analysis", "runtime", "payload"}


# ------------------------------------------------- publication gate (B3) --


def _args(**over):
    base = {
        "publish": True,
        "n": None,
        "forest": True,
        "design": "heldout",
        "seed": injection_test.SEED,
        "headline": report.PUBLICATION["headline"],
        "stale_ok": False,
        "collateral": [f"data/reports/{a}" for a in report.COLLATERAL_ARMS],
    }
    base.update(over)
    return argparse.Namespace(**base)


def test_the_publication_recipe_is_canonical():
    assert report.is_canonical(_args())


@pytest.mark.parametrize(
    ("what", "over"),
    [
        ("player cap", {"n": 50}),
        ("no forests", {"forest": False}),
        ("other design", {"design": "persistent"}),
        ("other seed", {"seed": 1}),
        # --headline drives the headline table AND both agreement matrices, so a
        # run under another one is a different report.
        ("other headline", {"headline": "remove_defensive:1.5"}),
        ("stale render", {"stale_ok": True}),
        ("no collateral", {"collateral": None}),
        ("one arm only", {"collateral": ["data/reports/collateral.parquet"]}),
        ("duplicate arm", {"collateral": ["data/reports/collateral.parquet"] * 2}),
        ("foreign arm", {"collateral": ["data/reports/something-else.parquet"]}),
        ("no --publish", {"publish": False}),
    ],
)
def test_anything_but_the_recipe_is_not_canonical(what, over):
    assert not report.is_canonical(_args(**over)), f"{what} must not be canonical"


def test_a_noncanonical_run_refuses_before_touching_the_warehouse(monkeypatch, tmp_path):
    """Behavioural, not classification: main() must return 2, leave the tracked
    report byte-identical, and never reach the mart -- the refusal was 35 lines
    after baseline.load(), so an invalid attempt residualised everything first."""
    tracked = Path(report.PUBLICATION["out"])
    before = tracked.read_bytes() if tracked.exists() else None

    def never(*a, **k):
        raise AssertionError("expensive work entered before the publication gate")

    monkeypatch.setattr(report.baseline, "load", never)
    monkeypatch.setattr(report.heldout, "score_all", never)
    monkeypatch.setattr(report.injection_test, "run", never)

    assert report.main(["--n", "25", "--out", str(tracked)]) == 2
    if before is not None:
        assert tracked.read_bytes() == before, "the tracked report was modified"


def test_canonical_looking_arguments_without_publish_cannot_publish(monkeypatch):
    """Recipe equality is content; --publish is authorisation. A diagnostic run
    that happens to match must not take publication side effects."""
    reports = Path("data/reports")
    args = _args(collateral=[str(reports / a) for a in report.COLLATERAL_ARMS], publish=False)
    assert not report.is_canonical(args)
    args.publish = True
    assert report.is_canonical(args), "the same recipe WITH --publish is canonical"


def test_apply_publication_produces_a_canonical_namespace(tmp_path):
    """The two helpers read one specification, so applying it must satisfy the
    comparison -- otherwise the spec has drifted from the gate again."""
    args = argparse.Namespace(publish=True)
    report.apply_publication(args, tmp_path)
    assert report.is_canonical(args)
    for field in report.PUBLICATION_FIELDS:
        assert getattr(args, field) == report.PUBLICATION[field]


def test_the_hook_invokes_exactly_the_publication_recipe(monkeypatch, tmp_path):
    """Behavioural: intercept the subprocess boundary and read the real argv,
    rather than grepping the script for a flag."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("report_freshness", "scripts/report_freshness.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)

    seen = {}

    class Done:
        returncode = 0

    def record(argv, **kw):
        seen["argv"] = argv
        return Done()

    monkeypatch.setattr(hook, "REPORT", tmp_path / "phase2.md")
    (tmp_path / "phase2.md").write_text("stub")
    monkeypatch.setattr(hook, "_reexec_in_project_env", lambda: None)
    monkeypatch.setattr(hook.subprocess, "run", record)
    monkeypatch.setattr(
        "fis.analysis.report.freshness", lambda *a, **k: ("render", "only the renderer changed")
    )
    hook.main()
    assert seen["argv"][1:] == ["-m", "fis.analysis.report", "--publish"], (
        f"the hook must run the publication recipe, got {seen['argv'][1:]}"
    )


# ------------------------------------------------- collateral provenance (B2) --


def test_every_collateral_arm_has_a_declared_recipe():
    assert set(report.COLLATERAL_ARMS) == {"collateral.parquet", "collateral-forest.parquet"}
    for arm in report.COLLATERAL_ARMS:
        assert "forest" in report.COLLATERAL_ARMS[arm], f"{arm} must declare its forest setting"


def test_the_two_arms_stamp_differently():
    """Swapping the arms must be refused, which needs their configs to differ."""
    raw = _raw()
    a, _ = report.collateral_config("collateral.parquet", raw)
    b, _ = report.collateral_config("collateral-forest.parquet", raw)
    assert a != b


def test_a_report_declaring_missing_collateral_is_not_fresh(tmp_path):
    _payload(tmp_path / "phase2.parquet", "abc")
    text = _report_text() + f"\n<!-- {report.COLLATERAL_STAMP}=collateral.parquet:zzz -->\n"
    state, detail = report.freshness(text, results=tmp_path / "phase2.parquet")
    assert state == "payload" and "collateral" in detail


def test_a_report_declaring_swapped_collateral_is_not_fresh(tmp_path):
    _payload(tmp_path / "phase2.parquet", "abc")
    _payload(tmp_path / "collateral.parquet", "a-different-arm")
    text = _report_text() + f"\n<!-- {report.COLLATERAL_STAMP}=collateral.parquet:zzz -->\n"
    state, _ = report.freshness(text, results=tmp_path / "phase2.parquet")
    assert state == "payload"


def test_matching_collateral_is_fresh(tmp_path):
    _payload(tmp_path / "phase2.parquet", "abc")
    _payload(tmp_path / "collateral.parquet", "zzz")
    text = _report_text() + f"\n<!-- {report.COLLATERAL_STAMP}=collateral.parquet:zzz -->\n"
    state, _ = report.freshness(text, results=tmp_path / "phase2.parquet")
    assert state == "fresh"


# ------------------------------------------------- the hook (B1) --


def test_the_hook_re_renders_through_the_publication_recipe():
    """The hook spelled the recipe out itself, omitted --results, and so
    resolved a payload path that does not exist -- turning a seconds-long
    re-render into a full campaign that also dropped collateral."""
    source = pathlib.Path("scripts/report_freshness.py").read_text()
    assert '"--publish"' in source, "the hook must use the one recipe"
    assert '"--census"' not in source, "spelling the recipe out again is how it drifted"
    assert "85 min" not in source, "the withdrawn timing must not be quoted"
