"""Part C, step 2: how much of what NESO paid for turn-down bought real delivery?

Scenarios, not an estimate: the true saving of DFS participants is unknown. Each scenario
fixes a true saving (% of each home's use) and opt-in foresight ρ, and reads the settled
claim off the settlement-floor grid (`floor.grid`: LCL placebo homes, working days, homes
opting into 80% of event days as NESO observed in 2022/23, the saving added to every home,
negatives floored per meter per half-hour as the rules require for manual opt-in meters).
Then:

    real share r = true saving ÷ floored claim
    overpayment  = (1 − r) × settled cost

The floored claim splits into the true saving, baseline error (plain claim − saving at
ρ = 0), the floor and opt-in selection. The last two interact: foresight raises the plain
claim but leaves fewer meters negative, so the floor adds less. Their split is therefore
order-free (Shapley, the average over both orders):

    floor     = ½ [(floored − plain at ρ = 0) + (floored − plain at ρ)]
    selection = ½ [(floored at ρ − floored at 0) + (plain at ρ − plain at 0)]

and the four parts still sum to the floored claim. Settled cost is NESO's published settled
cost per turn-down half-hour, which already carries pay-as-bid prices and the volume cap;
the question is what NESO would have paid had it settled the true saving at the same prices.

Intervals on r come from the grid's block bootstrap over LCL days and are narrow; the real
uncertainty is which scenario applies. Since November 2024 delivery below 50% of the
contracted volume earns reduced payment and below 25% none, so for that period the
proportional overpayment is a lower bound.
"""

import numpy as np
import pandas as pd

from uk_dfs.features.events import IN_DAY_ADJUSTMENT_REMOVED, LAUNCH, MARKET, SECOND, turn_down

# name -> (true saving %, foresight ρ, label)
SCENARIOS = {
    "S1": (40, 0.0, "Strong response, random opt-in"),
    "S2": (20, 0.1, "Moderate response, slight foresight"),
    "S3": (10, 0.1, "Weak response, slight foresight"),
    "S4": (5, 0.3, "Very weak response, modest foresight"),
}
# Settlement periods: DFS's three phases (`features.events`)
PERIODS = {
    LAUNCH: (None, IN_DAY_ADJUSTMENT_REMOVED),
    SECOND: (IN_DAY_ADJUSTMENT_REMOVED, pd.Timestamp("2024-06-01")),
    MARKET: (pd.Timestamp("2024-06-01"), None),
}
PARTS = ("true", "baseline", "floor", "selection")


def grid_points(scenarios: dict = SCENARIOS) -> tuple[list, list]:
    """The savings and ρ values `floor.grid` must cover: each scenario's, plus ρ = 0."""
    savings = sorted({s for s, _, _ in scenarios.values()})
    rhos = sorted({0.0} | {r for _, r, _ in scenarios.values()})
    return savings, rhos


def period_of(start: pd.Series, periods: dict = PERIODS) -> pd.Series:
    """The settlement period each timestamp falls in (None outside every period)."""
    out = pd.Series(None, index=start.index, dtype=object)
    for name, (lo, hi) in periods.items():
        m = pd.Series(True, index=start.index)
        if lo is not None:
            m &= start >= lo
        if hi is not None:
            m &= start < hi
        out[m] = name
    return out


def settled_spend(summary: pd.DataFrame, periods: dict = PERIODS) -> pd.DataFrame:
    """Turn-down settled volume (MWh), settled cost (£) and unsettled half-hours per
    period, from `neso.load_dfs()`'s half-hourly summary, plus a Total row."""
    dn = summary[summary.direction == "Downwards"]
    label = period_of(dn.start, periods)
    rows = {}
    for name in periods:
        p = dn[label == name]
        rows[name] = {"settled_mwh": p.settled.sum() / 2, "cost": p.settled_cost.sum(),
                      "unsettled_hh": int((p.settled.isna() & (p.proc > 0)).sum())}  # fmt: skip
    out = pd.DataFrame(rows).T
    out.loc["Total"] = out.sum()
    out["price"] = out.cost / out.settled_mwh
    return out


def event_prices(summary: pd.DataFrame, periods: dict = PERIODS) -> pd.DataFrame:
    """One row per turn-down event (`features.events.turn_down`): start, period, test,
    procured MWh, settled (delivered) MWh, accepted bid cost (£) and the average accepted
    price (£/MWh). Settled MWh is missing for events NESO hasn't settled yet; the price is
    from accepted bids, so those events still have one."""
    dn = turn_down(summary)
    out = dn.groupby("event").agg(
        start=("start", "first"),
        test=("type", lambda t: (t == "Test").any()),
        procured_mwh=("proc", lambda mw: mw.sum() / 2),
        settled_mwh=("settled", lambda mw: mw.sum(min_count=1) / 2),
        cost=("cost", "sum"),
    )
    out.insert(1, "period", period_of(out.start, periods))
    out["price"] = out.cost / out.procured_mwh
    return out.reset_index(drop=True)


def decompose(grid: pd.DataFrame, scenarios: dict = SCENARIOS) -> pd.DataFrame:
    """One row per scenario: real share of the floored claim (with interval), the
    inflation factor, and each part's share of the floored claim (`PARTS`; floor and
    selection split order-free, see the module docstring)."""
    g = grid.set_index(["saving_pct", "rho"])
    rows = []
    for name, (saving, rho, label) in scenarios.items():
        r, r0 = g.loc[(saving, rho)], g.loc[(saving, 0.0)]
        total = r.floored_pct
        rows.append({
            "scenario": name, "label": label, "saving_pct": saving, "rho": rho,
            "floored_pct": total,
            "real_share": saving / total,
            "real_share_lo": saving / r.floored_pct_hi,
            "real_share_hi": saving / r.floored_pct_lo,
            "inflation": total / saving,
            "true": saving / total,
            "baseline": (r0.claim_pct - saving) / total,
            "floor": ((r0.floored_pct - r0.claim_pct) + (total - r.claim_pct)) / 2 / total,
            "selection": ((total - r0.floored_pct) + (r.claim_pct - r0.claim_pct)) / 2 / total,
        })  # fmt: skip
    return pd.DataFrame(rows).set_index("scenario")


def overpayment(dec: pd.DataFrame, spend: pd.DataFrame) -> pd.DataFrame:
    """£ paid for delivery that didn't happen: scenarios (rows) × periods (columns)."""
    return pd.DataFrame(
        np.outer(1 - dec.real_share, spend.cost), index=dec.index, columns=spend.index
    )


if __name__ == "__main__":
    from uk_dfs.data import neso
    from uk_dfs.evaluation import floor
    from uk_dfs.evaluation.baseline_error import Panel
    from uk_dfs.reporting.outputs import save
    from uk_dfs.reporting.overpayment import plot_overpayment, text_report, web_data

    summary = neso.load_dfs()
    spend = settled_spend(summary)
    savings, rhos = grid_points()
    panel = Panel.load()
    dec = decompose(floor.grid(panel, savings=savings, rhos=rhos))
    over = overpayment(dec, spend)
    print(text_report(spend, dec, over))
    print("\nSensitivity: opt-in share (main: 80% of event days)")
    for q in (0.5, 0.95):
        d = decompose(floor.grid(panel, savings=savings, rhos=rhos, share=q, n_boot=100))
        total = overpayment(d, spend)["Total"] / 1e6
        print(f"  {q:.0%}: " + "; ".join(
            f"{k} real share {r.real_share:.2f}, selection {r.selection * 100:.0f}/100, "
            f"£{total[k]:.1f}m" for k, r in d.iterrows()))  # fmt: skip
    events = event_prices(summary)
    save("overpayment", plot_overpayment(spend, dec, over), web_data(spend, dec, over, events))
