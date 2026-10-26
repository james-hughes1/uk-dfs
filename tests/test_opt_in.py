"""Part B step 3 household opt-in on synthetic homes with known answers."""

import numpy as np
import pandas as pd
import pytest

from uk_dfs.evaluation import baseline_error as be
from uk_dfs.evaluation import opt_in

DATES = pd.date_range("2013-01-07", periods=120)  # Mon 7 Jan 2013, clock change on day 83


def test_perfect_foresight_picks_each_homes_quietest_days():
    rng = np.random.default_rng(0)
    score = rng.normal(0, 1, (3, 20))
    mask = np.ones_like(score, bool)
    mask[0, :4] = False
    pick = opt_in.choose(score, mask, rho=1.0, noise=rng.standard_normal(score.shape))
    assert not pick[~mask].any()
    for h in range(3):
        s = np.where(mask[h], score[h], -np.inf)
        top = np.argsort(s)[::-1][: mask[h].sum() // 2]
        assert set(np.flatnonzero(pick[h])) == set(top)


def test_random_opt_in_ignores_the_score():
    rng = np.random.default_rng(1)
    score = rng.normal(0, 1, (200, 100))
    mask = np.ones_like(score, bool)
    pick = opt_in.choose(score, mask, rho=0.0, noise=rng.standard_normal(score.shape), share=0.25)
    assert pick.mean() == pytest.approx(0.25, abs=0.01)
    assert abs(score[pick].mean()) < 0.05


def test_foresight_is_within_home():
    """A home with a big spread doesn't dominate: z is standardised per home."""
    score = np.vstack([np.arange(10.0), 100 * np.arange(10.0)])
    z = opt_in.standardise(score, np.ones_like(score, bool))
    assert z[0] == pytest.approx(z[1])
    assert np.isnan(opt_in.standardise(np.ones((1, 5)), np.ones((1, 5), bool))).all()


def noisy_panel(homes=60, sd=0.3, seed=2):
    rng = np.random.default_rng(seed)
    X = (0.25 * rng.lognormal(0, sd, (homes, len(DATES), 48))).astype("float32")
    temp = pd.Series(5.0, index=DATES)
    return be.Panel.build(X, DATES, np.ones(homes, bool), temp)


def test_sweep_claim_is_zero_at_random_opt_in_and_rises_with_foresight():
    out = opt_in.sweep(noisy_panel(), rhos=(0.0, 0.5, 1.0), n_boot=100)
    assert list(out.variant.unique()) == list(be.VARIANTS)
    plain = out[out.variant == be.VARIANTS[0]].set_index("rho")
    assert plain.claim_pct_lo[0.0] < 0 < plain.claim_pct_hi[0.0]  # pure noise: no bias
    assert plain.claim_pct[0.0] < plain.claim_pct[0.5] < plain.claim_pct[1.0]
    assert plain.claim_pct_lo[1.0] > 10
    # the floor always adds, and adds less as fewer opted-in meters come out negative
    assert (plain.floor_adds_pct > 0).all()
    assert plain.negative_hh_pct[0.0] > plain.negative_hh_pct[1.0]
    assert plain.floor_adds_pct[0.0] > plain.floor_adds_pct[1.0]
