"""Part B step 3 reality check on synthetic homes with a known response."""

import numpy as np
import pandas as pd
import pytest

from uk_dfs.evaluation import baseline_error as be
from uk_dfs.evaluation import reality_check as rc

DATES = pd.date_range("2013-01-07", periods=60)  # Mon 7 Jan 2013, no clock change


def tariffs(high_days, start="17:00", hours=3):
    """GMT half-hourly signal (January, so GMT = local) with High runs on `high_days`."""
    ts = pd.date_range(DATES[0], DATES[-1] + pd.Timedelta("1D"), freq="30min", inclusive="left")
    signal = pd.Series("Normal", index=ts)
    for d in high_days:
        t0 = DATES[d] + pd.Timedelta(f"{start}:00")
        signal[t0 : t0 + pd.Timedelta(hours=hours) - pd.Timedelta("30min")] = "High"
    return pd.DataFrame({"ts": ts, "signal": signal.to_numpy()})


def test_high_events_are_runs_within_a_day():
    t = tariffs([40, 45], start="17:00", hours=3)
    t.loc[t.ts == DATES[50] + pd.Timedelta("06:00:00"), "signal"] = "High"  # too early
    ev = rc.high_events(t, DATES)
    assert ev.d.tolist() == [40, 45]
    assert ev.start.tolist() == [34, 34] and ev.length.tolist() == [6, 6]


def panel_with_response(saving=0.05, noise=0.0, seed=0):
    """20 ToU + 20 Std homes at 0.25 kWh per half-hour; on event days ToU homes use
    `saving` kWh less per half-hour during the event."""
    rng = np.random.default_rng(seed)
    X = np.full((40, len(DATES), 48), 0.25) * rng.lognormal(0, noise, (40, len(DATES), 48))
    events = rc.high_events(tariffs([40, 45, 50]), DATES)
    for ev in events.itertuples():
        X[:20, ev.d, ev.start : ev.start + ev.length] -= saving
    control = np.r_[np.zeros(20, bool), np.ones(20, bool)]
    excluded = np.isin(np.arange(len(DATES)), events.d)
    panel = be.Panel.build(X.astype("float32"), DATES, control, pd.Series(5.0, index=DATES),
                           excluded)  # fmt: skip
    return panel, events


def test_recovers_a_known_response_exactly():
    panel, events = panel_with_response(saving=0.05)
    t = rc.event_table(panel, events)
    assert len(t) == 3
    assert (t.tou_claim - t.std_claim).to_numpy() == pytest.approx(100)  # 0.05 kWh/hh = 100 W
    s = rc.summarise(t, n_boot=50)
    assert s.loc["True effect, W per home", "estimate"] == pytest.approx(100)
    assert s.loc["BL01 claim, % of true", "estimate"] == pytest.approx(100)
    assert s.loc["ToU half-hours negative, %", "estimate"] == 0  # everyone saved


def test_noise_leaves_some_responders_negative():
    panel, events = panel_with_response(saving=0.02, noise=0.3)
    s = rc.summarise(rc.event_table(panel, events), n_boot=50)
    neg_tou = s.loc["ToU half-hours negative, %", "estimate"]
    neg_std = s.loc["Std half-hours negative, %", "estimate"]
    assert 0 < neg_tou < neg_std
    assert s.loc["BL01 floored claim, % of true", "estimate"] > 100
