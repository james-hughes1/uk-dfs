"""National check: does each DFS event show up as a dip in 5-minute GB generation?

Stacked difference-in-differences. For one event, take the event day and its matched
days (no DFS event, within ±21 days, same day type, daily mean temperature within 2 °C),
and every 5-minute slot t in a reference period R (the hour ending 10 minutes before the
event) and the event window W:

    y_dt = α_d + γ_t − δ · E_d · W_t + ε_dt

α_d absorbs each day's level, γ_t the shape of demand shared by all days, and δ is the
average reduction in the window (MW, positive = demand fell). On this balanced panel OLS
gives exactly the 2×2 difference of means: the event day's change from R into W, minus
the matched days' average change. Assumption (parallel trends): without the event, the
event day would have moved from R into W as the matched days did on average.

Each event gets its own α and γ (stacked), so there is one δ per event. Pooled:
detected ÷ claimed = Σδ / Σclaim, with a bootstrap over events; 5-minute slots within an
event are strongly autocorrelated, so the event is the unit of resampling. Placebos:
each matched day as a fake event, and the event day earlier in the afternoon.

Typical use:

    from uk_dfs.evaluation import event_study
    result = event_study.run()        # loads cached data
    result.summary                    # detected ÷ claimed per group, with placebos

or `uv run python -m uk_dfs.evaluation.event_study` to fetch, run and save the chart.
"""

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from uk_dfs.features.events import A1, A2, event_days, event_table

GROUPS = (A1, A2)


@dataclass(frozen=True)
class Spec:
    """Analysis settings, in minutes unless stated. Defaults are the main specification."""

    ref: int = 60  # reference period length
    gap: int = 10  # skipped just before the event, when early responders start
    after: int = 60  # kept after the event for the event-study profile
    reference: str = "before"  # "before", or "both" to add [end + gap, end + gap + ref)
    max_len: int = 120  # longer events are dropped
    window_days: int = 21  # matched days: within this many days of the event
    max_temp_diff: float = 2.0  # matched days: daily mean temperature within this, °C
    min_controls: int = 4  # matched days needed, with clean data
    jump_mw: float = 2000  # a 5-minute change bigger than this flags a publication glitch

    @property
    def guard(self) -> int:
        """Minutes before an event that must be free of other events: covers the
        reference period and the earlier-in-the-day placebo."""
        return 2 * self.max_len + 150

    def placebo_shift(self, minutes: int) -> int:
        """How far earlier the placebo window sits, so it ends before the real reference."""
        return minutes + self.gap + self.ref + 15

    def slots(self, minutes: int) -> np.ndarray:
        """Minutes from event start covered by one event's panel, in 5-minute steps."""
        return np.arange(-self.gap - self.ref, minutes + self.gap + self.after, 5)

    def reference_slots(self, minutes: int) -> np.ndarray:
        before = np.arange(-self.gap - self.ref, -self.gap, 5)
        if self.reference == "before":
            return before
        if self.reference == "both":
            if self.after < self.ref:
                raise ValueError("reference='both' needs after >= ref")
            return np.r_[before, np.arange(minutes + self.gap, minutes + self.gap + self.ref, 5)]
        raise ValueError(f"unknown reference: {self.reference!r}")


MAIN = Spec()  # the main specification


# --- Data ----------------------------------------------------------------------------------


class FiveMinute:
    """5-minute GB generation as a day × minute-of-day table, with glitches flagged."""

    def __init__(self, total: pd.Series, jump_mw: float = Spec.jump_mw):
        """`total`: MW per 5-minute interval on local time (`elexon.load_fuelinst_total()`)."""
        f = pd.DataFrame(
            {
                "v": total,
                "bad": total.diff().abs() > jump_mw,
                "date": total.index.normalize(),
                "m": total.index.hour * 60 + total.index.minute,
            }
        )
        self.values = f.pivot_table(index="date", columns="m", values="v")
        bad = f.pivot_table(index="date", columns="m", values="bad", aggfunc="max")
        self.bad = bad.fillna(True).astype(bool)

    def clean(self, dates: pd.DatetimeIndex, minutes: np.ndarray) -> pd.DatetimeIndex:
        """The days in `dates` with complete, glitch-free data at every one of `minutes`."""
        dates = pd.DatetimeIndex(dates).intersection(self.values.index)
        if len(minutes) == 0 or minutes[0] < 0 or minutes[-1] > 1435:
            return dates[:0]
        ok = ~self.bad.loc[dates, minutes].any(axis=1)
        ok &= self.values.loc[dates, minutes].notna().all(axis=1)
        return dates[ok.to_numpy()]


def matched_days(
    day: pd.Timestamp, pool: pd.DatetimeIndex, daily_temp: pd.Series, spec: Spec = MAIN
) -> pd.DatetimeIndex:
    """Control days for `day`: from `pool` (days with no DFS event), within
    `spec.window_days`, same day type (Mon–Fri vs weekend), temperature within
    `spec.max_temp_diff`."""
    near = np.abs((pool - day).days) <= spec.window_days
    same_type = (pool.dayofweek < 5) == (day.dayofweek < 5)
    similar = np.abs(daily_temp.reindex(pool).to_numpy() - daily_temp[day]) <= spec.max_temp_diff
    return pool[near & same_type & similar]


# --- One event -----------------------------------------------------------------------------


def did_panel(
    fm: FiveMinute,
    day: pd.Timestamp,
    controls: pd.DatetimeIndex,
    m0: int,
    minutes: int,
    spec: Spec = MAIN,
    shift: int = 0,
) -> pd.DataFrame | None:
    """Event day + clean controls, each minus its own reference-period mean (MW).

    Columns are minutes from event start (`spec.slots`). `shift` moves the whole set-up
    earlier, for the placebo. None if the event day itself has no clean data.
    """
    k = spec.slots(minutes)
    clock = m0 - shift + k
    days = fm.clean(controls.union([day]), clock)
    if day not in days:
        return None
    y = fm.values.loc[days, clock]
    y.columns = k
    return y.sub(y[spec.reference_slots(minutes)].mean(axis=1), axis=0)


def window_change(panel: pd.DataFrame, minutes: int) -> pd.Series:
    """Each day's mean over the event window, relative to its reference period."""
    return panel[np.arange(0, minutes, 5)].mean(axis=1)


def did_estimate(panel: pd.DataFrame, day: pd.Timestamp, minutes: int) -> float:
    """δ, MW (positive = reduction): event day's change into the window minus controls'."""
    change = window_change(panel, minutes)
    return -(change[day] - change.drop(day).mean())


def leave_one_out(panel: pd.DataFrame, day: pd.Timestamp, minutes: int) -> np.ndarray:
    """Placebo δ for each control day treated as the event, against the other controls."""
    c = -window_change(panel, minutes).drop(day)
    return (c - (c.sum() - c) / (len(c) - 1)).to_numpy()


def profile(panel: pd.DataFrame, day: pd.Timestamp) -> pd.Series:
    """Event-study profile: event day minus mean of controls, per slot (MW)."""
    return panel.loc[day] - panel.drop(day).mean()


# --- Which events can be used --------------------------------------------------------------

STEPS = {
    "has_settled": "Settled volume published",
    "short": "Lasts 2 hours or less",
    "has_5min": "5-minute generation data that day",
    "alone": "No other event near enough to interfere",
    "clean": "No data glitches, hour before to hour after",
    "matched": "At least 4 matched days with clean data",
}


def screen(
    events: pd.DataFrame,
    fm: FiveMinute,
    pool: pd.DatetimeIndex,
    daily_temp: pd.Series,
    spec: Spec = MAIN,
) -> pd.DataFrame:
    """`events` plus one boolean column per filter in `STEPS` (applied in that order),
    `n_controls` (clean matched days) and `used` (passes every filter)."""
    rows = []
    for i, e in events.iterrows():
        end = e.m0 + e.minutes
        others = events[(events.date == e.date) & (events.index != i)].m0
        r = {
            "short": e.minutes <= spec.max_len,
            "has_5min": e.date in fm.values.index,
            "alone": not (
                (others > e.m0 - spec.guard) & (others < end + spec.gap + spec.after)
            ).any(),
            "clean": False,
            "matched": False,
            "n_controls": np.nan,
        }
        if e.has_settled and r["short"] and r["has_5min"] and r["alone"]:
            clock = e.m0 + spec.slots(e.minutes)
            r["clean"] = len(fm.clean(pd.DatetimeIndex([e.date]), clock)) == 1
            if r["clean"] and e.date in daily_temp.index:
                r["n_controls"] = len(fm.clean(matched_days(e.date, pool, daily_temp, spec), clock))
                r["matched"] = r["n_controls"] >= spec.min_controls
        rows.append(r)
    out = events.join(pd.DataFrame(rows, index=events.index))
    out["used"] = out[list(STEPS)].all(axis=1)
    return out


def funnel(screened: pd.DataFrame) -> pd.DataFrame:
    """Events left after each filter, per group."""
    steps = list(STEPS)
    return pd.DataFrame(
        {
            g: [len(x)] + [int(x[steps[: k + 1]].all(axis=1).sum()) for k in range(len(steps))]
            for g, x in screened.groupby("group")
        },
        index=["All turn-down events"] + list(STEPS.values()),
    )


# --- All events ----------------------------------------------------------------------------


@dataclass
class Estimates:
    table: pd.DataFrame  # one row per used event: group, date, minutes, claim, delta, ...
    profiles: dict  # event id -> event-study profile (Series indexed by minutes from start)
    fakes: dict  # event id -> leave-one-out placebo deltas
    panels: dict  # event id -> did_panel (for the regression cross-check)


def estimate(
    screened: pd.DataFrame,
    fm: FiveMinute,
    pool: pd.DatetimeIndex,
    daily_temp: pd.Series,
    spec: Spec = MAIN,
) -> Estimates:
    """δ, profile, placebos and panel for every used event that has a clean panel."""
    rows, profiles, fakes, panels = [], {}, {}, {}
    for i, e in screened[screened.used].iterrows():
        controls = matched_days(e.date, pool, daily_temp, spec)
        panel = did_panel(fm, e.date, controls, e.m0, e.minutes, spec)
        if panel is None or len(panel) - 1 < spec.min_controls:
            continue
        shift = spec.placebo_shift(e.minutes)
        early = did_panel(fm, e.date, controls, e.m0, e.minutes, spec, shift)
        ok_early = early is not None and len(early) - 1 >= spec.min_controls
        rows.append(
            {
                "event": i,
                "group": e.group,
                "date": e.date,
                "start": e.start,
                "minutes": e.minutes,
                "claim": e.claim,
                "delta": did_estimate(panel, e.date, e.minutes),
                "n_controls": len(panel) - 1,
                "placebo_earlier": did_estimate(early, e.date, e.minutes) if ok_early else np.nan,
            }
        )
        profiles[i] = profile(panel, e.date)
        fakes[i] = leave_one_out(panel, e.date, e.minutes)
        panels[i] = panel
    cols = ["event", "group", "date", "start", "minutes", "claim", "delta", "n_controls",
            "placebo_earlier"]  # fmt: skip
    return Estimates(pd.DataFrame(rows, columns=cols).set_index("event"), profiles, fakes, panels)


# --- Pooling and inference -----------------------------------------------------------------


def bootstrap_ratio(delta, claim, rng: np.random.Generator, n: int = 2000) -> tuple:
    """Σδ / Σclaim and its 95% percentile interval, resampling events."""
    delta, claim = np.asarray(delta, float), np.asarray(claim, float)
    i = rng.integers(0, len(delta), (n, len(delta)))
    r = delta[i].mean(axis=1) / claim[i].mean(axis=1)
    return delta.mean() / claim.mean(), *np.percentile(r, [2.5, 97.5])


def placebo_null(fakes: list, claim, rng: np.random.Generator, n: int = 2000) -> np.ndarray:
    """Null distribution of detected ÷ claimed: one random fake event per real event."""
    draws = np.array([rng.choice(f, n) for f in fakes]).mean(axis=0)
    return draws / np.mean(claim)


def summarise(est: Estimates, n_boot: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Detected ÷ claimed per group for real events and both placebos, with 95% intervals.
    `p` is the share of the non-event-day null at or above the real estimate."""
    rng = np.random.default_rng(seed)
    out = []
    for g in GROUPS:
        t = est.table[est.table.group == g]
        if t.empty:
            continue
        r, lo, hi = bootstrap_ratio(t.delta, t.claim, rng, n_boot)
        null = placebo_null([est.fakes[i] for i in t.index], t.claim, rng, n_boot)
        out.append({"group": g, "test": "Real events", "ratio": r, "lo": lo, "hi": hi,
                    "n": len(t), "p": (null >= r).mean()})  # fmt: skip
        out.append({"group": g, "test": "Placebo: non-event days", "ratio": np.median(null),
                    "lo": np.percentile(null, 2.5), "hi": np.percentile(null, 97.5),
                    "n": len(t), "p": np.nan})  # fmt: skip
        pe = t.dropna(subset=["placebo_earlier"])
        r, lo, hi = bootstrap_ratio(pe.placebo_earlier, pe.claim, rng, n_boot)
        out.append({"group": g, "test": "Placebo: event day, earlier", "ratio": r, "lo": lo,
                    "hi": hi, "n": len(pe), "p": np.nan})  # fmt: skip
    return pd.DataFrame(out)


def _demean(a: np.ndarray) -> np.ndarray:
    """Remove row and column means (two-way fixed effects on a balanced panel)."""
    return (a - a.mean(1, keepdims=True) - a.mean(0, keepdims=True) + a.mean()).ravel()


def twfe(est: Estimates, group: str, spec: Spec = MAIN) -> dict:
    """The same estimate as one stacked regression, with cluster-robust standard errors.

    y = event-specific day effects + event-specific slot effects − δ·(event day × window),
    on reference + window slots only. Each event's panel is balanced, so two-way
    demeaning within each event is exact. Clusters: events, and calendar weeks.
    """
    ys, xs, by_event, by_week = [], [], [], []
    for i, row in est.table[est.table.group == group].iterrows():
        panel = est.panels[i]
        cols = np.r_[spec.reference_slots(row.minutes), np.arange(0, row.minutes, 5)]
        y = panel[cols].to_numpy()
        x = np.outer(panel.index == row.date, cols >= 0).astype(float)
        ys.append(_demean(y))
        xs.append(_demean(x))
        by_event += [i] * y.size
        by_week += [str(row.date.to_period("W"))] * y.size
    y, x = np.concatenate(ys), np.concatenate(xs)
    b = (x @ y) / (x @ x)
    out = {"delta": -b}
    for name, clusters in (("event", by_event), ("week", by_week)):
        s = pd.Series(x * (y - b * x)).groupby(np.array(clusters)).sum()
        g = len(s)
        se = np.sqrt((s**2).sum() * g / (g - 1)) / (x @ x) if g > 1 else np.nan
        out[f"se_{name}"] = se
        out[f"clusters_{name}"] = g
    return out


def robustness(
    screened: pd.DataFrame,
    fm: FiveMinute,
    pool: pd.DatetimeIndex,
    daily_temp: pd.Series,
    spec: Spec = MAIN,
    n_boot: int = 2000,
    seed: int = 0,
) -> pd.DataFrame:
    """Detected ÷ claimed under alternative reference periods, on the same events."""
    variants = [replace(spec, ref=r, after=r) for r in (30, 60, 90)]
    variants += [replace(spec, gap=g) for g in (0, 20)]
    variants += [replace(spec, ref=r, after=r, reference="both") for r in (30, 60, 90)]
    rng = np.random.default_rng(seed)
    out = []
    for v in variants:
        t = estimate(screened, fm, pool, daily_temp, v).table
        for g in GROUPS:
            x = t[t.group == g]
            if x.empty:
                continue
            r, lo, hi = bootstrap_ratio(x.delta, x.claim, rng, n_boot)
            out.append({"reference": v.reference, "ref": v.ref, "gap": v.gap, "group": g,
                        "ratio": r, "lo": lo, "hi": hi, "n": len(x),
                        "main": v == spec})  # fmt: skip
    return pd.DataFrame(out)


# --- Everything ----------------------------------------------------------------------------


@dataclass
class Result:
    spec: Spec
    events: pd.DataFrame  # every turn-down event, with screening columns
    funnel: pd.DataFrame
    estimates: Estimates
    summary: pd.DataFrame
    regression: pd.DataFrame
    robustness: pd.DataFrame


def analyse(
    summary: pd.DataFrame,
    total: pd.Series,
    daily_temp: pd.Series,
    spec: Spec = MAIN,
    n_boot: int = 2000,
    seed: int = 0,
) -> Result:
    """Run the whole analysis on loaded data.

    summary: `neso.load_dfs()`; total: `elexon.load_fuelinst_total()`;
    daily_temp: `weather.daily_temperature(weather.load_weather())`.
    """
    fm = FiveMinute(total, spec.jump_mw)
    days = pd.DatetimeIndex(daily_temp.dropna().index)
    pool = days[~days.isin(event_days(summary))]
    screened = screen(event_table(summary), fm, pool, daily_temp, spec)
    est = estimate(screened, fm, pool, daily_temp, spec)
    groups = [g for g in GROUPS if (est.table.group == g).any()]
    regression = pd.DataFrame({g: twfe(est, g, spec) for g in groups}).T
    return Result(
        spec=spec,
        events=screened,
        funnel=funnel(screened),
        estimates=est,
        summary=summarise(est, n_boot, seed),
        regression=regression,
        robustness=robustness(screened, fm, pool, daily_temp, spec, n_boot, seed),
    )


def run(spec: Spec = MAIN, n_boot: int = 2000, seed: int = 0) -> Result:
    """Load the cached data and run the analysis (fetch first; see `main`)."""
    from uk_dfs.data import elexon, neso, weather

    daily_temp = weather.daily_temperature(weather.load_weather())
    return analyse(neso.load_dfs(), elexon.load_fuelinst_total(), daily_temp, spec, n_boot, seed)


def main(fetch: bool = True) -> Result:
    """Fetch any missing data, run the analysis, print the tables and save the chart."""
    from uk_dfs.config import FIGURES_DIR
    from uk_dfs.data import elexon, neso, weather
    from uk_dfs.reporting.event_study import plot_event_study

    if fetch:
        neso.fetch_dfs()
        elexon.fetch_fuelinst("2022-11")
        weather.fetch_weather()
    result = run()
    with pd.option_context("display.width", 140, "display.float_format", "{:.2f}".format):
        print(result.funnel, end="\n\n")
        print(result.summary, end="\n\n")
        print(result.regression, end="\n\n")
        print(result.robustness)
    out = FIGURES_DIR / "event_study.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    plot_event_study(result).savefig(out)
    print(f"\nChart: {out}")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="use cached data only")
    main(fetch=not parser.parse_args().offline)
