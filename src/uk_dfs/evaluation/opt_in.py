"""Part B, step 3: how much does BL01 overpay when households choose when to take part?

DFS households opt in event by event. A home that expects a quiet evening anyway (out,
not cooking) can join and be paid for a saving it would have made regardless. BL01 can't
tell, because it compares the event with an average of past days.

Placebo again: flat-tariff (Std) homes on working days, so the true saving is zero. Each
home h gets a signal about its own evening on day d,

    signal_hd = ρ·z_hd + √(1 − ρ²)·u_hd,   u_hd ~ N(0, 1)

where z_hd is the home's claimed delivery that day (baseline − actual, mean over the
window), standardised over the home's own days. So ρ is the within-home correlation
between what the home expects and what happens: ρ = 0 is random opt-in, ρ = 1 perfect
foresight. Each home then opts in on the `share` of days with the highest signal, and we
score claimed delivery over the opted-in home-days only, with and without the per-meter
floor, as % of opted-in use.

The share sets the headroom for selection: a home that joins most events runs out of
evenings it would have been out anyway. With normal z the lift on chosen days is
ρ·φ(Φ⁻¹(1 − share)) / share standard deviations: 0.80ρ at 50%, 0.35ρ at 80%. The default,
80%, follows NESO's 2022/23 smart-meter evaluation (about 83% of eligible consumers opted
into each event, Table 6); other shares are reported as sensitivities.

ρ is unknown for real DFS homes, so results are a curve over ρ (calibrating it is further
work). One noise draw is shared across ρ (common random numbers), so the curve is smooth;
intervals are a moving-block bootstrap over days for that draw. NESO's own choice of event
days pushes the other way on cold snaps; that is handled with real DFS days in Part C.

Typical use:

    from uk_dfs.evaluation import baseline_error as be, opt_in
    panel = be.Panel.load()
    opt_in.sweep(panel)

or `uv run python -m uk_dfs.evaluation.opt_in`.
"""

import warnings
from collections.abc import Sequence

import numpy as np
import pandas as pd

from uk_dfs.evaluation.baseline_error import (
    MAIN,
    VARIANTS,
    Panel,
    Window,
    claim_summary,
    day_sums,
    delivery,
)

RHOS = tuple(np.round(np.linspace(0, 1, 11), 1))
SHARE = 0.8  # share of event days a home opts into (NESO 2022/23: about 83% per event)
SENSITIVITY_SHARES = (0.25, 0.5, 0.8, 0.95)


def placebo_mask(panel: Panel, ok: np.ndarray) -> np.ndarray:
    """(H, D) usable Std home-days on working days: where opt-in is simulated."""
    return panel.control[:, None] & ok & panel.days.working.to_numpy()[None, :]


def standardise(score: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """`score` (H, D) as a z-score over each home's own days in `mask`; NaN elsewhere and
    for homes with fewer than two days or no variation."""
    s = np.where(mask, score, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # homes with no usable days
        z = (s - np.nanmean(s, 1, keepdims=True)) / np.nanstd(s, 1, keepdims=True)
    return np.where(np.isfinite(z), z, np.nan)


def choose(
    score: np.ndarray, mask: np.ndarray, rho: float, noise: np.ndarray, share: float = SHARE
) -> np.ndarray:
    """(H, D) opt-in: each home joins on the `share` of its days in `mask` with the highest
    signal ρ·z + √(1 − ρ²)·noise, z being `score` standardised per home. A higher score
    means a quieter evening than the baseline (more claimed delivery)."""
    z = standardise(score, mask)
    signal = rho * z + np.sqrt(1 - rho**2) * noise
    signal = np.where(np.isnan(z), np.nan, signal)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        thresh = np.nanquantile(signal, 1 - share, axis=1, keepdims=True)
    return ~np.isnan(signal) & (signal >= thresh)


def sweep(
    panel: Panel,
    window: Window = MAIN,
    rhos: Sequence[float] = RHOS,
    share: float = SHARE,
    variants: Sequence[str] = VARIANTS,
    n_boot: int = 1000,
    block: int = 7,
    seed: int = 0,
) -> pd.DataFrame:
    """One row per BL01 variant and ρ: claim stats over opted-in home-days (see
    `baseline_error.claim_stats`), with block-bootstrap intervals. With the in-day
    adjustment the home is assumed to foresee its adjusted claim."""
    rows = []
    for variant in variants:
        e, use, ok = delivery(panel, window, adjusted=variant != VARIANTS[0])
        mask = placebo_mask(panel, ok)
        noise = np.random.default_rng(seed).standard_normal(mask.shape)
        score = e.mean(-1)  # claimed delivery over the window, W
        for rho in rhos:
            pick = choose(score, mask, rho, noise, share)
            s = claim_summary(day_sums(e, use, pick), n_boot, block, seed)
            rows.append({"window": window.label, "variant": variant, "rho": rho,
                         "share": share, **s})  # fmt: skip
    return pd.DataFrame(rows)


if __name__ == "__main__":
    from uk_dfs.reporting.opt_in import plot_opt_in, web_data
    from uk_dfs.reporting.outputs import save
    from uk_dfs.reporting.text import ci, table

    panel = Panel.load()
    out = sweep(panel)
    for variant, g in out.groupby("variant", sort=False):
        rows = pd.DataFrame({
            "ρ": g.rho.map("{:.1f}".format),
            "claim, % of use": [ci(r.claim_pct, r.claim_pct_lo, r.claim_pct_hi)
                                for r in g.itertuples()],
            "floored, % of use": [ci(r.floored_pct, r.floored_pct_lo, r.floored_pct_hi)
                                  for r in g.itertuples()],
            "half-hours negative, %": [ci(r.negative_hh_pct, r.negative_hh_pct_lo,
                                          r.negative_hh_pct_hi, signed=False)
                                       for r in g.itertuples()],
        })  # fmt: skip
        print(f"B5. Household opt-in ({variant}): Std placebo, working days, "
              f"{g.window.iloc[0]}, opt in on {g.share.iloc[0]:.0%} of days")  # fmt: skip
        print(f"    {g.meters.iloc[0]:,} opted-in home-days per row; block bootstrap over days\n")
        print(table(rows), "\n")

    sens = pd.concat([sweep(panel, rhos=(0.0, 0.3), share=s, variants=VARIANTS[:1])
                      for s in SENSITIVITY_SHARES])  # fmt: skip
    rows = pd.DataFrame({
        "share of days": sens.share.map("{:.0%}".format),
        "ρ": sens.rho.map("{:.1f}".format),
        "claim, % of use": [ci(r.claim_pct, r.claim_pct_lo, r.claim_pct_hi)
                            for r in sens.itertuples()],
        "floored, % of use": [ci(r.floored_pct, r.floored_pct_lo, r.floored_pct_hi)
                              for r in sens.itertuples()],
    })  # fmt: skip
    print("Sensitivity to the opt-in rate (BL01)\n")
    print(table(rows))
    save("opt_in", plot_opt_in(out), web_data(out))
