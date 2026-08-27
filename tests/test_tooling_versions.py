"""The three places ruff is declared must agree.

The lint gate is ruff's DEFAULT rule set, which grew from 62 rules to 416
between 0.9 and 0.16. So the version IS the rule selection, and three
declarations that can drift apart mean the hook, the pixi environment and a pip
install enforce three different standards -- which is what happened: pre-commit
pinned 0.9.1 while the pixi environment resolved 0.16.4, and code that passed
locally had 38 findings under the other.

Pinning alone would not have caught it. This does.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _pixi() -> str:
    pinned = tomllib.loads((ROOT / "pixi.toml").read_text())["dependencies"]["ruff"]
    return pinned.lstrip("=")


def _pyproject() -> str:
    dev = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    spec = next(d for d in dev["dev"] if d.startswith("ruff"))
    return spec.split("==", 1)[1]


def _pre_commit() -> str:
    text = (ROOT / ".pre-commit-config.yaml").read_text()
    match = re.search(r"ruff-pre-commit\s*\n\s*rev:\s*v?([0-9][^\s]*)", text)
    assert match, "no ruff hook rev found in .pre-commit-config.yaml"
    return match.group(1)


def test_every_declaration_pins_the_same_ruff():
    """A range in any of them is also a failure: '>=0.6' resolves differently in
    each environment, which is how 0.9.1 and 0.16.4 ended up side by side."""
    found = {
        "pixi.toml": _pixi(),
        "pyproject.toml": _pyproject(),
        ".pre-commit-config.yaml": _pre_commit(),
    }
    assert len(set(found.values())) == 1, f"ruff versions disagree: {found}"
    for where, version in found.items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), (
            f"{where} pins a range, not a version: {version}"
        )


def test_the_environments_ruff_matches_the_pin():
    """ruff is a binary, not an importable module, so ask it.

    The PROJECT's ruff, not whatever is on PATH: a contributor may have any
    version installed globally and the project does not control it. Skipped
    where neither is present, since that is not something to fail over.
    """
    env = ROOT / ".pixi" / "envs" / "default" / "bin" / "ruff"
    binary = str(env) if env.exists() else shutil.which("ruff")
    if binary is None:
        pytest.skip("no ruff in the project environment or on PATH")
    reported = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, check=True
    ).stdout.split()[-1]
    assert reported == _pixi(), (
        f"{binary} is {reported}, the project pins {_pixi()} -- run `pixi install`. "
        "The gate is the DEFAULT rule set, so a different binary enforces a "
        "different standard."
    )
