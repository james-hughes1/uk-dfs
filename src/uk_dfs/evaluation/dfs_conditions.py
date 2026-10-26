"""Part C, step 1: BL01's error under the conditions of real DFS events.

Part B measured BL01's placebo error on Low Carbon London (LCL) flat-tariff homes, mostly
at 17:00–18:00 on ordinary days. DFS events aren't ordinary: NESO picks the days (cold
spells in 2022/23, mostly summer since 2025), the clock times and the lengths, and B2
showed the error depends on those conditions. So this re-scores the placebo on the mix of
real events:

1. **Describe every DFS turn-down event**: clock time, length, day type, season, GB
   temperature and the temperature change (dT) against the event's own BL01 baseline days
   (all DFS event days excluded from baselines, turn-up included).
2. **Score LCL placebo windows at each event's clock time and length.**
3. **Post-stratify.** Each event is matched to LCL days in the same cell, dT band × day
   type × season. Where a cell has fewer than `min_days` usable LCL days the match
   coarsens: first drop season, then dT, then day type. Each event counts once (its cell's
   sums are scaled to one meter-day), so longer events weigh more in half-hour shares.

Read out per rules period (A1 2022/23, in-day adjustment on; A2 from 27 Oct 2023, off):
share of meter-periods negative, plain claim, floored claim, all % of use, under both BL01
variants (`in_force` marks the period's own rules). A "timing only" version, matched on
nothing but the window, separates the effect of when events run from what the weather
does. The true saving is zero throughout: this is baseline error, not DFS delivery.

Intervals: moving-block bootstrap over LCL days (the events are the population, not a
sample). GB dT is a population-weighted average and swings less than London's single grid
cell, so the extreme dT cells are rarer for DFS than for LCL; matching on bands handles
that. Turn-up events (from April 2026) are out of scope: the floor and the claim flip sign.

Typical use:

    from uk_dfs.evaluation import baseline_error as be, dfs_conditions as c1
    ev = c1.describe_events(neso.load_dfs(), weather.daily_temperature(weather.load_weather()))
    c1.transfer(be.Panel.load(), ev)

or `uv run python -m uk_dfs.evaluation.dfs_conditions`.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from uk_dfs.evaluation.baseline_error import (
    CLAIM_STATS,
    MAIN,
    VARIANTS,
    Panel,
    Window,
    block_indices,
    claim_stats,
    day_sums,
    delivery,
    interval,
)
from uk_dfs.evaluation.floor import DT_BINS, DT_LABELS
from uk_dfs.features import events
from uk_dfs.features.conditions import day_conditions
from uk_dfs.models import bl01

SEASONS = {1: "Winter", 2: "Winter", 3: "Spring/autumn", 4: "Spring/autumn", 5: "Summer",
           6: "Summer", 7: "Summer", 8: "Summer", 9: "Spring/autumn", 10: "Spring/autumn",
           11: "Winter", 12: "Winter"}  # fmt: skip
CELL = ("dT_band", "working", "season")
# Finest first; each event uses the first level with at least `min_days` LCL days
LEVELS = (CELL, ("dT_band", "working"), ("working",), ())
TIMING_ONLY = ((),)
RULES = {events.A1: VARIANTS[1], events.A2: VARIANTS[0]}  # the BL01 variant in force


def cells(days: pd.DataFrame) -> pd.DataFrame:
    """Cell labels for days with `temp`, `dT`, `working`: dT band, working, season."""
    idx = pd.DatetimeIndex(days.index)
    return pd.DataFrame(
        {
            "dT_band": pd.cut(days.dT, list(DT_BINS), labels=list(DT_LABELS)).astype(object),
            "working": days.working.astype(bool),
            "season": idx.month.map(SEASONS),
        },
        index=days.index,
    )


def describe_events(summary: pd.DataFrame, temp: pd.Series) -> pd.DataFrame:
    """One row per DFS turn-down event (`features.events.event_table`) with its window on
    the 48-slot grid, GB temp, dT against its own baseline days, and cell labels. Events
    without temperature data have NaN dT and no dT band."""
    ev = events.event_table(summary).reset_index(drop=True)
    first = ev.date.min() - pd.Timedelta(days=bl01.WINDOW_DAYS + 7)
    dates = pd.date_range(first, ev.date.max())
    excluded = dates.isin(events.event_days(summary))
    cond = day_conditions(temp, dates, excluded)
    ev = ev.join(cond[["temp", "dT"]], on="date").join(cells(cond), on="date")
    ev["slot"] = ev.m0 // 30
    ev["length"] = ev.minutes // 30
    return ev


def event_summary(ev: pd.DataFrame) -> pd.DataFrame:
    """One column per rules period: what DFS events look like."""

    def stats(g):
        return pd.Series({
            "events": len(g),
            "median length, h": g.minutes.median() / 60,
            "start 16:00–19:00, %": g.m0.between(16 * 60, 19 * 60 - 1).mean() * 100,
            "working day, %": g.working.mean() * 100,
            "winter (Nov–Feb), %": (g.season == "Winter").mean() * 100,
            "summer (May–Aug), %": (g.season == "Summer").mean() * 100,
            "mean GB temp, °C": g.temp.mean(),
            "mean dT, °C": g.dT.mean(),
            "dT < −2 °C, %": (g.dT < -2).mean() * 100,
            "dT > +2 °C, %": (g.dT > 2).mean() * 100,
            "no temperature data": g.dT.isna().sum(),
        })  # fmt: skip

    return pd.DataFrame({k: stats(g) for k, g in ev.groupby("group")})


def match(
    ev: pd.DataFrame,
    lcl: pd.DataFrame,
    usable: np.ndarray,
    levels: Sequence[tuple] = LEVELS,
    min_days: int = 20,
) -> tuple[np.ndarray, list]:
    """(E, D) bool: the LCL days each event is matched to, and the level each used. `lcl`
    holds cell labels per LCL day, `usable` (D,) days with enough homes."""
    M = np.zeros((len(ev), len(lcl)), bool)
    used = []
    for i, e in enumerate(ev.itertuples()):
        for level in levels:
            m = usable.copy()
            for col in level:
                m &= (lcl[col] == getattr(e, col)).to_numpy()
            if m.sum() >= min_days:
                M[i], level_used = m, level
                break
        else:
            raise ValueError(f"event {i} matches fewer than {min_days} usable LCL days")
        used.append(" × ".join(level_used) or "window only")
    return M, used


def _pooled(M: np.ndarray, by_window: dict, sums: dict, w: np.ndarray) -> np.ndarray:
    """claim_stats over events, each event's matched-day sums (weighted by `w`, the
    bootstrap count of each day) scaled to one meter-day."""
    total = np.zeros(sums[next(iter(sums))].shape[1])
    for key, rows in by_window.items():
        s = (M[rows] * w) @ sums[key]  # (events in window, SUMS)
        total += np.nansum(s / s[:, :1], 0)
    return claim_stats(total[None, :])


def transfer(
    panel: Panel,
    ev: pd.DataFrame,
    levels: Sequence[tuple] = LEVELS,
    min_days: int = 20,
    min_homes: int = 200,
    n_boot: int = 1000,
    block: int = 7,
    seed: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Placebo claim stats on the mix of DFS events, per rules period and BL01 variant,
    with block-bootstrap intervals over LCL days; and the per-event table (level matched,
    LCL days matched, point claim stats under the period's own rules). Events without
    temperature data are dropped (counted in `attrs`)."""
    no_temp = ev.dT.isna() & any("dT_band" in level for level in levels)
    ev = ev[~no_temp].reset_index(drop=True)
    lcl = cells(panel.days)
    std = panel.control[:, None]
    windows = {k: Window(*k) for k in zip(ev.slot, ev.length, strict=True)}
    sums = {v: {} for v in VARIANTS}
    for k, w in windows.items():
        for v in VARIANTS:
            e, use, ok = delivery(panel, w, adjusted=v != VARIANTS[0])
            sums[v][k] = day_sums(e, use, std & ok)
    M, used = match(ev, lcl, _usable(panel, min_homes), levels, min_days)

    rows = []
    rng = np.random.default_rng(seed)
    boot = [np.bincount(block_indices(len(lcl), block, rng), minlength=len(lcl))
            for _ in range(n_boot)]  # fmt: skip
    for group, g in ev.groupby("group"):
        by_window = g.groupby(["slot", "length"]).indices
        by_window = {k: g.index[i] for k, i in by_window.items()}
        for v in VARIANTS:
            est = _pooled(M, by_window, sums[v], np.ones(len(lcl)))
            draws = np.array([_pooled(M, by_window, sums[v], w) for w in boot])
            row = {"group": group, "variant": v, "in_force": RULES[group] == v, "events": len(g)}
            for k, x, lo, hi in zip(CLAIM_STATS, est, *interval(draws), strict=True):
                row |= {k: x, f"{k}_lo": lo, f"{k}_hi": hi}
            rows.append(row)

    per_event = ev[["date", "start", "minutes", "group", "temp", "dT", *CELL]].copy()
    per_event["matched_on"] = used
    per_event["lcl_days"] = M.sum(1)
    stats = []
    for i, e in ev.iterrows():
        s = M[i] @ sums[RULES[e.group]][e.slot, e.length]
        stats.append(claim_stats(s[None, :]))
    per_event[list(CLAIM_STATS)] = np.array(stats)
    out = pd.DataFrame(rows)
    out.attrs |= {"dropped_no_temp": int(no_temp.sum())}
    return out, per_event


def _usable(panel: Panel, min_homes: int) -> np.ndarray:
    """(D,) days with at least `min_homes` usable Std homes at 17:00–18:00 with the in-day
    adjustment (the stricter of the two variants)."""
    _, _, ok = delivery(panel, MAIN, adjusted=True)
    return (panel.control[:, None] & ok).sum(0) >= min_homes


def reference(panel: Panel, min_homes: int = 200) -> dict:
    """Part B's reference point: every usable LCL day at 17:00–18:00, per variant."""
    usable = _usable(panel, min_homes)
    out = {}
    for v in VARIANTS:
        e, use, ok = delivery(panel, MAIN, adjusted=v != VARIANTS[0])
        s = day_sums(e, use, panel.control[:, None] & ok)[usable]
        out[v] = dict(zip(CLAIM_STATS, claim_stats(s), strict=True))
    return out


if __name__ == "__main__":
    from uk_dfs.data import neso, weather
    from uk_dfs.reporting.dfs_conditions import plot_dfs_conditions, web_data
    from uk_dfs.reporting.outputs import save
    from uk_dfs.reporting.text import ci, table

    temp = weather.daily_temperature(weather.load_weather())
    ev = describe_events(neso.load_dfs(), temp)
    print("C1. DFS turn-down events by rules period\n")
    print(event_summary(ev).round(1).to_string(), "\n")

    panel = Panel.load()
    ref = reference(panel)
    results = {}
    for name, levels in (("Timing only (event windows, all LCL days)", TIMING_ONLY),
                         ("Timing + conditions (post-stratified)", LEVELS)):  # fmt: skip
        out, per_event = transfer(panel, ev, levels)
        results["timing only" if levels == TIMING_ONLY else "timing + conditions"] = out
        print(f"{name}: Std placebo, true saving zero; % of use, bootstrap over LCL days")
        if out.attrs["dropped_no_temp"]:
            print(f"    {out.attrs['dropped_no_temp']} events dropped: no temperature data")
        print()
        print(table(pd.DataFrame({
            "period": out.group,
            "baseline": out.variant + np.where(out.in_force, " *", ""),
            "events": out.events,
            **{lab: [ci(r[k], r[f"{k}_lo"], r[f"{k}_hi"], signed=k == "claim_pct")
                     for _, r in out.iterrows()]
               for k, lab in (("negative_hh_pct", "neg % (half-hour)"),
                              ("claim_pct", "claim %"), ("floored_pct", "floored %"))},
        })), "\n")  # fmt: skip
        if levels == LEVELS:
            print("Events by matching level:")
            print(per_event.groupby(["group", "matched_on"]).size().to_string(), "\n")
    print("* = the rules in force for that period")
    print("Reference, every LCL day 17:00–18:00: " + "; ".join(
        f"{v} claim {r['claim_pct']:+.1f}%, floored {r['floored_pct']:+.1f}%"
        for v, r in ref.items()))  # fmt: skip
    save("dfs_conditions", plot_dfs_conditions(ev, results, ref), web_data(ev, results, ref))
