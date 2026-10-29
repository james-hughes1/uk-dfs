"""Text report, chart and web data for the overpayment scenarios
(`uk_dfs.evaluation.overpayment`)."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uk_dfs.evaluation.overpayment import PARTS
from uk_dfs.reporting.style import AQUA, BLUE, BLUE_RAMP, INK2, ORANGE, YELLOW, style
from uk_dfs.reporting.text import table

PART_LABELS = {"true": "True saving", "baseline": "Baseline error", "floor": "Settlement floor",
               "selection": "Opt-in selection"}  # fmt: skip
PART_COLOURS = dict(zip(PARTS, (AQUA, YELLOW, ORANGE, BLUE), strict=True))


def text_report(spend: pd.DataFrame, dec: pd.DataFrame, over: pd.DataFrame) -> str:
    s = pd.DataFrame({
        "period": spend.index,
        "settled MWh": spend.settled_mwh.map("{:,.0f}".format),
        "settled cost": spend.cost.map("£{:,.0f}".format),
        "£/MWh": spend.price.map("{:,.0f}".format),
        "unsettled half-hours": spend.unsettled_hh.map("{:.0f}".format),
    })  # fmt: skip
    d = pd.DataFrame({
        "scenario": dec.index,
        "true saving %": dec.saving_pct.map("{:.0f}".format),
        "ρ": dec.rho.map("{:.1f}".format),
        "real share (95% CI)": [f"{r.real_share:.2f} ({r.real_share_lo:.2f}, {r.real_share_hi:.2f})"
                                for r in dec.itertuples()],
        "inflation": dec.inflation.map("{:.2f}×".format),
        **{f"{PART_LABELS[p].lower()} /100": (dec[p] * 100).map("{:.0f}".format) for p in PARTS},
    })  # fmt: skip
    o = (over / 1e6).round(1).rename_axis("£m overpaid").reset_index()
    return "\n".join([
        "C2. Turn-down settled by NESO", table(s), "",
        "Scenarios: floored claim split per 100 MWh settled (LCL placebo + true saving)",
        table(d), "", "Overpayment = (1 − real share) × settled cost", table(o.astype(str)),
    ])  # fmt: skip


def plot_overpayment(spend: pd.DataFrame, dec: pd.DataFrame, over: pd.DataFrame) -> plt.Figure:
    """Left: what each 100 MWh settled consists of, per scenario. Right: £ paid for
    delivery that didn't happen, by period."""
    periods = [p for p in over.columns if p != "Total"]
    with style():
        fig, (a, b) = plt.subplots(1, 2, figsize=(14, 4.8))
        y = np.arange(len(dec))[::-1]
        left = np.zeros(len(dec))
        for p in PARTS:
            v = dec[p].to_numpy() * 100
            a.barh(y, v, left=left, height=0.5, color=PART_COLOURS[p], label=PART_LABELS[p],
                   edgecolor="white", linewidth=2)  # fmt: skip
            for yy, vv, ll in zip(y, v, left, strict=True):
                if vv >= 8:
                    a.text(
                        ll + vv / 2,
                        yy,
                        f"{vv:.0f}",
                        ha="center",
                        va="center",
                        fontsize=8,
                        color="#0b0b0b" if p in ("true", "baseline") else "white",
                    )
            left += v
        a.set_yticks(y, [f"{s}: {r.saving_pct:.0f}% saving, ρ {r.rho:.1f}\n{r.label}"
                         for s, r in dec.iterrows()], fontsize=8)  # fmt: skip
        a.set_xlim(0, 100)
        a.set_xlabel("Per 100 MWh settled")
        a.set_title("What the settled volume is made of", fontsize=10)
        a.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=4, fontsize=8)
        a.grid(axis="y", visible=False)

        left = np.zeros(len(dec))
        ramp = BLUE_RAMP[::2] if len(periods) == 3 else BLUE_RAMP[: len(periods)]
        for p, colour in zip(periods, ramp, strict=True):
            v = over[p].to_numpy() / 1e6
            b.barh(y, v, left=left, height=0.5, color=colour, edgecolor="white", linewidth=2,
                   label=f"{p} (£{spend.cost[p] / 1e6:.1f}m settled)")  # fmt: skip
            left += v
        for yy, total in zip(y, over["Total"] / 1e6, strict=True):
            b.text(total, yy, f"  £{total:.1f}m", va="center", fontsize=9, color=INK2)
        b.set_yticks(y, dec.index)
        b.set_xlim(0, spend.cost["Total"] / 1e6)
        b.set_xlabel(f"£m paid for delivery that didn't happen (axis ends at all "
                     f"£{spend.cost['Total'] / 1e6:.1f}m settled)")  # fmt: skip
        b.set_title("Overpayment by period", fontsize=10)
        b.legend(loc="upper right", fontsize=8)
        b.grid(axis="y", visible=False)
        fig.suptitle("Overpayment scenarios: the floor, not the baseline, drives the gap",
                     x=0.01, ha="left", fontweight="bold")  # fmt: skip
        fig.tight_layout()
    return fig


def web_data(spend: pd.DataFrame, dec: pd.DataFrame, over: pd.DataFrame,
             events: pd.DataFrame) -> dict:  # fmt: skip
    return {
        "spend": spend.rename_axis("period").reset_index(),
        "events": events.assign(start=events.start.dt.strftime("%Y-%m-%dT%H:%M")),
        "scenarios": dec.reset_index(),
        "overpayment": over.rename_axis("scenario").reset_index(),
    }
