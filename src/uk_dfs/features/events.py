"""DFS events as one row each, split into the two groups the national check compares.

NESO publishes one row per event half-hour. An event is a run of consecutive procured
turn-down half-hours. The groups follow the BL01 rule change:

- A1: before 27 Oct 2023, in-day adjustment on for domestic meters (Procurement Rules v1)
- A2: from 27 Oct 2023, adjustment removed (Procurement Rules v2 onwards)
"""

import numpy as np
import pandas as pd

IN_DAY_ADJUSTMENT_REMOVED = pd.Timestamp("2023-10-27")
A1, A2 = "A1: 2022/23", "A2: Oct 2023+"


def event_table(summary: pd.DataFrame) -> pd.DataFrame:
    """One row per turn-down event from `neso.load_dfs()`'s half-hourly summary.

    Columns: start, date, m0 (start, minutes after local midnight), minutes (length),
    claim (mean settled MW over the event), has_settled (every half-hour settled), group.
    """
    dn = summary[(summary.direction == "Downwards") & (summary.proc > 0)]
    dn = dn.sort_values("start", kind="stable")
    event = (dn.start.diff() != pd.Timedelta("30min")).cumsum().rename("event")
    out = dn.groupby(event).agg(
        start=("start", "first"),
        halfhours=("start", "size"),
        claim=("settled", "mean"),
        has_settled=("settled", lambda s: s.notna().all()),
    )
    out["date"] = out.start.dt.normalize()
    out["m0"] = out.start.dt.hour * 60 + out.start.dt.minute
    out["minutes"] = 30 * out.pop("halfhours")
    out["group"] = np.where(out.date < IN_DAY_ADJUSTMENT_REMOVED, A1, A2)
    return out


def event_days(summary: pd.DataFrame) -> pd.DatetimeIndex:
    """Every day with any procured DFS volume, turn-up included: never a control day."""
    return pd.DatetimeIndex(summary.loc[summary.proc > 0, "date"].unique()).sort_values()
