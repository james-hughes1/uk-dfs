"""Plain-text report for Part B step 2 (`uk_dfs.evaluation.better_baselines`)."""

import pandas as pd

from uk_dfs.evaluation.baseline_error import Window
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
