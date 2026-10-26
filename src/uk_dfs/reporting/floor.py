"""Chart and web data for the settlement floor (`uk_dfs.evaluation.floor`)."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uk_dfs.reporting.style import BLUE, BLUE_RAMP, INK2, ORANGE, style

SERIES = {"floored_pct": ("Floored per half-hour (current rules)", ORANGE),
          "claim_pct": ("Plain claim", BLUE)}  # fmt: skip


def _band(ax, x, df, k, colour, label):
    ax.fill_between(x, df[f"{k}_lo"], df[f"{k}_hi"], color=colour, alpha=0.15, lw=0)
    ax.plot(x, df[k], color=colour, marker="o", ms=4, label=label)


def plot_floor(by_start: pd.DataFrame, by_cond: pd.DataFrame, grid: pd.DataFrame) -> plt.Figure:
    """Left: placebo claim with and without the floor by start time. Middle: by temperature
    change. Right: overclaim (floored claim − true saving) against foresight, per true
    saving."""
    with style():
        fig, (a, b, c) = plt.subplots(1, 3, figsize=(15, 4.8))
        hours = by_start.window.str[:2].astype(int)
        for k, (label, colour) in SERIES.items():
            _band(a, hours, by_start, k, colour, label)
        a.axhline(0, color=INK2, lw=0.8)
        a.set_xlabel("Start of one-hour window (hour of day)")
        a.set_ylabel("Claimed delivery, % of use (true value 0)")
        a.set_title("No response at all: by time of day", fontsize=10)
        a.legend(loc="center left", fontsize=8)

        dT = by_cond[by_cond.group.str.startswith("ΔT")]
        x = np.arange(len(dT))
        for k, (label, colour) in SERIES.items():
            b.errorbar(x, dT[k], yerr=[dT[k] - dT[f"{k}_lo"], dT[f"{k}_hi"] - dT[k]], fmt="o",
                       color=colour, ms=5, capsize=3, lw=1, label=label)  # fmt: skip
        for xx, (_, r) in zip(x, dT.iterrows(), strict=True):
            b.annotate(
                f"{r.negative_hh_pct:.0f}% neg.",
                (xx, r.floored_pct_hi),
                xytext=(0, 6),
                textcoords="offset points",
                ha="center",
                fontsize=7,
                color=INK2,
            )
        b.axhline(0, color=INK2, lw=0.8)
        b.set_xticks(x, dT.condition)
        b.set_xlabel("Temperature change vs baseline days, °C (share of half-hours negative)")
        b.set_title("By temperature change, 17:00–18:00", fontsize=10)

        savings = sorted(grid.saving_pct.unique())
        ramp = BLUE_RAMP[-len(savings) :] if len(savings) <= len(BLUE_RAMP) else BLUE_RAMP
        for s, colour in zip(savings, ramp, strict=False):
            g = grid[grid.saving_pct == s]
            c.plot(g.rho, g.overclaim_pct, color=colour, marker="o", ms=4,
                   label=f"True saving {s:.0f}%")  # fmt: skip
        c.axhline(0, color=INK2, lw=0.8)
        c.set_xlabel("Foresight ρ (opting in on evenings expected to be quiet)")
        c.set_ylabel("Overclaim: floored claim − true saving, points of use")
        c.set_title("With a real saving and opt-in choice", fontsize=10)
        c.legend(loc="upper left", fontsize=8)
        fig.suptitle("The settlement floor: negatives zeroed per meter per half-hour turn noise "
                     "into payment", x=0.01, ha="left", fontweight="bold")  # fmt: skip
        fig.tight_layout()
    return fig


def web_data(by_start: pd.DataFrame, by_cond: pd.DataFrame, slider: pd.DataFrame) -> dict:
    keep = ["negative_hh_pct", "claim_pct", "floored_pct"]
    return {
        "by_start": by_start[["window", *keep, "floored_pct_lo", "floored_pct_hi"]],
        "by_condition": by_cond[["group", "condition", *keep]],
        "grid": slider[["saving_pct", "rho", *keep]],
    }
