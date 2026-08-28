"""A rebuild must never leave the live parquet describing two parser versions.

Every test here pins one way that could happen: a partial run swapping itself
in, a limited run rewriting a slice of an already-stale set, or a failed
replacement emptying the live directory. The originals all reported success.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import signal
import subprocess
import sys
import textwrap

import pandas as pd
import pytest

from fis.ingest import wyscout
from fis.ingest.wyscout import INGEST_STAMP


def _parquet(directory, match_id: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"event_id": ["1"], "match_id": [match_id]}).to_parquet(
        directory / f"events_{match_id}.parquet", index=False
    )


def _args(**over) -> argparse.Namespace:
    base = {"fetch": False, "out": None, "limit": None, "force": False}
    return argparse.Namespace(**{**base, **over})


def test_a_limited_run_is_refused_while_the_set_is_stale(tmp_path, monkeypatch, capsys):
    """--limit rewrites a SLICE. Against a set written by another parser that
    leaves the rewritten matches current and the rest old, in one mart."""
    live = tmp_path / "parquet"
    _parquet(live, "1")
    (live / INGEST_STAMP).write_text(json.dumps({**wyscout.provenance(), "code": "older"}))
    monkeypatch.setattr(wyscout, "parquet_dir", lambda: live)
    monkeypatch.setattr(wyscout, "match_files", lambda: [tmp_path / "1.json", tmp_path / "2.json"])

    assert wyscout.run(_args(limit=1)) == 1
    assert "--limit cannot be combined with a stale parquet set" in capsys.readouterr().err
    # And the live set is exactly as it was.
    assert {p.name for p in live.glob("events_*.parquet")} == {"events_1.parquet"}


def test_a_failed_rebuild_leaves_the_live_set_untouched(tmp_path, monkeypatch):
    """One bad match in a full rebuild must not publish the other 1,940."""
    live = tmp_path / "parquet"
    _parquet(live, "old")
    monkeypatch.setattr(wyscout, "parquet_dir", lambda: live)
    monkeypatch.setattr(wyscout, "match_files", lambda: [tmp_path / "1.json", tmp_path / "2.json"])

    def ingest(match_id, path, out_dir):
        if match_id == "2":
            raise ValueError("unparseable")
        _parquet(out_dir, match_id)
        return out_dir / f"events_{match_id}.parquet", []

    monkeypatch.setattr(wyscout, "ingest_match", ingest)
    assert wyscout.run(_args(force=True)) == 1
    assert {p.name for p in live.glob("events_*.parquet")} == {"events_old.parquet"}
    assert not (live / INGEST_STAMP).exists(), "a failed rebuild must not stamp the live set"


def test_a_validated_rebuild_replaces_the_whole_directory(tmp_path, monkeypatch):
    """The success path: every match present, and the old set gone rather than
    merged with the new one."""
    live = tmp_path / "parquet"
    _parquet(live, "gone")
    monkeypatch.setattr(wyscout, "parquet_dir", lambda: live)
    monkeypatch.setattr(wyscout, "match_files", lambda: [tmp_path / "1.json", tmp_path / "2.json"])

    def ingest(match_id, path, out_dir):
        _parquet(out_dir, match_id)
        return out_dir / f"events_{match_id}.parquet", []

    monkeypatch.setattr(wyscout, "ingest_match", ingest)
    assert wyscout.run(_args(force=True)) == 0
    assert {p.name for p in live.glob("events_*.parquet")} == {
        "events_1.parquet",
        "events_2.parquet",
    }
    assert json.loads((live / INGEST_STAMP).read_text()) == wyscout.provenance()
    assert not (tmp_path / "parquet.staging").exists()


def test_an_incomplete_staged_set_is_refused_even_with_no_failures(tmp_path):
    """Validation is not just 'nothing raised': a match that never produced a
    file has to block the swap on its own."""
    staged = tmp_path / "staged"
    _parquet(staged, "1")
    (staged / INGEST_STAMP).write_text(json.dumps(wyscout.provenance()))
    expected = [tmp_path / "1.json", tmp_path / "2.json"]
    problem = wyscout._staged_problem(staged, expected, wyscout.provenance())
    assert "1 of 2 matches missing" in problem


def test_an_unreadable_staged_file_is_refused(tmp_path):
    staged = tmp_path / "staged"
    _parquet(staged, "1")
    (staged / "events_2.parquet").write_text("not parquet")
    (staged / INGEST_STAMP).write_text(json.dumps(wyscout.provenance()))
    expected = [tmp_path / "1.json", tmp_path / "2.json"]
    assert "unreadable" in wyscout._staged_problem(staged, expected, wyscout.provenance())


def test_a_staged_set_from_another_pipeline_is_refused(tmp_path):
    staged = tmp_path / "staged"
    _parquet(staged, "1")
    (staged / INGEST_STAMP).write_text(json.dumps({**wyscout.provenance(), "code": "other"}))
    assert "another pipeline" in wyscout._staged_problem(
        staged, [tmp_path / "1.json"], wyscout.provenance()
    )


def test_a_failed_swap_restores_the_previous_directory(tmp_path, monkeypatch):
    """If the second rename cannot complete, the live path must still hold the
    old set rather than nothing at all."""
    live = tmp_path / "parquet"
    staged = tmp_path / "parquet.staging"
    _parquet(live, "old")
    _parquet(staged, "new")

    real_rename = type(live).rename

    def rename(self, target):
        if self == staged:
            raise OSError("cross-device link")
        return real_rename(self, target)

    monkeypatch.setattr(type(live), "rename", rename)
    with pytest.raises(OSError):
        wyscout._swap(live, staged)
    assert {p.name for p in live.glob("events_*.parquet")} == {"events_old.parquet"}


def test_a_second_ingest_refuses_while_the_first_holds_the_guard(tmp_path):
    """.staging and .previous are fixed paths, so two runs would validate and
    promote each other's half-finished state."""
    live = tmp_path / "parquet"
    _parquet(live, "1")
    # Nesting is deliberate: the outer guard being HELD while the inner one is
    # attempted is exactly what this asserts, and flattening it hides that.
    with wyscout._single_writer(live):  # noqa: SIM117
        with pytest.raises(wyscout.Busy), wyscout._single_writer(live):
            pass


def test_the_guard_is_released_when_the_holder_dies(tmp_path):
    """An OS lock, not a lock file: a killed rebuild must not leave a stale
    guard blocking the recovery it just made necessary."""
    live = tmp_path / "parquet"
    _parquet(live, "1")
    holder = textwrap.dedent(f"""
        import os, pathlib, signal, time
        from fis.ingest import wyscout
        with wyscout._single_writer(pathlib.Path({str(live)!r})):
            os.kill(os.getpid(), signal.SIGKILL)
    """)
    env = {**os.environ, "PYTHONPATH": str(pathlib.Path(wyscout.__file__).parents[3])}
    subprocess.run([sys.executable, "-c", holder], env=env, capture_output=True, check=False)
    with wyscout._single_writer(live):
        pass  # acquires, or this raises


def test_a_leftover_beside_a_foreign_live_set_refuses_rather_than_guessing(tmp_path):
    """Same shape, but the live set is from another pipeline. Which one is wanted
    is not decidable here, so it must stop rather than delete either."""
    live = tmp_path / "parquet"
    previous = tmp_path / "parquet.previous"
    _parquet(live, "new")
    _parquet(previous, "old")
    (live / INGEST_STAMP).write_text(json.dumps({**wyscout.provenance(), "code": "older"}))
    with pytest.raises(wyscout.Unresolved, match="does not match this pipeline"):
        wyscout._recover(live, wyscout.provenance(), [tmp_path / "new.json"])
    assert previous.exists() and live.exists(), "neither may be removed"


# Four mutations: clear staging, the two renames, remove previous. Asserted
# from both sides below -- 6 here once made two cases pass without killing.
_MUTATIONS = 4


@pytest.mark.parametrize("kill_at", range(_MUTATIONS + 1))
def test_a_rebuild_interrupted_anywhere_recovers_to_one_complete_set(
    tmp_path, kill_at, monkeypatch
):
    """The invariant the whole replacement design exists for.

    Kill a rebuild at any filesystem mutation; running it again must leave the
    live directory holding EXACTLY the complete expected set -- never a mixture
    of two parser versions, and never a leftover that blocks the retry. Sweeping
    the kill point tests the property directly instead of enumerating states one
    bug report at a time.

    Each case asserts the child actually died where intended -- a kill that
    never fired proves nothing -- and the extra case must complete UNKILLED,
    pinning the count from above.
    """
    live = tmp_path / "parquet"
    _parquet(live, "old")
    matches = [tmp_path / "1.json", tmp_path / "2.json"]

    child = textwrap.dedent(f"""
        import os, pathlib, shutil, signal
        import pandas as pd
        from fis.ingest import wyscout
        live = pathlib.Path({str(live)!r})
        matches = [pathlib.Path(p) for p in {[str(m) for m in matches]!r}]
        wyscout.parquet_dir = lambda: live
        wyscout.match_files = lambda: matches
        def ingest(match_id, path, out_dir):
            out_dir.mkdir(parents=True, exist_ok=True)
            target = out_dir / f"events_{{match_id}}.parquet"
            pd.DataFrame({{"match_id": [match_id]}}).to_parquet(target, index=False)
            return target, []
        wyscout.ingest_match = ingest

        seen = [0]
        def trip():
            seen[0] += 1
            if seen[0] > {kill_at}:
                os.kill(os.getpid(), signal.SIGKILL)
        real_rename, real_rmtree = pathlib.Path.rename, shutil.rmtree
        pathlib.Path.rename = lambda self, target: (trip(), real_rename(self, target))[1]
        shutil.rmtree = lambda path, **kw: (trip(), real_rmtree(path, **kw))[1]

        import argparse
        wyscout.run(argparse.Namespace(fetch=False, out=None, limit=None, force=True))
    """)
    env = {**os.environ, "PYTHONPATH": str(pathlib.Path(wyscout.__file__).parents[3])}
    done = subprocess.run([sys.executable, "-c", child], env=env, capture_output=True, check=False)
    if kill_at < _MUTATIONS:
        assert done.returncode == -signal.SIGKILL, (
            f"the child survived a kill scheduled at mutation {kill_at} "
            f"(exit {done.returncode}) -- _MUTATIONS overstates the sweep.\n{done.stderr.decode()}"
        )
    else:
        assert done.returncode == 0, (
            f"a mutation past {_MUTATIONS} tripped the kill -- the sweep is "
            f"narrower than the rebuild (exit {done.returncode}).\n{done.stderr.decode()}"
        )

    # The retry: recovery and rebuild, exactly as an operator would run it.
    monkeypatch.setattr(wyscout, "parquet_dir", lambda: live)
    monkeypatch.setattr(wyscout, "match_files", lambda: matches)

    def ingest(match_id, path, out_dir):
        _parquet(out_dir, match_id)
        return out_dir / f"events_{match_id}.parquet", []

    monkeypatch.setattr(wyscout, "ingest_match", ingest)
    assert wyscout.run(_args(force=True)) == 0, f"the retry failed after a kill at {kill_at}"

    contents = {p.name for p in live.glob("events_*.parquet")}
    assert contents == {"events_1.parquet", "events_2.parquet"}, (
        f"killed at mutation {kill_at}: live holds {contents}, not the complete set"
    )
    assert json.loads((live / INGEST_STAMP).read_text()) == wyscout.provenance()
    assert not (tmp_path / "parquet.staging").exists()
    assert not (tmp_path / "parquet.previous").exists()
