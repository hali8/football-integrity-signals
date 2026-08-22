"""Canary tests for the kloppy/data workarounds.

These are written to FAIL when they become unnecessary. Because the repairs run
only after a load fails, an upstream fix makes them silently unreachable -- so
without these tests the workarounds would outlive their purpose indefinitely.

If ``test_defect_still_reproduces`` fails, that is good news: kloppy fixed the
bug. Delete the corresponding repair from fis.ingest.kloppy_workarounds.
"""

from __future__ import annotations

import json

import pytest
from kloppy import wyscout

from fis.data.wyscout import match_files
from fis.ingest.kloppy_workarounds import (
    EXTRA_TIME_PERIOD,
    NULL_ROSTER_ENTRY,
    PERIOD_IDS,
    SHOT_AS_FINAL_EVENT,
    TESTED_KLOPPY_VERSION,
    load_match,
)

# One representative match per defect, and one that needs nothing.
KNOWN = {
    EXTRA_TIME_PERIOD: "1694426",
    SHOT_AS_FINAL_EVENT: "1694433",
    NULL_ROSTER_ENTRY: "2499738",
}
CLEAN_MATCH = "1694390"

#: Counts observed across the full dataset when the workarounds were written.
EXPECTED_COUNTS = {EXTRA_TIME_PERIOD: 10, SHOT_AS_FINAL_EVENT: 6, NULL_ROSTER_ENTRY: 22}


@pytest.fixture(scope="session")
def files() -> dict[str, object]:
    paths = {p.stem: p for p in match_files()}
    if not paths:
        pytest.skip("dataset not downloaded; run fis-fetch-wyscout")
    return paths


def test_period_ids_match_kloppy():
    """Our period ordinals must agree with kloppy's canonical mapping.

    If this fails, kloppy changed what E1/E2/P mean and PERIOD_IDS must follow --
    otherwise a fixed V2 deserializer would produce different period_id values
    than we do, silently changing the parquet.
    """
    v3 = pytest.importorskip(
        "kloppy.infra.serializers.event.wyscout.deserializer_v3",
        reason="kloppy moved deserializer_v3; re-verify PERIOD_IDS by hand",
    )
    parse = getattr(v3, "_parse_period_id", None)
    if parse is None:
        pytest.fail("kloppy._parse_period_id is gone; re-verify PERIOD_IDS by hand")

    assert parse("1H") == 1
    assert parse("2H") == 2
    for code, expected in PERIOD_IDS.items():
        assert parse(code) == expected, f"kloppy now maps {code} to {parse(code)}, not {expected}"


@pytest.mark.parametrize("defect", sorted(KNOWN))
def test_defect_still_reproduces(defect, files):
    """A plain kloppy load must still fail -- otherwise the repair is obsolete."""
    path = files[KNOWN[defect]]
    with pytest.raises((TypeError, ValueError)):
        wyscout.load(event_data=str(path), data_version="V2")


@pytest.mark.parametrize("defect", sorted(KNOWN))
def test_workaround_repairs_it(defect, files):
    """load_match recovers the match, and reports exactly which repair it needed."""
    dataset, applied = load_match(files[KNOWN[defect]])
    assert defect in applied
    assert len(dataset.events) > 0


def test_clean_match_needs_no_repair(files):
    """The common path must be untouched: no JSON rewrite, no monkeypatch."""
    dataset, applied = load_match(files[CLEAN_MATCH])
    assert applied == []
    assert len(dataset.events) > 0


def test_extra_time_periods_are_ordered(files):
    """Extra time and penalties become periods 3, 4 and 5, in ascending order."""
    dataset, applied = load_match(files[KNOWN[EXTRA_TIME_PERIOD]])
    assert EXTRA_TIME_PERIOD in applied
    ids = [p.id for p in dataset.metadata.periods]
    assert ids == [1, 2, 3, 4, 5]
    assert ids == sorted(ids)


def test_final_shot_result_comes_from_its_own_tags(files):
    """The sentinel must not alter a shot's outcome, only its keeper qualifier.

    Tag 1802 is Wyscout's "not accurate", so the result must be OFF_TARGET or
    POST -- decided by the shot's tags, never by the absent next event.
    """
    path = files[KNOWN[SHOT_AS_FINAL_EVENT]]
    raw_last = json.loads(path.read_text())["events"][-1]
    assert 1802 in [t["id"] for t in raw_last["tags"]]

    dataset, applied = load_match(path)
    assert SHOT_AS_FINAL_EVENT in applied
    assert str(dataset.events[-1].result) in {"OFF_TARGET", "POST"}


def test_unrecognised_errors_are_not_swallowed(files, monkeypatch):
    """An unfamiliar failure must propagate, not trigger a speculative repair."""
    sentinel = RuntimeError("something new and unrecognised")

    def boom(*_args, **_kwargs):
        raise sentinel

    monkeypatch.setattr(wyscout, "load", boom)
    with pytest.raises(RuntimeError) as excinfo:
        load_match(files[CLEAN_MATCH])
    assert excinfo.value is sentinel


@pytest.mark.slow
def test_whole_dataset_loads(files):
    """Every match must load, and the repair counts must match what we documented."""
    counts: dict[str, int] = {}
    for path in files.values():
        _, applied = load_match(path)
        for name in applied:
            counts[name] = counts.get(name, 0) + 1
    assert counts == EXPECTED_COUNTS, (
        f"repair counts changed (kloppy {TESTED_KLOPPY_VERSION} expected "
        f"{EXPECTED_COUNTS}, got {counts})"
    )
