"""Chart and web data for BL01 under DFS conditions (`uk_dfs.evaluation.dfs_conditions`)."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uk_dfs.features.events import A1, A2
from uk_dfs.reporting.style import BLUE, INK2, MUTED, ORANGE, style

COLOURS = {A1: BLUE, A2: ORANGE}
SERIES = {"claim_pct": ("Plain claim", BLUE), "floored_pct": ("Floored per half-hour", ORANGE)}


def plot_dfs_conditions(ev: pd.DataFrame, results: dict, ref: dict) -> plt.Figure:
    """Left: every DFS turn-down event's temperature change against its own baseline days.
    Right: the LCL placebo claim on the mix of events, under each period's rules."""
    with style():
        fig, (a, b) = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={"width_ratios": [1.3, 1]})
        for g, e in ev.groupby("group"):
            a.scatter(e.date, e.dT, s=8 + e.minutes / 6, color=COLOURS[g], alpha=0.6, lw=0,
                      label=f"{g} ({len(e)} events)")  # fmt: skip
        a.axhline(0, color=INK2, lw=0.8)
        for y in (-2, 2):
            a.axhline(y, color=MUTED, lw=0.6)
        a.set_ylabel("Temperature change vs the event's BL01 baseline days, °C")
        a.set_title("DFS events weren't mostly cold snaps (dot size: event length)", fontsize=10)
        a.legend(loc="lower left", fontsize=8)

        rows = []
        for name, out in results.items():
            for _, r in out[out.in_force].iterrows():
                rows.append((f"{r.group.split(':')[0]} · {name}", r))
        y = np.arange(len(rows))[::-1]
        for k, (label, colour) in SERIES.items():
            v = np.array([r[k] for _, r in rows])
            lo = np.array([r[f"{k}_lo"] for _, r in rows])
            hi = np.array([r[f"{k}_hi"] for _, r in rows])
            b.errorbar(v, y, xerr=[v - lo, hi - v], fmt="o", color=colour, ms=6, capsize=3, lw=1,
                       label=label)  # fmt: skip
        main = ref[next(iter(ref))]
        b.axvline(0, color=INK2, lw=0.8)
        label = f"Reference, 17:00–18:00 every day: {main['floored_pct']:+.1f}%"
        b.axvline(main["floored_pct"], color=MUTED, lw=1, label=label)
        b.set_yticks(y, [name for name, _ in rows])
        b.set_xlabel("LCL placebo claim on the DFS event mix, % of use (true value 0)")
        b.set_title("BL01 under each period's rules, 95% CI", fontsize=10)
        b.legend(loc="center right", fontsize=8)
        b.grid(axis="y", visible=False)
        fig.suptitle("Transfer to DFS conditions: event timing and weather barely move the bias",
                     x=0.01, ha="left", fontweight="bold")  # fmt: skip
        fig.tight_layout()
    return fig


def web_data(ev: pd.DataFrame, results: dict, ref: dict) -> dict:
    return {
        "events": ev[["date", "group", "minutes", "temp", "dT"]].assign(
            date=ev.date.dt.strftime("%Y-%m-%d")
        ),
        "results": [
            {"setting": name, **r} for name, out in results.items() for r in out.to_dict("records")
        ],  # fmt: skip
        "reference": ref,
    }
