"""Elexon Insights (BMRS) data.

FUELINST: 5-minute average generation by fuel type for transmission-connected plant,
plus interconnectors and pumped storage, which go negative when exporting / pumping.
Summed over fuel types this tracks transmission demand at 5-minute resolution. Embedded
(distribution-connected) solar and wind are not in it: they appear as lower demand.

`fetch_fuelinst()` caches one Parquet file per calendar month in data/raw/elexon_fuelinst/.
It is idempotent: complete months already on disk are skipped; the current month is
always re-fetched.
"""

import json
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from uk_dfs.config import INTERIM_DIR, RAW_DIR

FUELINST_DIR = RAW_DIR / "elexon_fuelinst"
API = "https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELINST/stream"


def _fetch_month(month: pd.Period, force: bool) -> None:
    out = FUELINST_DIR / f"{month}.parquet"
    complete = month < pd.Timestamp.now(tz="UTC").tz_localize(None).to_period("M")
    if out.exists() and complete and not force:
        return
    start, end = month.start_time, (month + 1).start_time
    fmt = "%Y-%m-%dT%H:%MZ"
    url = f"{API}?publishDateTimeFrom={start:{fmt}}&publishDateTimeTo={end:{fmt}}"
    with urllib.request.urlopen(url, timeout=120) as r:
        recs = json.load(r)
    df = pd.DataFrame(recs)[["startTime", "fuelType", "generation"]]
    df["startTime"] = pd.to_datetime(df.startTime).dt.tz_localize(None)  # UTC
    df.to_parquet(out, index=False)


def fetch_fuelinst(start: str, end: str | None = None, force: bool = False) -> None:
    """Cache FUELINST for every month from `start` to `end` (default: this month)."""
    FUELINST_DIR.mkdir(parents=True, exist_ok=True)
    months = pd.period_range(start, end or pd.Timestamp.now(), freq="M")
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda m: _fetch_month(m, force), months))


SETTLEMENT_DIR = RAW_DIR / "elexon_settlement"
GSP_VOLUMES = INTERIM_DIR / "gsp_volumes.parquet"
RUN_ORDER = ["II", "SF", "R1", "R2", "R3", "RF", "DF"]  # later runs supersede earlier


def fetch_gp9(year: int, force: bool = False) -> Path:
    """Download Elexon Open Settlement Data GP9 (GSP Period Data) for one year."""
    SETTLEMENT_DIR.mkdir(parents=True, exist_ok=True)
    out = SETTLEMENT_DIR / f"GP9_{year}.zip"
    if not out.exists() or force:
        urllib.request.urlretrieve(f"https://elexon-open-data.s3.amazonaws.com/GP9_{year}.zip", out)
    return out


def build_gsp_volumes(year: int, start: str, force: bool = False) -> None:
    """Half-hourly metered net import (MWh) per Grid Supply Point from GP9.

    GP9 holds CDCA-metered volumes at each GSP (the transmission/distribution boundary),
    reissued at every settlement run; keeps the latest run per GSP, date and period, for
    settlement dates on or after `start`. Net = import − export, i.e. demand net of
    embedded generation behind that GSP.
    """
    if GSP_VOLUMES.exists() and not force:
        return
    zf = fetch_gp9(year)
    cols = ["GSP Id", "Settlement Date", "Settlement Run Type", "Settlement Period",
            "Meter Volume", "Import/Export Indicator"]  # fmt: skip
    names = subprocess.run(["unzip", "-Z1", str(zf)], capture_output=True, text=True).stdout.split()
    parts = []
    for name in names:
        with subprocess.Popen(["unzip", "-p", str(zf), name], stdout=subprocess.PIPE) as p:
            for chunk in pd.read_csv(p.stdout, usecols=cols, chunksize=2_000_000,
                                     dtype={"Settlement Date": str}):  # fmt: skip
                chunk = chunk[chunk["Settlement Date"] >= start.replace("-", "")]
                if len(chunk):
                    parts.append(chunk)
    df = pd.concat(parts, ignore_index=True)
    df = df.rename(columns=dict(zip(cols, ["gsp", "date", "run", "sp", "mwh", "ie"], strict=True)))
    df["run_rank"] = df.run.map({r: i for i, r in enumerate(RUN_ORDER)})
    df = df.sort_values("run_rank").drop_duplicates(["gsp", "date", "sp", "ie"], keep="last")
    df["mwh"] = df.mwh.where(df.ie == "I", -df.mwh)
    out = df.groupby(["gsp", "date", "sp"]).agg(mwh=("mwh", "sum"), run=("run", "max"))
    out = out.reset_index()
    out["date"] = pd.to_datetime(out.date, format="%Y%m%d")
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(GSP_VOLUMES, index=False)


def load_fuelinst_total(tz: str = "Europe/London") -> pd.Series:
    """Total FUELINST (MW) per 5-minute interval, indexed by local interval start."""
    df = pd.concat([pd.read_parquet(f) for f in sorted(FUELINST_DIR.glob("*.parquet"))])
    df = df.drop_duplicates(["startTime", "fuelType"])
    total = df.groupby("startTime").generation.sum()
    total = total.reindex(pd.date_range(total.index.min(), total.index.max(), freq="5min"))
    # Partial publications show up as short runs where most fuel types read ~0: mask
    # anything more than 4 GW from the rolling 1-hour median (real 5-min moves are < 2 GW)
    med = total.rolling(13, center=True, min_periods=5).median()
    total = total.mask(((total - med).abs() > 4000) | (total < 8000))  # GB never < ~12 GW
    total.index = total.index.tz_localize("UTC").tz_convert(tz).tz_localize(None)
    return total.groupby(level=0).mean()  # fold the repeated hour at autumn clock change
