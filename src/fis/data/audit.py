"""Content checks for downloaded datasets, and what any damage actually costs.

Checksums verify *transfer*, not *content*. They confirmed referees.json arrived
exactly as published -- and it is published truncated. This module covers the
class of problem a checksum cannot see: files that will not parse, and
identifiers referenced by one file but missing from another.

Every finding carries an **impact**: not "10 officials are missing" but "10
officials covering 39 of 7942 assignments, so a referee dimension will be null
for 0.5% of them". A count without a denominator is not actionable.

Checks are registered per dataset, so ``audit("wyscout", root)`` is the whole
interface and a second dataset is a new entry in ``REGISTRY``, not new plumbing.

On the division of labour: the structural check belongs here because a file that
will not parse blocks dbt entirely. The coverage checks are prototypes -- once
staging models exist they are better expressed as dbt ``relationships`` tests,
which is where a reviewer expects to find them. See TODO.md.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ERROR = "error"
WARNING = "warning"
OK = "ok"


@dataclass(frozen=True)
class Finding:
    level: str
    check: str
    message: str
    impact: str = ""


CheckFn = Callable[[Path], list["Finding"]]


def _load(root: Path, name: str):
    return json.loads((root / name).read_text(encoding="utf8"))


def _matches(root: Path) -> list[dict]:
    out: list[dict] = []
    for path in sorted(root.glob("matches_*.json")):
        out.extend(json.loads(path.read_text(encoding="utf8")))
    return out


def check_files_parse(root: Path) -> list[Finding]:
    """Every JSON file must parse. Anything that does not blocks dbt outright."""
    bad = []
    # .as-published siblings are the damaged originals, kept deliberately.
    for path in sorted(root.glob("*.json")):
        if path.name.startswith(".") or ".as-published" in path.name:
            continue
        try:
            json.loads(path.read_text(encoding="utf8"))
        except ValueError:
            bad.append(path.name)
    if bad:
        return [
            Finding(
                ERROR,
                "files-parse",
                f"{len(bad)} file(s) do not parse: " + ", ".join(bad),
                "dbt cannot read these at all; every model downstream of them fails.",
            )
        ]
    return [Finding(OK, "files-parse", "all reference files parse")]


#: A literal backslash-u-XXXX left in the text. The publisher double-escaped
#: non-ASCII, so json parsing yields the escape sequence rather than the
#: character: "Bayern M\\u00fcnchen" instead of "Bayern München".
_LITERAL_ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}")


def check_unicode_escapes(root: Path) -> list[Finding]:
    """Names published double-escaped, so the accents never decode."""
    worst: list[tuple[str, int, int]] = []
    for path in sorted(root.glob("*.json")):
        if path.name.startswith(".") or ".as-published" in path.name:
            continue
        try:
            records = json.loads(path.read_text(encoding="utf8"))
        except ValueError:
            continue  # reported by check_files_parse
        if not isinstance(records, list):
            continue
        hits = sum(1 for r in records if _LITERAL_ESCAPE.search(json.dumps(r)))
        if hits:
            worst.append((path.name, hits, len(records)))

    if not worst:
        return [Finding(OK, "unicode-escapes", "no double-escaped names")]

    affected = sum(h for _, h, _ in worst)
    total = sum(t for _, _, t in worst)
    detail = ", ".join(f"{n} {h}/{t}" for n, h, t in sorted(worst, key=lambda x: -x[1])[:4])
    return [
        Finding(
            WARNING,
            "unicode-escapes",
            f"{affected} of {total} records across {len(worst)} files carry literal \\uXXXX",
            f"{100 * affected / total:.0f}% of names will not render "
            f'("Bayern M\\u00fcnchen" not "Bayern München"); decode in staging. {detail}',
        )
    ]


def _coverage(
    check: str,
    referenced: dict[int, int],
    present: set[int],
    entity: str,
    unit: str,
    consequence: str,
) -> Finding:
    """Compare ids referenced against ids present, and price the difference."""
    missing = {i: n for i, n in referenced.items() if i not in present}
    total = sum(referenced.values())
    if not missing:
        return Finding(
            OK, check, f"all {len(referenced)} referenced {entity} present ({total} {unit})"
        )
    affected = sum(missing.values())
    pct = 100 * affected / total if total else 0
    shown = ", ".join(str(i) for i in sorted(missing)[:8])
    return Finding(
        WARNING,
        check,
        f"{len(missing)} of {len(referenced)} referenced {entity} have no entry",
        f"{affected} of {total} {unit} ({pct:.1f}%) — {consequence} "
        f"Missing ids: {shown}" + (" ..." if len(missing) > 8 else ""),
    )


def _tally(pairs) -> dict[int, int]:
    out: dict[int, int] = {}
    for value in pairs:
        if value:  # 0 is Wyscout's "unknown" placeholder, not a real id
            out[value] = out.get(value, 0) + 1
    return out


def check_referee_coverage(root: Path) -> list[Finding]:
    referenced = _tally(
        ref.get("refereeId") for match in _matches(root) for ref in (match.get("referees") or [])
    )
    present = {r["wyId"] for r in _load(root, "referees.json")}
    return [
        _coverage(
            "referee-coverage",
            referenced,
            present,
            "officials",
            "assignments",
            "a referee dimension will not resolve them.",
        )
    ]


def check_team_coverage(root: Path) -> list[Finding]:
    referenced = _tally(
        team.get("teamId")
        for match in _matches(root)
        for team in (match.get("teamsData") or {}).values()
    )
    present = {t["wyId"] for t in _load(root, "teams.json")}
    return [
        _coverage(
            "team-coverage",
            referenced,
            present,
            "teams",
            "match sides",
            "team names will be null.",
        )
    ]


def check_coach_coverage(root: Path) -> list[Finding]:
    referenced = _tally(
        team.get("coachId")
        for match in _matches(root)
        for team in (match.get("teamsData") or {}).values()
    )
    present = {c["wyId"] for c in _load(root, "coaches.json")}
    return [
        _coverage(
            "coach-coverage",
            referenced,
            present,
            "coaches",
            "match sides",
            "coach names will be null.",
        )
    ]


def check_competition_coverage(root: Path) -> list[Finding]:
    referenced = _tally(match.get("competitionId") for match in _matches(root))
    present = {c["wyId"] for c in _load(root, "competitions.json")}
    return [
        _coverage(
            "competition-coverage",
            referenced,
            present,
            "competitions",
            "matches",
            "competition names will be null.",
        )
    ]


def check_match_event_coverage(root: Path) -> list[Finding]:
    """Matches listed in the reference data vs per-match event files on disk."""
    from fis.data.wyscout import match_files

    listed = {m["wyId"] for m in _matches(root)}
    on_disk = {int(p.stem) for p in match_files() if p.stem.isdigit()}
    if not on_disk:
        return [Finding(WARNING, "match-event-coverage", "no event files found; run the fetch")]
    missing, extra = listed - on_disk, on_disk - listed
    if not missing and not extra:
        return [
            Finding(OK, "match-event-coverage", f"all {len(listed)} listed matches have events")
        ]
    return [
        Finding(
            WARNING,
            "match-event-coverage",
            f"{len(missing)} listed matches have no event file, {len(extra)} event files unlisted",
            "matches without events cannot produce event-derived signals.",
        )
    ]


REGISTRY: dict[str, tuple[CheckFn, ...]] = {
    "wyscout": (
        check_files_parse,
        check_unicode_escapes,
        check_referee_coverage,
        check_team_coverage,
        check_coach_coverage,
        check_competition_coverage,
        check_match_event_coverage,
    ),
}


def audit(dataset: str, root: Path | None = None) -> list[Finding]:
    """Run every registered check for ``dataset``."""
    if dataset not in REGISTRY:
        raise KeyError(f"no checks registered for {dataset!r}; known: {sorted(REGISTRY)}")
    if root is None:
        from fis.paths import json_dir

        root = json_dir()
    findings: list[Finding] = []
    for check in REGISTRY[dataset]:
        try:
            findings.extend(check(Path(root)))
        except Exception as exc:  # a broken check must not hide the other findings
            findings.append(Finding(ERROR, check.__name__, f"check itself failed: {exc!r}"))
    return findings


def format_report(findings: list[Finding], *, verbose: bool = False) -> str:
    """Human-readable summary. Quiet when everything is fine."""
    marks = {ERROR: "ERROR", WARNING: "WARN", OK: "ok"}
    lines = []
    for f in findings:
        if f.level == OK and not verbose:
            continue
        lines.append(f"  [{marks[f.level]}] {f.check}: {f.message}")
        if f.impact:
            lines.append(f"         impact: {f.impact}")
    errors = sum(f.level == ERROR for f in findings)
    warnings = sum(f.level == WARNING for f in findings)
    if not lines:
        return f"Data audit: {len(findings)} checks passed."
    return "\n".join(
        [f"Data audit: {errors} error(s), {warnings} warning(s), {len(findings)} checks.", *lines]
    )
