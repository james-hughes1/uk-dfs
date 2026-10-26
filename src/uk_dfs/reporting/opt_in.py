"""Chart and web data for household opt-in (`uk_dfs.evaluation.opt_in`)."""

import matplotlib.pyplot as plt
import pandas as pd

from uk_dfs.evaluation.baseline_error import VARIANTS
from uk_dfs.reporting.style import BLUE, INK2, ORANGE, style

COLOURS = dict(zip(VARIANTS, (BLUE, ORANGE), strict=True))
PANELS = {"claim_pct": "Plain claim", "floored_pct": "With the per-meter floor"}


def plot_opt_in(sweep: pd.DataFrame) -> plt.Figure:
    """Claimed delivery on opted-in home-days against foresight ρ, without and with the
    floor; one line per BL01 variant. The true saving is zero throughout."""
    with style():
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
        for ax, (k, title) in zip(axes, PANELS.items(), strict=True):
            for v, g in sweep.groupby("variant", sort=False):
                ax.fill_between(g.rho, g[f"{k}_lo"], g[f"{k}_hi"], color=COLOURS[v], alpha=0.15,
                                lw=0)  # fmt: skip
                ax.plot(g.rho, g[k], color=COLOURS[v], marker="o", ms=4, label=v)
                end = g.iloc[-1]
                ax.annotate(
                    f"{end[k]:+.0f}%",
                    (end.rho, end[k]),
                    xytext=(6, 0),
                    textcoords="offset points",
                    va="center",
                    fontsize=8,
                    color=INK2,
                )
            ax.axhline(0, color=INK2, lw=0.8)
            ax.set_xlabel("Foresight ρ (0 = random opt-in, 1 = perfect)")
            ax.set_title(title, fontsize=10)
        axes[0].set_ylabel("Claimed delivery on opted-in days, % of use (true value 0)")
        axes[0].legend(loc="upper left", fontsize=8)
        share = sweep.share.iloc[0]
        fig.suptitle(f"Household opt-in: homes join on {share:.0%} of working days, picking the "
                     f"evenings they expect to be quiet ({sweep.window.iloc[0]})", x=0.01,
                     ha="left", fontweight="bold")  # fmt: skip
        fig.tight_layout()
    return fig


def web_data(sweep: pd.DataFrame) -> dict:
    cols = ["variant", "rho", "claim_pct", "claim_pct_lo", "claim_pct_hi", "floored_pct",
            "floored_pct_lo", "floored_pct_hi", "negative_hh_pct"]  # fmt: skip
    return {"window": sweep.window.iloc[0], "share": sweep.share.iloc[0], "sweep": sweep[cols]}
