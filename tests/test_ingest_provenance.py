"""The ingest must notice when its own output is out of date.

Skipping matches whose parquet already exists is what makes an interrupted run
resumable. It is also how a pipeline fix silently fails to reach the data: the
files are there, so nothing is re-ingested. These tests pin the distinction --
same pipeline, skip; different pipeline, redo.
"""

from __future__ import annotations

import json

from fis.ingest.wyscout import INGEST_STAMP, provenance, stale


def test_first_run_is_not_stale(tmp_path):
    """No stamp and no output is a first run, not a stale one."""
    assert stale(tmp_path, provenance()) == []


def test_output_without_a_stamp_is_stale(tmp_path):
    """Parquet from before provenance existed cannot be vouched for."""
    (tmp_path / "events_1694390.parquet").touch()
    assert stale(tmp_path, provenance()) == ["produced before provenance was recorded"]


def test_matching_stamp_allows_skipping(tmp_path):
    current = provenance()
    (tmp_path / INGEST_STAMP).write_text(json.dumps(current))
    (tmp_path / "events_1694390.parquet").touch()
    assert stale(tmp_path, current) == []


def test_each_input_is_watched(tmp_path):
    """Data, parser and our code each invalidate the output on their own."""
    current = provenance()
    for key in ("dataset_commit", "kloppy", "code"):
        (tmp_path / INGEST_STAMP).write_text(json.dumps({**current, key: "different"}))
        reasons = stale(tmp_path, current)
        assert len(reasons) == 1
        assert reasons[0].startswith(f"{key}: different -> ")


def test_code_hash_covers_the_workarounds():
    """A change to kloppy_workarounds must change the fingerprint.

    That module decides what 87% of matches deserialise to, so an edit there is
    exactly the case this mechanism exists for.
    """
    from pathlib import Path

    from fis.ingest import kloppy_workarounds, wyscout

    before = provenance()["code"]
    path = Path(kloppy_workarounds.__file__)
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n# provenance probe\n")
        assert wyscout.provenance()["code"] != before
    finally:
        path.write_bytes(original)
