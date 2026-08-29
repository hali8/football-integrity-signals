"""The report tables: detection at two thresholds, and scorer agreement.

Two detection tables -- one per scorer family, max|z| in both -- and
the Phase 2c agreement matrices. Every number comes from
:func:`injection_test.cell_statistics`, so the tables and the sweep's text
summary cannot disagree; a second implementation of the same statistic is what
let a wrong estimator look verified.

Bars are DERIVED from the scored population at run time, never hardcoded.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fis import paths
from fis.analysis import baseline, heldout, injection_test

#: Categorical slots 1-4 of the reference dataviz palette, in its validated
#: adjacent order; a scorer keeps its hue in every chart.
SERIES_COLOR = {
    "max": "#2a78d6",
    "mahalanobis": "#eb6834",
    "mahalanobis_res": "#eb6834",
    "forest": "#1baf7a",
    "forest_res": "#1baf7a",
    "forest_norm": "#eda100",
    "forest_res_norm": "#eda100",
}
#: Blue sequential ramp (steps 100-550) for the agreement heatmaps.
SEQ_RAMP = ("#cde2fb", "#86b6ef", "#3987e5", "#1c5cab")
_INK, _INK2, _SURFACE, _GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e6e5e2"


#: max|z| is in both tables: the simplest scorer, so the baseline the others
#: must beat. Residual-space by construction, so its place in DIRECT is a choice.
SHARED = ("max",)
#: Both forest readings appear: the raw isolation score and the score
#: normalised against its own fit's training rows. They rank the same fit but
#: not identically, and the normalised one is the only form comparable across
#: players whose fits borrowed different amounts.
DIRECT = SHARED + ("mahalanobis", "forest", "forest_norm")
RESIDUAL = SHARED + ("mahalanobis_res", "forest_res", "forest_res_norm")

#: Every unique rule, in table order -- what the agreement matrices span.
EVERY_TALLY = DIRECT + tuple(s for s in RESIDUAL if s not in DIRECT)

#: 1% is what ships; 5% is above the gate's ceiling and asterisks itself.
RATES = (0.01, 0.05)

#: Below this, one player moves a cell by ten points or more, so the grid
#: measures its own sample rather than the scorers. Such cuts report a count
#: instead -- GK is thin enough that it will normally be one of them.
MIN_MATRIX_PLAYERS = 10


#: Stamped into the rendered markdown so staleness is detectable without the
#: warehouse: ANALYSIS covers the code behind the results, RENDER this module,
#: RUNTIME the installed numerical environment, RESULTS the payload parquet.
#: They fail differently -- see freshness().
ANALYSIS_STAMP = "fis-analysis"
RENDER_STAMP = "fis-render"
RUNTIME_STAMP = "fis-runtime"
RESULTS_STAMP = "fis-results"
#: Column and scorer renames, applied ONLY under --stale-ok so an artefact from
#: before a rename can still be rendered. Never on the normal path, where the
#: stamp refuses stale input outright.
LEGACY_RENAMES = {"mahalanobis_z": "mahalanobis_res"}


#: The one string both the banner and the pre-push hook test for.
STALE_MARKER = "These numbers are stale"
#: Delimits the block the render OWNS in the README. Prose outside it is the
#: author's; numbers inside it come from the run, so they cannot go stale by
#: being hand-copied -- which is how a wrong figure got published once.
SUMMARY_OPEN = "<!-- fis-summary:start -->"
SUMMARY_CLOSE = "<!-- fis-summary:end -->"
#: Ends the block the README lifts. Everything after it -- what the scorers see,
#: the injection map, calibration -- belongs to the report alone.
HEADLINE_END = "<!-- fis-headline:end -->"
# Worded to the antecedent: a source hash knows the code changed, not that a
# number moved.
STALE_BANNER = (
    f"> **⚠ {STALE_MARKER}.** The analysis code has changed since they were "
    "produced, so they may no longer describe the current detector. "
    "Regenerate with `fis-report --forest --jobs -1`.\n"
)


def _runtime() -> str:
    """Installed versions of the numerical path -- what moves a result with no
    source change. Versions, not constraints; environments, not machines."""
    from importlib import metadata

    parts = [f"python={sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"]
    for name in ("numpy", "pandas", "scipy", "scikit-learn", "joblib", "pyarrow", "matplotlib"):
        try:
            parts.append(f"{name}={metadata.version(name)}")
        except metadata.PackageNotFoundError:
            parts.append(f"{name}=absent")
    return ",".join(parts)


def _stamps(stale: bool = False, results_stamp: str | None = None) -> dict[str, str]:
    """Current hashes for everything a rendered report depends on.

    ``stale`` poisons the analysis stamp so a report rendered from rejected
    results cannot pass --check. ``results_stamp`` pins the payload consumed.
    """
    stamps = {
        ANALYSIS_STAMP: "stale" if stale else heldout._code_fingerprint((injection_test,)),
        RENDER_STAMP: heldout._code_fingerprint((sys.modules[__name__],)),
        RUNTIME_STAMP: _runtime(),
    }
    if results_stamp is not None:
        stamps[RESULTS_STAMP] = "stale" if stale else results_stamp
    return stamps


def freshness(text: str, results: Path | None = None) -> tuple[str, str]:
    """Classify a rendered report against the code and payload as they stand.

    Returns (state, detail): fresh | render | analysis | runtime | payload |
    unknown. Split because they cost different amounts to fix: a render is
    seconds, analysis and runtime invalidate the results, and payload means
    the backing results are gone or are not the stamped ones.

    ``results`` is checked only where its directory exists -- a checkout without
    the warehouse cannot tell "deleted" from "never fetched".
    """
    now = _stamps()
    found = {
        k: v
        for k, v in (
            line.removeprefix("<!-- ").removesuffix(" -->").split("=", 1)
            for line in text.splitlines()
            # "=" required: markers share the fis- prefix but carry no value.
            if line.startswith("<!-- fis-") and "=" in line
        )
    }
    if not found:
        return "unknown", "no stamp: rendered before freshness tracking existed"
    if found.get(ANALYSIS_STAMP) != now[ANALYSIS_STAMP]:
        return "analysis", (
            "the estimator or injection code has changed since these results "
            "were saved, so they may no longer describe it -- a full campaign "
            "re-run is needed"
        )
    if RUNTIME_STAMP in found and found[RUNTIME_STAMP] != now[RUNTIME_STAMP]:
        was = dict(p.split("=", 1) for p in found[RUNTIME_STAMP].split(",") if "=" in p)
        is_ = dict(p.split("=", 1) for p in now[RUNTIME_STAMP].split(",") if "=" in p)
        drift = [
            f"{k} {was.get(k, '?')}→{is_.get(k, '?')}" for k in is_ if was.get(k) != is_.get(k)
        ]
        return "runtime", (
            f"the numerical environment changed ({', '.join(drift)}) -- the same "
            "source can now produce different numbers, so re-run or restore the pinned environment"
        )
    stamped_payload = found.get(RESULTS_STAMP)
    if stamped_payload and results is not None and results.parent.exists():
        if not results.exists():
            return "payload", (
                f"the stamped results payload is missing at {results} -- the report "
                "presents numbers whose backing no longer exists; re-run the campaign"
            )
        import pyarrow.parquet as pq

        held = (pq.read_schema(results).metadata or {}).get(b"fis_fingerprint", b"").decode()
        if held != stamped_payload:
            return "payload", (
                f"the results at {results} are not the ones this report was rendered "
                "from -- re-render from the right payload or re-run"
            )
    if found.get(RENDER_STAMP) != now[RENDER_STAMP]:
        return "render", "only the renderer changed -- re-render from the saved results"
    return "fresh", "matches the code as it stands"


def _clear_banner(text: str) -> str:
    """Drop the stale warning, however it was worded.

    Matching the generated string exactly meant a hand-edited banner never
    cleared, so the warning outlived the re-run that answered it.
    """
    lines = text.splitlines(keepends=True)
    kept = [ln for ln in lines if STALE_MARKER not in ln]
    if len(kept) == len(lines):
        return text
    out = "".join(kept)
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out


def _put_summary(text: str, scored: pd.DataFrame, rendered: str) -> str:
    """Rewrite the README block the render owns, if the markers are there.

    The numbers are LIFTED from the rendered report rather than recomputed, so
    the README cannot disagree with the tables it links to.
    """
    if SUMMARY_OPEN not in text or SUMMARY_CLOSE not in text:
        return text
    body = rendered.partition("## Headline\n")[2]
    # The marker is the boundary; the fold is the fallback for older renders.
    body = body.split(HEADLINE_END, 1)[0].split("\n<details>", 1)[0].strip()
    block = (
        f"{SUMMARY_OPEN}\n\n"
        f"One full-population run: {len(scored):,} player-matches, "
        f"{scored['player_id'].nunique():,} players.\n\n"
        f"{body}\n\n"
        f"{SUMMARY_CLOSE}"
    )
    head, _, rest = text.partition(SUMMARY_OPEN)
    _, _, tail = rest.partition(SUMMARY_CLOSE)
    return head + block + tail


def _fold(title: str, body: str) -> str:
    """A GitHub-collapsible section. The blank line after </summary> is what
    makes GitHub render the body as markdown; without it a table is prose."""
    return f"\n<details>\n<summary><b>{title}</b></summary>\n\n{body.lstrip(chr(10))}\n\n</details>"


def _context(scored: pd.DataFrame, rates: tuple[float, ...], headline) -> str:
    """Provenance, so the first grid is not the first thing a reader sees."""
    from datetime import UTC, datetime

    mechanism, severity = headline
    bars = " and ".join(f"{r:.0%}" for r in sorted(rates))
    return (
        f"`fis-report`, {datetime.now(UTC).date().isoformat()}. "
        f"{len(scored):,} player-matches / {scored['player_id'].nunique():,} players; "
        f"severity ladder k = {injection_test.SEVERITIES}; bars at {bars}; "
        f"agreement matrices on `{mechanism}:{severity:g}`."
    )


def experiment_note() -> str:
    """What the scorers see, and where the injection actually lands.

    Different spaces on purpose: scorers read the metrics, mechanisms move the
    counts underneath, so a metric shift is a consequence and never an edit.
    """
    rates = ", ".join(f"`{m}`" for m in baseline.RATE_METRICS)
    volumes = ", ".join(f"`{m}_per_90`" for m in baseline.VOLUME_METRICS)
    return "\n".join(
        [
            (
                f"**What the scorers see.** Six per-match metrics — {rates}, "
                f"{volumes} — or their leave-one-out per-player residuals: "
                "max|z| and the `_res` scorers read the residual z's, "
                "`mahalanobis` and `forest` the metric vector directly."
            ),
            "",
            (
                "**Where the injection lands.** Never on those metrics: each "
                "mechanism moves hidden action counts — events a manipulator "
                "actually controls — and every metric is re-derived from what "
                "survives. What the scorer sees move is downstream of that:"
            ),
            "",
            "| hidden variable moved | mechanism | what the scorer sees move |",
            "|---|---|---|",
            (
                "| `defensive_actions` — the total, interceptions included | "
                "`remove_defensive` | `defensive_actions_per_90` ↓; the success "
                "rate is re-drawn over the survivors and barely shifts, because a "
                "hypergeometric removal takes successes in proportion |"
            ),
            (
                "| `touches_in_defensive_third` **and** the x-position of the "
                "player's actions (`sum_start_x_in_defensive_third`) — **two "
                "variables that can only move together**: a touch relocated out of "
                "the defensive third is, by identity, both one fewer touch there "
                "and more of the player's action mass further upfield | "
                "`relocate_upfield` | `touches_in_defensive_third_per_90` ↓ and "
                "`mean_action_x` ↑, jointly |"
            ),
            (
                "| `defensive_actions_successful` | `defensive_success` | "
                "`defensive_action_success_pct` ↓ (attempts frozen) |"
            ),
            (
                "| `passes_completed` | `pass_completion` | `pass_completion_pct` ↓ "
                "(`passes` volume frozen) |"
            ),
            "",
            (
                "Five hidden variables over four channels. They are not five "
                "independent knobs: the counts overlap by set membership — "
                "`defensive_actions_successful` nests inside `defensive_actions`, "
                "and about a quarter of defensive-third touches ARE defensive "
                "actions — so `remove_defensive` moves part of what the other "
                "channels control. The coordinated condition splits k across the "
                "four in quadrature and applies them in a fixed order, re-sizing "
                "each against the state the previous one left, rather than "
                "pretending they are simultaneous and independent. "
                "`throttle_defensive` drives the same variable as "
                "`defensive_success`, as a fraction of successes lost rather than "
                "k·σ, so it is excluded from the composition."
            ),
        ]
    )


def calibration_note(scored: pd.DataFrame, census: pd.DataFrame, bars: dict, rate: float) -> str:
    """The bug check: every derived bar must flag ``rate`` of the clean census.

    One sentence when they all do, the per-scorer list when one deviates.
    """
    flagged = baseline.flag(scored, rate)
    shares = {"max": float(flagged["is_flagged"].mean())}
    for name in injection_test.SCORERS + injection_test.FOREST_SCORERS:
        if name == "max" or name not in census:
            continue
        column = census[name].dropna()
        if len(column) and np.isfinite(bars.get(name, np.nan)):
            shares[name] = float((column >= bars[name]).mean())
    worst = max(abs(v - rate) for v in shares.values())
    if worst < 5e-4:
        return (
            f"Calibration: every derived bar flags {rate:.2%} of the clean census "
            f"(largest deviation {worst:.4%}), so the recovery columns are read "
            "against a true base rate."
        )
    listed = "  ".join(f"{k} {v:.4%}" for k, v in shares.items())
    return f"Calibration (target {rate:.2%}): {listed}"


def headline_summary(stats: pd.DataFrame, low: float, headline) -> str:
    """The result the tables exist to support, derived from THIS run's cells.

    Hardcoding it would be the delivered-rate mistake again: a summary that
    reads as measured while quietly describing an earlier population."""
    mechanism, severity = headline
    single = "pass_completion"

    def pick(tally: str, mech: str):
        row = stats[
            (stats.tally == tally) & (stats.mechanism == mech) & (stats.severity == severity)
        ]
        return row.iloc[0] if len(row) and np.isfinite(row.iloc[0].recovery) else None

    # Every unique scorer, not a chosen four: showing both forests while
    # showing one of the two mahalanobis scorers made the omission look like a
    # verdict. The normalised variants stay out -- they rank the same fits.
    tallies = [x for x in EVERY_TALLY if not x.endswith("_norm")]
    table = [
        f"| | single metric (`{single}`) | coordinated (all four) |",
        "|---|---:|---:|",
    ]

    def cell(r) -> str:
        if r is None:
            return "n/a"
        auc = f", auc {r.auc:.3f}" if np.isfinite(r.auc) else ""
        return f"{int(r.recovered):,}/{int(r.n):,} ({r.recovery:.1%}{auc})"

    for tally in tallies:
        a, b = pick(tally, single), pick(tally, mechanism)
        if a is None and b is None:
            continue
        label = "max\\|z\\|" if tally == "max" else tally
        table.append(f"| {label} | {cell(a)} | {cell(b)} |")

    # Only claimed when the forests are in the table.
    forest, univariate = pick("forest", mechanism), pick("max", mechanism)
    said_forest = forest is not None and pick("forest", single) is not None
    tail = (
        "The forests are weakest against a single metric and strongest against the coordinated one."
        if said_forest
        else ""
    )
    if said_forest and univariate is not None and univariate.recovery:
        tail += (
            f" On the coordinated injection the forest recovers "
            f"**{forest.recovery / univariate.recovery:.1f}× max|z|**."
        )
    # Recovery is a count past one cut; AUC ranks the whole distribution. When
    # they disagree the headline has to say so, or it reports the flattering one.
    scored = [(x, pick(x, mechanism)) for x in tallies]
    scored = [(x, r) for x, r in scored if r is not None and np.isfinite(r.auc)]
    if scored:
        by_bar = max(scored, key=lambda pair: pair[1].recovery)
        by_rank = max(scored, key=lambda pair: pair[1].auc)
        if by_bar[0] != by_rank[0]:
            lead = (
                " That is a statement about the bar, not about ranking: "
                if tail
                else "Recovery counts crossings of one cut; AUC ranks the whole distribution: "
            )
            tail += (
                f"{lead}`{by_rank[0]}` "
                f"ranks perturbed rows above clean ones more reliably (auc "
                f"{by_rank[1].auc:.3f} against `{by_bar[0]}`'s {by_bar[1].auc:.3f}), while "
                f"`{by_bar[0]}` moves fewer rows further past the cut."
            )
    return "\n".join(
        [
            "\n## Headline\n",
            (
                "**The best scorer depends on the manipulation** — recovery at the "
                f"{low:.0%} bar, k={severity:g}:"
            ),
            "",
            *table,
            "",
            tail,
        ]
    )


def _save_svg(fig, path: Path) -> None:
    """Deterministic SVG: no timestamp, fixed hash salt, text kept as text --
    a re-render of unchanged numbers must not produce a diff."""
    import matplotlib

    matplotlib.rcParams["svg.hashsalt"] = "fis"
    matplotlib.rcParams["svg.fonttype"] = "none"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="svg", metadata={"Date": None}, bbox_inches="tight")
    # Emit what the whitespace hooks would leave, so a fresh render is not
    # rewritten on every commit and stays byte-comparable with the tracked file.
    body = "\n".join(line.rstrip() for line in path.read_text().splitlines())
    path.write_text(body.rstrip("\n") + "\n")


def _styled(ax) -> None:
    ax.set_facecolor(_SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(_GRID)
    ax.grid(axis="y", color=_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=_INK2, labelsize=9)


def _plot_recovery(
    stats: pd.DataFrame, tallies: tuple[str, ...], mechanisms: list[str], path: Path
) -> None:
    """Recovery against dose, one panel per mechanism, one line per scorer."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        1,
        len(mechanisms),
        figsize=(4.4 * len(mechanisms), 3.4),
        sharey=True,
        facecolor=_SURFACE,
    )
    axes = [axes] if len(mechanisms) == 1 else list(axes)
    span = max(stats["recovery"].max() * 100, 1.0)
    for ax, mech in zip(axes, mechanisms):
        _styled(ax)
        rows = stats[stats.mechanism == mech]
        ends = []
        for tally in tallies:
            r = rows[rows.tally == tally].sort_values("severity")
            if r.empty:
                continue
            ax.plot(
                r["severity"],
                r["recovery"] * 100,
                color=SERIES_COLOR[tally],
                linewidth=2,
                marker="o",
                markersize=6,
                label=tally,
            )
            ends.append((r.iloc[-1]["severity"], r.iloc[-1]["recovery"] * 100, tally))
        # Dodge the end labels apart: lines that finish together otherwise
        # overprint their names.
        gap = span * 0.055
        placed = []
        for x, y, tally in sorted(ends, key=lambda e: e[1]):
            slot = y if not placed else max(y, placed[-1] + gap)
            placed.append(slot)
            ax.annotate(
                tally,
                (x, slot),
                textcoords="offset points",
                xytext=(6, -3),
                fontsize=8,
                color=_INK2,
            )
        ax.set_title(mech, fontsize=10, color=_INK)
        ax.set_xlabel("severity k", fontsize=9, color=_INK2)
        ax.set_ylabel("targets recovered (%)", fontsize=9, color=_INK2)
        # sharey keeps the panels comparable but strips every inner panel's tick
        # labels; put them back, or a panel read on its own has no scale.
        ax.tick_params(labelleft=True)
        ax.margins(x=0.18)
    axes[0].legend(frameon=False, fontsize=8, labelcolor=_INK2)
    _save_svg(fig, path)
    plt.close(fig)


def _plot_matrix(labels: list[str], values, texts, title: str, path: Path) -> None:
    """Agreement matrix as a shaded grid, the table's exact numbers in the
    boxes -- it replaces the raw grid rather than accompanying it."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("fis_seq", SEQ_RAMP)
    n = len(labels)
    fig, ax = plt.subplots(figsize=(1.2 + 0.8 * n, 1.0 + 0.62 * n), facecolor=_SURFACE)
    ax.imshow(values, cmap=cmap, vmin=0, vmax=100)
    ax.set_xticks(range(n), labels, rotation=45, ha="right", fontsize=8, color=_INK2)
    ax.set_yticks(range(n), labels, fontsize=8, color=_INK2)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for i in range(n):
        for j in range(n):
            v = values[i][j]
            ax.text(
                j,
                i,
                texts[i][j],
                ha="center",
                va="center",
                fontsize=7.5,
                color=_SURFACE if np.isfinite(v) and v > 55 else _INK,
            )
    ax.set_title(title, fontsize=10, color=_INK)
    _save_svg(fig, path)
    plt.close(fig)


def _slug(name: str) -> str:
    return name.replace("|", "").replace(" ", "_").lower()


def detection_section(
    per_rate: dict[float, pd.DataFrame],
    tallies: tuple[str, ...],
    title: str,
    headline_mechanism: str,
    plots_dir: Path | None,
) -> str:
    """A detection family: default plot, one fold per other comparison, and the
    raw table folded beneath -- the nearest GitHub gets to a dropdown."""
    lead = (
        "max|z| is the simplest scorer, carried in both tables as the baseline "
        "the others have to beat.\n"
    )
    table = _fold("raw table", detection_table(per_rate, tallies, title))
    if plots_dir is None:
        return f"{lead}\n{table}"
    stats = per_rate[min(per_rate)]

    def peak(mech: str) -> float:
        # At the mechanism's OWN top dose: ladders differ (throttle is a
        # fraction, not a sigma), so a global top-k would drop it entirely.
        rows = stats[stats.mechanism == mech]
        r = rows[rows.severity == rows.severity.max()].recovery.max()
        return float(r) if np.isfinite(r) else -1.0

    ranked = sorted(
        (m for m in stats.mechanism.unique() if m != headline_mechanism and peak(m) >= 0),
        key=lambda m: -peak(m),
    )
    slug = _slug(title.split()[0])
    default = [ranked[0], headline_mechanism] if ranked else [headline_mechanism]
    _plot_recovery(stats, tallies, default, plots_dir / f"{slug}.svg")
    parts = [
        lead,
        f"![recovery against severity, {' and '.join(default)}](plots/{slug}.svg)",
    ]
    for mech in ranked[1:]:
        name = f"{slug}_{_slug(mech)}.svg"
        _plot_recovery(stats, tallies, [mech], plots_dir / name)
        parts.append(_fold(mech, f"![recovery against severity, {mech}](plots/{name})"))
    parts.append(table)
    return "\n".join(parts)


def _pct(value: float, width: int = 5) -> str:
    return "n/a".rjust(width) if not np.isfinite(value) else f"{value:{width}.1%}"


def detection_table(
    per_rate: dict[float, pd.DataFrame], tallies: tuple[str, ...], title: str
) -> str:
    """One family's cells at both thresholds.

    AUC, achieved dose and clipped share are threshold-FREE, so they appear
    once. Printing them per rate would imply a dependence that does not exist
    and invite reading two identical columns as agreement between thresholds.
    """
    low, high = min(per_rate), max(per_rate)
    base = per_rate[low]
    lines = [
        (
            "max|z| is the simplest scorer, carried in both tables as the baseline "
            "the others have to beat.\n"
        ),
        (
            f"| scorer | injection | k | delivered | delivered z | n | dosed | auc | clipped "
            f"| recovery @{low:.0%} | recovery @{high:.0%} | collateral |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for tally in tallies:
        rows = base[base.tally == tally]
        if rows.empty:
            continue
        for first, row in enumerate(rows.itertuples()):
            other = per_rate[high]
            match = other[
                (other.tally == tally)
                & (other.mechanism == row.mechanism)
                & (other.severity == row.severity)
            ]
            hi = match.iloc[0] if len(match) else None
            collateral = f"{row.shift:+.4f}" if row.collateral_measurable else "not measured"

            def rate(cell) -> str:
                """Attempted-target rate, then the same numerator over the rows
                the injection actually moved, then in brackets how many rows
                could not reach the k this row is labelled with."""
                out = f"{int(cell.recovered):,}/{int(cell.n):,} ({_pct(cell.recovery)})"
                if np.isfinite(cell.recovery_dosed):
                    out += (
                        f" → {int(cell.recovered_dosed):,}/{int(cell.n_dosed):,}"
                        f" ({_pct(cell.recovery_dosed)})"
                    )
                if getattr(cell, "n_short", 0):
                    out += f" [{int(cell.n_short):,} short]"
                return out

            high_cell = rate(hi) if hi is not None else "n/a"
            dosed_n = f"{int(row.n_dosed):,}" if row.n_dosed else "n/a"
            delivered = f"{row.achieved:+.2f} sd" if np.isfinite(row.achieved) else "per-DOF"
            # Scorers pick different target rows; delivered z is what says
            # those rows took comparable doses.
            moved_z = getattr(row, "delivered_z", np.nan)
            delivered_z = f"{moved_z:+.2f}" if np.isfinite(moved_z) else "n/a"
            lines.append(
                f"| {f'**{tally}**' if not first else ''} | {row.mechanism} "
                f"| {row.severity:.3g} | {delivered} | {delivered_z} | {row.n:,} | {dosed_n} "
                f"| {f'{row.auc:.3f}' if np.isfinite(row.auc) else 'n/a'} "
                f"| {_pct(row.clipped, 4)} "
                f"| {rate(row)} "
                f"| {high_cell} | {collateral} |"
            )
    return "\n".join(lines)


def _matrix(labels: list[str], cell) -> str:
    """Square markdown table of ``cell(a, b)``, row label first."""
    rows = [
        "| | " + " | ".join(labels) + " |",
        "|---|" + "---:|" * len(labels),
    ]
    for a in labels:
        rows.append(f"| **{a}** | " + " | ".join(cell(a, b) for b in labels) + " |")
    return "\n".join(rows)


def _grid(labels: list[str], share, title: str, plot: Path | None) -> str:
    """A matrix as a heatmap when a path is given, else nothing.

    ``share(a, b)`` returns (percentage, n); NaN renders as an empty cell. The
    caller falls back to :func:`_matrix` when this returns "" -- so the position
    cuts and the all-positions grid render the same way rather than one being a
    plot and the others raw tables.
    """
    if plot is None:
        return ""
    values, texts = [], []
    for a in labels:
        row_v, row_t = [], []
        for b in labels:
            pct, n = share(a, b)
            row_v.append(pct if n else float("nan"))
            row_t.append(f"{pct:.0f}%" if n else "–")
        values.append(row_v)
        texts.append(row_t)
    _plot_matrix(labels, values, texts, title, plot)
    return f"![{title}](plots/{plot.name})"


def target_agreement(
    scored: pd.DataFrame,
    census: pd.DataFrame,
    scorers: tuple[str, ...],
    plots_dir: Path | None = None,
) -> str:
    """Share of players for whom two scorers chose the SAME match.

    Independent of mechanism, severity AND bar: every column medianed on is a
    clean census column, so this is one matrix rather than one per condition.
    Players a scorer could not score are excluded from its pairs and reported
    as coverage instead -- they inherit max|z|'s row, and counting
    that as agreement would flatter exactly the scorers with the least to say.
    """
    default, choices = injection_test.target_choices(scored, census, scorers)
    everyone = set(default)
    present = [s for s in scorers if s in choices]
    position = census.groupby("player_id")["position_code"].first()

    def block(players: set, title: str, folded: bool = False, plot: Path | None = None) -> str:
        def share(a: str, b: str) -> tuple[float, int]:
            both = set(choices[a]) & set(choices[b]) & players
            if not both:
                return float("nan"), 0
            same = sum(1 for q in both if choices[a][q] == choices[b][q])
            return 100.0 * same / len(both), len(both)

        def cell(a: str, b: str) -> str:
            pct, n = share(a, b)
            return "n/a" if not n else f"{pct:.0f}% ({n})"

        # Reported only when a scorer misses someone: a line reading 100% every
        # time trains a reader to skip the one case worth seeing.
        gaps = ", ".join(
            f"{s} {len(set(choices[s]) & players) / len(players):.0%}"
            for s in present
            if players and len(set(choices[s]) & players) < len(players)
        )
        note = f"\n\nincomplete coverage: {gaps}" if gaps else ""
        body = _grid(present, share, f"same target match chosen (n={len(players):,})", plot)
        body = body or _matrix(present, cell)
        if folded:
            return (
                f"\n<details>\n<summary>{title} (n={len(players):,})</summary>\n"
                f"\n{body}{note}\n\n</details>"
            )
        return f"\n### {title} (n={len(players):,})\n\n{body}{note}"

    out = ["\nIndependent of bar and dose. A gap in coverage is reported under the grid."]
    main = plots_dir / "target_agreement.svg" if plots_dir else None
    out.append(block(everyone, "all positions", folded=False, plot=main))
    for code in heldout.POSITIONS:
        cut = {q for q in everyone if position.get(q) == code}
        if not cut:
            continue
        if len(cut) < MIN_MATRIX_PLAYERS:
            out.append(
                f"\n*position {code}: {len(cut)} players — too few to compare; "
                "a grid this thin measures the sample, not the scorers.*"
            )
            continue
        cut_plot = plots_dir / f"target_agreement_{code}.svg" if plots_dir else None
        out.append(block(cut, f"position {code}", folded=True, plot=cut_plot))
    return "\n".join(out)


def detection_agreement(
    results: pd.DataFrame,
    bars: dict[str, float],
    mechanism: str,
    severity: float,
    tallies: tuple[str, ...],
    rate: float,
    plots_dir: Path | None = None,
) -> str:
    """Share of flagged PLAYERS two scorers share, at one dose and one bar.

    Counted per player, not per row: two scorers perturb different matches, so
    a row-level comparison would score them as disagreeing whenever their
    target choices differ, which Matrix 1 already measures separately.
    """
    block = results[
        (results.mechanism == mechanism) & (results.severity == severity) & results.is_target
    ]
    position = block.groupby("player_id")["position_code"].first()
    caught: dict[str, set] = {}
    for tally in injection_test.tallies_for(set(block["scorer"]), bars):
        if tally not in tallies:
            continue
        r = block[block.scorer == tally]
        caught[tally] = set(r.loc[r["after"] >= bars[tally], "player_id"])
    present = [t for t in tallies if t in caught]

    def block_for(players: set, title: str, folded: bool = False, plot: Path | None = None) -> str:
        sets = {t: caught[t] & players for t in present}

        def share(a: str, b: str) -> tuple[float, int]:
            """Row-normalised |A∩B|/|A|, and the union as the count. NaN when
            nothing was caught either side."""
            union = len(sets[a] | sets[b])
            if not union:
                return float("nan"), 0
            shared = len(sets[a] & sets[b])
            return (100.0 * shared / len(sets[a]) if sets[a] else 0.0), union

        def cell(a: str, b: str) -> str:
            union = len(sets[a] | sets[b])
            if not union:
                return "n/a"
            shared = len(sets[a] & sets[b])
            # A caught nothing, so "of A's catches" has no denominator -- the
            # Jaccard still does, and 0% there is a real statement about B.
            row = f"{shared / len(sets[a]):.0%}" if sets[a] else "-"
            return f"{row}/{shared / union:.0%}"

        sizes = ", ".join(f"{t} {len(sets[t])}" for t in present)
        body = _grid(present, share, f"of A's catches, % (n={len(players):,})", plot)
        body = body or _matrix(present, cell)
        if folded:
            return (
                f"\n<details>\n<summary>{title} (n={len(players):,})</summary>\n"
                f"\n{body}\n\ncaught: {sizes}\n\n</details>"
            )
        return f"\n### {title} (n={len(players):,})\n\n{body}\n\ncaught: {sizes}"

    everyone = set(block["player_id"])
    out = [
        (
            "\nCell = `|A∩B|/|A|` / Jaccard in the tables; the heatmaps show the "
            "row-normalised share alone. Row A, column B: of the players A caught, "
            "the share B also caught. Asymmetric on purpose."
        ),
    ]
    main = plots_dir / "detection_agreement.svg" if plots_dir else None
    out.append(block_for(everyone, "all positions", folded=False, plot=main))
    for code in heldout.POSITIONS:
        cut = {q for q in everyone if position.get(q) == code}
        if not cut:
            continue
        if len(cut) < MIN_MATRIX_PLAYERS:
            out.append(
                f"\n*position {code}: {len(cut)} players — too few to compare; "
                "a grid this thin measures the sample, not the scorers.*"
            )
            continue
        cut_plot = plots_dir / f"detection_agreement_{code}.svg" if plots_dir else None
        out.append(block_for(cut, f"position {code}", folded=True, plot=cut_plot))
    return "\n".join(out)


def build(
    scored: pd.DataFrame,
    census: pd.DataFrame,
    results: pd.DataFrame,
    headline: tuple[str, float],
    rates: tuple[float, ...] = RATES,
    plots_dir: Path | None = None,
    stale: bool = False,
    results_stamp: str | None = None,
    collateral: pd.DataFrame | None = None,
) -> str:
    """Every table, from one results frame.

    ``collateral`` is a SECOND frame, from persistent runs: the held-out design
    scores only targets, so it cannot measure collateral at all.
    """
    bars = {r: heldout.production_bars(scored, census, r) for r in rates}
    per_rate = {r: injection_test.cell_statistics(results, bars[r]) for r in rates}
    # "max" is merged in from the scored frame, not a census column, so it must
    # be admitted explicitly or max|z| drops out of the matrix. A
    # forest-free census still CARRIES the forest columns, all-NaN, so presence
    # is not enough -- they would fill the matrix with dead rows at 0% coverage.
    scorers = tuple(
        s
        for s in injection_test.SCORERS + injection_test.FOREST_SCORERS
        if s == "max" or (s in census and census[s].notna().any())
    )
    mechanism, severity = headline
    parts = [
        *(f"<!-- {k}={v} -->" for k, v in _stamps(stale, results_stamp).items()),
        "# Injection sensitivity\n",
        _context(scored, rates, headline),
        headline_summary(per_rate[min(rates)], min(rates), headline),
        f"\n{HEADLINE_END}",
        "",
        experiment_note(),
        "",
        calibration_note(scored, census, bars[min(rates)], min(rates)),
        _fold(
            "DIRECT metric space",
            detection_section(per_rate, DIRECT, "DIRECT metric space", mechanism, plots_dir),
        ),
        _fold(
            "RESIDUAL (z) space",
            detection_section(per_rate, RESIDUAL, "RESIDUAL (z) space", mechanism, plots_dir),
        ),
        _fold(
            "Target agreement (same match chosen)",
            target_agreement(scored, census, scorers, plots_dir),
        ),
    ]
    # Matrix 2 at the PRIMARY rate only. The 5% pass was a control on whether
    # agreement is a bar artefact; the caught counts printed under each grid
    # carry that, and the census is cached, so it can be added later without
    # refitting anything.
    primary = min(rates)
    parts.append(
        _fold(
            f"Detection agreement ({mechanism}, k={severity:g}, bar {primary:.0%})",
            detection_agreement(
                results, bars[primary], mechanism, severity, EVERY_TALLY, primary, plots_dir
            ),
        )
    )
    if collateral is not None and len(collateral):
        parts.append(
            _fold(
                "Collateral — what an injection does to the player's OTHER matches",
                collateral_section(
                    injection_test.cell_statistics(collateral, bars[primary]), primary
                ),
            )
        )
    parts.append(_fold("Notes", caption(scored, census, rates)))
    return "\n".join(parts)


def collateral_section(stats: pd.DataFrame, rate: float) -> str:
    """What an injection does to the player's OTHER matches.

    A separate section, not a column, because the detection tables come from the
    held-out design, which scores only targets and so cannot measure this at all.
    These rows come from persistent runs, where the fixed match stays in the
    player's history and every other row of his is rescored against a baseline
    that now contains it.
    """
    live = stats[stats.collateral_measurable & (stats.severity > 0)]
    if live.empty:
        return "No collateral measured: these results carry no non-target rows."

    def table(block: pd.DataFrame) -> str:
        out = [
            "| scorer | injection | k | flagged before | after | net rows | moved | shift (sd) |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        seen = None
        for r in block.itertuples():
            net = round((r.others_after - r.others_before) * r.n_other)
            label = f"**{r.tally}**" if r.tally != seen else ""
            seen = r.tally
            out.append(
                f"| {label} | {r.mechanism} | {r.severity:.3g} "
                f"| {r.others_before:.2%} | {r.others_after:.2%} | {net:+,} "
                f"| {r.contaminated / r.n_other:.0%} | {r.shift_sd:+.4f} |"
            )
        return "\n".join(out)

    # The condition every scorer shares: the forests were run on it alone.
    shared = live[live.mechanism == "correlated"].sort_values(["tally", "severity"])
    worst = live.loc[live.shift_sd.idxmin()]
    down = int((live.shift_sd < 0).sum())
    rose = live[live.others_after > live.others_before]
    lifts = rose.tally.value_counts()
    body = [table(shared)] if not shared.empty else []
    body.append(
        f"\nInjecting one match barely moves the rest of the player's history. Over "
        f"{len(live)} measured conditions the largest median shift is "
        f"**{worst.shift_sd:+.4f} sd** (`{worst.tally}`, {worst.mechanism} k={worst.severity:.3g}) "
        f"against a {rate:.0%} bar, and the flagged share of other matches stays within "
        f"{min(live.others_after):.2%}–{max(live.others_after):.2%} of a {live.others_before.iloc[0]:.2%} "
        "baseline. Almost nothing crosses."
    )
    body.append(
        f"\nThe shift is downward in {down} of {len(live)} conditions. That is the expected "
        "direction: leaving a perturbed row in the player's history widens his own scale "
        "estimate, and a wider spread deflates every other row's z, so contamination makes "
        "the remaining matches look slightly LESS anomalous rather than more."
    )
    if len(lifts):
        first = lifts.index[0]
        body.append(
            f"\nThe flagged share still ticks up in {len(rose)} conditions, "
            f"{lifts.iloc[0]} of them `{first}` — it reads the MAXIMUM of six per-metric z's, "
            "so when the perturbed metric's z is deflated the maximum can simply move to "
            "another metric. The multivariate scorers have no such escape."
        )

    others = live[live.mechanism != "correlated"]
    if not others.empty:
        body.append(
            _fold(
                "Every other mechanism (scorers whose run covered the full grid)",
                table(others.sort_values(["tally", "mechanism", "severity"])),
            )
        )
    return "\n".join(body)


def _shrinkage_note(scored: pd.DataFrame) -> str:
    """The covariance shrinkage actually in force, per position."""
    nus = heldout.position_nus(scored)
    if not nus:
        return "- Covariance shrinkage: no position pool large enough to estimate."
    detail = ", ".join(f"{p} {v:.2f}" for p, v in nus.items())
    return (
        f"- **Covariance shrinkage** `nu` {min(nus.values()):.2f}–{max(nus.values()):.2f} "
        f"({detail}), the matches of evidence each position's covariance is worth. "
        "A player's own covariance carries weight n/(n+nu), so it takes over as his "
        "history lengthens rather than at a match-count threshold."
    )


def caption(scored: pd.DataFrame, census: pd.DataFrame, rates: tuple[float, ...]) -> str:
    """What a reader needs to not over-read the tables."""
    return "\n".join(
        [
            (
                f"\n- Population {len(scored):,} rows / {scored['player_id'].nunique():,} players. "
                "**Observed, not certified-clean**, so base rates are upper bounds on FPR."
            ),
            # The evaluated cut is a dbt var, not a Python constant, so it is read
            # off the frame -- writing 30 into the string would misstate the
            # population the moment the mart is rebuilt with a different value.
            (
                f"- Eligibility: ≥{baseline.BASELINE_MIN_MINUTES:g} min baselines, "
                f"≥{scored['minutes_played'].min():g} min evaluated "
                f"(the mart's cut, read off this frame), "
                f"≥{baseline.MIN_PLAYER_MATCHES:g} appearances."
            ),
            # Derived, not quoted: the range is a measurement of one population and
            # would go quietly wrong the moment the mart moves. Costs ~0.3s.
            _shrinkage_note(scored),
            (
                "- **Two denominators.** `recovery` is over ALL attempted targets; the figure after "
                "`→` is the same numerator over `dosed` — rows the injection actually moved. A "
                "requested dose that rounds below one event is a real draw from the treatment and "
                "stays in the first; conditioning only on non-zero draws would select on the "
                "randomisation. **On the coordinated row it reads n/a**: 'some channel moved' is "
                "true on nearly every row and would imply a correction that was not made — there "
                "the per-channel `acted` shares carry it instead."
            ),
            (
                "- **Recovery** is crossing the bar *because of* the injection (below when clean, "
                "above after). It is not the same as caught, which counts rows already flagged "
                "before anything was injected. Rates print as **recovered / targets**: the targets "
                "are the whole population — one injected row per player, chosen before anything was "
                "perturbed — so there is no sample and no interval to put on them."
            ),
            (
                "- **The experiment is a scorer-relative typical-match challenge.** Each scorer's "
                "target is the match nearest that player's own median under that scorer — the same "
                "selection rule for every scorer, realised on different rows. The question each row "
                "answers is: injected into the kind of match this scorer finds unremarkable for "
                "this player, is the signal detected? The `delivered`/`delivered z` columns are the "
                "cross-scorer check that the different rows received comparable doses."
            ),
            (
                "- **AUC is a cohort-referenced two-sample (Mann–Whitney) comparison** of the "
                "target cohort's clean and after distributions, ties counted half — not per-row "
                "pairs. It is threshold-free *at each specified dose*, so it is reported once "
                "rather than per rate. At k=0 the two multisets are identical, so the no-skill "
                "line is **exactly 0.5**, and the k=0 row measures that rather than setting it."
            ),
            (
                "- **Do not compare mechanism rows as if they were equally injected.** `delivered` "
                "is the dose that actually landed, and it varies by mechanism: `pass_completion` "
                "delivers essentially all of what is asked and clips on no rows, while "
                "`remove_defensive` clips on most rows and lands under half. A mechanism that looks "
                "harder to detect may simply have been injected more weakly."
            ),
            (
                "- **Clipped** is the share of injected targets whose dose was TRUNCATED — the "
                "mechanism ran out of successes to relabel, or actions to remove, or touches to "
                "relocate. Those rows received *less* than was asked for, so a miss there is "
                "delivery rather than detection. Read it beside the achieved dose, which says how "
                "much was actually delivered on average."
            ),
            (
                "- Detection agreement is **one condition and the primary bar only**. Agreement rises with "
                "set size alone, so read the `caught` counts under each grid before reading the "
                "percentages. Note that k is split across channels on the coordinated condition "
                "(`compose` spends the quadratic budget equally until a channel reaches its "
                "capacity; capped channels take less and the remainder is redistributed to the "
                "uncapped ones, which therefore take MORE than k/√parts. The total reaches k "
                "unless every channel caps) — so a channel is not simply at k/√parts."
            ),
            (
                f"- Position grids resting on fewer than {MIN_MATRIX_PLAYERS} players report a "
                "count instead of percentages. Below that, one player moves a cell by ten points."
            ),
            "- Bars are derived from this population at run time, never hardcoded.",
        ]
    )


def is_canonical(n: int | None, forest: bool, design: str, seed: int) -> bool:
    """Whether a run is the published study's recipe. Anything narrower is a
    diagnostic and must not overwrite publication-facing output."""
    return n is None and forest and design == "heldout" and seed == injection_test.SEED


def _mark_stale(target: Path, state: str) -> int:
    """Band the report and the README so a deferred re-run is visible upstream.

    A stale number that nobody has labelled is worse than no number: the whole
    point of publishing is that someone downstream reads it without checking
    when it was made.
    """
    if state in ("fresh", "render"):
        print(f"{target}: {state}; no stale banner needed")
        return 0
    text = target.read_text(encoding="utf-8")
    if STALE_MARKER not in text:
        head, _, rest = text.partition("# Injection sensitivity\n")
        target.write_text(
            head + "# Injection sensitivity\n\n" + STALE_BANNER + rest, encoding="utf-8"
        )
        print(f"banded {target}")
    readme = Path("README.md")
    if readme.exists():
        rt = readme.read_text(encoding="utf-8")
        marker = "## Output / analysis summary"
        if marker in rt and STALE_MARKER not in rt:
            readme.write_text(
                rt.replace(marker, marker + "\n\n" + STALE_BANNER, 1), encoding="utf-8"
            )
            print("banded README.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fis-report", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--n",
        type=int,
        default=None,
        help="cap the players SCORED. Hyperparameters and residuals are still "
        "derived from the whole mart per condition, which is deliberate but "
        "means a small --n speeds this up far less than it looks.",
    )
    parser.add_argument(
        "--results",
        type=str,
        default=None,
        help="parquet holding the injection results. If it exists, the analysis "
        "is SKIPPED and the report re-renders from it, so a caption or "
        "column change costs seconds rather than a whole campaign. Written "
        "on every run and fingerprint-guarded, so results computed under a "
        "different estimator are refused rather than silently rendered.",
    )
    parser.add_argument(
        "--census",
        type=str,
        default=None,
        help="parquet to cache the census in. With forests it dominates the "
        "runtime, and it is fingerprint-guarded, so re-rendering a table "
        "costs nothing rather than refitting every row.",
    )
    parser.add_argument(
        "--collateral",
        action="append",
        default=None,
        help="parquet from a PERSISTENT run, repeatable. The held-out design "
        "scores only targets, so collateral needs its own run; these frames fill "
        "the collateral section and nothing else.",
    )
    parser.add_argument("--jobs", type=int, default=-1)
    parser.add_argument("--seed", type=int, default=injection_test.SEED)
    parser.add_argument("--forest", action="store_true", help="fit forests (dominates the runtime)")
    parser.add_argument(
        "--headline",
        default="correlated:3.0",
        help="mechanism:severity keying the agreement matrices. The coordinated "
        "case by default: it is what a manipulator most resembles, and "
        "compose() spends the quadratic budget equally until a channel reaches its "
        "capacity, then redistributes the remainder to the uncapped channels -- so a "
        "capped channel takes less than k/sqrt(parts) and an uncapped one takes more. "
        "Re-pick it after a "
        "run if the grids are uninformative; the matrices need no fitting, "
        "so a re-render is seconds against a cached census.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="classify the published report against the current code and exit: "
        "0 fresh, 1 needs a re-render (seconds), 2 needs a full campaign re-run. "
        "Reads no data, so it works anywhere the code does.",
    )
    parser.add_argument(
        "--stale-ok",
        action="store_true",
        help="render from a results parquet the stamp rejects, and band the "
        "output as stale. For previewing a report's shape before paying for the "
        "re-run the changed code demands.",
    )
    parser.add_argument(
        "--mark-stale",
        action="store_true",
        help="band the published report and the README's headline with a stale "
        "warning, for when a re-run is deferred rather than done.",
    )
    parser.add_argument(
        "--design",
        choices=("persistent", "heldout"),
        default="heldout",
        help="heldout scores only each scorer's targets against criteria fixed "
        "on the clean census -- no collateral, cheap enough for forests. "
        "persistent leaves the fixed match in the player's history and measures "
        "what it does to his other matches, at a fit per row per frame. Target "
        "scores are identical either way.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="markdown file to write (default: <data dir>/reports/phase2.md)",
    )
    args = parser.parse_args(argv)

    published = Path(args.out) if args.out else paths.report_dir() / "phase2.md"
    if args.check or args.mark_stale:
        # The PUBLISHED copy is the tracked one -- that is what the hook
        # checks and what a reader arriving from the README opens. The data-dir
        # render is a working artefact and nobody cites it.
        tracked = Path("results/phase2.md")
        target = tracked if tracked.exists() else published
        if not target.exists():
            print(f"no report at {target}; nothing to check")
            return 0
        # The payload sits beside the working render; results/ is markdown only.
        payload = Path(args.results) if args.results else published.with_suffix(".parquet")
        state, detail = freshness(target.read_text(encoding="utf-8"), results=payload)
        if args.mark_stale:
            return _mark_stale(target, state)
        print(f"{target}: {state} -- {detail}")
        return {"fresh": 0, "render": 1, "analysis": 2, "runtime": 2, "payload": 2, "unknown": 2}[
            state
        ]

    name, _, dose = args.headline.partition(":")
    mart = baseline.load()
    frame = baseline.prepare(mart)
    scored, _ = baseline.residuals(frame)
    scored = scored[scored["is_scoreable"]]
    if args.n:
        keep = scored["player_id"].drop_duplicates().head(args.n)
        scored = scored[scored["player_id"].isin(set(keep))]

    cache = Path(args.census) if args.census else None
    settings = heldout.scoring_config(forest=args.forest)
    # ONE resolved recipe for runner and stamp: resolving twice lets a run
    # under one recipe be stamped as another.
    recipe = injection_test.canonical_recipe(
        forest=args.forest,
        design=args.design,
        seed=args.seed,
        compositions={"correlated": tuple(injection_test.COMPOSITION_ORDER)},
    )
    run_settings = injection_test.campaign_config(settings, recipe, mart)
    # Only the canonical recipe may touch the README; the rest self-label.
    canonical = is_canonical(args.n, args.forest, args.design, args.seed)
    if cache is not None and cache.exists():
        if args.stale_ok:
            census = pd.read_parquet(cache).rename(columns=LEGACY_RENAMES)
        else:
            census = heldout.read_census(cache, scored, config=settings)
    else:
        census = heldout.score_all(scored, forest=args.forest, jobs=args.jobs)
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            heldout.write_census(cache, census, scored, config=settings)
    path = Path(args.out) if args.out else paths.report_dir() / "phase2.md"
    saved = Path(args.results) if args.results else path.with_suffix(".parquet")
    if saved.exists():
        # Rendering is a pure function of stored results, so a table change
        # costs a re-render rather than a re-analysis.
        # injection_test IS the code that made these, so it must be in the
        # stamp -- the census hash covers baseline+heldout only, and a saved
        # results file would otherwise survive a change to the allocator, a
        # capacity, a mechanism or the ladder and re-render silently stale.
        if args.stale_ok:
            results = pd.read_parquet(saved).rename(columns=LEGACY_RENAMES)
            results["scorer"] = results["scorer"].replace(LEGACY_RENAMES)
            print(f"reading {saved} WITHOUT the stamp check; output banded stale")
        else:
            results = heldout.read_stamped(
                saved, scored, what="results", extra=(injection_test,), config=run_settings
            )
        print(f"re-rendering from {saved}; analysis skipped")
    else:
        # The coordinated multi-variable injection is part of the condition
        # list, not an extra: it is the case a real manipulator most resembles,
        # and the one where per-DOF truncation matters most, since composing
        # sizes each relabelling against a denominator earlier steps thinned.
        results = injection_test.run(
            scored,
            mart,
            census,
            forest=recipe["forest"],
            design=recipe["design"],
            severities=recipe["severities"],
            mechanisms=recipe["mechanisms"],
            compositions=recipe["compositions"],
            metrics=recipe["metrics"],
            scorers=recipe["scorers"],
            seed=recipe["seed"],
            jobs=args.jobs,
            progress=True,
        )
        saved.parent.mkdir(parents=True, exist_ok=True)
        heldout.write_stamped(saved, results, scored, extra=(injection_test,), config=run_settings)
    collateral = None
    if args.collateral:
        frames = [pd.read_parquet(c) for c in args.collateral]
        collateral = pd.concat(frames, ignore_index=True)
        print(f"collateral from {len(frames)} run(s): {len(collateral):,} rows")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = build(
        scored,
        census,
        results,
        (name, float(dose)),
        plots_dir=path.parent / "plots",
        stale=args.stale_ok,
        results_stamp=heldout.fingerprint(scored, extra=(injection_test,), config=run_settings),
        collateral=collateral,
    )
    banner = STALE_BANNER if args.stale_ok else None
    if not canonical:
        banner = (
            "> **Diagnostic run — not the published result.** Rendered from a "
            f"non-canonical recipe (`--n {args.n}`, forest={args.forest}, "
            f"design={args.design}, seed={args.seed}); publication-facing output "
            "is untouched.\n"
        )
    if banner:
        head, _, rest = rendered.partition("# Injection sensitivity\n")
        rendered = head + "# Injection sensitivity\n\n" + banner + rest
    path.write_text(rendered, encoding="utf-8")
    # A fresh render answers the banner, so it clears it. Gated: only the
    # canonical recipe rewrites the block a reader will cite.
    readme = Path("README.md")
    if canonical and not args.stale_ok and readme.exists():
        before = readme.read_text(encoding="utf-8")
        after = _put_summary(_clear_banner(before), scored, rendered)
        if after != before:
            readme.write_text(after, encoding="utf-8")
            print("updated README.md: summary regenerated, stale banner cleared")
    elif not canonical:
        print("non-canonical recipe: output labelled diagnostic, README untouched")
    print(f"wrote {path}\nresults at {saved}  (re-render from this; no rerun needed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
