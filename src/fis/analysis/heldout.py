"""Per-player scoring: the census, the fits behind it, and the production bars.

:func:`score_all` scores every eligible row against a fit from that player's
other matches, shrunk toward his position pool so there is no match floor and
no cliff. :func:`production_bars` cuts each scorer at the rate that census
delivers. The injection experiment that used to live here is now
:mod:`fis.analysis.injection_test`.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from fis.analysis import baseline

FOREST_TREES = 50


def forest_target_rows(dimensions: int) -> int:
    """Rows a forest needs to resolve ``dimensions`` metrics: 2**d, since an
    isolation tree is ceil(log2(n)) deep. Scales with the fit, self-clears as
    careers lengthen."""
    return int(2**dimensions)


#: Ceiling on a borrowed training set. sklearn subsamples to 256 per tree
#: anyway, so beyond it the borrowing buys depth that is never used.
#: INERT at the current metric count: it binds only when 2**d > 256, i.e. from
#: NINE observed metrics. The min() below still evaluates it on every borrow.
POOL_BORROW_CAP = 256


def borrow_seed(player_id) -> int:
    """Stable per-player seed for the pool draw. crc32 rather than ``hash``,
    which is salted per process and so would differ between parallel workers."""
    import zlib

    return int(zlib.crc32(str(player_id).encode()))


#: Bumped only if the fingerprint's own definition changes, which would make
#: old stamps unreadable rather than merely stale.
FINGERPRINT_VERSION = 1


def _code_fingerprint(extra: tuple = ()) -> str:
    """Hash of the scoring code's parsed form.

    Comments never reach the AST and docstrings are stripped, so prose edits
    do not invalidate a cache while a changed borrowing rule, shrinkage weight
    or covariance estimator does -- the class of change that alters values
    without moving any column, and which a column check cannot see.

    ``extra`` covers code a caller's frame depends on beyond the scoring path.
    A census needs only baseline and this module; injection RESULTS also depend
    on the mechanisms, the allocator and the ladder, and would otherwise
    survive a change to any of them.
    """
    parts = []
    for module in (baseline, sys.modules[__name__], *extra):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                body.pop(0)
        parts.append(ast.dump(tree))
    return hashlib.sha256("".join(parts).encode()).hexdigest()[:16]


def _data_fingerprint(scored: pd.DataFrame) -> str:
    """Content hash of the frame a census is built from.

    Covers the mart and everything upstream of it: two sessions share one
    warehouse, so a dbt build moves the marts under every cached census with
    nothing else detecting it.
    """
    # Raw metrics AND residuals: the census consumes both directly, so a
    # frame whose z columns moved while its counts did not must still fail.
    columns = [c for c in (*baseline.METRICS, *residual_columns(baseline.METRICS)) if c in scored]
    # Every input score_all reads, not just the metrics: position_code picks
    # the position pool and its shrinkage target, and match_id drives the
    # leave-one-out exclusion, so either can move the census on its own.
    keys = [c for c in ("player_id", "match_id", "position_code") if c in scored]
    # Per row, not per column sum. A census is aligned to this frame by
    # position, so a reordering or an offsetting pair of edits must break the
    # hash; column totals see neither.
    rows = pd.util.hash_pandas_object(scored[[*keys, *columns]], index=False)
    digest = hashlib.sha256()
    digest.update("|".join(["v3", str(len(scored)), *keys, *columns]).encode())
    digest.update(rows.to_numpy().tobytes())
    return digest.hexdigest()[:16]


def scoring_config(
    metrics: list[str] | None = None, forest: bool = False, limit_players: int | None = None
) -> str:
    """The arguments to :func:`score_all` that change the census it returns.

    The frame hash cannot see these: ``metrics`` and ``forest`` decide which
    columns exist, and ``limit_players`` caps the population INSIDE the call, so
    a partial census would otherwise be stamped against the whole frame. ``jobs``
    is excluded -- verified byte-identical at every setting.
    """
    # NOT sorted: metric order reaches the forest through feature indices, so
    # two orders can score differently. Canonicalising would let one stamp cover
    # both; preserving it can only cost a cache miss.
    chosen = ",".join(metrics or baseline.METRICS)
    return f"metrics={chosen}|forest={bool(forest)}|players={limit_players}"


def results_config(scoring: str, seed: int) -> str:
    """What changes an injection run's output beyond the code and the frame.

    Separate from :func:`scoring_config` because the census does NOT depend on
    the injection seed while the results do -- stamping both with the scoring
    settings alone lets a run under one seed be reused under another. The design
    constants move with the injection_test code fingerprint already.
    """
    return f"{scoring}|seed={seed}"


def fingerprint(scored: pd.DataFrame, extra: tuple = (), config: str = "") -> str:
    """What a stamped frame must match to be reused."""
    return (
        f"v{FINGERPRINT_VERSION}.{_data_fingerprint(scored)}"
        f".{_code_fingerprint(extra)}.{hashlib.sha256(config.encode()).hexdigest()[:8]}"
    )


def write_stamped(
    path: Path, frame: pd.DataFrame, scored: pd.DataFrame, extra: tuple = (), config: str = ""
) -> None:
    """Cache any derived frame, stamped with the data and code that made it."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    stamped = {
        **(table.schema.metadata or {}),
        b"fis_fingerprint": fingerprint(scored, extra, config).encode(),
    }
    pq.write_table(table.replace_schema_metadata(stamped), path)


def read_stamped(
    path: Path,
    scored: pd.DataFrame,
    what: str = "cache",
    extra: tuple = (),
    config: str = "",
) -> pd.DataFrame:
    """Load a stamped frame, refusing one the current inputs did not produce.

    The whole point of caching an expensive frame is not recomputing it, which
    is also how a result computed under a different estimator gets rendered
    with nothing in the output to show it.
    """
    import pyarrow.parquet as pq

    stored = (pq.read_schema(path).metadata or {}).get(b"fis_fingerprint", b"").decode()
    current = fingerprint(scored, extra, config)
    if stored != current:
        raise ValueError(
            f"{what} at {path} was built from different inputs "
            f"(stamped {stored or 'nothing'}, now {current}) -- the mart or the "
            "scoring code has moved under it. Delete it and rebuild."
        )
    return pd.read_parquet(path)


def write_census(path: Path, census: pd.DataFrame, scored: pd.DataFrame, config: str = "") -> None:
    """Cache a census, stamped with the data, code and settings that made it."""
    write_stamped(path, census, scored, config=config)


def read_census(path: Path, scored: pd.DataFrame, config: str = "") -> pd.DataFrame:
    """Load a cached census, refusing one the current inputs did not produce."""
    return read_stamped(path, scored, what="census", config=config)


#: Positions pooled for the fallback fit.
POSITIONS = ("GK", "DF", "MD", "FW")


def position_nus(scored: pd.DataFrame, metrics: list[str] | None = None) -> dict[str, float]:
    """Matches of evidence each position's covariance is worth.

    Exposed so a caption can DERIVE the shrinkage range instead of quoting a
    constant measured on one population -- it costs about a third of a second
    and cannot go quietly wrong when the mart moves.
    """
    metrics = metrics or baseline.METRICS
    floor = len(metrics) + 2
    out = {}
    for position in POSITIONS:
        pool = scored[scored["position_code"] == position].dropna(subset=metrics)
        if len(pool) < floor:
            continue
        out[position] = covariance_nu(pool[metrics].to_numpy(float), pool["player_id"].to_numpy())
    return out


def shrinkage_weight(n: int, nu: float) -> float:
    """Share of a player's own covariance in the blend with his position's:
    n/(n + nu), the inverse-Wishart posterior weight."""
    if n <= 0:
        return 0.0
    return float(n / (n + nu)) if np.isfinite(nu) else 0.0


def covariance_nu(rows: np.ndarray, players: np.ndarray) -> float:
    """Matches of evidence the position covariance is worth, estimated.

    The covariance twin of baseline.informativeness: between over within,
    pooled across all matrix entries (metrics standardised first, median
    across entries against heavy tails). Entry variances from fourth moments,
    distribution-free. inf when nothing to estimate from.
    """
    spread = rows.std(axis=0, ddof=1)
    x = rows / np.where(spread > 0, spread, 1.0)
    covariances, variances, sizes = [], [], []
    for player in np.unique(players):
        own = x[players == player]
        n = len(own)
        if n < 3:
            continue
        centred = own - own.mean(axis=0)
        covariance = centred.T @ centred / (n - 1)
        squares = centred**2
        variance = (squares.T @ squares / n - covariance**2) / n
        covariances.append(covariance)
        variances.append(variance)
        sizes.append(n)
    if len(covariances) < 2:
        return float("inf")
    covariances = np.array(covariances)
    variances = np.array(variances)
    sizes = np.array(sizes, dtype=float)[:, None, None]
    between = covariances.var(axis=0, ddof=1) - variances.mean(axis=0)
    within = (sizes * variances).mean(axis=0)
    usable = (within > 0) & np.isfinite(between) & np.isfinite(within)
    if not usable.any():
        return float("inf")
    ratio = float(np.median(np.maximum(between[usable], 0.0) / within[usable]))
    return 1.0 / ratio if ratio > 0 else float("inf")


class _Fit:
    """One training set, scoring vectors that may have unmeasurable metrics.

    A NaN metric is marginalised out, not treated as voiding the row.
    ``target`` and ``weight`` shrink the covariance toward a well-estimated
    one, which is what lets a thin history be scored at all.
    """

    def __init__(
        self,
        train_x: np.ndarray,
        target: np.ndarray | None = None,
        weight: float = 1.0,
        pool: np.ndarray | None = None,
        seed: int = 0,
    ):
        self.train_x = train_x
        self.weight = weight
        self.pool = pool
        self.seed = seed
        self.centre = train_x.mean(axis=0)
        own = np.cov(train_x, rowvar=False) if len(train_x) > 1 else None
        if own is None:
            self.cov = target
        elif target is None or weight >= 1.0:
            self.cov = own
        else:
            self.cov = weight * own + (1.0 - weight) * target
        self._cache: dict = {}
        self._forests: dict = {}
        self._reference: dict = {}

    def _precision(self, observed: np.ndarray) -> np.ndarray:
        key = observed.tobytes()
        if key not in self._cache:
            self._cache[key] = np.linalg.pinv(self.cov[np.ix_(observed, observed)])
        return self._cache[key]

    def _training_rows(self, dimensions: int) -> np.ndarray:
        """The player's rows, topped up from his position pool to the depth a
        ``dimensions``-wide fit needs -- sample borrowing, the only shrinkage
        a partitioning scorer can take."""
        own = self.train_x
        if self.pool is None or not len(own):
            return own
        wanted = forest_target_rows(dimensions) - len(own)
        wanted = min(wanted, POOL_BORROW_CAP - len(own), len(self.pool))
        if wanted <= 0:
            return own
        # Deterministic per player, not global: one shared seed gave every
        # thin player the SAME borrowed rows, so their scores moved together
        # and the draw's error stopped averaging out across the population.
        picked = np.random.default_rng(self.seed).choice(len(self.pool), wanted, replace=False)
        return np.vstack([own, self.pool[picked]])

    def own_fraction(self, dimensions: int) -> float:
        """Share of a ``dimensions``-wide forest's training rows that are the
        player's own -- how individual its verdict is."""
        rows = self._training_rows(dimensions)
        return float(len(self.train_x) / len(rows)) if len(rows) else float("nan")

    def _forest(self, observed: np.ndarray):
        key = observed.tobytes()
        if key not in self._forests:
            from sklearn.ensemble import IsolationForest

            rows = self._training_rows(int(observed.sum()))
            self._forests[key] = IsolationForest(n_estimators=FOREST_TREES, random_state=0).fit(
                rows[:, observed]
            )
        return self._forests[key]

    def _reference_moments(self, observed: np.ndarray) -> tuple[float, float]:
        """Mean and sd of the forest's own training-row scores, for
        normalisation -- a raw isolation score is only interpretable against
        the fit that produced it."""
        key = observed.tobytes()
        if key not in self._reference:
            rows = self._training_rows(int(observed.sum()))
            s = -self._forest(observed).score_samples(rows[:, observed])
            sd = float(s.std(ddof=1)) if len(s) > 1 else np.nan
            self._reference[key] = (float(s.mean()), sd if sd > 0 else np.nan)
        return self._reference[key]

    def distance(self, x: np.ndarray) -> float:
        """Mahalanobis only. Fits no forest, which is the whole runtime."""
        observed = ~np.isnan(x)
        if observed.sum() < 2:
            return np.nan
        centred = x[observed] - self.centre[observed]
        return float(np.sqrt(max(centred @ self._precision(observed) @ centred, 0)))

    def score(self, x: np.ndarray) -> tuple[float, float, float]:
        """Mahalanobis distance, raw forest score, and normalised forest score."""
        observed = ~np.isnan(x)
        if observed.sum() < 2:
            return np.nan, np.nan, np.nan
        raw = float(-self._forest(observed).score_samples(x[observed][None, :])[0])
        centre, spread = self._reference_moments(observed)
        return self.distance(x), raw, (raw - centre) / spread if spread else np.nan


#: The residual columns, from baseline.residuals -- reimplementing them
#: would be a second convention to keep in step with the first.
def residual_columns(metrics: list[str]) -> list[str]:
    return [f"z_{m}" for m in metrics]


def score_all(
    scored: pd.DataFrame,
    metrics: list[str] | None = None,
    limit_players: int | None = None,
    forest: bool = False,
    jobs: int = 1,
) -> pd.DataFrame:
    """Clean Mahalanobis and forest scores for every eligible row, no injection.

    Incomplete vectors are marginalised, not dropped. The covariance is shrunk
    toward the position pool and the forest borrows rows to the same end, so
    neither has a match floor; ``fit_source`` records which estimator scored
    the row.
    """
    warnings.filterwarnings("ignore")
    metrics = metrics or baseline.METRICS
    zcols = residual_columns(metrics)
    floor = len(metrics) + 2

    every = scored[metrics].dropna().to_numpy(dtype=float)
    global_fit = _Fit(every) if len(every) >= floor else None
    position_fits, position_z, position_rows = {}, {}, {}
    position_nu, position_nu_z, position_z_rows = {}, {}, {}
    for position in POSITIONS:
        pool = scored[scored["position_code"] == position].dropna(subset=metrics)
        if len(pool) < floor:
            continue
        x = pool[metrics].to_numpy(float)
        position_rows[position] = x
        position_fits[position] = _Fit(x)
        ids = pool["player_id"].to_numpy()
        position_nu[position] = covariance_nu(x, ids)
        frame_z = pool[zcols + ["player_id"]].dropna()
        z = frame_z[zcols].to_numpy(dtype=float)
        position_z_rows[position] = z
        position_z[position] = _Fit(z) if len(z) >= floor else None
        position_nu_z[position] = covariance_nu(z, frame_z["player_id"].to_numpy())

    def one_player(pid, g) -> list[tuple]:
        rows = []
        if g.empty:
            return rows
        position = g["position_code"].iloc[0]
        fallback = position_fits.get(position) or global_fit
        if fallback is None:
            return rows
        complete = g.dropna(subset=metrics)
        complete_x = complete[metrics].to_numpy(dtype=float)
        complete_z = complete[zcols].to_numpy(dtype=float)
        complete_ids = complete["match_id"].to_numpy()
        target = fallback.cov

        for x, zrow, match_id in zip(
            g[metrics].to_numpy(dtype=float),
            g[zcols].to_numpy(dtype=float),
            g["match_id"].to_numpy(),
        ):
            # Leave-one-out over the player's complete rows.
            train = complete_x[complete_ids != match_id]
            fit, source = fallback, "position"
            if len(train) >= 2:
                fit = _Fit(
                    train,
                    target=target,
                    weight=shrinkage_weight(len(train), position_nu.get(position, np.inf)),
                    pool=position_rows.get(position),
                    seed=borrow_seed(pid),
                )
                source = "shrunk"
            mdist = fit.distance(x)
            # Same question as max|z|, combined by covariance instead of a
            # maximum; picks its own target row downstream.
            zresid = zresid_norm = zofrac = np.nan
            ztrain = complete_z[complete_ids != match_id]
            ztrain = ztrain[~np.isnan(ztrain).any(axis=1)]
            # Falls back to the position fit exactly as raw space does above;
            # without it a player with too few complete z-rows scored NaN.
            pool_z = position_z.get(position)
            zfit = pool_z
            if len(ztrain) >= 2:
                zfit = _Fit(
                    ztrain,
                    target=pool_z.cov if pool_z is not None else None,
                    weight=shrinkage_weight(len(ztrain), position_nu_z.get(position, np.inf)),
                    pool=position_z_rows.get(position),
                    seed=borrow_seed(pid),
                )
            zdist = zfit.distance(zrow) if zfit is not None else np.nan
            # z is already centred and scaled per player, so a borrowed pool row
            # is on the same footing -- cheaper to justify than in raw space.
            if forest and zfit is not None:
                _, zresid, zresid_norm = zfit.score(zrow)
                # The residual fit's own share: reporting the raw fit's beside a
                # residual score would mislabel the flags most likely to be acted on.
                zofrac = zfit.own_fraction(int((~np.isnan(zrow)).sum()))
            # Forest off by default: one fit per row is the entire runtime.
            fscore = fz = ofrac = np.nan
            if forest:
                _, fscore, fz = fit.score(x)
                # A position fallback holds none of the player's own rows.
                ofrac = 0.0 if source == "position" else fit.own_fraction(int((~np.isnan(x)).sum()))
            rows.append(
                (
                    pid,
                    match_id,
                    position,
                    source,
                    mdist,
                    zdist,
                    fscore,
                    fz,
                    ofrac,
                    zresid,
                    zresid_norm,
                    zofrac,
                )
            )
        return rows

    # Per-player, and its only draw is seeded from the player id, so the loop
    # is embarrassingly parallel and reproduces whatever the worker split is.
    histories = list(scored.groupby("player_id"))[:limit_players]
    if jobs and jobs != 1:
        from joblib import Parallel, delayed

        batches = Parallel(n_jobs=jobs)(delayed(one_player)(pid, g) for pid, g in histories)
    else:
        batches = [one_player(pid, g) for pid, g in histories]
    rows = [row for batch in batches for row in batch]

    return pd.DataFrame(
        rows,
        columns=[
            "player_id",
            "match_id",
            "position_code",
            "fit_source",
            "mahalanobis",
            "mahalanobis_res",
            "forest",
            "forest_norm",
            "forest_own_fraction",
            "forest_res",
            "forest_res_norm",
            "forest_res_own_fraction",
        ],
    )


def production_bars(
    scored: pd.DataFrame,
    census: pd.DataFrame,
    rate: float = baseline.DEFAULT_FLAG_RATE,
) -> dict[str, float]:
    """One cut per tagger, each tagging ``rate`` of the clean population.

    Drawn from the census, not from the injected rows, which are one per
    player and not a population. The baseline's cut is flag()'s own.
    """
    forest_cols = ("forest", "forest_norm", "forest_res", "forest_res_norm")
    have = [n for n in forest_cols if n in census]
    if have and len(have) != len(forest_cols):
        # All four absent is a census built without forests, which is fine.
        # SOME absent means the names moved under it -- the rename case, and
        # the one that would otherwise reach a bare KeyError downstream.
        raise KeyError(
            f"census carries only {have} of {list(forest_cols)}; it predates a "
            "column rename -- rebuild it with score_all(..., forest=True)"
        )
    flagged = baseline.flag(scored, rate)
    bars = {"max": float(flagged["flag_threshold"].iloc[0])}
    for name in ("mahalanobis", "mahalanobis_res", *forest_cols):
        if name not in census:
            if name in forest_cols:
                continue
            raise KeyError(
                f"census has no {name!r} column; rebuild it (a census cached "
                "before a column rename or added scorer is stale)"
            )
        clean = census[name].dropna()
        # A scorer switched off upstream has no census to cut, so no bar.
        bars[name] = float(np.nanquantile(clean, 1 - rate)) if len(clean) else np.nan
    return bars
