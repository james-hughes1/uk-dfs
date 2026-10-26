"""Part B step 3 settlement floor on synthetic homes with known answers."""

import numpy as np
import pandas as pd
import pytest

from uk_dfs.evaluation import baseline_error as be
from uk_dfs.evaluation import floor

DATES = pd.date_range("2013-01-07", periods=120)  # Mon 7 Jan 2013, clock change on day 83


def noisy_panel(homes=30, sd=0.3, seed=3):
    rng = np.random.default_rng(seed)
    X = 0.25 * rng.lognormal(0, sd, (homes, len(DATES), 48))
    X[: homes // 3] *= 2  # a third of homes are twice as big
    temp = pd.Series(rng.normal(5, 3, len(DATES)), index=DATES)
    return be.Panel.build(X.astype("float32"), DATES, np.ones(homes, bool), temp)


def test_home_size_terciles():
    use = np.array([1.0, 2, 3, 4, 5, 6, 7])[:, None, None] * np.ones((7, 2, 2))
    mask = np.ones((7, 2), bool)
    mask[6] = False
    size = floor.home_size(use, mask)
    assert list(size[:6]) == ["Small", "Small", "Medium", "Medium", "Large", "Large"]
    assert size[6] is None


def test_by_condition_all_matches_meter_stats():
    panel = noisy_panel()
    c = floor.by_condition(panel, n_boot=50)
    assert set(c.group) == {"All", "ΔT vs baseline days, °C", "Home size", "Day type"}
    e, use, ok = be.delivery(panel, be.MAIN)
    m = be.meter_stats(e, use, ok)
    row = c[c.group == "All"].iloc[0]
    assert row.meters == m["home_days"]
    assert row.floored_pct == pytest.approx(m["floored_pct"])
    assert row.negative_hh_pct == pytest.approx(m["negative_hh_pct"])
    days = c[c.group == "Day type"]
    assert days.meters.sum() == row.meters
    # pure noise: about half the meters negative, and the floor adds a lot
    assert 35 < row.negative_hh_pct < 65 and row.floor_adds_pct > 5


def test_by_start_one_row_per_window():
    s = floor.by_start(noisy_panel(), n_boot=20)
    assert list(s.window) == [w.label for w in floor.DAYTIME]


def test_grid_a_large_saving_leaves_nothing_to_floor():
    panel = noisy_panel(sd=0.05)
    g = floor.grid(panel, savings=(0, 50), rhos=(0.0, 0.5), n_boot=20).set_index(
        ["saving_pct", "rho"]
    )
    big = g.loc[50]
    assert (big.negative_hh_pct == 0).all()
    assert big.floor_adds_pct.to_numpy() == pytest.approx(0)
    assert big.claim_pct.to_numpy() == pytest.approx(50, abs=3)
    none = g.loc[0]
    assert (none.floor_adds_pct > 0).all()
    assert (none.overclaim_pct == none.floored_pct).all()
