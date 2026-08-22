# football-integrity-signals

Package to get familiar with match and player data.

Fetches a public Wyscout event dataset, normalises it into one parquet file per
match, and gives a duckdb/dbt warehouse to build match-integrity signals on top of.

## Stage rule

Each stage reads only the output of the one before it:

| Stage               | Reads            | Writes                    |
| ------------------- | ---------------- | ------------------------- |
| `fis-fetch-wyscout` | upstream GitHub  | `data/download/`          |
| `src/fis/ingest/`   | `data/download/` | `data/parquet/`           |
| `warehouse/`        | `data/parquet/`  | marts (duckdb)            |
| `analysis/`         | marts            | figures, tables, findings |

**Nothing in `analysis/` touches raw JSON — a missing column there means a missing
dbt model, not a backwards reach.**

The rule earns its keep at exactly the moment it is inconvenient. Reaching back to
`data/parquet/` (or worse, the JSON) from an analysis script is always the faster
fix in the moment, and it is how the warehouse quietly stops being the source of
truth: two definitions of the same quantity drift apart, and neither is wrong
anywhere you can see. If a mart lacks a column, add it to the mart.

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

## Prerequisites

[pixi](https://pixi.sh) manages the environment, including Python itself, so it
cannot be installed from this repository:

```bash
curl -fsSL https://pixi.sh/install.sh | sh   # macOS / Linux
brew install pixi                            # macOS, via Homebrew
winget install prefix-dev.pixi               # Windows
```

Alternatively `pip install -e ".[warehouse,analysis]"` into an environment you
manage yourself. CI exercises that path on every push, so it is known to resolve.

## Install

```bash
pixi install
pixi run hooks-install   # once per clone: installs the pre-commit hook
```

This provisions the conda environment and installs the package itself in editable
mode, which puts the console scripts on your `PATH`.

## Quick start

```bash
fis-fetch-wyscout      # download the dataset  (~255 MiB, 1941 matches)
fis-ingest-wyscout     # convert JSON -> parquet
```

Or via pixi tasks, without activating the environment:

```bash
pixi run fetch
pixi run ingest
```

Both commands are idempotent — re-running skips work that is already done. To
ingest a handful of matches while iterating:

```bash
fis-ingest-wyscout --limit 10
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
├── download/wyscout/processed-v2/files/*.json   # upstream, immutable, disposable
└── parquet/events_<match_id>.parquet            # our normalised output
```

Both are gitignored — everything under `data/` is reproducible from the two
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
fis-fetch-wyscout --commit <sha>          # one-off override
fis-fetch-wyscout --force                 # re-download regardless
fis-fetch-wyscout --dest /scratch/wyscout # somewhere else entirely
```

## Ingest

Each match is loaded with [kloppy](https://github.com/PySport/kloppy) and
transformed to `ACTION_EXECUTING_TEAM` orientation before anything else — without
that, every spatial metric is noise. kloppy's frame covers a single match and
carries no match id, so one is added as a `match_id` column, which everything
downstream keys on.

One bad match never aborts the run; failures are collected and reported at the end.

### Deserialisation workarounds

38 of the 1941 matches will not load with a plain `kloppy.wyscout.load`. Three
distinct defects are responsible, repaired in
[src/fis/ingest/kloppy_workarounds.py](src/fis/ingest/kloppy_workarounds.py):

| Defect                | Files | Cause                                           |
| --------------------- | ----- | ----------------------------------------------- |
| `extra-time-period`   | 10    | kloppy: `deserializer_v2` evaluates `int("E1")` |
| `shot-as-final-event` | 6     | kloppy: `_parse_shot` lookahead is unguarded    |
| `null-roster-entry`   | 22    | upstream data: a `null` entry in `players`      |

**Repairs are applied lazily and specifically.** Every match is first loaded
normally; only a failure matching a known signature triggers a repair and a
retry. An unrecognised error is re-raised untouched, so a new defect surfaces as
a failure rather than being silently absorbed. The ~98% of matches that load
cleanly are never touched — no JSON is re-parsed and no monkeypatch is installed.

Two of the defects raise an identical
`TypeError: 'NoneType' object is not subscriptable`, so they are told apart by
the kloppy function on the traceback, not by the message. That also means a
kloppy restructure stops matching anything and the error surfaces, instead of a
stale patch mis-firing.

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

**These workarounds are meant to die.** Because repairs run only after a
failure, an upstream fix would make them silently unreachable.
`tests/test_kloppy_workarounds.py` asserts each defect _still reproduces_ — when
kloppy fixes one, that test fails and tells you to delete the repair.

kloppy is pinned to `>=3.19,<3.20` for the same reason the dataset commit is
pinned: the parser version determines the ingested output as much as the input
data does.

## Warehouse

A self-contained duckdb + dbt project lives in `warehouse/`. The `raw.events`
source globs the parquet output via `external_location`, honouring `FIS_DATA_DIR`
so it follows the same path resolution as the Python code.

```bash
pixi run dbt-debug     # verify the connection and project config
pixi run build         # dbt build
```

Run dbt from the repository root. Its relative paths — the duckdb file in
`warehouse/profiles.yml` and the parquet glob in `_sources.yml` — resolve against
the working directory rather than the project directory, and pixi always runs
tasks from the manifest directory. The pixi tasks pass `--project-dir warehouse
--profiles-dir warehouse` for you.

## Analysis

`fis.warehouse` is the only sanctioned input for analysis code:

```python
from fis import warehouse

warehouse.mart_names()                                  # what is built
warehouse.mart("mart_match_summary")                    # -> DataFrame
warehouse.mart("mart_match_summary", columns=["xg"])    # validated selection
```

Every failure names the remedy rather than surfacing a duckdb traceback:

```
Mart 'mart_match_summary' has no column(s): xg_conceded.
  Available: match_id, events
  Fix: a missing column is a missing dbt model, not a backwards
       reach. Add it to warehouse/models/marts/mart_match_summary.sql and
       run `pixi run ingest && pixi run build`.
```

## Development

```bash
pixi run lint            # ruff, including the stage-rule bans
pixi run hooks           # every pre-commit hook, across all files
pixi run test            # fast tests
pixi run test-all        # adds the slow pass over all 1941 matches
```

Tests needing the dataset skip themselves when it is absent, so `pixi run test`
works on a fresh clone. CI runs them that way — what still executes there is the
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
├── data/wyscout.py           dataset fetch    -> fis-fetch-wyscout
├── ingest/wyscout.py         JSON -> parquet  -> fis-ingest-wyscout
└── analysis/                 reads marts only; ruff.toml enforces it
warehouse/
├── dbt_project.yml           dbt project
├── profiles.yml              duckdb target
└── models/{staging,intermediate,marts}
utils/                        thin shell wrapper around fis-fetch-wyscout
.github/workflows/ci.yml      lint + package/dbt-parse
```

## Status

Early. Fetch, ingest, the dbt wiring and the stage-rule enforcement all work and
are tested end to end. No signal models exist yet: `staging/` holds only the
source definition, and `intermediate/` and `marts/` are empty — so
`warehouse.mart_names()` returns nothing until you add one.
