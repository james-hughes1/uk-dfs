"""BL01 against hand-computed cases built from the DFS Procurement Rules.

NESO's participation guidance (Appendix 5) gives the procedure but no numbers, so each
case below constructs data where the right answer is obvious.
"""

import numpy as np
import pandas as pd
import pytest

from uk_dfs.models import bl01

# Mon 2 Jan 2023 → 90 days; no clock changes until 26 Mar
DATES = pd.date_range("2023-01-02", periods=90, freq="D")


def flat_cube(values_by_day):
    """One household, each day flat at the given value."""
    return np.repeat(np.asarray(values_by_day, "float32")[None, :, None], 48, axis=2)


def test_day_types():
    d = pd.DatetimeIndex(["2013-03-29", "2013-03-30", "2013-03-31", "2013-04-02"])
    assert bl01.working_days(d).tolist() == [False, False, False, True]  # Good Friday
    assert bl01.clock_change_days(d).tolist() == [False, False, True, False]


def test_working_day_uses_ten_most_recent_working_days():
    X = flat_cube(np.arange(90))  # day i uses i kWh per slot
    B, n = bl01.unadjusted(X, DATES)
    d = 80  # Fri 24 Mar 2023
    prev = [i for i in range(d - 1, d - 61, -1) if DATES[i].dayofweek < 5][:10]
    assert n[0, d] == 10
    assert B[0, d, 0] == pytest.approx(np.mean(prev))


def test_event_days_and_missing_data_are_skipped():
    X = flat_cube(np.arange(90))
    d = 80
    events = np.zeros(90, bool)
    events[79] = True  # Thu before
    X[0, 78, 5] = np.nan  # Wed before has a gap
    B, n = bl01.unadjusted(X, DATES, events)
    prev = [i for i in range(d - 1, d - 61, -1) if DATES[i].dayofweek < 5 and i not in (78, 79)]
    assert B[0, d, 0] == pytest.approx(np.mean(prev[:10]))


def test_non_working_day_takes_middle_two_of_four():
    totals = np.full(90, 1.0)
    # the four Saturdays/Sundays before Sun 26 Feb (day 55): 25, 19, 18, 12 Feb
    for i, v in zip([54, 48, 47, 41], [9.0, 1.0, 3.0, 5.0], strict=True):
        totals[i] = v
    B, n = bl01.unadjusted(flat_cube(totals), DATES)
    assert n[0, 55] == 2
    assert B[0, 55, 0] == pytest.approx((3.0 + 5.0) / 2)


def test_insufficient_history_defaults_to_out_turn():
    X = flat_cube(np.arange(90))
    B, n = bl01.unadjusted(X, DATES)
    assert n[0, 3] == 0  # Thu 5 Jan: only 3 working days before it
    np.testing.assert_array_equal(B[0, 3], X[0, 3])
    assert n[0, 6] == 0 and n[0, 5] == 0  # first weekend has no history


def test_in_day_adjustment_window():
    X = np.zeros((1, 1, 48), "float32")
    B = np.zeros_like(X)
    X[0, 0, 26:32] = 0.6  # 13:00–16:00, the window for a 17:00 start (slot 34)
    X[0, 0, 32:34] = 9.0  # the hour just before is ignored
    assert bl01.in_day_adjustment(X, B, 34)[0, 0] == pytest.approx(0.6)
