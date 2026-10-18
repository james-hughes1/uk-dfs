"""Day-level conditions that BL01's error depends on.

The key one is the temperature change: the day's temperature minus the average over the
days BL01 would draw its baseline from. BL01 assumes the event day looks like those days,
so it errs when the weather has moved since. The day selection mirrors `models.bl01`
(same day type, previous 60 days, not a clock-change or event day; 10 most recent for a
working day, 4 for a non-working day) at portfolio level, so it ignores each home's
missing data and the middle-two rule for non-working days.
"""

import numpy as np
import pandas as pd

from uk_dfs.models import bl01


def temperature_change(
    temp: pd.Series, dates: pd.DatetimeIndex, event_days: np.ndarray | None = None
) -> pd.Series:
    """°C, indexed by `dates`; NaN where there aren't enough baseline days."""
    t = temp.reindex(dates).to_numpy()
    work = bl01.working_days(dates)
    usable = ~bl01.clock_change_days(dates)
    if event_days is not None:
        usable &= ~np.asarray(event_days)
    out = np.full(len(dates), np.nan)
    for d in range(len(dates)):
        c = np.arange(d - 1, max(-1, d - bl01.WINDOW_DAYS - 1), -1)  # most recent first
        k = 10 if work[d] else 4
        c = c[(work[c] == work[d]) & usable[c]][:k]
        if len(c) == k:
            out[d] = t[d] - t[c].mean()
    return pd.Series(out, index=dates, name="dT")


def day_conditions(
    temp: pd.Series, dates: pd.DatetimeIndex, event_days: np.ndarray | None = None
) -> pd.DataFrame:
    """One row per day: temp, dT (temperature change), working (bool)."""
    return pd.DataFrame(
        {
            "temp": temp.reindex(dates).to_numpy(),
            "dT": temperature_change(temp, dates, event_days).to_numpy(),
            "working": bl01.working_days(dates),
        },
        index=dates,
    )
