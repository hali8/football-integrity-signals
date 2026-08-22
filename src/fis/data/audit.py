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

On the division of labour: what stays here is what must be known *before* dbt
runs. A file that will not parse blocks dbt entirely, and names that will not
render are a property of the bytes rather than of any model.

The referential checks that used to live here are now dbt ``relationships``
tests in ``warehouse/models/staging/_models.yml`` -- foreign keys belong next to
the models they constrain, where a reviewer expects them and where they run on
every build rather than only after a download.
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


REGISTRY: dict[str, tuple[CheckFn, ...]] = {
    "wyscout": (
        check_files_parse,
        check_unicode_escapes,
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
