"""Part B, step 2: can a baseline built on weather and calendar beat BL01?

Out-of-sample comparison on the flat-tariff (Std) homes, where true delivery is zero, so
every claim is error (as in step 1, `evaluation.baseline_error`). Train on March 2012 –
February 2013, test on March 2013 – February 2014: each a full seasonal year, because
BL01's error has a seasonal level (it lags rising use in autumn and falling use in
spring), and a model trained on part of the year learns that part's level. The Std homes
were never signalled, so the test year needn't be the trial year. For one window (default
17:00–18:00):

1. **BL01**: as settled today.
2. **BL01 + in-day adj**: the 2022/23 rules. A benchmark, not a candidate: it uses the
   household's own use on the day, so it can be gamed.
3. **BL01 × temperature** and 4. **Gradient boosting** (`models.baselines`): only inputs
   participants can't influence.

Scores, on the test year:
- **per meter**: MAE, and what the per-meter floor would add (it acts on per-meter noise,
  so a baseline that only fixes portfolio bias leaves it untouched);
- **per portfolio** (Std homes each day, % of usage): bias, day-to-day SD and MAE;
- **change in MAE against BL01**, with a paired moving-block bootstrap over test days
  (both methods resampled on the same days);
- **bias by temperature change**, the cold-snap problem from step 1.

Weather is observed, not forecast. Archived forecasts don't reach back to 2012–14, so
`forecast_error_sd` adds day-ahead-style noise to the temperature as a sensitivity check.

Typical use:

    from uk_dfs.evaluation import baseline_error as be, better_baselines as bb
    panel = be.Panel.load()
    result = bb.run(panel, sunset)

or `uv run python -m uk_dfs.evaluation.better_baselines`.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from uk_dfs.evaluation import baseline_error as be
from uk_dfs.models import bl01
from uk_dfs.models.baselines import BoostedRatio, TemperatureScaled

TRAIN_END = pd.Timestamp("2013-03-01")  # train: March 2012 (first usable) – February 2013
TEST_END = pd.Timestamp("2014-03-01")  # test: March 2013 – February 2014
BENCHMARKS = ("BL01", "BL01 + in-day adj")
DT_BINS = [-np.inf, -4, -2, 0, 2, 4, np.inf]
DT_LABELS = ["< −4", "−4…−2", "−2…0", "0…2", "2…4", "> 4"]


def home_days(
    panel: be.Panel,
    sunset: pd.Series,
    window: be.Window = be.MAIN,
    min_baseline: float = 0.02,
    forecast_error_sd: float = 0.0,
    seed: int = 0,
) -> pd.DataFrame:
    """One row per usable Std home-day: actual, BL01 and BL01 + in-day adjustment (kWh over
    the window), and the features. Home-days with a near-zero baseline (below
    `min_baseline` kWh) are dropped for every method, since the boosted model predicts a
    ratio to BL01. `size` is the home's mean use in the window before `TRAIN_END`, so the
    test year doesn't leak into it."""
    w = window.slots
    actual = panel.X[..., w].sum(-1)
    base = panel.B[..., w].sum(-1)
    ida = bl01.in_day_adjustment(panel.X, panel.B, window.start) * window.length
    _, _, ok = be.delivery(panel, window, adjusted=True)
    dT = panel.days.dT.to_numpy()
    mask = panel.control[:, None] & ok & (base > min_baseline) & ~np.isnan(dT)[None, :]
    train = np.asarray(panel.dates < TRAIN_END)
    size = np.nanmean(np.where(mask & train[None, :], actual, np.nan), axis=1)

    h, d = np.nonzero(mask)
    noise = np.random.default_rng(seed).normal(0, forecast_error_sd, len(panel.dates))
    days = panel.days
    return pd.DataFrame(
        {
            "home": h,
            "date": panel.dates[d],
            "actual": actual[h, d],
            "bl01": base[h, d],
            "bl01_ida": base[h, d] + ida[h, d],
            "size": size[h],
            "temp": days.temp.to_numpy()[d] + noise[d],
            "dT": dT[d] + noise[d],  # only the day itself is forecast; baseline days are past
            "sunset": sunset.reindex(panel.dates).to_numpy()[d],
            "dow": panel.dates.dayofweek[d],
            "working": days.working.to_numpy()[d].astype(int),
        }
    )


@dataclass
class Comparison:
    window: be.Window
    test: pd.DataFrame  # test home-days with one prediction column per method
    methods: list[str]
    models: dict = field(default_factory=dict)  # fitted candidates by name


def compare(hd: pd.DataFrame, window: be.Window = be.MAIN, candidates=None) -> Comparison:
    """Fit the candidates on home-days before `TRAIN_END`; predict for the test year
    (`TRAIN_END` to `TEST_END`)."""
    candidates = candidates or [TemperatureScaled(), BoostedRatio()]
    train = hd[hd.date < TRAIN_END]
    test = hd[(hd.date >= TRAIN_END) & (hd.date < TEST_END)].copy()
    test["BL01"] = test.bl01
    test["BL01 + in-day adj"] = test.bl01_ida
    models = {}
    for m in candidates:
        models[m.name] = m.fit(train)
        test[m.name] = m.predict(test)
    return Comparison(window, test, [*BENCHMARKS, *models], models)


def daily_pct(test: pd.DataFrame, method: str, min_homes: int = 200) -> pd.Series:
    """Portfolio claimed delivery per test day, % of usage."""
    g = test.assign(claim=test[method] - test.actual).groupby("date")
    day = g.agg(claim=("claim", "sum"), actual=("actual", "sum"), homes=("home", "size"))
    day = day[day.homes >= min_homes]
    return day.claim / day.actual * 100


def score(
    c: Comparison, n_boot: int = 1000, block: int = 7, seed: int = 0, min_homes: int = 200
) -> pd.DataFrame:
    """One row per method: per-meter and portfolio errors on the test year, and the
    change in MAE against BL01 with 95% paired block-bootstrap intervals."""
    t = c.test
    to_w = 2000 / c.window.length  # kWh over the window -> average W
    use_w = t.actual.mean() * to_w
    pct = pd.DataFrame({m: daily_pct(t, m, min_homes) for m in c.methods}).dropna()
    abs_e = pd.DataFrame({m: (t[m] - t.actual).abs() * to_w for m in c.methods})
    meter_day = abs_e.groupby(t.date).mean().reindex(pct.index)  # mean |error| per day

    rows = []
    for m in c.methods:
        e = (t[m] - t.actual) * to_w
        p = pct[m].to_numpy()
        d_port = np.abs(p) - np.abs(pct["BL01"].to_numpy())
        d_meter = (meter_day[m] - meter_day["BL01"]).to_numpy()
        rng = np.random.default_rng(seed)
        draws = be.block_bootstrap(
            len(p), lambda i, a=d_port, b=d_meter: [a[i].mean(), b[i].mean()], block, n_boot, rng
        )
        (lo_p, lo_m), (hi_p, hi_m) = be.interval(draws)
        rows.append({
            "method": m,
            "meter_mae_W": e.abs().mean(),
            "meter_mae_pct": e.abs().mean() / use_w * 100,
            "meter_floored_pct": np.maximum(e, 0).mean() / use_w * 100,
            "meter_mae_change_W": d_meter.mean(), "meter_mae_change_lo": lo_m,
            "meter_mae_change_hi": hi_m,
            "portfolio_bias_pct": p.mean(),
            "portfolio_sd_pct": p.std(),
            "portfolio_mae_pct": np.abs(p).mean(),
            "portfolio_mae_change": d_port.mean(), "portfolio_mae_change_lo": lo_p,
            "portfolio_mae_change_hi": hi_p,
        })  # fmt: skip
    out = pd.DataFrame(rows).set_index("method")
    out.attrs |= {"days": len(pct), "home_days": len(t), "use_W": use_w}
    return out


def bias_by_temperature_change(c: Comparison, min_homes: int = 200) -> pd.DataFrame:
    """Mean portfolio claim (% of usage) per temperature-change band, per method."""
    pct = pd.DataFrame({m: daily_pct(c.test, m, min_homes) for m in c.methods}).dropna()
    dT = c.test.groupby("date").dT.first().reindex(pct.index)
    band = pd.cut(dT, DT_BINS, labels=DT_LABELS)
    out = pct.groupby(band, observed=False).mean()
    out.insert(0, "days", band.value_counts().reindex(out.index))
    return out


def run(
    panel: be.Panel,
    sunset: pd.Series,
    window: be.Window = be.MAIN,
    forecast_error_sd: float = 0.0,
    n_boot: int = 1000,
    min_homes: int = 200,
) -> tuple[Comparison, pd.DataFrame, pd.DataFrame]:
    """Build the home-days, fit, score: (comparison, scores, bias by temperature change)."""
    hd = home_days(panel, sunset, window, forecast_error_sd=forecast_error_sd)
    c = compare(hd, window)
    return c, score(c, n_boot, min_homes=min_homes), bias_by_temperature_change(c, min_homes)


if __name__ == "__main__":
    from uk_dfs.data import weather
    from uk_dfs.reporting.better_baselines import plot_better_baselines, text_report, web_data
    from uk_dfs.reporting.outputs import save

    panel = be.Panel.load()
    sunset = weather.load_london_weather().sunset_h
    c, scores, by_dT = run(panel, sunset)
    k = c.models["BL01 × temperature"].k
    print(text_report(scores, by_dT, c.window, f"{k * 100:+.1f}% per °C"))
    _, noisy, _ = run(panel, sunset, forecast_error_sd=1.5)
    print("\nSensitivity: temperature with day-ahead-style error (SD 1.5 °C)")
    print(text_report(noisy, None, c.window, None, header=False))
    save("better_baselines", plot_better_baselines(scores, by_dT, c.window),
         web_data(scores, by_dT, c.window))  # fmt: skip
