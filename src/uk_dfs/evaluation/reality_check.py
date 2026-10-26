"""Part B, step 3: a reality check against a real, randomised response.

Everywhere else in Part B the true effect is zero (placebo) or simulated. Here it is
real: in 2013 the time-of-use (ToU) homes were sent High prices and the flat-tariff (Std)
homes weren't, and the two groups were randomised. For the first hour of each High event
(a DFS-like window), and home h in group g:

    claimed delivery e_h = BL01 − actual   (W, per half-hour)
    true effect = mean e over ToU homes − mean e over Std homes   (difference-in-differences)

What it's for:
- **Does BL01 credit a real response correctly?** Claimed ÷ true for plain BL01.
- **How unevenly is a real response spread?** The share of ToU meters that still come out
  negative, against Std. That sets how much the per-meter settlement floor adds when
  homes really respond (the input B6 and Part C need).
- **2022/23 context:** claimed ÷ true with the in-day adjustment. The trial isn't DFS
  (events last 3–24 hours, no opt-in, a price not a reward), so read its size loosely.

Each event's first hour counts once; intervals come from a bootstrap over events.

Typical use:

    from uk_dfs.evaluation import baseline_error as be, reality_check as rc
    panel = be.Panel.load()
    events = rc.high_events(lcl.load_tariffs(), panel.dates)
    rc.summarise(rc.event_table(panel, events))

or `uv run python -m uk_dfs.evaluation.reality_check`.
"""

import numpy as np
import pandas as pd

from uk_dfs.evaluation.baseline_error import KW, Panel
from uk_dfs.models import bl01

TZ = "Europe/London"


def high_events(tariffs: pd.DataFrame, dates: pd.DatetimeIndex, earliest: int = 16) -> pd.DataFrame:
    """One row per High-price run within a local day: date, d (index into `dates`), start
    slot and length in half-hours. Runs starting before slot `earliest` (08:00) are
    dropped, so the in-day adjustment's reference window falls on the same day, and so are
    clock-change days."""
    local = tariffs.ts.dt.tz_localize("UTC").dt.tz_convert(TZ).dt.tz_localize(None)
    slot = local.dt.hour * 2 + local.dt.minute // 30
    high = tariffs.signal.eq("High").to_numpy()
    t = pd.DataFrame({"date": local.dt.normalize(), "slot": slot, "high": high})
    t = t.sort_values(["date", "slot"])
    run = ((t.high != t.high.shift()) | (t.date != t.date.shift())).cumsum()
    ev = t[t.high].groupby(run[t.high]).agg(date=("date", "first"), start=("slot", "min"),
                                            length=("slot", "size"))  # fmt: skip
    ev = ev[(ev.start >= earliest) & ev.date.isin(dates)]
    ev = ev[~bl01.clock_change_days(pd.DatetimeIndex(ev.date))]
    ev["d"] = dates.get_indexer(ev.date)
    return ev.reset_index(drop=True)


def event_table(panel: Panel, events: pd.DataFrame, hours: float = 1.0) -> pd.DataFrame:
    """One row per event: for ToU and Std homes, mean use, claimed delivery (plain, with
    the in-day adjustment, floored per half-hour) in W, and the share of half-hours
    negative, over the first `hours` of the event."""
    n = int(hours * 2)
    tou = ~panel.control
    rows = []
    for ev in events.itertuples():
        if ev.length < n:
            continue
        w = slice(ev.start, ev.start + n)
        X = panel.X[:, ev.d, w]
        e = (panel.B[:, ev.d, w] - X) * KW
        adj = bl01.in_day_adjustment(panel.X[:, ev.d : ev.d + 1], panel.B[:, ev.d : ev.d + 1],
                                     ev.start)[:, 0] * KW  # fmt: skip
        ok = (panel.n_days[:, ev.d] > 0) & ~np.isnan(X).any(-1) & ~np.isnan(adj)
        row = {"date": ev.date, "start": ev.start / 2, "length_h": ev.length / 2}
        for g, gm in (("tou", tou), ("std", panel.control)):
            m = gm & ok
            row |= {
                f"{g}_homes": m.sum(),
                f"{g}_use": X[m].mean() * KW,
                f"{g}_claim": e[m].mean(),
                f"{g}_claim_ida": (e[m] + adj[m, None]).mean(),
                f"{g}_floored": np.maximum(e[m], 0).mean(),
                f"{g}_negative": np.mean(e[m] < 0) * 100,
            }
        rows.append(row)
    return pd.DataFrame(rows)


def _summary(t: pd.DataFrame) -> np.ndarray:
    true = t.tou_claim.mean() - t.std_claim.mean()
    use = t.tou_use.mean()
    return np.array([
        true,
        true / use * 100,
        t.tou_claim.mean() / true * 100,
        t.tou_claim_ida.mean() / true * 100,
        t.tou_floored.mean() / true * 100,
        t.std_negative.mean(),
        t.tou_negative.mean(),
        (t.std_floored.mean() - t.std_claim.mean()) / t.std_use.mean() * 100,
        (t.tou_floored.mean() - t.tou_claim.mean()) / use * 100,
    ])  # fmt: skip


QUANTITIES = (
    "True effect, W per home",
    "True effect, % of ToU use",
    "BL01 claim, % of true",
    "BL01 + in-day adj claim, % of true (2022/23 rules)",
    "BL01 floored claim, % of true",
    "Std half-hours negative, %",
    "ToU half-hours negative, %",
    "Floor adds, Std, % of use",
    "Floor adds, ToU, % of use",
)


def summarise(t: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Pooled over events (ratios of means), with 95% intervals from a bootstrap over
    events."""
    rng = np.random.default_rng(seed)
    draws = np.array([_summary(t.iloc[rng.integers(0, len(t), len(t))]) for _ in range(n_boot)])
    lo, hi = np.percentile(draws, [2.5, 97.5], axis=0)
    out = pd.DataFrame({"estimate": _summary(t), "lo": lo, "hi": hi}, index=list(QUANTITIES))
    out.attrs |= {"events": len(t)}
    return out


if __name__ == "__main__":
    from uk_dfs.data import lcl
    from uk_dfs.reporting.outputs import save
    from uk_dfs.reporting.reality_check import plot_reality_check, web_data
    from uk_dfs.reporting.text import ci, table

    panel = Panel.load()
    t = event_table(panel, high_events(lcl.load_tariffs(), panel.dates))
    s = summarise(t)
    est = [ci(*r, signed=False) for r in s.to_numpy()]
    rows = pd.DataFrame({"": s.index, "estimate (95% CI)": est})
    print(f"Reality check: first hour of {s.attrs['events']} High-price events, 2013")
    print("    ToU vs randomised Std control; bootstrap over events\n")
    print(table(rows))
    save("reality_check", plot_reality_check(s), web_data(s))
