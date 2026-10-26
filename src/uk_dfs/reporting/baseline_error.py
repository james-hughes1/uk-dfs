"""Text report, chart and web data for Part B step 1 (`uk_dfs.evaluation.baseline_error`)."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uk_dfs.evaluation.baseline_error import MAIN, VARIANTS
from uk_dfs.reporting.style import BLUE, INK2, ORANGE, style
from uk_dfs.reporting.text import ci as _ci
from uk_dfs.reporting.text import table as _table

SHORT = {VARIANTS[0]: "BL01", VARIANTS[1]: "+ in-day adj"}


def text_report(acc: pd.DataFrame, reg: pd.DataFrame) -> str:
    """B1 per-meter and portfolio tables, then the B2 regression, as aligned text."""
    meter = pd.DataFrame(
        {
            "window": acc.window,
            "baseline": acc.variant.map(SHORT),
            "use W": acc.meter_use_W.map("{:.0f}".format),
            "bias W": acc.meter_bias_W.map("{:+.1f}".format),
            "SD W": acc.meter_sd_W.map("{:.0f}".format),
            "MAE %": acc.meter_mae_pct.map("{:.0f}".format),
            "negative %": acc.meter_negative_hh_pct.map("{:.0f}".format),
            "floor adds %": acc.meter_floored_pct.map("{:.1f}".format),
        }
    )
    port = pd.DataFrame(
        {
            "window": acc.window,
            "baseline": acc.variant.map(SHORT),
            **{
                label: [
                    _ci(
                        r[f"portfolio_{k}"],
                        r[f"portfolio_{k}_lo"],
                        r[f"portfolio_{k}_hi"],
                        signed=k == "bias_pct",
                    )  # fmt: skip
                    for _, r in acc.iterrows()
                ]
                for k, label in (
                    ("bias_pct", "bias"),
                    ("sd_pct", "day-to-day SD"),
                    ("mae_pct", "MAE"),
                )  # fmt: skip
            },
        }
    )
    b2 = pd.DataFrame(
        {
            "term": reg.index,
            **{SHORT[v]: [_ci(*reg.loc[t, v], dp=2) for t in reg.index] for v in VARIANTS},
        }
    )
    fit = reg.attrs.get(VARIANTS[0], {})
    days = acc.portfolio_days.iloc[0]
    homes = acc.meter_home_days.iloc[0]
    lines = [
        "B1. Placebo accuracy: flat-tariff homes, so true delivery is zero",
        f"    claimed delivery = baseline − actual; {days} days, ~{homes:,} home-days per row",
        "",
        "Per meter (one home on one day). negative % = share of half-hours below zero;",
        "floor adds % = claimed delivery if negatives are set to zero, % of usage",
        _table(meter),
        "",
        "Portfolio (all flat-tariff homes, each day), % of usage, 95% block-bootstrap CI",
        _table(port),
        "",
        "B2. Daily portfolio error regressed on conditions, percentage points of usage",
        f"    one-hour windows 16:00–20:00 stacked; {fit.get('days', '?')} days, "
        f"R² {fit.get('r2', float('nan')):.2f} (BL01); 95% block-bootstrap CI",
        _table(b2),
    ]
    return "\n".join(lines)


COLOURS = dict(zip(VARIANTS, (BLUE, ORANGE), strict=True))
METER_BINS = np.arange(-2000, 2001, 50)  # W
PORTFOLIO_BINS = np.arange(-150, 151, 10)  # W per home


def fit_line(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    """Simple least-squares slope and intercept, for drawing (B2's regression has more
    terms)."""
    ok = x.notna() & y.notna()
    slope, intercept = np.polyfit(x[ok], y[ok], 1)
    return slope, intercept


def plot_baseline_error(meters: np.ndarray, days: pd.DataFrame, reg: pd.DataFrame) -> plt.Figure:
    """Left: claimed delivery for one home-day vs the portfolio's daily average (both
    should be zero). Right: the portfolio's daily claim against the temperature change."""
    with style():
        fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5))
        port = days[f"{VARIANTS[0]}: claimed_W"].to_numpy()
        a.hist(meters, METER_BINS, density=True, histtype="stepfilled", color=BLUE, alpha=0.15)
        a.hist(meters, METER_BINS, density=True, histtype="step", color=BLUE,
               label=f"One home on one day (SD {meters.std():.0f} W)")  # fmt: skip
        a.hist(port, PORTFOLIO_BINS, density=True, histtype="stepfilled", color=ORANGE, alpha=0.15)
        a.hist(port, PORTFOLIO_BINS, density=True, histtype="step", color=ORANGE,
               label=f"Portfolio average, each day (SD {port.std():.0f} W)")  # fmt: skip
        a.axvline(0, color=INK2, lw=0.8)
        a.set_xlim(-1500, 1500)
        a.set_yticks([])
        a.set_xlabel(f"Claimed delivery, W ({MAIN.label}, plain BL01; true value 0)")
        a.set_title("One home is noise; a portfolio averages out", fontsize=10)
        a.legend(loc="upper left", fontsize=8)

        for v in VARIANTS:
            y = days[f"{v}: pct"]
            slope = reg.loc["dT (per °C)", (v, "coef")]
            b.scatter(days.dT, y, s=10, color=COLOURS[v], alpha=0.35, lw=0)
            k, c = fit_line(days.dT, y)
            x = np.linspace(days.dT.min(), days.dT.max(), 2)
            b.plot(x, c + k * x, color=COLOURS[v],
                   label=f"{v}: {slope:+.1f} points per °C (B2 regression)")  # fmt: skip
        b.axhline(0, color=INK2, lw=0.8)
        b.axvline(0, color=INK2, lw=0.8)
        b.set_xlabel("Temperature change vs the day's BL01 baseline days, °C")
        b.set_ylabel("Portfolio claimed delivery, % of use")
        b.set_title("Days warmer than the baseline days look like savings", fontsize=10)
        b.legend(loc="upper left", fontsize=8)
        fig.suptitle("Placebo: BL01 on flat-tariff homes that were never asked to respond",
                     x=0.01, ha="left", fontweight="bold")  # fmt: skip
        fig.tight_layout()
    return fig


def _hist(x: np.ndarray, bins: np.ndarray) -> list[dict]:
    density, edges = np.histogram(x, bins, density=True)
    return [
        {"x0": lo, "x1": hi, "density": d}
        for lo, hi, d in zip(edges, edges[1:], density, strict=False)
    ]


def web_data(meters: np.ndarray, days: pd.DataFrame, acc: pd.DataFrame, examples: list) -> dict:
    main = acc[acc.window == MAIN.label].set_index("variant")
    port = days[f"{VARIANTS[0]}: claimed_W"].to_numpy()
    return {
        "window": MAIN.label,
        "meter_hist": _hist(meters, METER_BINS),
        "portfolio_hist": _hist(port, PORTFOLIO_BINS),
        "meter_sd_W": meters.std(),
        "portfolio_sd_W": port.std(),
        "days": pd.DataFrame(
            {
                "date": days.index.strftime("%Y-%m-%d"),
                "dT": days.dT,
                "bl01": days[f"{VARIANTS[0]}: pct"],
                "ida": days[f"{VARIANTS[1]}: pct"],
            }
        ),  # fmt: skip
        "fits": {
            SHORT[v]: dict(
                zip(("slope", "intercept"), fit_line(days.dT, days[f"{v}: pct"]), strict=True)
            )
            for v in VARIANTS
        },  # fmt: skip
        "stats": main.reset_index(),
        "examples": examples,
    }
