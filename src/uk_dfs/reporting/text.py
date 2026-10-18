"""Plain-text tables for terminal reports."""

import pandas as pd


def ci(est: float, lo: float, hi: float, signed: bool = True, dp: int = 1) -> str:
    """ "estimate (low, high)"."""
    f = f"{{:{'+' if signed else ''}.{dp}f}}"
    return f"{f.format(est)} ({f.format(lo)}, {f.format(hi)})"


def table(df: pd.DataFrame) -> str:
    """Left-aligned text columns, two spaces apart, with a rule under the header."""
    cols = [[str(c), *map(str, df[c])] for c in df.columns]
    widths = [max(map(len, c)) for c in cols]
    rows = [
        "  ".join(c[i].ljust(w) for c, w in zip(cols, widths, strict=True)).rstrip()
        for i in range(len(df) + 1)
    ]
    return "\n".join([rows[0], "  ".join("─" * w for w in widths), *rows[1:]])
