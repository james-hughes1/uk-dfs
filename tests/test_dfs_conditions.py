"""Part C step 1: DFS event conditions and post-stratified placebo error."""

import numpy as np
import pandas as pd
import pytest

from uk_dfs.evaluation import baseline_error as be
from uk_dfs.evaluation import dfs_conditions as c1
from uk_dfs.features import events
from uk_dfs.features.conditions import temperature_change

LCL_DATES = pd.date_range("2013-01-07", periods=150)  # Mon 7 Jan 2013


def summary(starts, minutes=60):
    """NESO-style half-hourly summary: one turn-down event per start."""
    rows = []
    for s in pd.to_datetime(starts):
        for k in range(minutes // 30):
            t = s + pd.Timedelta(minutes=30 * k)
            rows.append({"start": t, "date": t.normalize(), "direction": "Downwards",
                         "proc": 100.0, "settled": 90.0})  # fmt: skip
    return pd.DataFrame(rows)


def test_describe_events_excludes_previous_event_days_from_dT():
    days = pd.date_range("2025-09-01", "2025-12-31")
    temp = pd.Series(10.0, index=days)
    temp["2025-11-20"] = 0.0  # a cold event day
    temp["2025-11-25"] = 15.0  # a warm event day
    ev = c1.describe_events(summary(["2025-11-20 17:00", "2025-11-25 16:30"], 120), temp)
    assert ev.slot.tolist() == [34, 33] and ev.length.tolist() == [4, 4]
    assert ev.season.tolist() == ["Winter", "Winter"] and ev.working.all()
    assert ev.dT.tolist() == pytest.approx([-10, 5])  # the cold day isn't a baseline day
    assert ev.dT_band.tolist() == ["< −4", "> 4"]
    assert ev.group.eq(events.SINCE_OCT_2023).all()


def test_working_day_baseline_with_five_to_nine_days():
    dates = pd.date_range("2025-09-01", periods=70)
    temp = pd.Series(np.arange(70.0), index=dates)
    excluded = np.zeros(70, bool)
    excluded[60 - 14 : 60] = True  # the 10 working days before day 60 are event days
    dT = temperature_change(temp, dates, excluded)
    assert not np.isnan(dT.iloc[60])  # earlier working days still give at least 5
    excluded[:60] = True
    assert np.isnan(temperature_change(temp, dates, excluded).iloc[60])


def test_match_coarsens_when_a_cell_is_thin():
    lcl = pd.DataFrame({"dT_band": ["< −4"] * 3 + ["0…2"] * 30, "working": True,
                        "season": ["Winter"] * 3 + ["Summer"] * 30})  # fmt: skip
    ev = pd.DataFrame({"dT_band": ["0…2", "< −4"], "working": True, "season": "Summer"})
    M, used = c1.match(ev, lcl, np.ones(len(lcl), bool), min_days=5)
    assert used == [" × ".join(c1.CELL), "working"]
    assert M[0].sum() == 30 and M[1].sum() == 33
    with pytest.raises(ValueError):
        c1.match(ev, lcl, np.zeros(len(lcl), bool), min_days=5)


def panel(homes=40, seed=0):
    rng = np.random.default_rng(seed)
    X = (0.25 * rng.lognormal(0, 0.3, (homes, len(LCL_DATES), 48))).astype("float32")
    temp = pd.Series(rng.normal(8, 3, len(LCL_DATES)), index=LCL_DATES)
    return be.Panel.build(X, LCL_DATES, np.ones(homes, bool), temp)


def event_rows(cells, slot=34, length=2):
    """Synthetic events in the given (dT_band, working, season) cells."""
    base = {"date": pd.Timestamp("2025-01-15"), "start": pd.NaT, "minutes": 30 * length,
            "group": events.SINCE_OCT_2023, "temp": 5.0, "dT": 0.0, "slot": slot,
            "length": length}  # fmt: skip
    return pd.DataFrame([base | dict(zip(c1.CELL, c, strict=True)) for c in cells])


def cell_sums(p, cell, window=be.MAIN, min_homes=20):
    lcl = c1.cells(p.days)
    m = c1._usable(p, min_homes) & (lcl[list(c1.CELL)] == cell).all(axis=1).to_numpy()
    e, use, ok = be.delivery(p, window)
    return be.day_sums(e, use, p.control[:, None] & ok)[m], m.sum()


def test_one_event_equals_its_cell():
    p = panel()
    lcl = c1.cells(p.days)
    cell = tuple(lcl[list(c1.CELL)].value_counts().index[0])
    out, per_event = c1.transfer(p, event_rows([cell]), min_days=5, min_homes=20, n_boot=50)
    s, n = cell_sums(p, cell)
    row = out[out.variant == be.VARIANTS[0]].iloc[0]
    assert row.in_force and row.events == 1
    for k, v in zip(be.CLAIM_STATS, be.claim_stats(s), strict=True):
        assert row[k] == pytest.approx(v)
        assert row[f"{k}_lo"] <= row[k] <= row[f"{k}_hi"]
    assert per_event.lcl_days.iloc[0] == n
    assert per_event.matched_on.iloc[0] == " × ".join(c1.CELL)


def test_events_count_equally_whatever_their_cells_size():
    p = panel(seed=1)
    lcl = c1.cells(p.days)
    big, small = (tuple(c) for c in lcl[list(c1.CELL)].value_counts().index[:2])
    out, _ = c1.transfer(p, event_rows([big, small]), min_days=5, min_homes=20, n_boot=20)
    a, _ = cell_sums(p, big)
    b, _ = cell_sums(p, small)
    a, b = a.sum(0), b.sum(0)
    expected = be.claim_stats((a / a[0] + b / b[0])[None, :])
    row = out[out.variant == be.VARIANTS[0]].iloc[0]
    assert [row[k] for k in be.CLAIM_STATS] == pytest.approx(expected)


def test_timing_only_ignores_conditions():
    p = panel(seed=2)
    ev = event_rows([("no such band", True, "Winter")], slot=36, length=4)
    out, per_event = c1.transfer(p, ev, c1.TIMING_ONLY, min_days=5, min_homes=20, n_boot=20)
    assert per_event.matched_on.iloc[0] == "window only"
    assert per_event.lcl_days.iloc[0] == c1._usable(p, 20).sum()
