"""Targeted repairs for defects hit when deserialising this Wyscout dataset.

Applied lazily and specifically. :func:`load_match` first tries an ordinary
``wyscout.load``; only when that fails with a *recognised* signature does it
apply the matching repair and retry. Anything unrecognised is re-raised
untouched, so a new defect surfaces as a failure rather than being silently
papered over.

Four defects occur across the 1941 matches. The first two raise an identical
``TypeError: 'NoneType' object is not subscriptable``, so they are told apart by
the kloppy function that raised, not by the message -- see :func:`_classify`.

=====================  =====  ============================================
defect                 files  cause
=====================  =====  ============================================
EXTRA_TIME_PERIOD         10  kloppy: deserializer_v2 does ``int("E1")``
SHOT_AS_FINAL_EVENT        6  kloppy: ``_parse_shot`` lookahead is unguarded
NULL_ROSTER_ENTRY         22  upstream data: a ``null`` entry in ``players``
LOST_INTERCEPTION_HOST   255  kloppy: ``events[:-1]`` drops the wrong event
=====================  =====  ============================================

All four are verified lossless on this dataset; see the README.

LOST_INTERCEPTION_HOST raises nothing -- it silently deletes 283 real events --
so it is found by inspecting the loaded dataset rather than by catching. The
detection is the fix's own off switch: a corrected kloppy produces no orphans
and the repair does not run. ``tests/test_kloppy_workarounds.py`` is what tells
you the others have become obsolete.
"""

from __future__ import annotations

import io
import json
import warnings
from contextlib import contextmanager
from pathlib import Path

import kloppy
from kloppy import wyscout
from kloppy.infra.serializers.event.wyscout import deserializer_v2 as _d2

#: kloppy release these repairs were written and verified against. They reach
#: into private internals, so a different version is worth flagging -- though the
#: real safety net is _classify(), which stops recognising anything if those
#: internals move, turning a silent mis-repair into a plain failure.
TESTED_KLOPPY_VERSION = "3.19.0"

EXTRA_TIME_PERIOD = "extra-time-period"
SHOT_AS_FINAL_EVENT = "shot-as-final-event"
NULL_ROSTER_ENTRY = "null-roster-entry"
LOST_INTERCEPTION_HOST = "lost-interception-host"

#: Only the raising defects; LOST_INTERCEPTION_HOST is found after a clean load.
ALL_DEFECTS = (EXTRA_TIME_PERIOD, SHOT_AS_FINAL_EVENT, NULL_ROSTER_ENTRY)

#: Wyscout's "interception" tag and the Duel event id, as literals for the same
#: reason as PERIOD_IDS -- an import of a moved private name would fail every
#: match, not just the affected ones. test_wyscout_constants guards them.
INTERCEPTION_TAG = 1401
DUEL_EVENT_ID = 1

#: Prefix kloppy gives the interception it inserts beside a tagged pass or
#: clearance. The id after it is the host event's own.
SYNTHESISED_PREFIX = "interception-"

#: Period ordinals for the codes deserializer_v2 cannot parse. These match
#: kloppy's own canonical mapping in deserializer_v3._parse_period_id, so a fixed
#: V2 deserializer will produce the same period_id values we do and an upgrade
#: cannot silently shift the data. Deliberately a literal rather than an import:
#: _parse_period_id is private, and an import would fail for every match rather
#: than just the ones needing repair. test_period_ids_match_kloppy guards it.
PERIOD_IDS = {"E1": 3, "E2": 4, "P": 5}

#: V2 derives the period with ``int(matchPeriod.replace("H", ""))``, so feeding it
#: "3H" yields 3. matchPeriod is read in exactly two places in deserializer_v2,
#: both only to derive period_id, which is why rewriting the string is a complete
#: fix rather than a patch of a single call site.
PERIOD_REMAP = {code: f"{ordinal}H" for code, ordinal in PERIOD_IDS.items()}

#: Substituted for a missing lookahead event. Both lookups in _parse_shot compare
#: against real Wyscout ids, so None matches neither and no goalkeeper qualifier
#: is added -- correct, because there is no following save to describe. The shot's
#: result comes from its own tags and is unaffected.
_NO_NEXT_EVENT = {"eventId": None, "subEventId": None}


def _kloppy_frames(exc: BaseException) -> list[str]:
    """Names of the kloppy functions on the traceback, outermost first."""
    frames, tb = [], exc.__traceback__
    while tb is not None:
        code = tb.tb_frame.f_code
        if "kloppy" in code.co_filename:
            frames.append(code.co_name)
        tb = tb.tb_next
    return frames


def _classify(exc: BaseException) -> str | None:
    """Which known defect this is, or None if unrecognised."""
    frames = _kloppy_frames(exc)
    if not frames:
        return None

    if isinstance(exc, ValueError) and "_deserialize" in frames:
        # Message reads: invalid literal for int() with base 10: 'E1'
        if any(f"'{code}'" in str(exc) for code in PERIOD_REMAP):
            return EXTRA_TIME_PERIOD
        return None

    if isinstance(exc, TypeError):
        # Identical message from both; only the raising function separates them.
        if "_parse_shot" in frames:
            return SHOT_AS_FINAL_EVENT
        if "_parse_team" in frames:
            return NULL_ROSTER_ENTRY
    return None


@contextmanager
def guarded_parse_shot():
    """Give ``_parse_shot`` a sentinel instead of None when a shot has no successor."""
    original = _d2._parse_shot

    def patched(raw_event, next_event):
        return original(raw_event, next_event or _NO_NEXT_EVENT)

    _d2._parse_shot = patched
    try:
        yield
    finally:
        _d2._parse_shot = original


def remap_extra_time_periods(raw: dict) -> None:
    """Rewrite period codes V2 cannot parse into ones that yield the V3 ordinal."""
    for event in raw["events"]:
        event["matchPeriod"] = PERIOD_REMAP.get(event["matchPeriod"], event["matchPeriod"])


def drop_null_roster_entries(raw: dict) -> None:
    """Remove ``null`` roster slots, which carry no player to record."""
    for team_id, entries in raw.get("players", {}).items():
        raw["players"][team_id] = [e for e in entries if e and e.get("player")]


def deleted_hosts(dataset, raw: dict) -> dict[str, int]:
    """Events kloppy dropped, mapped to the tagged duel that displaced them.

    Converting a tagged duel drops the event before it, on the assumption that
    it is the other half of the duel pair. When it is not -- a pass, a shot, a
    touch -- a real event is lost. Duels are excluded: dropping those is the
    behaviour being aimed for, and is correct whenever the pair is adjacent.
    """
    present = {str(event.event_id) for event in dataset.records}
    events = raw["events"]
    lost = {}
    for i, event in enumerate(events[:-1]):
        following = events[i + 1]
        if following["eventId"] != DUEL_EVENT_ID or event["eventId"] == DUEL_EVENT_ID:
            continue
        if not any(tag["id"] == INTERCEPTION_TAG for tag in following["tags"]):
            continue
        if str(event["id"]) not in present:
            lost[str(event["id"])] = i + 1
    return lost


def restore_deleted_hosts(dataset, raw: dict, *, data_version: str, patch_shot: bool) -> list[str]:
    """Put back the events dropped by ``events[:-1]``. Returns the ids restored.

    Deserialises a second time with the offending duels' interception tag
    removed. Without the tag those duels are not converted, nothing is dropped,
    and the lost events survive to be copied across. Only they are taken, so
    every other event stays exactly as the first load produced it.
    """
    lost = deleted_hosts(dataset, raw)
    if not lost:
        return []

    patched = json.loads(json.dumps(raw))
    for i in set(lost.values()):
        patched["events"][i]["tags"] = [
            tag for tag in patched["events"][i]["tags"] if tag["id"] != INTERCEPTION_TAG
        ]
    reference = _load(io.BytesIO(json.dumps(patched).encode()), data_version, patch_shot)

    restored = []
    for position, event in enumerate(reference.records):
        if str(event.event_id) not in lost:
            continue
        # Anchor on the nearest earlier event the first load kept, so the
        # restored event lands where the reference says it belongs.
        at = 0
        for earlier in reversed(reference.records[:position]):
            index = _index_of(dataset, str(earlier.event_id))
            if index is not None:
                at = index + 1
                break
        dataset.records.insert(at, event)
        restored.append(str(event.event_id))
    return restored


def _index_of(dataset, event_id: str) -> int | None:
    for index, event in enumerate(dataset.records):
        if str(event.event_id) == event_id:
            return index
    return None


def _load(source, data_version: str, patch_shot: bool):
    if patch_shot:
        with guarded_parse_shot():
            return wyscout.load(event_data=source, data_version=data_version)
    return wyscout.load(event_data=source, data_version=data_version)


def load_match(path: Path, *, data_version: str = "V2"):
    """Deserialise one match, repairing only recognised defects.

    Returns ``(dataset, applied)``. ``applied`` lists the repairs that were
    needed -- empty for the ~85% of matches that load cleanly.
    """
    path = Path(path)
    raw: dict | None = None
    applied: list[str] = []
    patch_shot = False

    # One pass per raising defect, plus a final attempt once all have been applied.
    for _ in range(len(ALL_DEFECTS) + 1):
        source = str(path) if raw is None else io.BytesIO(json.dumps(raw).encode())
        try:
            dataset = _load(source, data_version, patch_shot)
        except Exception as exc:
            defect = _classify(exc)
            # Unrecognised, or a repair that failed to take: surface it unchanged.
            if defect is None or defect in applied:
                raise

            if kloppy.__version__ != TESTED_KLOPPY_VERSION:
                warnings.warn(
                    f"Applying workaround {defect!r} against kloppy "
                    f"{kloppy.__version__}, but it was verified against "
                    f"{TESTED_KLOPPY_VERSION}. Re-check that it is still lossless.",
                    RuntimeWarning,
                    stacklevel=2,
                )

            if defect == SHOT_AS_FINAL_EVENT:
                patch_shot = True
            else:
                if raw is None:
                    raw = json.loads(path.read_text())
                if defect == EXTRA_TIME_PERIOD:
                    remap_extra_time_periods(raw)
                elif defect == NULL_ROSTER_ENTRY:
                    drop_null_roster_entries(raw)
            applied.append(defect)
            continue

        # Loaded. The remaining defect raises nothing, so it is found by
        # comparing what came back against the file it came from.
        if raw is None:
            raw = json.loads(path.read_text())
        if restore_deleted_hosts(dataset, raw, data_version=data_version, patch_shot=patch_shot):
            applied.append(LOST_INTERCEPTION_HOST)
        return dataset, applied

    raise RuntimeError(f"workarounds did not converge for {path}: applied {applied}")
