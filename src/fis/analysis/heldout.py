"""Per-player scoring: the census, the fits behind it, and the production bars.

:func:`score_all` scores every eligible row against a fit from that player's
other matches, shrunk toward his position pool so there is no match floor and
no cliff. :func:`production_bars` cuts each scorer at the rate that census
delivers. The injection experiment that used to live here is now
:mod:`fis.analysis.injection_test`.
"""

from __future__ import annotations

import warnings

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
POOL_BORROW_CAP = 256


def _mahalanobis_distance(train: np.ndarray, test: np.ndarray) -> float:
    centre = train.mean(axis=0)
    covariance = np.cov(train, rowvar=False)
    centred = test - centre
    return float(np.sqrt(max(centred @ np.linalg.pinv(covariance) @ centred, 0)))


#: Positions pooled for the fallback fit.
POSITIONS = ("GK", "DF", "MD", "FW")


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
    ):
        self.train_x = train_x
        self.weight = weight
        self.pool = pool
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
        # Deterministic draw: the same fit must reproduce across workers.
        picked = np.random.default_rng(0).choice(len(self.pool), wanted, replace=False)
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


#: The shipped residual columns, from baseline.residuals -- reimplementing them
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
    position_nu, position_nu_z = {}, {}
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
                )
                source = "shrunk"
            mdist = fit.distance(x)
            # Same question as max|z|, combined by covariance instead of a
            # maximum; picks its own target row downstream.
            zdist = np.nan
            ztrain = complete_z[complete_ids != match_id]
            ztrain = ztrain[~np.isnan(ztrain).any(axis=1)]
            if len(ztrain) >= 2:
                pool_z = position_z.get(position)
                zfit = _Fit(
                    ztrain,
                    target=pool_z.cov if pool_z is not None else None,
                    weight=shrinkage_weight(len(ztrain), position_nu_z.get(position, np.inf)),
                )
                zdist = zfit.distance(zrow)
            # Forest off by default: one fit per row is the entire runtime.
            fscore = fz = ofrac = np.nan
            if forest:
                _, fscore, fz = fit.score(x)
                # A position fallback holds none of the player's own rows.
                ofrac = 0.0 if source == "position" else fit.own_fraction(int((~np.isnan(x)).sum()))
            rows.append((pid, match_id, position, source, mdist, zdist, fscore, fz, ofrac))
        return rows

    # Per-player and rng-free, so the loop is embarrassingly parallel.
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
            "mahalanobis_z",
            "forest",
            "forest_z",
            "forest_own_fraction",
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
    bars = {"max": float(baseline.flag(scored, rate)["flag_threshold"].iloc[0])}
    for name in ("mahalanobis", "mahalanobis_z", "forest", "forest_z"):
        clean = census[name].dropna()
        # A scorer switched off upstream has no census to cut, so no bar.
        bars[name] = float(np.nanquantile(clean, 1 - rate)) if len(clean) else np.nan
    return bars
