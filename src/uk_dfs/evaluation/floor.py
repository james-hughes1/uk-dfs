"""Part B, step 3: the settlement floor for manual opt-in meters.

The guidance zeroes negative delivery per meter per settlement period (half-hour) before
summing a unit: in V11 (December 2023) providers enter 0 for a negative opt-in meter row
(Appendix 2, rule 7); in V18 (August 2026) the negative is reported but "will not be
settled" for manual opt-in meters (section 3.6, Table 2). So noise that nets to zero across
homes stops netting: every meter that comes out above its baseline counts as 0, every one
below counts in full.

What the floor adds therefore depends on the share of participating meter-periods that
come out negative. Three views, all plain BL01 (the floor arrived after the in-day
adjustment was removed):

1. **Placebo, by condition.** Std homes, true saving zero: share negative, plain claim and
   floored claim (per meter-hour and per half-hour), by temperature change against the
   baseline days, home size, day type and start time.
2. **A real response.** Time-of-use homes in High events: `reality_check` already reports
   their share negative and what the floor adds, against the Std control.
3. **Opt-in × saving grid.** Add a true saving of r% of each home's use, let homes opt in
   on half of days with foresight ρ (`opt_in`), and read off the share negative, the
   floored claim and the overclaim (floored claim − true saving). A published DFS share
   of negative meters would then convert into a floor effect via this grid.

Intervals: moving-block bootstrap over days, as in `baseline_error`.

Typical use:

    from uk_dfs.evaluation import baseline_error as be, floor
    panel = be.Panel.load()
    floor.by_condition(panel); floor.by_start(panel); floor.grid(panel)

or `uv run python -m uk_dfs.evaluation.floor`.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from uk_dfs.evaluation import opt_in
from uk_dfs.evaluation.baseline_error import (
    MAIN,
    Panel,
    Window,
    claim_summary,
    day_sums,
    delivery,
)

DT_BINS = (-np.inf, -4, -2, 0, 2, 4, np.inf)
DT_LABELS = ("< −4", "−4…−2", "−2…0", "0…2", "2…4", "> 4")
SIZE_LABELS = ("Small", "Medium", "Large")
# One-hour windows starting on the hour, 07:00 … 21:00
DAYTIME = tuple(Window(s) for s in range(14, 44, 2))
SAVINGS = (0, 10, 20, 30)
GRID_RHOS = (0.0, 0.1, 0.2, 0.3, 0.5, 0.7)
# The web app's interactive floor card: a finer grid, point estimates only matter
SLIDER_SAVINGS = (0, 5, 10, 15, 20, 25, 30, 40, 50)
SLIDER_RHOS = tuple(np.round(np.arange(0, 0.71, 0.1), 1))


def home_size(use: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """(H,) tercile label of each home's mean use over its days in `mask`, ranked among
    homes with any such day; None for the rest."""
    n = mask.sum(1)
    mean = np.where(mask[..., None], use, 0).sum((1, 2)) / np.maximum(n, 1) / use.shape[-1]
    out = np.full(len(n), None, dtype=object)
    has = n > 0
    out[has] = np.asarray(pd.qcut(mean[has], 3, labels=list(SIZE_LABELS)))
    return out


def conditions(panel: Panel, use: np.ndarray, mask: np.ndarray) -> dict:
    """{(group, label): (H, D) mask} for the placebo breakdown."""
    dT = pd.cut(panel.days.dT, list(DT_BINS), labels=list(DT_LABELS)).to_numpy()
    working = panel.days.working.to_numpy()
    size = home_size(use, mask)
    out = {("All", ""): mask}
    out |= {("ΔT vs baseline days, °C", k): mask & (dT == k)[None, :] for k in DT_LABELS}
    out |= {("Home size", k): mask & (size == k)[:, None] for k in SIZE_LABELS}
    out |= {("Day type", k): mask & (working == w)[None, :]
            for k, w in (("Working", True), ("Non-working", False))}  # fmt: skip
    return out


def by_condition(
    panel: Panel, window: Window = MAIN, n_boot: int = 1000, block: int = 7, seed: int = 0
) -> pd.DataFrame:
    """One row per condition: claim stats for Std placebo home-days (`claim_stats`)."""
    e, use, ok = delivery(panel, window)
    mask = panel.control[:, None] & ok
    rows = []
    for (group, label), m in conditions(panel, use, mask).items():
        rows.append({"group": group, "condition": label,
                     **claim_summary(day_sums(e, use, m), n_boot, block, seed)})  # fmt: skip
    return pd.DataFrame(rows)


def by_start(
    panel: Panel,
    windows: Sequence[Window] = DAYTIME,
    n_boot: int = 1000,
    block: int = 7,
    seed: int = 0,
) -> pd.DataFrame:
    """One row per window: claim stats for Std placebo home-days."""
    rows = []
    for w in windows:
        e, use, ok = delivery(panel, w)
        s = claim_summary(day_sums(e, use, panel.control[:, None] & ok), n_boot, block, seed)
        rows.append({"window": w.label, **s})
    return pd.DataFrame(rows)


def grid(
    panel: Panel,
    window: Window = MAIN,
    savings: Sequence[float] = SAVINGS,
    rhos: Sequence[float] = GRID_RHOS,
    share: float = 0.5,
    n_boot: int = 1000,
    block: int = 7,
    seed: int = 0,
) -> pd.DataFrame:
    """One row per true saving r (% of each home's use, every half-hour) and foresight ρ:
    claim stats over opted-in Std home-days on working days, plus the overclaim (floored
    claim − r, points of use). Each home foresees its claim including the saving."""
    e, use, ok = delivery(panel, window)
    mask = opt_in.placebo_mask(panel, ok)
    noise = np.random.default_rng(seed).standard_normal(mask.shape)
    rows = []
    for r in savings:
        e_r = e + use * r / 100  # a real saving lowers actual use, raising delivery
        for rho in rhos:
            pick = opt_in.choose(e_r.mean(-1), mask, rho, noise, share)
            s = claim_summary(day_sums(e_r, use, pick), n_boot, block, seed)
            rows.append({"saving_pct": r, "rho": rho, **s})
    out = pd.DataFrame(rows)
    for suffix in ("", "_lo", "_hi"):
        out[f"overclaim_pct{suffix}"] = out[f"floored_pct{suffix}"] - out.saving_pct
    return out


if __name__ == "__main__":
    from uk_dfs.data import lcl
    from uk_dfs.evaluation import reality_check as rc
    from uk_dfs.reporting.floor import plot_floor, web_data
    from uk_dfs.reporting.outputs import save
    from uk_dfs.reporting.text import ci, table

    def cols(df: pd.DataFrame) -> dict:
        def f(k, signed=True):
            return [ci(r[k], r[f"{k}_lo"], r[f"{k}_hi"], signed=signed) for _, r in df.iterrows()]

        return {
            "neg % (hour)": f("negative_pct", False),
            "neg % (half-hour)": f("negative_hh_pct", False),
            "claim %": f("claim_pct"),
            "floored % (hour)": f("floored_meter_pct"),
            "floored % (half-hour)": f("floored_pct"),
        }

    panel = Panel.load()
    c = by_condition(panel)
    print(f"B6. Settlement floor: Std placebo, {MAIN.label}, all usable days")
    print("    % of use; block bootstrap over days\n")
    print(table(pd.DataFrame({"group": c.group, "condition": c.condition, **cols(c)})), "\n")

    s = by_start(panel)
    print("By start time (one-hour windows)\n")
    print(table(pd.DataFrame({"window": s.window, **cols(s)})), "\n")

    t = rc.summarise(rc.event_table(panel, rc.high_events(lcl.load_tariffs(), panel.dates)))
    keep = [q for q in rc.QUANTITIES if "negative" in q or "Floor adds" in q]
    print("A real response: first hour of High events (from reality_check)\n")
    print(table(pd.DataFrame({"": keep, "estimate (95% CI)":
                              [ci(*t.loc[q], signed=False) for q in keep]})), "\n")  # fmt: skip

    g = grid(panel)
    print("Opt-in × true saving: Std placebo, working days, opt in on half of days\n")
    print(table(pd.DataFrame({
        "saving %": g.saving_pct.map("{:.0f}".format),
        "ρ": g.rho.map("{:.1f}".format),
        **{k: v for k, v in cols(g).items() if "hour)" not in k or "half" in k},
        "overclaim, points": [ci(r.overclaim_pct, r.overclaim_pct_lo, r.overclaim_pct_hi)
                              for r in g.itertuples()],
    })))  # fmt: skip
    slider = grid(panel, savings=SLIDER_SAVINGS, rhos=SLIDER_RHOS, n_boot=20)
    save("floor", plot_floor(s, c, g), web_data(s, c, slider))
