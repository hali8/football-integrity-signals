# football-integrity-signals

Package to get familiar with match and player data.

Fetches a public Wyscout event dataset, normalises it into one parquet file per
match, and gives a duckdb/dbt warehouse to build match-integrity signals on top of.

## Output / analysis summary

A limited pathfinder — at what level an injected signal can be found in
aggregate data, with no attempt to account for all correlated factors.

One full-population run, 2026-08-27: 43,993 player-matches, 2,140 players, seven
scorers against five single mechanisms plus a coordinated four-channel injection.
One typical match per player: the dose is k times that player's own spread, so
injecting at the centre is what makes k mean k.

**The best scorer depends on the manipulation.** Against a single metric, max|z|
— the simplest scorer, and the baseline the others have to beat — is
competitive and the isolation forests are last. Against a coordinated
manipulation across four variables the order reverses: the forests recover
**2.1× max|z|** (21.7% against 10.4% of injected targets, 1% bar, k=3). The case
a real fixer most resembles is the one max|z| handles worst.

Which scorer leads depends on the bar as well as the manipulation. At 5% the
order reverses again — `mahalanobis_res` recovers 44.8% against the forest's
43.7% on the same injection — so neither dominates.

[Full sensitivity tables](results/phase2.md)

Three limits. The population is observed, not certified-clean, so base rates
are upper bounds on the false-positive rate. These measure sensitivity to
_simulated_ manipulation — nothing here is validated against a confirmed case.
And the run is held-out: only the injected rows are scored, so what a
manipulation does to the player's OTHER matches is not measured.

## Stage rule

Each stage reads only the output of the one before it:

| Stage             | Reads                         | Writes                         |
| ----------------- | ----------------------------- | ------------------------------ |
| `fis-fetch`       | upstream GitHub, Figshare     | `data/download/`, `data/json/` |
| `src/fis/ingest/` | `data/download/`              | `data/parquet/`                |
| `warehouse/`      | `data/parquet/`, `data/json/` | marts (duckdb)                 |
| `analysis/`       | marts                         | figures, tables, findings      |

The dimension files are read in place; only the event data justified a
materialisation stage. Events need kloppy to decode them to a typed parquet
layer before dbt sees them. dbt reads dimensions — players, teams, referees,
coaches, competitions — in place. From there both paths are the same: staging
models flatten and type-repair them, and the marts are built in duckdb, which is
all analysis ever reads.

**Nothing in `analysis/` touches raw data — a missing column means a missing dbt
model, not a backwards reach.**

the warehouse should always be the source of
truth -- avoiding invisible definition drift.

`data/download/` is immutable and disposable — pinned upstream content, deletable
and re-fetchable at any time. Everything downstream of it is reproducible by
re-running the stages in order.

### How it is enforced

The rule is checked at three points, deliberately escalating from gentle to hard:

| Where           | What happens                                                    |
| --------------- | --------------------------------------------------------------- |
| At runtime      | `StageRuleWarning`, and the path is returned anyway             |
| At `git commit` | the pre-commit hook rejects the commit                          |
| In CI           | the `lint` job fails, and `package` asserts the ban still fires |

The runtime layer never raises: an exploratory session must not break mid-flight.
`fis.paths.parquet_dir()` called from anything under `fis.analysis` warns and
points at `fis.warehouse.mart()`. The lint layer is what stops it reaching a merge
— `src/fis/analysis/ruff.toml` bans those accessors, and `kloppy`, for that
directory only.

Separately, dbt writes each layer to its own schema (`main_staging`,
`main_intermediate`, `main_marts`), so "analysis reads marts only" is a property
of the database rather than a convention.

## Environment

Two routes. **pixi** is the supported one — it provisions Python itself, so it
cannot be installed from this repository:

```bash
curl -fsSL https://pixi.sh/install.sh | sh   # macOS / Linux
winget install prefix-dev.pixi               # Windows
```

The lock file is solved for `osx-arm64` only. Elsewhere, either add your
platform to `pixi.toml` and re-lock, or take the pip route below.

```bash
pixi install
pixi run hooks-install   # once per clone: installs the git hooks
```

**Or pip**, into an environment you manage yourself. CI takes this route on every
push, so it is known to resolve:

```bash
pip install -e ".[warehouse,analysis,dev]"
export DBT_PROJECT_DIR=warehouse DBT_PROFILES_DIR=warehouse
pre-commit install --hook-type pre-commit --hook-type pre-push
```

The two exports are what `[activation.env]` sets for you under pixi; dbt will not
find `warehouse/` without them.

Either way the package installs editable, which puts the console scripts on your
`PATH`. The pixi tasks are shorthand for those scripts, and nothing depends on
them:

| pixi task           | equivalent                      |
| ------------------- | ------------------------------- |
| `pixi run fetch`    | `fis-fetch && fis-gen-dbt-docs` |
| `pixi run ingest`   | `fis-ingest`                    |
| `pixi run build`    | `dbt build`                     |
| `pixi run test`     | `pytest -m 'not slow'`          |
| `pixi run test-all` | `pytest`                        |
| `pixi run lint`     | `ruff check src`                |
| `pixi run hooks`    | `pre-commit run --all-files`    |

`pixi run build` chains fetch and ingest first; run them in that order by hand.

## Quick start

```bash
fis-fetch      # download the dataset  (~255 MiB, 1941 matches)
fis-ingest     # convert JSON -> parquet
```

Or `pixi run fetch` / `pixi run ingest`, without activating the environment.

Both are idempotent: re-running skips work already done **by the current
pipeline**. Change the ingest code, the kloppy version or the pinned dataset
commit and the next run re-ingests everything rather than trusting the files it
finds — see [Knowing when the parquet is out of date](#knowing-when-the-parquet-is-out-of-date).
To ingest a handful of matches while iterating:

```bash
fis-ingest --limit 10
```

## Where data goes

All paths resolve through `fis.paths`, which is the single source of truth. The
data root is chosen in this order:

| Order | Location                                       | When                                |
| ----- | ---------------------------------------------- | ----------------------------------- |
| 1     | `$FIS_DATA_DIR`                                | always wins, if set                 |
| 2     | `<project root>/data`                          | source checkout or editable install |
| 3     | `<user cache>/football-integrity-signals/data` | installed from a wheel              |

The project root is found by walking up to `pyproject.toml` rather than shelling
out to `git rev-parse`, so it also works in a tarball export or a Docker image
with no `.git` directory. It is the directory holding `pyproject.toml` and `src/`
— so `data/` sits beside `src/`, never inside the package.

The user cache directory is platform-specific:

| Platform | Path                                                                      |
| -------- | ------------------------------------------------------------------------- |
| Linux    | `$XDG_CACHE_HOME/football-integrity-signals/data`, default `~/.cache/...` |
| macOS    | `~/Library/Caches/football-integrity-signals/data`                        |
| Windows  | `%LOCALAPPDATA%\football-integrity-signals\Cache\data`                    |

One consequence worth being aware of: if you ever `pip install` this package
outside the checkout, it will not see the `data/` you have already downloaded —
it will go looking in the user cache instead. Point `FIS_DATA_DIR` at your
existing `data/` directory to share it.

```
data/
├── download/wyscout/processed-v2/files/*.json   # upstream events, immutable
├── json/                                        # upstream dimensions, read in place
│   ├── matches_*.json  players.json  teams.json
│   ├── referees.json   coaches.json  competitions.json
│   └── eventid2name.csv  tags2name.csv
└── parquet/events_<match_id>.parquet            # our normalised output
```

All three are gitignored — everything under `data/` is reproducible from the two
commands above.

## Dataset

[koenvo/wyscout-soccer-match-event-dataset](https://github.com/koenvo/wyscout-soccer-match-event-dataset),
`processed-v2` subtree, pinned to commit `ebc4c54c`.

The pin lives in `DATASET_COMMIT` in [src/fis/data/wyscout.py](src/fis/data/wyscout.py).
Bumping it is a deliberate, reviewable change: a `.fis-dataset.json` stamp in the
download directory records which revision is on disk, so a changed pin triggers a
re-download instead of silently mixing revisions.

The download is a plain HTTPS tarball fetch — no `git` needed at runtime — staged
in a temp directory and swapped into place, so an interrupted run cannot leave a
half-populated directory that a later run mistakes for complete.

```bash
fis-fetch --commit <sha>          # one-off override
fis-fetch --force                 # re-download regardless
fis-fetch --dest /scratch/wyscout # somewhere else entirely
fis-fetch --no-reference          # skip the Figshare tables
fis-fetch --no-audit              # skip the post-download checks
```

### Reference tables

The same fetch also pulls the dimensions from the original Figshare collection
published with Pappalardo et al. (2019), into `data/json/`:

`matches_*.json` (dates, teams, scores, referee assignments), `players.json`,
`teams.json`, `competitions.json`, `referees.json`, `coaches.json`, plus
`eventid2name.csv` and `tags2name.csv` for decoding the numeric event and tag
ids. Roughly 2.7 MB in total.

Each file is pinned by Figshare **file id and md5**, and the checksum is verified
after download — a silently republished file fails loudly rather than changing
your results. koenvo mirrors four of these but not competitions, referees or
coaches, so all of them come from Figshare rather than splitting provenance.

`events.zip` is deliberately not fetched: it holds the same events as the 1941
per-match files, and expands past 1 GB.

**`referees.json` is published truncated.** It ends mid-record, so duckdb cannot
read it at all. The fetcher detects this specific damage, recovers all 627
records — salvaging the final partial one, which keeps every field except its
last — and preserves the original as `referees.as-published.json`. The repair is
lazy: a file that parses is left exactly as downloaded, so an upstream fix makes
it a no-op.

### Post-download audit

Checksums verify transfer, not content. After fetching, `audit("wyscout")` in
[src/fis/data/audit.py](src/fis/data/audit.py) checks that every file parses and
that ids referenced by one file exist in another, reporting what any gap costs:

```
Data audit: 0 error(s), 2 warning(s), 6 checks.
  [WARN] referee-coverage: 10 of 637 referenced officials have no entry
         impact: 95 of 7942 assignments (1.2%) — a referee dimension will not resolve them.
  [WARN] coach-coverage: 3 of 211 referenced coaches have no entry
         impact: 13 of 3645 match sides (0.4%) — coach names will be null.
```

Both gaps are upstream data, not our processing. The audit never fails the
fetch — the data is still worth having — but the number is visible, so it cannot
drift unnoticed. Checks are registered per dataset, so a second source is a new
entry in `REGISTRY`.

## Ingest

Each match is loaded with [kloppy](https://github.com/PySport/kloppy) and
transformed to `ACTION_EXECUTING_TEAM` orientation before anything else — without
that, every spatial metric is noise. kloppy's frame covers a single match and
carries no match id, so one is added as a `match_id` column, which everything
downstream keys on.

One bad match never aborts the run; failures are collected and reported at the end.

### Knowing when the parquet is out of date

Matches whose parquet already exists are skipped, which is what makes an
interrupted run resumable. On its own that is also how a pipeline fix fails to
reach the data: the files are there, so nothing is re-ingested and every number
downstream keeps coming from the old parse.

So `data/parquet/.fis-ingest.json` records the three things that decide what the
output contains — the pinned dataset commit, the kloppy version, and a hash of
`ingest/wyscout.py` and `ingest/kloppy_workarounds.py`. When any differs from
what is on disk, the run says which one and re-ingests everything.

The stamp is written only after a complete run with no failures, so an
interrupted one leaves no claim behind and the next starts over rather than
mixing output from two pipelines. Editing a comment in either module also
triggers a full re-ingest; half an hour of compute is the cheaper mistake.
`--force` re-ingests regardless.

### Deserialisation workarounds

38 of the 1941 matches will not load with a plain `kloppy.wyscout.load`, and a
further 1690 load while quietly missing events. Four distinct defects are
responsible, repaired in
[src/fis/ingest/kloppy_workarounds.py](src/fis/ingest/kloppy_workarounds.py):

| Defect                   | Files | Cause                                           |
| ------------------------ | ----- | ----------------------------------------------- |
| `extra-time-period`      | 10    | kloppy: `deserializer_v2` evaluates `int("E1")` |
| `shot-as-final-event`    | 6     | kloppy: `_parse_shot` lookahead is unguarded    |
| `null-roster-entry`      | 22    | upstream data: a `null` entry in `players`      |
| `lost-interception-host` | 1690  | kloppy: `events[:-1]` drops the wrong event     |

**The first three are applied lazily and specifically.** Every match is loaded
normally; only a failure matching a known signature triggers a repair and a
retry. An unrecognised error is re-raised untouched, so a new defect surfaces as
a failure rather than being silently absorbed.

Two of them raise an identical
`TypeError: 'NoneType' object is not subscriptable`, so they are told apart by
the kloppy function on the traceback, not by the message. That also means a
kloppy restructure stops matching anything and the error surfaces, instead of a
stale patch mis-firing.

**The fourth raises nothing**, so it cannot be caught — it is found by comparing
the loaded dataset against the file it came from. That check runs on every
match, which is why the clean path now re-reads its JSON. See below for what it
detects and why the repair is lossless.

Nothing on disk is modified. JSON is repaired in memory and passed to kloppy as a
`BytesIO`, so `data/download/` stays byte-identical to the pinned commit that
`.fis-dataset.json` asserts.

**Why each is lossless.**

- _Extra time._ kloppy's V2 deserialiser reads `matchPeriod` in exactly two
  places, both only to derive `period_id`, so rewriting the string is complete
  rather than a patch of one call site. `E1/E2/P` become periods 3/4/5 —
  identical to kloppy's own canonical mapping in `deserializer_v3._parse_period_id`,
  which is what a fixed V2 deserialiser would almost certainly use. A test
  asserts that agreement, so an upstream fix cannot silently shift your data.
- _Shot as final event._ A shot's result comes from its own tags; `next_event`
  only decides whether a goalkeeper qualifier is attached. All six such shots
  carry tag 1802 ("not accurate") and resolve to `OFF_TARGET` or `POST`, so no
  save qualifier existed to lose. Verified: all six files are time-ordered and
  the shot really is the final event, so no save is hiding out of file order.
- _Null roster._ The entry carries no player, so dropping it removes nothing.
- _Lost interception host._ Only events kloppy deleted are put back, so nothing
  else can move. The second parse differs from the first solely in that the
  offending duels are no longer converted: kloppy's lookahead reads a following
  event's type, subtype and team but never its tags, at all six call sites, so
  removing tag 1401 from a duel cannot change how any other event is parsed.
  Verified across all 1941 matches — afterwards the only events still absent are
  offsides, which kloppy merges into the following pass or shot by design, and
  the paired duels it means to remove.

**Why the fourth defect matters more than the other three.** Wyscout V2 has no
interception event type; a touch that wins the ball is tagged 1401 on whatever
it already was. kloppy turns that tag into an `InterceptionEvent`, substituting
it for a tagged duel and deleting the duel's partner row — with `events[:-1]`,
which drops the last event appended without checking that it is a duel. When the
tagged duel is the first of its pair the partner comes _after_ it, so the event
deleted is whatever preceded it: **4400 events across 1690 matches, including 35
shots**. Only 310 leave a dangling `interception-<id>` behind; the other 4090
disappear with nothing marking their absence. So we had been losing events silently.

**These workarounds are meant to die.** An upstream fix would make them
unreachable — the first three because nothing raises, the fourth because the
comparison finds nothing to repair.
`tests/test_kloppy_workarounds.py` asserts each defect _still reproduces_ — when
kloppy fixes one, that test fails and tells you to delete the repair.

kloppy is pinned to `>=3.19,<3.20` for the same reason the dataset commit is
pinned: the parser version determines the ingested output as much as the input
data does.

## Warehouse

A self-contained duckdb + dbt project lives in `warehouse/`, resolving everything
through `external_location` honouring `FIS_DATA_DIR`, so it follows the same path
resolution as the Python code.

One source group, `wyscout`, because that is where all of it comes from — the
events included. kloppy transcoded them and the orientation was transformed, but
no fact in the warehouse originated with us.

| Table                                                                | Read as                        |
| -------------------------------------------------------------------- | ------------------------------ |
| `events`                                                             | parquet glob, `data/parquet/`  |
| `matches`, `players`, `teams`, `competitions`, `referees`, `coaches` | `read_json_auto`, `data/json/` |
| `eventid2name`, `tags2name`                                          | `read_csv_auto`, `data/json/`  |

The group's default location is `read_json_auto`; `events` and the two CSVs
override it, and `matches` also adds `union_by_name=true` because `groupName`
appears only in the tournament files.

```bash
pixi run dbt-debug     # verify the connection and project config
pixi run build         # dbt build
pixi run dbt <cmd>     # anything else: dbt ls, dbt test, dbt show ...
```

Under pixi, reach dbt with `pixi run` or from inside `pixi shell`; on the pip
route it is already on your `PATH`. Either way dbt finds `warehouse/` from
`DBT_PROJECT_DIR` and `DBT_PROFILES_DIR` — set by `[activation.env]` under pixi,
exported by hand otherwise.

### Where the warehouse looks for data

Nothing to configure. `_sources.yml` reads
`{{ env_var('FIS_DATA_DIR', 'data') }}`, and the fallback is correct because dbt
can only run from the repository root anyway — `DBT_PROJECT_DIR`,
`DBT_PROFILES_DIR` and the duckdb path in `profiles.yml` are all relative to the
working directory. From there `./data` **is** `fis.paths.data_dir()`, which
resolves to `<the directory holding pyproject.toml>/data`. pixi always starts
tasks in the manifest directory, so this holds however you invoke them.

Set `FIS_DATA_DIR` to point somewhere else, and both sides follow it —
`data_dir()` checks the same variable first. `fis-data-dir` prints whatever is
currently in effect:

```bash
fis-data-dir                          # where is my data?
FIS_DATA_DIR=/scratch pixi run build  # build against a different copy
```

**Run it from the repository root.** Those two variables are relative, and so are
the paths dbt reads out of the project — the duckdb file in `profiles.yml` and
the parquet glob in `_sources.yml`. All of them resolve against the working
directory, and the repository root is where they are correct. `pixi run` handles
this for you by always starting from the manifest directory; inside `pixi shell`
it is yours to get right.

### Adding a source

verification is done in CI and in `dbt build` alongside
everything else.

1. Add the table under the right group in
   [\_sources.yml](warehouse/models/staging/_sources.yml). A new file format
   needs a new group with its own `external_location`; a new table in an existing
   format needs only a `- name:`.
2. Give it `data_tests: [not_empty]`, and `unique` / `not_null` on its key.
   Check the key really is unique first — a test you add already broken teaches
   the team to ignore red builds.
3. Describe the nested columns. `teamsData` and `referees` are the ones staging
   models unnest, and a reader should not have to query the data to learn its
   shape.
4. `pixi run dbt build`. That compiles every model, runs every test, and is the
   whole verification story.

`not_empty` is a custom generic test in
[warehouse/tests/generic/](warehouse/tests/generic/not_empty.sql). It exists
because dbt validates that a source's _configuration_ parses, never that it
resolves to anything: with no model selecting from it, a source pointing at a
missing file is completely invisible — `dbt build` reports `Nothing to do` and
exits clean.

Once every source feeds a staging model, a wrong path fails at compile time
anyway and this test becomes partly redundant. What it still catches is the case
`dbt build` never will: a path that resolves but returns **zero rows**. duckdb
reads `[]` as 0 rows rather than raising, so models build, marts come out empty,
and nothing else complains.

## Metric definitions

**Drafted, not decided.** The SQL implements these; it does not choose them.
Anything below marked _open_ is a judgement that has not been made yet.

| Metric                         | Definition                                                                                                                                                                                   |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `position`                     | The player's registered role. Wyscout records no per-match position.                                                                                                                         |
| `minutes_played`               | From the lineups and substitutions, capped at the match's own length — not a nominal 90. Inferred from the player's own events for 50 player-matches whose substitution is missing upstream. |
| `is_eligible`                  | `minutes_played >= 30`. A column, not a filter: the mart keeps every row and the analysis decides.                                                                                           |
| `passes`                       | Every pass credited to the player, goal kicks included.                                                                                                                                      |
| `passes_with_outcome`          | Passes Wyscout tagged for accuracy, plus short goal kicks whose outcome is inferred.                                                                                                         |
| `passes_completed`             | Recorded completions plus inferred ones, over that same set.                                                                                                                                 |
| `passes_unjudged`              | `passes − passes_with_outcome`. Long goal kicks.                                                                                                                                             |
| `passes_outcome_inferred`      | How much of `passes_completed` is derived rather than recorded.                                                                                                                              |
| `pass_completion_pct`          | `passes_completed / passes_with_outcome`, null when nothing was judged.                                                                                                                      |
| `crosses`                      | Events whose qualifier list contains `Pass:CROSS`.                                                                                                                                           |
| `interceptions`                | Every interception, whichever event kloppy built it from. A volume measure only — see below.                                                                                                 |
| `tackles` / `tackles_won`      | Sliding tackles among the player's duels, and how many were won.                                                                                                                             |
| `defensive_actions`            | Defensive volume: defensive-side duels, clearances and interceptions. An interception recorded as a clearance is one action, not two.                                                        |
| `defensive_action_success_pct` | Defensive duels won plus clearances that removed danger, over those same actions. A narrower set than `defensive_actions`.                                                                   |
| `touches_in_defensive_third`   | Actions starting at `x < 1/3`.                                                                                                                                                               |
| `mean_action_x`                | Mean starting `x` over the player's actions that have a position.                                                                                                                            |

**Every action is scored on the tag Wyscout wrote for it** — won or lost for
duels, accurate for passes, danger removed for clearances. Scoring everything on
the accuracy tag made the rate a blend of four different constructs, and for
clearances it ran backwards.

**Duel side comes from the raw subevent, not from kloppy's event type.** kloppy
maps a ground attacking duel and a ground defending duel to the same `GROUND`
type, so `subevent_id` is the only place the two are told apart.

**Only the ground defending duel is a defensive action.** Wyscout gives air and
loose-ball duels no side, and against who held the ball beforehand they are even
contests — about as often the player's own team as the opponent's. Counting them
as defending would fill the denominator with players challenging for a ball
their side already had, so they stay in the taxonomy as plain duels. Ground
attacking duels belong to the player carrying the ball. A sliding tackle is a
tag on a duel rather than a kind of its own, and keeps its own count.

**A clearance succeeds if it found a teammate or put the ball out of play.**
Conceding a corner is the one out-of-play outcome that leaves the defence worse
off; a throw-in is the job done. kloppy hardcodes
`result: None` for clearances, which is why the ingest carries the raw tag ids.

**Interceptions carry no rate.** Wyscout logs an interception as something that
happened, not an attempt that could have failed — almost none carry a lost
tag. The failed attempts are not recorded anywhere, so there is no denominator, and a
success rate over them would be near-100% by construction. They stay in
`defensive_actions` and in the per-90 volume.

**Crosses must be counted from `qualifiers`, never from `pass_type`.** kloppy's
flat column keeps only the last qualifier it attached, so a cross tagged "high"
appears as `HIGH_PASS`: 26,444 crosses instead of 62,169.

`x` runs 0 at the player's own goal-line to 1 at the opponent's, because ingest
transforms every event to `ACTION_EXECUTING_TEAM` orientation. So
`touches_in_defensive_third` and `mean_action_x` are comparable across teams and
halves without further adjustment.

### Goal kicks

**Wyscout never scores a goal kick for accuracy.** All 31,797 carry neither tag
1801 nor 1802, and no other set piece is affected — throw-ins, corners and free
kicks are tagged like open play. It is a convention, not a gap, and treating the
absence as failure would record every goal kick a keeper takes as a failed pass.

A goal kick is still a pass, so it counts in `passes`. What it lacks is an
outcome, which is a denominator question. Two kinds, split on where the ball
lands, because they behave differently:

|                                 | Retained by the kicking team |
| ------------------------------- | ---------------------------- |
| lands before `x = 0.3` — 7,434  | 95–97%                       |
| lands beyond `x = 0.4` — 21,572 | 31–57%                       |

A short goal kick is an ordinary pass to a defender and has a determinate
outcome. A long one is a contested 50/50 and does not.

So short goal kicks get an **inferred** outcome — completed if the kicking team
makes the next deliberate on-the-ball action — and long ones get none. That rule
agrees with Wyscout on **94–95%** of labelled passes of comparable length,
falling to 87–91% at long-ball distances, which is why it is not extended to
them. The inference is never mixed into the recorded counts:
`passes_outcome_inferred` isolates it, and subtracting gives the recorded-only
figure. Across the dataset the two differ by 0.07pp; for a goalkeeper they do not.

`0.3` is about 31 m from the goal line, where the retention curve breaks. Wyscout
files every goal kick as `Goal kick` with no subtype and no tags, so there is no
upstream distinction to defer to and the line is ours.

**Goal kicks have no start position.** Wyscout writes a corner-flag sentinel —
`(0,0)` or `(100,100)`, both variants, in the same match — so `stg_events` nulls
it rather than passing on a coordinate that would place 17,299 goal kicks at the
opponent's corner flag. The end point is genuine and kept. They therefore carry
no weight in `mean_action_x` and cannot land in `touches_in_defensive_third`.

### Interceptions

Wyscout V2 has no interception event type either. A touch that wins the ball is
filed as whatever it already was and tagged 1401; kloppy turns that tag into an
`InterceptionEvent`, inserting one beside a pass or clearance and substituting
one for a duel or touch. So an interception always has a **host**, and the leaf
names it:

| Leaf                        | kloppy's treatment            |
| --------------------------- | ----------------------------- |
| `interception_as_pass`      | inserted beside the pass      |
| `interception_as_touch`     | replaced _Others on the ball_ |
| `interception_as_clearance` | inserted beside the clearance |
| `interception_as_duel`      | replaced the duel             |

The duel leaf is the one place the interception tag outranks the subevent.
Wyscout files a won ball under what the player did next, so a ball won and then
carried is recorded as a ground _attacking_ duel carrying tag 1401. Those rows
are preceded by the opponent holding the ball far more often than untagged
attacking duels are, so the tag is believed and the row counts as an
interception.

`interceptions` sums all four — the number of times the player won the ball.
`defensive_actions` excludes `interception_as_clearance`, because those
clearances are already in the sum and one touch would otherwise count twice.
Naming the host rather than filtering it means a new pass or defensive metric
meets the distinction instead of inheriting the double-count.

### Why these metrics

Grounded in Ellens (2019): fixing showed clearest in defenders, and positional
metrics carried it better than event-based ones — players moved upfield, further
from their position centroid, with more lateral spread, stretching the defensive
line.

Hence three of six metrics defensive, four of five injection mechanisms
defensive, and `relocate_upfield` moving touches out of the defensive third
rather than degrading a count.

Motivation for what we inject, not support for what we measure: a Research
Master's thesis, not peer-reviewed, two matches and four instructed defenders.

> Ellens, S. (2019). _Can we catch the crooks: examining performance metrics of
> match-fixing association football players._ Research Master thesis, Institute
> for Health and Sport, Victoria University, Melbourne, Australia. 88 pp.
> <https://vuir.vu.edu.au/40593/>

### What the residual vector leaves out

`crosses/90` is excluded from the v1 residual vector: a MAD z-score overstates
the rarity of large values for a zero-inflated count, so its scores aren't on a
comparable surprise scale with the other metrics. The correct treatment is an
exposure-adjusted count model, deferred.

The symptom was that it drove 7 of the top 20 while being unscoreable for 52% of
player-matches — most players never cross, so their MAD is zero, and the
occasional crossers have a baseline like `0, 0, 1, 1` whose MAD of 0.5 is the
coarsest non-zero value the metric can produce. An 11-cross match divided by
that reads z = 14; a count model puts the same match at 5.6, and the empirical
tail at about 3.2.

`crosses` remains in the mart as a count. It is the per-90 residual that is
withdrawn, not the measurement.

**Position.** Ellens's positional metrics need tracking data — centroid distance
and lateral spread cannot be derived from events. The proxies here are
`touches_in_defensive_third_per_90` and `mean_action_x`, which is why
`relocate_upfield` moves touches rather than the player. Tracking data is a
derived requirement, not a nice-to-have.

### Open questions

- **Recoveries have no outcome at all** in the source: no accurate tag is ever
  written for them. They cannot join a success rate on any definition.
- **Per 90 is an analysis-layer step, not a mart column.** The mart stores
  per-match counts; `baseline.prepare` divides the three volume metrics by
  exposure at read time. Any other consumer of the mart gets counts, and
  comparing a substitute with a starter needs the rate.
- **The short goal-kick threshold is read off a curve.** `end_x < 0.3` is where
  retention breaks, 95% below and 57% above. Nobody has checked it against a
  football definition — whether the ball reached the kicking team's own half, say.

## Analysis

`fis.warehouse` is the only sanctioned input for analysis code:

```python
from fis import warehouse

warehouse.mart_names()
# ['fct_player_match_metrics']

warehouse.mart("fct_player_match_metrics")
# 53,719 rows x 16 columns -> DataFrame

warehouse.mart("fct_player_match_metrics", columns=["player_id", "pass_completion_pct"])
```

The analysis entry points all read the mart through it: `fis-baseline`
(publishes flags), `fis-injection-test` (sensitivity harness),
`fis-report` (Phase 2 tables, written to `data/reports/`),
`fis-feature-sweep` (leave-one-variable-out arms).

Every failure names the remedy rather than surfacing a duckdb traceback. Asking
for a column that does not exist:

```
Mart 'fct_player_match_metrics' has no column(s): xg_conceded.
  Available: match_id, player_id, team_id, actions, passes, passes_completed, ...
  Fix: a missing column is a missing dbt model, not a backwards
       reach. Add it to warehouse/models/marts/fct_player_match_metrics.sql and
       run `pixi run ingest && pixi run build`.
```

Asking for a mart that does not exist:

```
No mart 'mart_match_summary' in schema 'main_marts'.
  Available: fct_player_match_metrics
  Fix: a missing mart is a missing dbt model. Add
       warehouse/models/marts/mart_match_summary.sql, then run `pixi run ingest && pixi run build`.
  Do NOT read data/parquet/ from analysis -- see the stage rule in README.
```

## Development

```bash
pixi run lint            # ruff, including the stage-rule bans
pixi run hooks           # every pre-commit hook, across all files
pixi run test            # fast tests
pixi run test-all        # adds the slow pass over all 1941 matches
```

Or the underlying commands directly — see the table under
[Environment](#environment).

Tests needing the dataset or a built warehouse skip themselves when it is
absent, so the suite works on a fresh clone. CI runs them that way — what still executes there is the
check that our period mapping agrees with kloppy's, which is the one guarding
against a silent change to ingested data.

`ruff format` is the formatter — there is no black hook, since running both means
two tools fighting over the same files. Prettier handles YAML, JSON and Markdown;
SQL is left alone, as prettier has no dbt-jinja support. `check-added-large-files`
caps additions at 1 MB so the 255 MiB dataset can never reach a commit.

CI runs the same `.pre-commit-config.yaml`, so the hook and the pipeline cannot
drift apart.

## Layout

```
src/fis/
├── paths.py                  path resolution — single source of truth
├── warehouse.py              mart access — the only input for analysis
├── data/wyscout.py           dataset fetch    -> fis-fetch
├── data/figshare.py          reference tables -> data/json
├── data/audit.py             post-download checks, scoped by dataset
├── data/dbt_docs.py          publisher field docs -> dbt doc blocks
├── ingest/wyscout.py         JSON -> parquet  -> fis-ingest
├── ingest/kloppy_workarounds.py   repairs for four deserialisation defects
└── analysis/                 reads marts only; ruff.toml enforces it
    ├── baseline.py           per-player residuals, EB shrinkage -> fis-baseline
    ├── heldout.py            leave-one-out census, forests, bars
    ├── injection_test.py     injection mechanisms + harness -> fis-injection-test
    ├── report.py             the Phase 2 tables            -> fis-report
    └── feature_sweep.py      leave-one-variable-out arms    -> fis-feature-sweep
warehouse/
├── dbt_project.yml           dbt project
├── profiles.yml              duckdb target
├── macros/                   reusable SQL, e.g. the unicode decoder
├── models/{staging,intermediate,marts,audit}
└── tests/                    singular tests, plus tests/generic/
utils/                        thin shell wrapper around fis-fetch
.github/workflows/ci.yml      lint + package/dbt-parse
```

## Status

One vertical slice, end to end. Fetch, ingest, the dbt wiring and the stage-rule
enforcement work and are tested; 14 staging models, 2 intermediate and
`fct_player_match_metrics` build from a single `dbt build`.

The slice is deliberately thin — enough metrics to prove the spine, not the full
set. What it has cost more than it looks: the ingest carries four workarounds for
kloppy defects, one of which was silently deleting 4,400 events, and two of the
metric definitions turn on Wyscout conventions that are documented nowhere. Those
are written up where they bite, not collected in one place.

A scoring layer sits on top of the mart (`src/fis/analysis/`) — per-player
residuals with empirical-Bayes shrinkage at three levels (location, scale,
covariance), a leave-one-out census with Mahalanobis and isolation-forest
scorers in both raw and residual space, and a sigma-calibrated injection
harness for measuring detector sensitivity.

The estimator work is settled as of 2026-08-26: match-count gates replaced by
continuous shrinkage plus a stated evaluation floor (`MIN_PLAYER_MATCHES = 5`,
a policy decision rather than an estimator threshold), and every remaining
hyperparameter estimated rather than asserted. `fis-report` renders the
sensitivity tables to markdown; `fis-baseline` publishes
`fct_player_match_flags`.
