"""Part B, step 1: how wrong is BL01 when nobody responds?

Placebo test. The Low Carbon London flat-tariff (Std) homes were never sent a price
signal, so their true delivery in any window is zero and whatever BL01 claims for them is
error. For home h on day d and a window of half-hours:

    claimed delivery e_hd = baseline_hd − actual_hd   (average W over the window)

Positive means BL01 would pay for a saving that didn't happen.

- **B1, accuracy.** Per meter (one home-day): bias, SD, MAE, the share that comes out
  negative and what the per-meter settlement floor would add. Per portfolio (the Std
  homes' mean each day, as % of their usage): mean bias, day-to-day SD and MAE.
- **B2, when is it biased.** One regression of the daily portfolio error on conditions,
  stacked over windows w (start times):

      pct_dw = β0 + β1·dT_d + β2·(temp_d − 10) + β3·nonworking_d + Σ γ_w + ε_dw

  dT is the temperature change against the day's BL01 baseline days
  (`features.conditions`); γ_w are start-time effects relative to the first window.

Both are run with plain BL01 and with the 2022/23 in-day adjustment.

Uncertainty: moving-block bootstrap over days. Weather spells make neighbouring days'
errors alike, so days are resampled in circular blocks of `block` consecutive days, and all
windows of a day travel together. Intervals are 95% percentile intervals.

Typical use:

    from uk_dfs.evaluation import baseline_error as be
    panel = be.Panel.load()          # LCL cube + BL01 + London weather, ~1 GB in memory
    be.accuracy(panel)               # B1
    be.bias_regression(panel)        # B2

or `uv run python -m uk_dfs.evaluation.baseline_error`.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from uk_dfs.features.conditions import day_conditions
from uk_dfs.models import bl01

KW = 2000  # kWh per half-hour -> average W
VARIANTS = ("BL01", "BL01 + in-day adj")


@dataclass(frozen=True)
class Window:
    """A settlement window on the 48-slot local grid: `start` slot (34 = 17:00), `length`
    in half-hours."""

    start: int
    length: int = 2

    @property
    def slots(self) -> slice:
        return slice(self.start, self.start + self.length)

    @property
    def label(self) -> str:
        def hhmm(s):
            return f"{s // 2:02d}:{30 * (s % 2):02d}"

        return f"{hhmm(self.start)}–{hhmm(self.start + self.length)}"


MAIN = Window(34)  # 17:00–18:00, a typical one-hour DFS event
# DFS hours: one- and two-hour windows starting on the hour, 16:00–19:00
DFS_WINDOWS = tuple(Window(s, n) for n in (2, 4) for s in range(32, 40, 2))
# One-hour windows for the start-time effects in B2
EVENING = tuple(Window(s) for s in range(32, 40, 2))


@dataclass
class Panel:
    """Everything the placebo test needs, built once.

    X, B: (H, D, 48) actual use and unadjusted BL01, kWh per half-hour; n_days: (H, D)
    days in each baseline (0 = insufficient history); control: (H,) bool, the Std homes;
    days: one row per date with temp, dT and working.
    """

    X: np.ndarray
    B: np.ndarray
    n_days: np.ndarray
    dates: pd.DatetimeIndex
    control: np.ndarray
    days: pd.DataFrame
    first_day: pd.Timestamp | None = None

    @classmethod
    def build(
        cls,
        X: np.ndarray,
        dates: pd.DatetimeIndex,
        control: np.ndarray,
        temp: pd.Series,
        excluded: np.ndarray | None = None,
        first_day: str | None = None,
    ) -> "Panel":
        """Compute BL01 and the day conditions. `excluded`: (D,) days left out of every
        baseline (the trial's price-signal days, as BL01 skips event days)."""
        B, n_days = bl01.unadjusted(X, dates, excluded)
        days = day_conditions(temp, dates, excluded)
        first = pd.Timestamp(first_day) if first_day else None
        return cls(X, B, n_days, dates, np.asarray(control), days, first)

    @classmethod
    def load(cls) -> "Panel":
        """The LCL cube (all ToU homes + a sample of Std homes) and London weather. Days
        before March 2012 are dropped: few homes had joined and baselines lack history."""
        from uk_dfs.data import lcl, weather

        lcl.build()
        lcl.build_aggregates()
        lcl.build_cube()
        weather.fetch_london_weather()
        Xm, _, tou, dates = lcl.load_cube()
        temp = weather.load_london_weather().temp
        return cls.build(np.array(Xm), dates, ~tou, temp, lcl.signal_days(dates), "2012-03-01")


# --- Claimed delivery ---------------------------------------------------------------------


def delivery(
    panel: Panel, window: Window, adjusted: bool = False
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Claimed delivery and actual use per home, day and half-hour (W, shape (H, D, L)),
    and a (H, D) mask of usable home-days: a baseline exists, the window (and, if
    `adjusted`, the in-day reference window) is complete, not a clock-change day."""
    w = window.slots
    X = panel.X[..., w]
    e = (panel.B[..., w] - X) * KW
    ok = (panel.n_days > 0) & ~np.isnan(X).any(-1)
    ok &= ~bl01.clock_change_days(panel.dates)[None, :]
    if panel.first_day is not None:
        ok &= np.asarray(panel.dates >= panel.first_day)[None, :]
    if adjusted:
        adj = bl01.in_day_adjustment(panel.X, panel.B, window.start)  # kWh per half-hour
        e = e + adj[..., None] * KW
        ok &= ~np.isnan(adj)
    return e, X * KW, ok


def meter_stats(e: np.ndarray, use: np.ndarray, mask: np.ndarray) -> dict:
    """Per-meter accuracy over the home-days in `mask`. Shares in %, the rest in W or % of
    mean use. The floor zeroes negative delivery per half-hour (one settlement period), as
    the rules apply it to manual opt-in meters."""
    e_hh, u = e[mask], use[mask]
    e_w = e_hh.mean(-1)  # per meter over the whole window
    mean_use = u.mean()
    return {
        "home_days": len(e_w),
        "use_W": mean_use,
        "bias_W": e_w.mean(),
        "sd_W": e_w.std(),
        "mae_W": np.abs(e_w).mean(),
        "mae_pct": np.abs(e_w).mean() / mean_use * 100,
        "negative_pct": np.mean(e_w < 0) * 100,
        "negative_hh_pct": np.mean(e_hh < 0) * 100,
        "floored_pct": np.maximum(e_hh, 0).mean() / mean_use * 100,
    }


def portfolio_daily(
    e: np.ndarray, use: np.ndarray, mask: np.ndarray, dates: pd.DatetimeIndex, min_homes: int = 200
) -> pd.DataFrame:
    """One row per day with at least `min_homes` usable homes: mean claimed delivery and
    use (W per home), the claim as % of use, and the number of homes."""
    m = mask[..., None]
    n = mask.sum(0)
    claimed = np.where(m, e, 0).sum((0, 2)) / np.maximum(n, 1) / e.shape[-1]
    used = np.where(m, use, 0).sum((0, 2)) / np.maximum(n, 1) / e.shape[-1]
    out = pd.DataFrame({"claimed_W": claimed, "use_W": used, "homes": n}, index=dates)
    out = out[out.homes >= min_homes]
    out["pct"] = out.claimed_W / out.use_W * 100
    return out


# --- Moving-block bootstrap ---------------------------------------------------------------


def block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    """n positions made of circular runs of `block` consecutive positions."""
    starts = rng.integers(0, n, -(-n // block))
    return ((starts[:, None] + np.arange(block)) % n).ravel()[:n]


def block_bootstrap(
    n: int,
    stat: Callable[[np.ndarray], np.ndarray | float],
    block: int = 7,
    n_boot: int = 1000,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """`stat` evaluated on `n_boot` block-resampled position arrays: (n_boot, ...)."""
    rng = rng or np.random.default_rng(0)
    return np.array([stat(block_indices(n, block, rng)) for _ in range(n_boot)])


def interval(draws: np.ndarray) -> tuple:
    """95% percentile interval along the first axis."""
    return tuple(np.percentile(draws, [2.5, 97.5], axis=0))


# --- B1: accuracy -------------------------------------------------------------------------


PORTFOLIO_STATS = ("bias_pct", "sd_pct", "mae_pct")


def portfolio_stats(p: np.ndarray) -> np.ndarray:
    """Mean bias, day-to-day SD and MAE of daily portfolio errors (% of usage)."""
    return np.array([p.mean(), p.std(), np.abs(p).mean()])


def accuracy(
    panel: Panel,
    windows: Sequence[Window] = (MAIN,),
    n_boot: int = 1000,
    block: int = 7,
    seed: int = 0,
    min_homes: int = 200,
) -> pd.DataFrame:
    """One row per window and BL01 variant: per-meter stats (`meter_*`) and portfolio
    stats (`portfolio_*`, % of usage, with block-bootstrap intervals)."""
    rows = []
    for w in windows:
        for variant in VARIANTS:
            e, use, ok = delivery(panel, w, adjusted=variant != VARIANTS[0])
            mask = panel.control[:, None] & ok
            row = {"window": w.label, "variant": variant}
            row |= {f"meter_{k}": v for k, v in meter_stats(e, use, mask).items()}
            daily = portfolio_daily(e, use, mask, panel.dates, min_homes)
            p = daily.pct.to_numpy()
            rng = np.random.default_rng(seed)
            stat = lambda i, p=p: portfolio_stats(p[i])  # noqa: E731
            draws = block_bootstrap(len(p), stat, block, n_boot, rng)
            row["portfolio_days"] = len(p)
            for name, est, lo, hi in zip(PORTFOLIO_STATS, portfolio_stats(p), *interval(draws),
                                         strict=True):  # fmt: skip
                row |= {f"portfolio_{name}": est, f"portfolio_{name}_lo": lo,
                        f"portfolio_{name}_hi": hi}  # fmt: skip
            rows.append(row)
    return pd.DataFrame(rows)


# --- B2: when is it biased ----------------------------------------------------------------


def condition_rows(
    panel: Panel,
    windows: Sequence[Window] = EVENING,
    adjusted: bool = False,
    min_homes: int = 200,
) -> pd.DataFrame:
    """Daily portfolio error per window, joined to the day's conditions: one row per day
    and window, for `regress`."""
    out = []
    for w in windows:
        e, use, ok = delivery(panel, w, adjusted)
        daily = portfolio_daily(e, use, panel.control[:, None] & ok, panel.dates, min_homes)
        out.append(daily[["pct"]].join(panel.days).assign(window=w.label))
    rows = pd.concat(out).dropna(subset=["pct", "dT", "temp"])
    return rows.rename_axis("date").reset_index()


def design(rows: pd.DataFrame) -> pd.DataFrame:
    """Regressors: intercept, dT, temp − 10 °C, non-working day, start-time dummies."""
    X = pd.DataFrame(
        {
            "intercept": 1.0,
            "dT (per °C)": rows.dT,
            "temp − 10 °C (per °C)": rows.temp - 10,
            "non-working day": (~rows.working.astype(bool)).astype(float),
        },
        index=rows.index,
    )
    windows = pd.unique(rows.window)
    for w in windows[1:]:
        X[f"start {w} (vs {windows[0]})"] = (rows.window == w).astype(float)
    return X


def regress(rows: pd.DataFrame, n_boot: int = 1000, block: int = 7, seed: int = 0) -> pd.DataFrame:
    """OLS of `pct` on `design(rows)`, with a moving-block bootstrap over dates."""
    if rows.empty:
        raise ValueError("no day has enough usable homes; lower min_homes?")
    X = design(rows)
    A, y = X.to_numpy(), rows.pct.to_numpy()
    coef = np.linalg.lstsq(A, y, rcond=None)[0]
    days = np.sort(rows.date.unique())
    by_day = rows.groupby("date").indices
    groups = [by_day[d] for d in days]

    def fit(i):
        r = np.concatenate([groups[j] for j in i])
        return np.linalg.lstsq(A[r], y[r], rcond=None)[0]

    lo, hi = interval(block_bootstrap(len(days), fit, block, n_boot, np.random.default_rng(seed)))
    out = pd.DataFrame({"coef": coef, "lo": lo, "hi": hi}, index=X.columns)
    resid = y - A @ coef
    out.attrs |= {"rows": len(y), "days": len(days), "r2": 1 - resid.var() / y.var()}
    return out


def bias_regression(
    panel: Panel,
    windows: Sequence[Window] = EVENING,
    n_boot: int = 1000,
    block: int = 7,
    seed: int = 0,
    min_homes: int = 200,
) -> pd.DataFrame:
    """B2 for both BL01 variants, side by side: coefficient (percentage points of usage)
    and 95% interval."""
    out = {}
    for variant in VARIANTS:
        rows = condition_rows(panel, windows, variant != VARIANTS[0], min_homes)
        out[variant] = regress(rows, n_boot, block, seed)
    table = pd.concat(out, axis=1)
    table.attrs = {v: r.attrs for v, r in out.items()}  # rows, days, r2 per variant
    return table


if __name__ == "__main__":
    from uk_dfs.reporting.baseline_error import text_report

    panel = Panel.load()
    print(text_report(accuracy(panel, DFS_WINDOWS), bias_regression(panel)))
