"""The figshare payload is verified as consumed, not as downloaded.

The download md5s cannot: matches.zip is deleted after extraction and repaired
files are rewritten. The manifest hashes what is on disk, exact-set, because
dbt discovers these files by glob.
"""

from __future__ import annotations

import json

import pytest

from fis.data import figshare


@pytest.fixture
def payload(tmp_path):
    """A stamped directory the manifest declares intact."""
    (tmp_path / "matches_England.json").write_text('[{"wyId": 1}]')
    (tmp_path / "referees.json").write_text('[{"wyId": 2}]')
    (tmp_path / "referees.json.as-published").write_text('[{"wyId": 2},')
    stamp = figshare._expected_stamp()
    stamp["repaired"] = {"referees.json": "truncated upstream; recovered 1 records"}
    stamp["manifest"] = figshare._manifest(tmp_path)
    (tmp_path / figshare.STAMP_NAME).write_text(json.dumps(stamp))
    return tmp_path


def test_an_untouched_payload_passes_without_network(payload):
    assert figshare.verify(payload) == []


def test_an_altered_extracted_file_fails(payload):
    (payload / "matches_England.json").write_text('[{"wyId": 1}, {"wyId": 99}]')
    assert any("altered: matches_England.json" in p for p in figshare.verify(payload))


def test_an_altered_repaired_live_file_fails(payload):
    """Ingestion reads the live file, not the preserved sibling."""
    (payload / "referees.json").write_text("[]")
    assert any("altered: referees.json" in p for p in figshare.verify(payload))


def test_a_truncated_file_fails_on_size_alone(payload):
    original = (payload / "matches_England.json").read_bytes()
    (payload / "matches_England.json").write_bytes(original[:-3])
    assert any("altered" in p for p in figshare.verify(payload))


def test_a_deleted_file_fails(payload):
    (payload / "referees.json").unlink()
    assert any("missing: referees.json" in p for p in figshare.verify(payload))


def test_an_unmanifested_extra_fails(payload):
    """dbt unions matches_*.json, so an extra would silently join raw.matches."""
    (payload / "matches_zz.json").write_text("[]")
    assert any("not in the manifest: matches_zz.json" in p for p in figshare.verify(payload))


def test_a_stamp_without_a_manifest_is_not_current(payload):
    stamp = json.loads((payload / figshare.STAMP_NAME).read_text())
    del stamp["manifest"]
    (payload / figshare.STAMP_NAME).write_text(json.dumps(stamp))
    assert any("no payload manifest" in p for p in figshare.verify(payload))


def test_a_drifted_pin_fails_even_with_an_intact_manifest(payload):
    stamp = json.loads((payload / figshare.STAMP_NAME).read_text())
    stamp["files"]["players.json"]["md5"] = "0" * 32
    (payload / figshare.STAMP_NAME).write_text(json.dumps(stamp))
    assert any("no longer matches the pin" in p for p in figshare.verify(payload))


def test_a_repair_leaves_nothing_a_source_glob_matches(tmp_path):
    """A repair must leave no sibling that a source glob would union in."""
    (tmp_path / "matches_England.json").write_text('[{"wyId": 1}, {"wyId": 2},')
    repaired = figshare._repair_payload(tmp_path)
    assert "matches_England.json" in repaired
    globbed = {p.name for p in tmp_path.glob("matches_*.json")}
    assert globbed == {"matches_England.json"}, "the sibling leaked into the source glob"
    assert (tmp_path / "matches_England.json.as-published").exists()
    assert json.loads((tmp_path / "matches_England.json").read_text()) == [
        {"wyId": 1},
        {"wyId": 2},
    ]


def test_the_manifest_covers_siblings_and_skips_hidden_files(payload):
    manifest = json.loads((payload / figshare.STAMP_NAME).read_text())["manifest"]
    assert "referees.json.as-published" in manifest
    assert figshare.STAMP_NAME not in manifest


def test_a_stamped_checkout_without_match_files_is_not_fetched(tmp_path, monkeypatch):
    """Existence-only, not stamp-only: a gutted checkout is not fetched."""
    from fis.data import wyscout

    root = tmp_path / "wyscout"
    files = root / wyscout.WANTED_SUBDIR / "files"
    files.mkdir(parents=True)
    (root / wyscout.STAMP_NAME).write_text(json.dumps({"commit": wyscout.DATASET_COMMIT}))
    assert not wyscout.is_fetched(root), "a stamp over no match files is not a fetch"

    (files / "1.json").write_text("[]")
    assert wyscout.is_fetched(root)
