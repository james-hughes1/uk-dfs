"""BL01 baseline (Elexon P376) as used to settle DFS, vectorised over households.

Rules (DFS Procurement Rules, Schedule 3 Part 3; data/raw/neso_docs/379391.txt):
1. Eligible days for day D: D-60 … D-1, same day type (Working / Non-Working), complete
   half-hourly data, not an event day, not a clock-change day.
2. Working day: the 10 most recent eligible days (5–9 → all of them; <5 → insufficient).
   Non-Working day: the 4 most recent (<4 → insufficient), then the middle 2 ranked by
   daily total.
3. Unadjusted baseline = mean of those days, slot by slot. If insufficient, the baseline
   defaults to the out-turn (so delivery is zero).
4. In-day adjustment (domestic, 2022/23 rules only; removed from 27 Oct 2023): add the mean
   of (actual − unadjusted baseline) over the 3 hours ending 1 hour before the event.

Data is a (household, day, slot) array on a 48-slot local-time grid.
"""

import numpy as np
import pandas as pd

WINDOW_DAYS = 60
# England & Wales bank holidays covering the Low Carbon London period and 2022/23 DFS
BANK_HOLIDAYS = pd.to_datetime([
    "2011-01-03", "2011-04-22", "2011-04-25", "2011-04-29", "2011-05-02", "2011-05-30",
    "2011-08-29", "2011-12-26", "2011-12-27",
    "2012-01-02", "2012-04-06", "2012-04-09", "2012-05-07", "2012-06-04", "2012-06-05",
    "2012-08-27", "2012-12-25", "2012-12-26",
    "2013-01-01", "2013-03-29", "2013-04-01", "2013-05-06", "2013-05-27", "2013-08-26",
    "2013-12-25", "2013-12-26",
    "2014-01-01", "2014-04-18", "2014-04-21", "2014-05-05", "2014-05-26", "2014-08-25",
    "2014-12-25", "2014-12-26",
    "2022-01-03", "2022-04-15", "2022-04-18", "2022-05-02", "2022-06-02", "2022-06-03",
    "2022-08-29", "2022-09-19", "2022-12-26", "2022-12-27",
    "2023-01-02", "2023-04-07", "2023-04-10", "2023-05-01", "2023-05-08", "2023-05-29",
    "2023-08-28", "2023-12-25", "2023-12-26",
])  # fmt: skip


def working_days(dates: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray((dates.dayofweek < 5) & ~dates.isin(BANK_HOLIDAYS))


def clock_change_days(dates: pd.DatetimeIndex) -> np.ndarray:
    """Last Sunday of March and of October."""
    last_sunday = (dates.dayofweek == 6) & ((dates + pd.Timedelta(days=7)).month != dates.month)
    return np.asarray(last_sunday & dates.month.isin([3, 10]))


def unadjusted(
    X: np.ndarray,
    dates: pd.DatetimeIndex,
    event_days: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Unadjusted BL01 baseline for every household and day.

    X: (H, D, 48) kWh, NaN = missing; dates: the D consecutive days.
    event_days: bool (D,) or (H, D), days excluded from baselines.
    Returns (B, n): B is (H, D, 48); n is (H, D) days averaged, 0 where insufficient
    (B is then the out-turn, as the rules require).
    """
    H, D, _ = X.shape
    if event_days is None:
        event_days = np.zeros(D, bool)
    event_days = np.broadcast_to(event_days, (H, D))
    work = working_days(dates)
    usable = ~clock_change_days(dates)
    complete = ~np.isnan(X).any(axis=2)  # (H, D)
    totals = np.nansum(X, axis=2)

    B = np.array(X, dtype="float32")  # default: out-turn
    n = np.zeros((H, D), dtype="int8")
    for d in range(D):
        lo = max(0, d - WINDOW_DAYS)
        c = np.arange(d - 1, lo - 1, -1)  # most recent first
        c = c[(work[c] == work[d]) & usable[c]]
        if not len(c):
            continue
        E = complete[:, c] & ~event_days[:, c]
        rank = np.cumsum(E, axis=1)
        if work[d]:
            sel = E & (rank <= 10)
            ok = sel.sum(1) >= 5
        else:
            sel4 = E & (rank <= 4)
            ok = sel4.sum(1) == 4
            # middle two of the four, ranked by daily total
            order = np.argsort(np.where(sel4, totals[:, c], np.inf), axis=1, kind="stable")
            sel = np.zeros_like(sel4)
            rows = np.arange(H)[:, None]
            sel[rows, order[:, 1:3]] = True
            sel &= sel4
        k = sel.sum(1)
        Xc = np.where(sel[:, :, None], X[:, c, :], 0).sum(1)
        B[ok, d] = Xc[ok] / k[ok, None]
        n[ok, d] = k[ok]
    return B, n


def in_day_adjustment(X: np.ndarray, B: np.ndarray, start_slot: int) -> np.ndarray:
    """(H, D) additive adjustment for an event starting at `start_slot`.

    Reference window: the 6 slots ending 1 hour (2 slots) before the event starts.
    """
    if start_slot < 8:
        raise ValueError("reference window would start before midnight")
    w = slice(start_slot - 8, start_slot - 2)
    return np.mean(X[..., w] - B[..., w], axis=-1)
