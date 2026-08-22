# Draft kloppy issues

Two genuine kloppy bugs found while ingesting the Wyscout open dataset. Neither
is reported upstream — searches for `matchPeriod E1`, `_parse_shot NoneType` and
`wyscout NoneType subscriptable` in `PySport/kloppy` returned nothing relevant.

File at <https://github.com/PySport/kloppy/issues/new>. They are independent, so
file them separately.

The third defect we work around (a `null` entry in `players`) is a data problem
in `koenvo/wyscout-soccer-match-event-dataset`, not a kloppy bug, so it is not
drafted here. It could still be worth a defensive-skip PR against `_parse_team`.

---

## Issue 1 — Wyscout V2 deserializer cannot parse extra-time periods

**Title:** `Wyscout V2 deserializer crashes on extra-time periods (V3 handles them)`

### Description

`deserializer_v2.py` derives the period with:

```python
period_id = int(raw_event["matchPeriod"].replace("H", ""))
```

That handles `1H` and `2H`, but Wyscout also uses `E1`, `E2` and `P` for extra
time and penalties, which reach `int()` unchanged and raise.

Extra-time support was added for Wyscout **V3** in #351, and periods beyond two
were added to the domain model in #256, but `deserializer_v2.py` was never
updated. V3 already has the correct mapping in `_parse_period_id`:

```python
def _parse_period_id(raw_period: str) -> int:
    if "H" in raw_period:   period_id = int(raw_period.replace("H", ""))
    elif "E" in raw_period: period_id = 2 + int(raw_period.replace("E", ""))
    elif raw_period == "P": period_id = 5
```

### Reproduction

Match 1694426 is Switzerland–Poland from Euro 2016 (1–1, decided on penalties),
so it has `E1`, `E2` and `P` periods. It is in the public dataset that
`wyscout.load_open_data()` itself points at.

```python
from kloppy import wyscout
wyscout.load_open_data("1694426")
```

```
ValueError: invalid literal for int() with base 10: 'E1'
  File ".../wyscout/deserializer_v2.py", line 501, in _deserialize
    next_period_id = int(next_event["matchPeriod"].replace("H", ""))
```

### Impact

10 of the 1941 matches in the public Wyscout dataset fail to load — every match
that went to extra time. Since `load_open_data()` serves this dataset, the bug
is reachable from kloppy's own documented entry point.

### Suggested fix

Use the existing `_parse_period_id` at both call sites in `deserializer_v2.py`
(lines ~501 and ~507), promoting it to a shared helper. That keeps V2 and V3
agreeing on what `E1`/`E2`/`P` mean, rather than introducing a third mapping.

I am happy to open a PR if that approach is agreeable.

---

## Issue 2 — `_parse_shot` crashes when a shot is the final event of a match

**Title:** `Wyscout V2 _parse_shot raises TypeError when a shot is the last event`

### Description

`_deserialize` sets `next_event = None` on the final event:

```python
next_event = None
if (idx + 1) < len(raw_events["events"]):
    next_event = raw_events["events"][idx + 1]
```

`_parse_shot` then dereferences it without a guard:

```python
if next_event["eventId"] == wyscout_events.SAVE.EVENT:   # line 187
```

`_parse_pass` performs the same lookahead and _does_ guard it:

```python
if next_event:                                            # line 257
    if next_event["eventId"] == wyscout_events.OFFSIDE.EVENT:
```

So a match ending on a pass parses fine, while one ending on a shot crashes.

### Reproduction

Match 1694433 is England–Iceland from Euro 2016, which ends on an off-target
shot.

```python
from kloppy import wyscout
wyscout.load_open_data("1694433")
```

```
TypeError: 'NoneType' object is not subscriptable
  File ".../wyscout/deserializer_v2.py", line 187, in _parse_shot
    if next_event["eventId"] == wyscout_events.SAVE.EVENT:
```

### Impact

6 of the 1941 matches in the public dataset. A match ending on a wayward shot is
unremarkable, so this is not an edge case in the data — only in the parser.

Affected matches also reach `_parse_shot` via `_parse_set_piece` (line 372), so
a match ending on a free-kick shot fails the same way (e.g. 2516925).

### Suggested fix

Guard the lookahead the way `_parse_pass` already does:

```python
if next_event and next_event["eventId"] == wyscout_events.SAVE.EVENT:
```

The shot's `result` is derived from its own tags and is unaffected; only the
optional `GoalkeeperQualifier` depends on `next_event`, and when there is no
following event there is correctly no goalkeeper action to record.
