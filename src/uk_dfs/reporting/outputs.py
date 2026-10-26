"""Save an analysis's chart (for the report) and its chart data (for the web app).

Every `evaluation` module's `__main__` ends with `save(name, fig, data)`:

- the figure goes to reports/figures/<name>.png;
- the data goes to web/data/<name>.js as `window.STUDY["<name>"] = {...}`. A script file
  rather than JSON, so web/index.html also works opened straight from disk (no server).
"""

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uk_dfs.config import FIGURES_DIR, WEB_DATA_DIR


def plain(x):
    """`x` as JSON-ready Python: numpy and pandas scalars, arrays, Series and DataFrames
    (as records) converted, NaN and inf as None, floats rounded to 6 significant places."""
    if isinstance(x, pd.DataFrame):
        return [plain(r) for r in x.to_dict("records")]
    if isinstance(x, pd.Series | pd.Index | np.ndarray | list | tuple):
        return [plain(v) for v in (x.tolist() if hasattr(x, "tolist") else x)]
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, pd.Timestamp):
        return x.strftime("%Y-%m-%d")
    if isinstance(x, np.bool_ | bool):
        return bool(x)
    if isinstance(x, np.integer | int):
        return int(x)
    if isinstance(x, np.floating | float):
        x = float(x)
        return None if not math.isfinite(x) else float(f"{x:.6g}")
    return x


def save_figure(fig: plt.Figure, name: str) -> Path:
    out = FIGURES_DIR / f"{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)
    return out


def save_web_data(name: str, data: dict) -> Path:
    out = WEB_DATA_DIR / f"{name}.js"
    out.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(plain(data), ensure_ascii=False, separators=(",", ":"))
    out.write_text(f"window.STUDY = window.STUDY || {{}};\nwindow.STUDY[{name!r}] = {body};\n")
    return out


def save(name: str, fig: plt.Figure | None = None, data: dict | None = None) -> None:
    """Save whichever of the figure and web data are given, and say where."""
    if fig is not None:
        print(f"\nChart: {save_figure(fig, name)}")
    if data is not None:
        print(f"Web data: {save_web_data(name, data)}")
