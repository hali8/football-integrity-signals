"""Things that silently changed the answer without changing the guard.

The census stamp must move when ANY input to ``score_all`` moves: hashing column
sums, then hashing only the metric columns, then omitting the call's own
settings each left a way to reuse a cache that no longer described the data.

The clearance successor must be the next SOURCE event, ordered by the source
array position. kloppy inserts synthesized interceptions beside their host, so a
window over every row puts a child between a clearance and the ball leaving
play; and event ids are not monotonic enough to break ties on.
"""

from __future__ import annotations

import inspect
import json

import duckdb
import numpy as np
import pandas as pd
import pytest

from fis.analysis import baseline, heldout, injection_test
from fis.ingest import wyscout


def _scored(n: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    columns = list(baseline.METRICS) + list(heldout.residual_columns(baseline.METRICS))
    frame = pd.DataFrame({c: rng.normal(size=n) for c in columns})
    frame["player_id"] = np.arange(n) % 8
    frame["match_id"] = np.arange(n)
    frame["position_code"] = ["DF", "MD", "FW", "GK"] * (n // 4)
    return frame


#: Mirrors raw_sequence in int_player_match_actions.sql. The population
#: crosstabs after a rebuild are the real check; this pins the mechanism.
_RAW_SEQUENCE = """
select event_id,
       lead(event_type) over w as next_event_type,
       lead(set_piece_type, 2) over w as restart_type
from events
where parent_event_id is null
window w as (
    partition by match_id, period_id
    order by seconds_into_period, source_index
)
"""


def _sequence(events: pd.DataFrame) -> pd.DataFrame:
    con = duckdb.connect()
    con.register("events", events)
    return con.sql(_RAW_SEQUENCE).df().set_index("event_id")


def test_a_synthesized_child_does_not_displace_the_clearance_successor():
    """clearance -> synthesized interception -> ball out -> corner. Windowed over
    every row the clearance sees INTERCEPTION then BALL_OUT and never reaches the
    restart, so a conceded corner reads as a successful clearance."""
    events = pd.DataFrame(
        {
            "event_id": ["100", "interception-100", "101", "102"],
            "parent_event_id": [None, "100", None, None],
            "match_id": ["m"] * 4,
            "period_id": [1] * 4,
            "seconds_into_period": [10.0, 10.0, 11.0, 12.0],
            "source_index": [0, 1, 2, 3],
            "event_type": ["CLEARANCE", "INTERCEPTION", "BALL_OUT", "PASS"],
            "set_piece_type": [None, None, None, "CORNER_KICK"],
        }
    )
    row = _sequence(events).loc["100"]
    assert row.next_event_type == "BALL_OUT", "the synthesized child must not be the successor"
    assert row.restart_type == "CORNER_KICK", "the restart must be reachable two offsets on"


def test_source_order_wins_when_the_event_ids_disagree_with_it():
    """Event ids are NOT reliably monotonic in source order -- a scan of all
    1,941 matches found equal-time pairs the numeric id reverses. The array
    position decides, so this pins the case where the two disagree."""
    events = pd.DataFrame(
        {
            # ids descend while the source order ascends: ordering on either the
            # numeric id or the raw string would reverse this pair.
            "event_id": ["500", "400"],
            "parent_event_id": [None, None],
            "match_id": ["m"] * 2,
            "period_id": [1] * 2,
            "seconds_into_period": [10.0, 10.0],
            "source_index": [0, 1],
            "event_type": ["CLEARANCE", "BALL_OUT"],
            "set_piece_type": [None, None],
        }
    )
    assert _sequence(events).loc["500"].next_event_type == "BALL_OUT"


def test_ingest_records_the_source_array_position(tmp_path):
    """A SQL test cannot see an ingest that fills source_index wrongly, so the
    array positions are pinned where they are read."""
    events = [
        {"id": 500, "tags": [{"id": 1801}], "subEventId": 12},
        {"id": 400, "tags": [], "subEventId": 11},
        {"id": 900, "tags": [], "subEventId": ""},
    ]
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"events": events}))
    fields = wyscout._raw_fields(path)
    assert [fields[k][2] for k in ("500", "400", "900")] == [0, 1, 2], "array order, not id order"
    assert fields["500"][0] == [1801] and fields["500"][1] == 12
    assert fields["900"][1] is None, "a blank subEventId is absent, not zero"


def _perturbations(frame: pd.DataFrame):
    """Every input a cached census depends on, one change each.

    The list IS the contract. Enumerating inputs one test at a time is what
    failed twice: position_code and match_id were missing from the hash, then
    the injection seed was missing from the results stamp, and each was found by
    review rather than by the suite.
    """
    columns = list(baseline.METRICS) + list(heldout.residual_columns(baseline.METRICS))
    for column in ("player_id", "match_id", "position_code"):
        moved = frame.copy()
        numeric = pd.api.types.is_numeric_dtype(moved[column])
        moved.loc[0, column] = 9_999 if numeric else "ZZ"
        yield f"frame: {column}", moved, ""
    for column in columns:
        moved = frame.copy()
        moved.loc[0, column] += 1.0
        yield f"frame: {column}", moved, ""
    swapped = frame.copy()
    swapped.iloc[[0, 1]] = swapped.iloc[[1, 0]].to_numpy()
    yield "frame: row order", swapped, ""
    offset = frame.copy()
    offset.loc[0, columns[0]] += 1.0
    offset.loc[1, columns[0]] -= 1.0
    yield "frame: offsetting edits", offset, ""

    base = heldout.scoring_config()
    yield "config: forest", frame, heldout.scoring_config(forest=True)
    yield "config: limit_players", frame, heldout.scoring_config(limit_players=50)
    yield "config: metrics", frame, heldout.scoring_config(metrics=list(baseline.METRICS)[:-1])
    yield (
        "config: metric order",
        frame,
        heldout.scoring_config(metrics=list(reversed(baseline.METRICS))),
    )
    yield "config: seed", frame, heldout.results_config(base, 7)


@pytest.mark.parametrize(
    ("what", "moved", "config"),
    [pytest.param(*case[:1], *case[1:], id=case[0]) for case in _perturbations(_scored())],
)
def test_changing_any_scoring_input_changes_the_stamp(what, moved, config):
    """A cached frame is reused if and only if every input that can change it is
    unchanged. Swept rather than enumerated, so a new input is covered the day
    it is added to the list above."""
    base = heldout.fingerprint(_scored(), config=heldout.scoring_config())
    assert heldout.fingerprint(moved, config=config) != base, f"{what} left the stamp unmoved"


def test_an_untouched_frame_keeps_its_stamp():
    """The other half of iff: identical inputs must still hit the cache."""
    frame = _scored()
    settings = heldout.scoring_config()
    assert heldout.fingerprint(frame.copy(), config=settings) == heldout.fingerprint(
        frame, config=settings
    )


def test_a_stamped_frame_is_refused_under_a_different_configuration(tmp_path):
    """The sweep covers the hash; this covers the guard that reads it."""
    frame = _scored()
    cached = pd.DataFrame({"player_id": frame.player_id, "mahalanobis": 1.0})
    path = tmp_path / "census.parquet"
    heldout.write_census(path, cached, frame, config=heldout.scoring_config(forest=True))
    with pytest.raises(ValueError, match="different inputs"):
        heldout.read_census(path, frame, config=heldout.scoring_config(forest=False))
    assert len(heldout.read_census(path, frame, config=heldout.scoring_config(forest=True))) == len(
        cached
    )


def test_every_scoring_parameter_is_accounted_for():
    """The sweep only covers inputs someone remembered to list. This fails when
    a parameter is ADDED to score_all() or run() without being classified, which
    is the shape of both omissions found in review."""
    stamped = {"metrics", "forest", "limit_players"}
    # The frame is hashed directly; jobs is verified byte-identical at every
    # setting; the rest are frames or design constants covered by the code hash.
    otherwise = {"scored", "jobs"}
    found = set(inspect.signature(heldout.score_all).parameters)
    assert found == stamped | otherwise, (
        f"score_all's parameters changed: {found ^ (stamped | otherwise)}. Add it to "
        "scoring_config() and to `stamped`, or to `otherwise` with the reason."
    )

    run_stamped = {"seed", "forest", "metrics", "design", "scorers"}
    run_otherwise = {
        "scored",
        "raw",
        "census",
        "jobs",
        "severities",
        "mechanisms",
        "compositions",
        "progress",  # prints only; cannot reach a number
    }
    found = set(inspect.signature(injection_test.run).parameters)
    assert found == run_stamped | run_otherwise, (
        f"injection_test.run's parameters changed: {found ^ (run_stamped | run_otherwise)}. "
        "Add it to results_config() and to `run_stamped`, or to `run_otherwise`."
    )


def test_the_stale_banner_clears_however_it_was_worded():
    """Matching the generated string exactly meant a hand-edited banner never
    cleared, so a warning outlived the re-run that answered it."""
    from fis.analysis import report

    edited = (
        "## Output / analysis summary\n\n"
        "> **⚠ These numbers are stale.** The gate has since been removed, so the\n"
        "figures below do not describe the current detector.\n\n"
        "Real prose that must survive.\n"
    )
    cleared = report._clear_banner(edited)
    assert report.STALE_MARKER not in cleared
    assert "Real prose that must survive." in cleared
    assert "\n\n\n" not in cleared, "no gap left where the banner was"
    # Idempotent, and a README without one is returned untouched.
    assert report._clear_banner(cleared) == cleared


def test_the_readme_summary_is_written_from_the_render():
    """The numbers a reader sees in the README are LIFTED from the report, not
    retyped -- hand-copying is how a wrong figure reached a published summary."""
    from fis.analysis import report

    readme = (
        "Author's prose above.\n\n"
        f"{report.SUMMARY_OPEN}\n\nstale hand-typed numbers\n\n{report.SUMMARY_CLOSE}\n\n"
        "Author's prose below.\n"
    )
    rendered = (
        "# Injection sensitivity\n\n## Headline\n\n"
        "| | single | coordinated |\n|---|---:|---:|\n| forest | 1/2 (50.0%) | 3/4 (75.0%) |\n\n"
        "The forests win on the coordinated one.\n\nCalibration: every bar flags 1.00%.\n"
        "\n<details>\n<summary><b>DIRECT</b></summary>\n\ndetection grids\n\n</details>\n"
    )
    scored = _scored()
    out = report._put_summary(readme, scored, rendered)
    assert "stale hand-typed numbers" not in out
    assert "| forest | 1/2 (50.0%) | 3/4 (75.0%) |" in out
    assert "The forests win on the coordinated one." in out
    assert "Calibration: every bar flags 1.00%." in out, "the calibration line travels with it"
    assert "detection grids" not in out, "the folds are the report's, not the README's"
    assert f"{len(scored):,} player-matches" in out
    assert out.startswith("Author's prose above.") and out.rstrip().endswith(
        "Author's prose below."
    )


def test_a_readme_without_markers_is_left_alone():
    from fis.analysis import report

    plain = "No markers here.\n"
    assert report._put_summary(plain, _scored(), "## Headline\nx\n```\n") == plain
