"""Event study on synthetic 5-minute data where the right answer is known."""

import numpy as np
import pandas as pd
import pytest

from uk_dfs.evaluation import event_study as es
from uk_dfs.features.events import A1, A2, event_table

DAYS = pd.date_range("2022-11-01", "2022-12-15")
EVENT_DAY = pd.Timestamp("2022-11-30")  # a Wednesday
M0, MINUTES = 17 * 60 + 30, 60  # 17:30–18:30


def generation(dip=0.0, noise=0.0, seed=0) -> pd.Series:
    """Smooth daily shape + a different level every day, + `dip` MW off the event window."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(DAYS[0], DAYS[-1] + pd.Timedelta("1D"), freq="5min", inclusive="left")
    m = idx.hour * 60 + idx.minute
    shape = 30_000 + 8_000 * np.sin(np.pi * m / 1440)
    level = pd.Series(rng.uniform(-1500, 1500, len(DAYS)), index=DAYS)
    v = shape + level.reindex(idx.normalize()).to_numpy() + rng.normal(0, noise, len(idx))
    in_event = (idx.normalize() == EVENT_DAY) & (m >= M0) & (m < M0 + MINUTES)
    return pd.Series(np.where(in_event, v - dip, v), index=idx)


def dfs_summary(claim=200.0) -> pd.DataFrame:
    """NESO-style half-hourly summary for the one event."""
    start = EVENT_DAY + pd.to_timedelta([M0, M0 + 30], unit="min")
    return pd.DataFrame(
        {
            "start": start,
            "date": EVENT_DAY,
            "direction": "Downwards",
            "proc": 250.0,
            "settled": claim,
        }  # fmt: skip
    )


@pytest.fixture
def temps():
    return pd.Series(5.0, index=DAYS)


def panel_for(total, temps, spec=es.MAIN):
    fm = es.FiveMinute(total)
    pool = DAYS.drop(EVENT_DAY)
    controls = es.matched_days(EVENT_DAY, pool, temps, spec)
    return es.did_panel(fm, EVENT_DAY, controls, M0, MINUTES, spec)


def test_recovers_a_known_dip_despite_day_levels(temps):
    panel = panel_for(generation(dip=300), temps)
    assert es.did_estimate(panel, EVENT_DAY, MINUTES) == pytest.approx(300)


def test_no_event_means_no_dip(temps):
    panel = panel_for(generation(dip=0), temps)
    assert es.did_estimate(panel, EVENT_DAY, MINUTES) == pytest.approx(0, abs=1e-6)


def test_profile_shows_the_dip_only_inside_the_window(temps):
    p = es.profile(panel_for(generation(dip=300), temps), EVENT_DAY)
    assert p[(p.index >= 0) & (p.index < MINUTES)].to_numpy() == pytest.approx(-300)
    assert p[p.index < 0].to_numpy() == pytest.approx(0, abs=1e-6)


@pytest.mark.parametrize("reference", ["before", "after", "both"])
def test_every_reference_recovers_a_known_dip(temps, reference):
    spec = es.Spec(reference=reference, ref=120, gap=60, after=120)
    panel = panel_for(generation(dip=300), temps, spec)
    assert es.did_estimate(panel, EVENT_DAY, MINUTES) == pytest.approx(300)


def test_after_reference_sits_past_the_gap():
    spec = es.Spec(reference="after", ref=120, gap=60)
    ref = spec.reference_slots(MINUTES)
    assert ref[0] == MINUTES + 60 and ref[-1] == MINUTES + 60 + 115
    assert spec.slots(MINUTES)[0] == 0 and spec.slots(MINUTES)[-1] == ref[-1]


def test_leave_one_out_placebos_sum_to_zero(temps):
    panel = panel_for(generation(noise=50), temps)
    fakes = es.leave_one_out(panel, EVENT_DAY, MINUTES)
    assert len(fakes) == len(panel) - 1
    assert fakes.sum() == pytest.approx(0, abs=1e-6)


def test_regression_equals_difference_of_means(temps):
    """One event, balanced panel: the two-way fixed-effects δ is the 2×2 DiD exactly."""
    result = es.analyse(dfs_summary(), generation(dip=250, noise=80), temps, n_boot=50)
    assert result.regression.loc[A1, "delta"] == pytest.approx(result.estimates.table.delta.iloc[0])


def test_analyse_end_to_end(temps):
    result = es.analyse(dfs_summary(claim=200), generation(dip=200), temps, n_boot=50)
    assert result.funnel.loc["At least 4 matched days with clean data", A1] == 1
    real = result.summary.set_index("test").loc["Real events"]
    assert real.ratio == pytest.approx(1.0)
    assert set(result.robustness.group) == {A1}
    rb = result.robustness
    assert len(rb) == len(es.VARIANTS)
    cols = ["ratio", "lo", "hi"]
    assert rb.loc[rb.main, cols].iloc[0].tolist() == pytest.approx(real[cols].tolist())
    assert rb.ratio.to_numpy() == pytest.approx(1.0)  # a clean dip: every reference agrees


def test_glitches_and_out_of_day_minutes_are_not_clean():
    total = generation()
    total[EVENT_DAY + pd.Timedelta(minutes=M0 + 10)] -= 5000  # partial publication
    fm = es.FiveMinute(total)
    minutes = M0 + es.MAIN.slots(MINUTES)
    assert EVENT_DAY not in fm.clean(pd.DatetimeIndex([EVENT_DAY]), minutes)
    assert len(fm.clean(DAYS, np.arange(-10, 30, 5))) == 0


def test_matched_days_rules():
    temps = pd.Series(5.0, index=DAYS)
    temps[pd.Timestamp("2022-11-29")] = 9.0  # too warm
    pool = DAYS.drop(EVENT_DAY)
    m = es.matched_days(EVENT_DAY, pool, temps)
    assert EVENT_DAY not in m
    assert pd.Timestamp("2022-11-29") not in m
    assert (m.dayofweek < 5).all()  # weekday event -> weekday controls
    assert (np.abs((m - EVENT_DAY).days) <= 21).all()
    assert pd.Timestamp("2022-12-01") in m


def test_reference_both_needs_an_hour_after():
    with pytest.raises(ValueError):
        es.Spec(reference="both", ref=90, after=60).reference_slots(60)


def test_bootstrap_ratio_is_ratio_of_means():
    r, lo, hi = es.bootstrap_ratio([100, 300], [200, 200], np.random.default_rng(0), n=200)
    assert r == pytest.approx(1.0)
    assert lo <= r <= hi


def test_event_table_groups_half_hours():
    starts = pd.to_datetime([
        "2023-01-24 16:30", "2023-01-24 17:00", "2023-01-24 17:30",  # one 90-minute event
        "2023-01-25 09:00",                                          # next day: another
        "2024-01-10 17:00",                                          # after the rule change
        "2024-01-11 17:00",                                          # turn-up: excluded
        "2024-01-12 17:00",                                          # nothing procured
    ])  # fmt: skip
    summary = pd.DataFrame(
        {
            "start": starts,
            "date": starts.normalize(),
            "direction": ["Downwards"] * 5 + ["Upwards", "Downwards"],
            "proc": [100, 100, 100, 50, 30, 20, 0],
            "settled": [80, 90, np.nan, 40, 10, 5, 0],
        }
    )
    ev = event_table(summary)
    assert list(ev.minutes) == [90, 30, 30]
    assert list(ev.m0) == [990, 540, 1020]
    assert list(ev.group) == [A1, A1, A2]
    assert list(ev.has_settled) == [False, True, True]
    assert ev.claim.iloc[0] == pytest.approx(85)
