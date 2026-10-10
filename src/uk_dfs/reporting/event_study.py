"""Chart for the national event study (`uk_dfs.evaluation.event_study`)."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uk_dfs.evaluation.event_study import GROUPS, Result
from uk_dfs.reporting.style import AQUA, BLUE, GRID, INK2, ORANGE, style

COLOURS = dict(zip(GROUPS, (BLUE, ORANGE), strict=True))
TESTS = ("Real events", "Placebo: non-event days", "Placebo: event day, earlier")
FAMILIES = {  # reference period -> what it assumes
    "before": "Before the event: assumes nothing unusual beforehand",
    "after": "After the event: assumes delayed use has returned",
    "both": "Before + after: assumes both, cancels steady drift",
}


def plot_event_study(result: Result) -> plt.Figure:
    """Top: event-study profile per group (most common event length). Bottom left: real
    events vs placebos. Bottom right: alternative reference periods."""
    est, spec = result.estimates, result.spec
    groups = [g for g in GROUPS if (est.table.group == g).any()]
    with style():
        fig = plt.figure(figsize=(14, 11))
        gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.1])

        for i, g in enumerate(groups):
            ax = fig.add_subplot(gs[0, i])
            t = est.table[est.table.group == g]
            length = t.minutes.mode().iloc[0]
            ids = t.index[t.minutes == length]
            p = pd.concat([est.profiles[j] for j in ids], axis=1)
            mu, se = p.mean(axis=1), p.std(axis=1) / np.sqrt(p.shape[1])
            claim = t.loc[ids, "claim"].mean()
            ax.axvspan(-spec.gap - spec.ref, -spec.gap, color=GRID, alpha=0.6, lw=0)
            ax.axvspan(0, length, color=AQUA, alpha=0.12, lw=0)
            ax.hlines(-claim, 0, length, color=AQUA, lw=2.5, label=f"Claimed: −{claim:.0f} MW")
            x = mu.index + 2.5  # centre of each 5-minute interval
            ax.fill_between(x, mu - 1.96 * se, mu + 1.96 * se, color=COLOURS[g], alpha=0.2, lw=0)
            ax.plot(x, mu, color=COLOURS[g], marker="o", ms=3,
                    label="Event day − matched days, 95% CI")  # fmt: skip
            ax.axhline(0, color=INK2, lw=0.8)
            ax.set_xlabel("Minutes from event start (grey: reference period)")
            ax.set_title(f"{g}: {len(ids)} events lasting {length} min", fontsize=10)
            ax.legend(loc="lower left", fontsize=8)
        fig.axes[0].set_ylabel("Change from own reference period, MW\n(event day − matched days)")

        ax = fig.add_subplot(gs[1, 0])
        y = 0
        for g in groups:
            for test in TESTS:
                q = result.summary[(result.summary.group == g) & (result.summary.test == test)]
                q = q.iloc[0]
                real = test == TESTS[0]
                ax.errorbar(q.ratio, y, xerr=[[q.ratio - q.lo], [q.hi - q.ratio]],
                            fmt="o" if real else "s", mfc=COLOURS[g] if real else "white",
                            color=COLOURS[g], ms=7, capsize=3, lw=1.2)  # fmt: skip
                extra = f"  (p = {q.p:.2f} vs placebo)" if real else ""
                ax.text(-2.9, y + 0.3, f"{g} · {test}{extra}", fontsize=8, color=INK2)
                y -= 1
            y -= 0.6
        ax.axvline(0, color=INK2, lw=0.8)
        ax.axvline(1, color=AQUA, ls="--", lw=1.5)
        ax.set_xlim(-3, 4)
        ax.set_ylim(y + 1, 0.9)
        ax.set_yticks([])
        ax.set_xlabel("Detected ÷ claimed (dashed: all claimed delivery real)")
        ax.set_title("Real events vs placebos (95% intervals)", fontsize=10)

        ax = fig.add_subplot(gs[1, 1])
        rb = result.robustness
        y, ticks, labels = 0.0, [], []
        for family, header in FAMILIES.items():
            ax.text(-2.9, y + 0.1, header, fontsize=8, color=INK2, style="italic")
            y -= 0.8
            for (ref, gap), q in rb[rb.reference == family].groupby(["ref", "gap"], sort=False):
                for k, g in enumerate(groups):
                    r = q[q.group == g]
                    if r.empty:
                        continue
                    r = r.iloc[0]
                    yy = y + (0.15 if k == 0 else -0.15)
                    ax.errorbar(r.ratio, yy, xerr=[[r.ratio - r.lo], [r.hi - r.ratio]],
                                fmt="o", color=COLOURS[g], ms=4, capsize=2, lw=0.8,
                                label=g if not labels else None)  # fmt: skip
                ticks.append(y)
                labels.append((f"{ref} min · gap {gap}", q.main.any()))
                y -= 1
            y -= 0.3
        ax.set_yticks(ticks, [text for text, _ in labels], fontsize=8)
        for tick, (_, main) in zip(ax.get_yticklabels(), labels, strict=True):
            if main:
                tick.set_fontweight("bold")
        ax.axvline(0, color=INK2, lw=0.8)
        ax.axvline(1, color=AQUA, ls="--", lw=1.5)
        ax.set_xlim(-3, 4)
        ax.set_ylim(y + 0.5, 0.6)
        ax.set_xlabel("Detected ÷ claimed, 95% CI")
        ax.set_title("Robustness: reference period (main specification in bold)", fontsize=10)
        ax.legend(loc="lower right", fontsize=8)

        real = result.summary[result.summary.test == TESTS[0]].set_index("group")
        title = "; ".join(
            f"{g.split(':')[0]} detects {real.ratio[g]:.2f}× the claim "
            f"({real.lo[g]:.2f} to {real.hi[g]:.2f})"
            for g in groups
        )
        fig.suptitle(f"Difference-in-differences event study: {title}", x=0.01, ha="left",
                     fontweight="bold")  # fmt: skip
        fig.tight_layout()
    return fig
