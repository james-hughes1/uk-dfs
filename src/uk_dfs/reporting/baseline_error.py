"""Plain-text report for Part B step 1 (`uk_dfs.evaluation.baseline_error`)."""

import pandas as pd

from uk_dfs.evaluation.baseline_error import VARIANTS
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
