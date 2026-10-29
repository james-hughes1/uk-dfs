"""DFS events as one row each, and the names the study uses for DFS's phases.

NESO publishes one row per event half-hour. An event is a run of consecutive procured
turn-down half-hours. Two rule changes split DFS into three phases:

- Launch winter (2022/23): £3,000/MWh guaranteed price for tests, in-day adjustment on for
  domestic meters (Procurement Rules v1)
- Second winter (2023/24): guaranteed price kept, in-day adjustment removed from 27 Oct 2023
- Market phase (Nov 2024+): no guaranteed price, called in merit year-round, plain BL01

The national check has too few second-winter events to stand alone, so it compares the
launch winter with everything since Oct 2023 (the BL01 rule change).
"""

import numpy as np
import pandas as pd

IN_DAY_ADJUSTMENT_REMOVED = pd.Timestamp("2023-10-27")
LAUNCH = "Launch winter (2022/23)"
SECOND = "Second winter (2023/24)"
MARKET = "Market phase (Nov 2024+)"
SINCE_OCT_2023 = "Since Oct 2023"  # second winter + market phase: plain BL01


def turn_down(summary: pd.DataFrame) -> pd.DataFrame:
    """Procured turn-down half-hours in time order, numbered by `event`: one number per run
    of consecutive half-hours."""
    dn = summary[(summary.direction == "Downwards") & (summary.proc > 0)]
    dn = dn.sort_values("start", kind="stable")
    return dn.assign(event=(dn.start.diff() != pd.Timedelta("30min")).cumsum())


def event_table(summary: pd.DataFrame) -> pd.DataFrame:
    """One row per turn-down event from `neso.load_dfs()`'s half-hourly summary.

    Columns: start, date, m0 (start, minutes after local midnight), minutes (length),
    claim (mean settled MW over the event), has_settled (every half-hour settled), group.
    """
    dn = turn_down(summary)
    out = dn.groupby("event").agg(
        start=("start", "first"),
        halfhours=("start", "size"),
        claim=("settled", "mean"),
        has_settled=("settled", lambda s: s.notna().all()),
    )
    out["date"] = out.start.dt.normalize()
    out["m0"] = out.start.dt.hour * 60 + out.start.dt.minute
    out["minutes"] = 30 * out.pop("halfhours")
    out["group"] = np.where(out.date < IN_DAY_ADJUSTMENT_REMOVED, LAUNCH, SINCE_OCT_2023)
    return out


def event_days(summary: pd.DataFrame) -> pd.DatetimeIndex:
    """Every day with any procured DFS volume, turn-up included: never a control day."""
    return pd.DatetimeIndex(summary.loc[summary.proc > 0, "date"].unique()).sort_values()
