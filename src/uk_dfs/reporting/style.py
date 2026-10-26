"""Project chart style: a fixed categorical palette and quiet axes."""

import matplotlib.pyplot as plt

# Categorical palette, always assigned in this order
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
CATEGORICAL = (BLUE, ORANGE, AQUA, YELLOW)
# Ordinal ramp (one hue, light to dark) for ordered series such as savings levels
BLUE_RAMP = ("#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281")
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e4e3df"

RC = {
    "figure.dpi": 110,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "font.size": 10,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK2,
    "axes.titlecolor": INK,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "legend.frameon": False,
    "lines.linewidth": 2,
}


def style():
    """Context manager applying the project style: `with style(): ...`."""
    return plt.rc_context(RC)
