"""Chart and web data for the reality check (`uk_dfs.evaluation.reality_check`)."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uk_dfs.evaluation.reality_check import QUANTITIES
from uk_dfs.reporting.style import AQUA, BLUE, INK2, ORANGE, style

CLAIMS = {  # summary row -> bar label
    QUANTITIES[2]: "Plain BL01",
    QUANTITIES[3]: "BL01 + in-day adjustment\n(2022/23 rules)",
    QUANTITIES[4]: "BL01, negatives floored\nper meter (current rules)",
}


def plot_reality_check(s: pd.DataFrame) -> plt.Figure:
    """Left: what each settlement rule claims, as % of the true (randomised) effect. Right:
    share of meter half-hours that come out negative, with and without a real response."""
    with style():
        fig, (a, b) = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [1.8, 1]})
        rows = s.loc[list(CLAIMS)]
        y = np.arange(len(rows))[::-1]
        a.barh(y, rows.estimate, height=0.45, color=BLUE)
        a.errorbar(rows.estimate, y, xerr=[rows.estimate - rows.lo, rows.hi - rows.estimate],
                   fmt="none", color=INK2, capsize=3, lw=1)  # fmt: skip
        for yy, (_, r) in zip(y, rows.iterrows(), strict=True):
            a.text(r.hi, yy, f"  {r.estimate:.0f}%", va="center", fontsize=9, color=INK2)
        a.axvline(100, color=AQUA, lw=2, label="True effect (time-of-use vs randomised control)")
        a.set_yticks(y, list(CLAIMS.values()))
        a.set_xlabel("Claimed delivery, % of the true effect (95% CI, bootstrap over events)")
        a.set_title(f"What BL01 would pay for a real {s.estimate.iloc[1]:.0f}% saving",
                    fontsize=10)  # fmt: skip
        a.legend(loc="upper right", fontsize=8)
        a.grid(axis="y", visible=False)

        neg = s.loc[[QUANTITIES[5], QUANTITIES[6]]]
        x = np.arange(2)
        b.bar(x, neg.estimate, width=0.45, color=[ORANGE, BLUE])
        b.errorbar(x, neg.estimate, yerr=[neg.estimate - neg.lo, neg.hi - neg.estimate],
                   fmt="none", color=INK2, capsize=3, lw=1)  # fmt: skip
        for xx, v in zip(x, neg.estimate, strict=True):
            b.text(xx, v / 2, f"{v:.0f}%", ha="center", color="white", fontweight="bold")
        b.set_xticks(x, ["Flat tariff\n(no response)", "Time-of-use\n(real response)"])
        b.set_ylabel("Meter half-hours with negative delivery, %")
        b.set_title("A real response barely shrinks the negatives", fontsize=10)
        b.grid(axis="x", visible=False)
        fig.suptitle(f"Reality check: first hour of {s.attrs.get('events', '?')} randomised "
                     "High-price events, Low Carbon London 2013", x=0.01, ha="left",
                     fontweight="bold")  # fmt: skip
        fig.tight_layout()
    return fig


def web_data(s: pd.DataFrame) -> dict:
    return {"events": s.attrs.get("events"),
            "summary": s.rename_axis("quantity").reset_index()}  # fmt: skip
