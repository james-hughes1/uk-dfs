"""Part B step 1 (placebo accuracy, bias regression) on synthetic homes with known answers."""

import numpy as np
import pandas as pd
import pytest

from uk_dfs.evaluation import baseline_error as be
from uk_dfs.features.conditions import temperature_change

# Mon 2 Jan 2023 -> 90 days; the clock changes on Sun 26 Mar (day 83)
DATES = pd.date_range("2023-01-02", periods=90, freq="D")
W = be.MAIN  # 17:00–18:00, slots 34-35


def flat_panel(level=0.25, homes=3, temp=5.0):
    X = np.full((homes, len(DATES), 48), level, "float32")
    return X, pd.Series(temp, index=DATES)


def test_window_label_and_slots():
    assert be.Window(34).label == "17:00–18:00"
    assert be.Window(33, 4).label == "16:30–18:30"
    assert be.Window(34, 4).slots == slice(34, 38)


def test_no_error_when_every_day_is_the_same():
    X, temp = flat_panel()
    panel = be.Panel.build(X, DATES, np.ones(3, bool), temp)
    e, use, ok = be.delivery(panel, W)
    assert ok[:, 30:83].all() and not ok[:, 0].any()  # day 0 has no history
    assert not ok[:, 83].any()  # Sun 26 Mar 2023: clock change
    assert np.abs(e[ok]).max() == pytest.approx(0)
    assert use[ok].mean() == pytest.approx(500)  # 0.25 kWh per half-hour = 500 W


def test_a_quiet_evening_shows_up_as_claimed_delivery():
    X, temp = flat_panel()
    d = 60
    X[1, d, 34:36] = 0.20  # home 1 uses 100 W less in the window that day
    panel = be.Panel.build(X, DATES, np.ones(3, bool), temp)
    e, _, ok = be.delivery(panel, W)
    assert e[1, d] == pytest.approx([100, 100])
    assert np.abs(np.delete(e[:, d], 1, axis=0)).max() == pytest.approx(0)


def test_in_day_adjustment_is_added():
    X, temp = flat_panel()
    d = 60
    X[0, d, 26:32] += 0.05  # +100 W over 13:00–16:00, the reference window for 17:00
    panel = be.Panel.build(X, DATES, np.ones(3, bool), temp)
    e, _, _ = be.delivery(panel, W, adjusted=True)
    assert e[0, d] == pytest.approx([100, 100])  # baseline raised, actual unchanged


def test_meter_stats_share_negative_and_floor():
    e = np.array([[[100.0, 100.0]], [[-100.0, -100.0]]])  # one meter +100 W, one −100 W
    use = np.full_like(e, 500.0)
    s = be.meter_stats(e, use, np.ones((2, 1), bool))
    assert s["bias_W"] == pytest.approx(0)
    assert s["negative_pct"] == pytest.approx(50)
    assert s["floored_pct"] == pytest.approx(10)  # mean max(e, 0) = 50 W of 500 W


def test_floor_is_per_half_hour():
    e = np.array([[[100.0, -100.0]]])  # nets to zero over the hour
    s = be.meter_stats(e, np.full_like(e, 500.0), np.ones((1, 1), bool))
    assert s["negative_pct"] == 0 and s["negative_hh_pct"] == pytest.approx(50)
    assert s["floored_pct"] == pytest.approx(10)


def test_portfolio_daily_is_mean_claim_over_mean_use():
    e = np.zeros((2, 3, 2))
    e[:, 1] = [[50, 50], [150, 150]]
    use = np.full_like(e, 500.0)
    mask = np.ones((2, 3), bool)
    mask[1, 2] = False
    p = be.portfolio_daily(e, use, mask, DATES[:3], min_homes=2)
    assert list(p.index) == list(DATES[:2])  # day 2 has only one usable home
    assert p.pct.tolist() == pytest.approx([0, 20])


def test_block_indices_are_circular_runs():
    i = be.block_indices(10, 4, np.random.default_rng(1))
    assert len(i) == 10
    for run in (i[:4], i[4:8]):
        assert np.all(np.diff(run) % 10 == 1)


def test_block_bootstrap_interval_covers_the_mean():
    x = np.random.default_rng(2).normal(3, 1, 400)
    draws = be.block_bootstrap(len(x), lambda i: x[i].mean(), block=7, n_boot=300)
    lo, hi = be.interval(draws)
    assert lo < 3 < hi and hi - lo < 0.5


def test_temperature_change_against_baseline_days():
    temp = pd.Series(5.0, index=DATES)
    temp[DATES[60]] = 9.0  # Fri 3 Mar is 4 °C warmer than everything before it
    dT = temperature_change(temp, DATES)
    assert dT.iloc[60] == pytest.approx(4.0)
    assert dT.iloc[63] == pytest.approx(-0.4)  # Mon 6 Mar: the warm day is 1 of 10 baseline days
    assert dT.iloc[61] == pytest.approx(0)  # Sat 4 Mar: weekend baseline days only
    assert np.isnan(dT.iloc[2])  # not enough history


def test_regression_recovers_known_effects():
    rng = np.random.default_rng(3)
    days = pd.date_range("2013-01-01", periods=300)
    rows = []
    for w in ("17:00–18:00", "18:00–19:00"):
        dT = rng.normal(0, 2, len(days))
        temp = rng.normal(10, 5, len(days))
        working = days.dayofweek < 5
        pct = 1 + 2 * dT - 0.5 * (temp - 10) - 3 * ~working + (w != "17:00–18:00") * 1.5
        noise = rng.normal(0, 0.5, len(days))
        cols = {"dT": dT, "temp": temp, "working": working, "window": w}
        rows.append(pd.DataFrame({"date": days, "pct": pct + noise, **cols}))
    out = be.regress(pd.concat(rows, ignore_index=True), n_boot=200)
    expected = [1, 2, -0.5, -3, 1.5]
    assert out.coef.to_numpy() == pytest.approx(expected, abs=0.15)
    assert ((out.lo <= out.coef) & (out.coef <= out.hi)).all()
    assert (out.hi - out.lo < 0.5).all()


def test_accuracy_and_regression_run_end_to_end():
    X, _ = flat_panel(homes=4)
    X = X + np.random.default_rng(4).normal(0, 0.02, X.shape).astype("float32")
    temp = pd.Series(np.random.default_rng(5).normal(5, 2, len(DATES)), index=DATES)
    panel = be.Panel.build(X, DATES, np.array([True, True, True, False]), temp)
    acc = be.accuracy(panel, (W,), n_boot=50, min_homes=3)
    assert list(acc.variant) == list(be.VARIANTS)
    assert (acc.meter_home_days > 0).all()
    assert (acc.portfolio_sd_pct_lo <= acc.portfolio_sd_pct).all()
    rows = be.condition_rows(panel, be.EVENING, min_homes=3)
    assert set(rows.window) == {w.label for w in be.EVENING}


def test_text_report_has_both_parts():
    from uk_dfs.reporting.baseline_error import text_report

    X, _ = flat_panel(homes=4)
    X = X + np.random.default_rng(6).normal(0, 0.02, X.shape).astype("float32")
    temp = pd.Series(np.random.default_rng(7).normal(5, 2, len(DATES)), index=DATES)
    panel = be.Panel.build(X, DATES, np.ones(4, bool), temp)
    acc = be.accuracy(panel, (W,), n_boot=20, min_homes=3)
    text = text_report(acc, be.bias_regression(panel, n_boot=20, min_homes=3))
    assert "B1. Placebo accuracy" in text and "B2." in text
    assert "17:00–18:00  BL01" in text and "dT (per °C)" in text


def test_claim_stats_match_meter_stats_and_floor_per_meter_vs_half_hour():
    e = np.array([[[100.0, -100.0]], [[-50.0, -50.0]]])  # nets to 0 over the hour; −50 W
    use = np.full_like(e, 500.0)
    mask = np.ones((2, 1), bool)
    s = dict(zip(be.CLAIM_STATS, be.claim_stats(be.day_sums(e, use, mask)), strict=True))
    m = be.meter_stats(e, use, mask)
    assert s["negative_pct"] == pytest.approx(m["negative_pct"]) == pytest.approx(50)
    assert s["negative_hh_pct"] == pytest.approx(m["negative_hh_pct"]) == pytest.approx(75)
    assert s["claim_pct"] == pytest.approx(m["bias_W"] / m["use_W"] * 100) == pytest.approx(-5)
    assert s["floored_pct"] == pytest.approx(m["floored_pct"]) == pytest.approx(5)
    assert s["floored_meter_pct"] == 0  # neither meter is positive over the hour
    assert s["floor_adds_pct"] == pytest.approx(10)


def test_day_sums_ignore_masked_cells_and_claim_summary_drops_empty_days():
    rng = np.random.default_rng(8)
    e = rng.normal(0, 100, (5, 40, 2))
    use = np.full_like(e, 500.0)
    mask = np.ones((5, 40), bool)
    mask[:, :10] = False  # no usable meters on the first 10 days
    e[~mask] = np.nan
    sums = be.day_sums(e, use, mask)
    assert not np.isnan(sums).any() and (sums[:10] == 0).all()
    s = be.claim_summary(sums, n_boot=100)
    assert s["meters"] == 150
    assert s["claim_pct"] == pytest.approx(np.nanmean(e) / 5)
    for k in be.CLAIM_STATS:
        assert s[f"{k}_lo"] <= s[k] <= s[f"{k}_hi"]
