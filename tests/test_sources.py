"""The source registry decides what fis-fetch/fis-ingest do with no arguments."""

from __future__ import annotations

import pytest

from fis import sources


def test_known_sources_include_wyscout():
    assert sources.known() == ["wyscout"]


def test_default_is_wyscout_alone():
    assert sources.resolve(None) == ["wyscout"]


def test_all_returns_every_known_source():
    assert sources.resolve(None, all_=True) == sources.known()


def test_explicit_source_is_returned_alone():
    assert sources.resolve("wyscout") == ["wyscout"]


def test_all_wins_over_an_explicit_source():
    assert sources.resolve("wyscout", all_=True) == sources.known()


def test_unknown_source_names_the_known_ones():
    with pytest.raises(KeyError, match="unknown source 'not-a-source'.*wyscout"):
        sources.resolve("not-a-source")


def test_get_unknown_source_names_the_known_ones():
    with pytest.raises(KeyError, match="unknown source 'not-a-source'.*wyscout"):
        sources.get("not-a-source")


def test_installed_rejects_an_unknown_stage():
    with pytest.raises(ValueError, match="'fetched' or 'ingested'"):
        sources.installed("both")


def test_each_source_declares_a_positive_download_estimate():
    for name in sources.known():
        assert sources.get(name).approx_download_gb > 0
