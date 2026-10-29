"""Part C step 2 overpayment scenarios on hand-made inputs."""

import numpy as np
import pandas as pd
import pytest

from uk_dfs.evaluation import overpayment as op
from uk_dfs.features.events import LAUNCH, MARKET, SECOND


def fake_grid():
    """floor.grid-shaped rows: plain claim = saving + 1, floor adds 20, foresight adds 10ρ."""
    rows = []
    for s in (5, 10, 20, 40):
        for rho in (0.0, 0.1, 0.3):
            fl = s + 1 + 20 + 10 * rho
            rows.append(
                {
                    "saving_pct": s,
                    "rho": rho,
                    "claim_pct": s + 1 + 30 * rho,
                    "floored_pct": fl,
                    "floored_pct_lo": fl - 1,
                    "floored_pct_hi": fl + 1,
                }
            )
    return pd.DataFrame(rows)


def test_grid_points_cover_every_scenario_and_rho_zero():
    savings, rhos = op.grid_points()
    assert savings == [5, 10, 20, 40]
    assert rhos == [0.0, 0.1, 0.3]


def test_decompose_parts_sum_to_one_and_match_the_grid():
    dec = op.decompose(fake_grid())
    parts = dec[list(op.PARTS)].sum(axis=1)
    assert parts.to_numpy() == pytest.approx(1.0)
    s2 = dec.loc["S2"]  # saving 20, ρ 0.1: plain 21 → 24, floored 41 → 42
    assert s2.real_share == pytest.approx(20 / 42)
    assert s2.inflation == pytest.approx(42 / 20)
    assert s2.baseline == pytest.approx(1 / 42)
    assert s2.floor == pytest.approx((20 + 18) / 2 / 42)  # floor at ρ = 0 and at ρ = 0.1
    assert s2.selection == pytest.approx((1 + 3) / 2 / 42)  # on the floored and plain claim
    assert s2.real_share_lo < s2.real_share < s2.real_share_hi
    assert dec.loc["S1", "selection"] == pytest.approx(0)  # ρ = 0


def test_settled_spend_splits_periods_and_counts_unsettled():
    start = pd.to_datetime(
        [
            "2023-01-10 17:00",
            "2023-12-05 17:00",
            "2025-01-08 17:00",
            "2025-01-08 17:30",
            "2026-07-01 18:00",
        ]
    )
    summary = pd.DataFrame({
        "start": start, "direction": ["Downwards"] * 4 + ["Upwards"],
        "proc": 100.0, "settled": [100.0, 50.0, 20.0, np.nan, 10.0],
        "settled_cost": [300_000.0, 150_000.0, 4_000.0, np.nan, 99.0],
    })  # fmt: skip
    s = op.settled_spend(summary)
    assert list(s.index) == [LAUNCH, SECOND, MARKET, "Total"]
    assert s.loc[LAUNCH, "settled_mwh"] == 50  # MW over a half-hour
    assert s.loc[MARKET, "unsettled_hh"] == 1
    assert s.loc["Total", "cost"] == 454_000  # turn-up excluded
    assert s.loc[LAUNCH, "price"] == pytest.approx(6000)


def test_event_prices_groups_runs_and_prices_accepted_bids():
    start = pd.to_datetime(["2023-01-10 17:00", "2023-01-10 17:30", "2025-01-08 17:00",
                            "2025-01-08 18:00", "2025-01-09 17:00"])  # fmt: skip
    summary = pd.DataFrame({
        "start": start, "direction": ["Downwards"] * 4 + ["Upwards"],
        "type": ["Test", "Test", "Live", "Live", "Live"],
        "proc": [100.0, 50.0, 40.0, 20.0, 30.0],
        "cost": [150_000.0, 75_000.0, 1_000.0, 600.0, 9.0],
        "settled": [90.0, 40.0, np.nan, 20.0, 30.0],
    })  # fmt: skip
    ev = op.event_prices(summary)
    assert list(ev.period) == [LAUNCH, MARKET, MARKET]  # 18:00 not contiguous
    assert list(ev.test) == [True, False, False]
    assert list(ev.procured_mwh) == [75, 20, 10]  # MW over half-hours; turn-up excluded
    assert list(ev.price) == pytest.approx([3000, 50, 60])
    assert ev.settled_mwh.iloc[0] == 65
    assert np.isnan(ev.settled_mwh.iloc[1])  # not settled yet


def test_overpayment_is_unreal_share_times_cost():
    dec = pd.DataFrame({"real_share": [1.0, 0.25]}, index=["A", "B"])
    spend = pd.DataFrame({"cost": [100.0, 40.0]}, index=["p", "Total"])
    over = op.overpayment(dec, spend)
    assert over.loc["A"].tolist() == [0, 0]
    assert over.loc["B"].tolist() == [75, 30]
