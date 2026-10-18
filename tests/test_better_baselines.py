"""Part B step 2 (alternative baselines) on synthetic homes with known answers."""

import numpy as np
import pandas as pd
import pytest

from uk_dfs.evaluation import baseline_error as be
from uk_dfs.evaluation import better_baselines as bb
from uk_dfs.models.baselines import BoostedRatio, TemperatureScaled

# Spans both the training year (Mar 2012 – Feb 2013) and the test year
DATES = pd.date_range("2012-03-01", "2014-02-28")
K = -0.02  # use falls 2% per °C warmer than the baseline days


def weather(seed=0):
    rng = np.random.default_rng(seed)
    season = 10 - 7 * np.cos(2 * np.pi * (DATES.dayofyear - 20) / 365)
    temp = pd.Series(season + rng.normal(0, 2.5, len(DATES)), index=DATES)
    sunset = pd.Series(18 + 2 * np.sin(2 * np.pi * (DATES.dayofyear - 80) / 365), index=DATES)
    return temp, sunset


def weather_driven_panel(homes=40, seed=0):
    """Homes whose evening use moves with the temperature change, as BL01 can't follow."""
    rng = np.random.default_rng(seed)
    temp, sunset = weather(seed)
    probe = be.Panel.build(np.ones((1, len(DATES), 48), "float32"), DATES, [True], temp)
    dT = np.nan_to_num(probe.days.dT.to_numpy())
    level = rng.uniform(0.15, 0.4, homes)[:, None, None]
    X = level * np.exp(K * dT)[None, :, None] * np.ones((1, 1, 48))
    X = X * rng.lognormal(0, 0.15, X.shape)
    return be.Panel.build(X.astype("float32"), DATES, np.ones(homes, bool), temp), sunset


def day_table(ratio_level=1.0, seed=1):
    """Home-days whose actual ÷ BL01 is ratio_level · exp(K · dT) exactly."""
    rng = np.random.default_rng(seed)
    days = pd.date_range("2013-01-01", periods=200)
    dT = rng.normal(0, 3, len(days))
    rows = pd.DataFrame({"date": np.repeat(days, 5), "dT": np.repeat(dT, 5),
                         "bl01": rng.uniform(0.3, 0.6, 5 * len(days))})  # fmt: skip
    rows["actual"] = rows.bl01 * ratio_level * np.exp(K * rows.dT)
    return rows


def test_temperature_scaling_recovers_k_and_ignores_the_level():
    rows = day_table(ratio_level=1.05)
    m = TemperatureScaled().fit(rows)
    assert m.k == pytest.approx(K, abs=1e-6)
    expected = rows.bl01 * np.exp(K * rows.dT)  # without the 5% level
    assert m.predict(rows) == pytest.approx(expected.to_numpy())


def test_boosted_ratio_is_level_free_by_default():
    rows = day_table(ratio_level=1.05)
    rows[["size", "temp", "sunset", "dow", "working"]] = 0.5, 10.0, 18.0, 2, 1
    free = BoostedRatio(min_samples_leaf=20).fit(rows)
    assert free.predict(rows).sum() == pytest.approx(rows.bl01.sum())
    raw = BoostedRatio(min_samples_leaf=20, level_free=False).fit(rows)
    assert raw.predict(rows).sum() / rows.bl01.sum() == pytest.approx(1.05, abs=0.01)


def test_home_days_size_comes_from_the_training_year_only():
    panel, sunset = weather_driven_panel(homes=3)
    panel.X[0, np.asarray(DATES >= bb.TRAIN_END)] *= 3  # home 0 triples its use in the test year
    hd = bb.home_days(panel, sunset)
    train = hd[(hd.home == 0) & (hd.date < bb.TRAIN_END)]
    assert hd[hd.home == 0]["size"].iloc[0] == pytest.approx(train.actual.mean())


def test_forecast_error_moves_temp_and_dT_together():
    panel, sunset = weather_driven_panel(homes=3)
    a = bb.home_days(panel, sunset)
    b = bb.home_days(panel, sunset, forecast_error_sd=1.5)
    shift = b.temp - a.temp
    assert shift.std() > 1 and (b.dT - a.dT).to_numpy() == pytest.approx(shift.to_numpy())


def test_weather_aware_baselines_beat_bl01_when_use_follows_the_weather():
    panel, sunset = weather_driven_panel()
    c = bb.compare(bb.home_days(panel, sunset))
    assert c.test.date.min() >= bb.TRAIN_END and c.test.date.max() < bb.TEST_END
    assert c.models["BL01 × temperature"].k == pytest.approx(K, abs=0.005)
    s = bb.score(c, n_boot=50, min_homes=20)
    assert list(s.index) == c.methods
    for m in ("BL01 × temperature", "Gradient boosting"):
        assert s.loc[m, "portfolio_mae_pct"] < s.loc["BL01", "portfolio_mae_pct"]
        assert s.loc[m, "portfolio_mae_change_hi"] < 0  # better, and clearly so
    by = bb.bias_by_temperature_change(c, min_homes=20)
    cold, warm = by.loc["< −4", "BL01"], by.loc["> 4", "BL01"]
    assert cold < 0 < warm  # BL01 under-states use on cold snaps, over-states on warm ones
    assert abs(by.loc["< −4", "BL01 × temperature"]) < abs(cold)


def test_a_perfect_baseline_scores_zero():
    panel, sunset = weather_driven_panel(homes=25)
    c = bb.compare(bb.home_days(panel, sunset))
    c.test["Perfect"] = c.test.actual
    c.methods.append("Perfect")
    s = bb.score(c, n_boot=20, min_homes=20)
    assert s.loc["Perfect", ["meter_mae_W", "portfolio_mae_pct", "meter_floored_pct"]].tolist() == (
        pytest.approx([0, 0, 0])
    )


def test_text_report_renders():
    from uk_dfs.reporting.better_baselines import text_report

    panel, sunset = weather_driven_panel(homes=25)
    c = bb.compare(bb.home_days(panel, sunset))
    scores = bb.score(c, n_boot=20, min_homes=20)
    by_dT = bb.bias_by_temperature_change(c, min_homes=20)
    text = text_report(scores, by_dT, c.window, "-2.0% per °C")
    assert "B3. Better baselines" in text and "Gradient boosting" in text and "< −4" in text
