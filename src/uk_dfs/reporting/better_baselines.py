"""Text report, chart and web data for Part B step 2 (`uk_dfs.evaluation.better_baselines`)."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uk_dfs.evaluation.baseline_error import Window
from uk_dfs.reporting.baseline_error import fit_line
from uk_dfs.reporting.style import CATEGORICAL, INK2, style
from uk_dfs.reporting.text import ci, table


def text_report(
    scores: pd.DataFrame,
    by_dT: pd.DataFrame | None,
    window: Window,
    k_note: str | None = None,
    header: bool = True,
) -> str:
    """Scores per method (per meter and per portfolio), then bias by temperature change."""
    s = scores
    meter = pd.DataFrame(
        {
            "baseline": s.index,
            "MAE W": s.meter_mae_W.map("{:.0f}".format),
            "MAE %": s.meter_mae_pct.map("{:.1f}".format),
            "change vs BL01, W": [
                "—"
                if m == "BL01"
                else ci(
                    *s.loc[m, ["meter_mae_change_W", "meter_mae_change_lo", "meter_mae_change_hi"]]
                )  # fmt: skip
                for m in s.index
            ],
            "floor adds %": s.meter_floored_pct.map("{:.1f}".format),
        }
    )
    port = pd.DataFrame(
        {
            "baseline": s.index,
            "bias %": s.portfolio_bias_pct.map("{:+.1f}".format),
            "day-to-day SD %": s.portfolio_sd_pct.map("{:.1f}".format),
            "MAE %": s.portfolio_mae_pct.map("{:.1f}".format),
            "change vs BL01, pts": [
                "—"
                if m == "BL01"
                else ci(
                    *s.loc[
                        m,
                        [
                            "portfolio_mae_change",
                            "portfolio_mae_change_lo",
                            "portfolio_mae_change_hi",
                        ],
                    ]
                )  # fmt: skip
                for m in s.index
            ],
        }
    )
    lines = []
    if header:
        lines += [
            f"B3. Better baselines: flat-tariff homes, {window.label}, true delivery is zero",
            "    train Mar 2012 – Feb 2013, test Mar 2013 – Feb 2014: "
            f"{s.attrs['days']} test days, {s.attrs['home_days']:,} home-days, "
            f"mean use {s.attrs['use_W']:.0f} W",
        ]
        if k_note:
            lines.append(f"    BL01 × temperature: {k_note} warmer than the baseline days")
        lines.append("")
    lines += [
        "Per meter (one home on one day); change in MAE with 95% paired block-bootstrap CI",
        table(meter),
        "",
        "Portfolio (all flat-tariff homes, each day), % of usage",
        table(port),
    ]
    if by_dT is not None:
        b = by_dT.copy()
        out = pd.DataFrame({"temperature change °C": b.index.astype(str),
                            "days": b.days.astype(int).astype(str)})  # fmt: skip
        for m in b.columns[1:]:
            out[m] = b[m].map("{:+.1f}".format)
        lines += ["", "Portfolio claim by temperature change vs baseline days, % of usage",
                  table(out)]  # fmt: skip
    return "\n".join(lines)


def plot_better_baselines(scores: pd.DataFrame, by_dT: pd.DataFrame, window: Window) -> plt.Figure:
    """Left: portfolio claim by temperature change, per baseline. Right: daily portfolio
    MAE per baseline, with the change against BL01."""
    methods = list(scores.index)
    colours = dict(zip(methods, CATEGORICAL, strict=False))
    with style():
        fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={"width_ratios": [1.4, 1]})
        x = np.arange(len(by_dT))
        for m in methods:
            a.plot(x, by_dT[m], color=colours[m], marker="o", ms=5, label=m)
        a.axhline(0, color=INK2, lw=0.8)
        a.set_xticks(
            x, [f"{band}\n({n} days)" for band, n in zip(by_dT.index, by_dT.days, strict=True)]
        )
        a.set_xlabel("Temperature change vs the day's BL01 baseline days, °C")
        a.set_ylabel("Portfolio claimed delivery, % of use (true value 0)")
        a.set_title("Bias by temperature change", fontsize=10)
        a.legend(loc="upper left", fontsize=8)

        y = np.arange(len(methods))[::-1]
        b.barh(y, scores.portfolio_mae_pct, height=0.5, color=[colours[m] for m in methods])
        for yy, m in zip(y, methods, strict=True):
            r = scores.loc[m]
            note = (
                ""
                if m == "BL01"
                else (
                    f"  {r.portfolio_mae_change:+.1f} pts "
                    f"({r.portfolio_mae_change_lo:+.1f}, {r.portfolio_mae_change_hi:+.1f})"
                )
            )
            b.text(r.portfolio_mae_pct, yy, f" {r.portfolio_mae_pct:.1f}%{note}", va="center",
                   fontsize=8, color=INK2)  # fmt: skip
        b.set_yticks(y, methods)
        b.set_xlim(0, scores.portfolio_mae_pct.max() * 1.9)
        b.set_xlabel("Daily portfolio error (MAE), % of use")
        b.set_title("Accuracy (change vs BL01, 95% CI)", fontsize=10)
        b.grid(axis="y", visible=False)
        fig.suptitle(f"Better baselines: test year Mar 2013 – Feb 2014, {window.label}",
                     x=0.01, ha="left", fontweight="bold")  # fmt: skip
        fig.tight_layout()
    return fig


def web_data(scores: pd.DataFrame, by_dT: pd.DataFrame, window: Window,
             days: pd.DataFrame) -> dict:  # fmt: skip
    """`days` is `daily_claims()`: one row per test day, with a straight-line fit per method."""
    return {
        "window": window.label,
        "methods": list(scores.index),
        "scores": scores.reset_index(),
        "by_dT": by_dT.rename_axis("band").reset_index().astype({"band": str}),
        "days": days.assign(date=days.index.strftime("%Y-%m-%d")).reset_index(drop=True),
        "fits": {
            m: dict(zip(("slope", "intercept"), fit_line(days.dT, days[m]), strict=True))
            for m in scores.index
        },  # fmt: skip
    }
