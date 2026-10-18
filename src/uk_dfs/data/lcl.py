"""Low Carbon London smart meter data (UK Power Networks, London Datastore).

5,567 households, half-hourly kWh, Nov 2011 – Feb 2014. ~1,100 were on a dynamic
time-of-use (dToU) tariff through 2013; the rest stayed on a flat tariff.

Raw files (fetched by hand into data/raw/lcl/):
- LCL-FullData.zip   one ~10 GB CSV, 167M rows, each reading stamped at the END of its half-hour
- Tariffs.xlsx       2013 dToU price signal per half hour (High / Low / Normal), stamped at START

All times are GMT. Interim outputs label every half-hour by its start.

`build()` streams the CSV out of the zip (via the `unzip` CLI: the archive uses
Deflate64, which Python's zipfile can't read) and writes compact Parquet to data/interim/lcl/.
It is idempotent: existing outputs are left alone unless `force=True`.
"""

import subprocess

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from uk_dfs.config import INTERIM_DIR, RAW_DIR

RAW = RAW_DIR / "lcl"
OUT = INTERIM_DIR / "lcl"
READINGS = OUT / "readings.parquet"
HOUSEHOLDS = OUT / "households.parquet"

# Raw readings are stamped at the END of their half-hour; Tariffs.xlsx at the START. `build()`
# subtracts this so every `ts` in data/interim/lcl/ marks the start, like the tariff file.
# Source: UK Data Service SN 7857 user guide (Schofield et al. 2015), consumption tables:
# "Time-stamp at the end of each half-hour measurement period in the GMT time-zone."
READING_LABEL = pd.Timedelta("30min")

SCHEMA = pa.schema([("household", pa.int16()), ("ts", pa.timestamp("s")), ("kwh", pa.float32())])


def _household_id(lclid: pd.Series) -> pd.Series:
    # "MAC000002" -> 2
    return lclid.str.slice(3).astype("int16")


def build(force: bool = False, chunksize: int = 5_000_000) -> None:
    if READINGS.exists() and HOUSEHOLDS.exists() and not force:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    households = {}
    cmd = ["unzip", "-p", str(RAW / "LCL-FullData.zip"), "*.csv"]
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as proc:
        with pq.ParquetWriter(READINGS, SCHEMA) as writer:
            f = proc.stdout
            for chunk in pd.read_csv(f, chunksize=chunksize, dtype=str):
                chunk.columns = chunk.columns.str.strip()
                kwh_col = next(c for c in chunk.columns if c.lower().startswith("kwh"))
                for row in chunk.drop_duplicates("LCLid").itertuples(index=False):
                    households.setdefault(row.LCLid, row)
                out = pd.DataFrame(
                    {
                        "household": _household_id(chunk.LCLid),
                        # "2012-10-12 00:30:00.0000000": drop the 7-digit fraction, and
                        # relabel from the end of the half-hour to its start (see READING_LABEL)
                        "ts": (
                            pd.to_datetime(chunk.DateTime.str.slice(0, 19)) - READING_LABEL
                        ).astype("datetime64[s]"),
                        # "Null" readings become NaN
                        "kwh": pd.to_numeric(chunk[kwh_col].str.strip(), errors="coerce").astype(
                            "float32"
                        ),
                    }
                )
                writer.write_table(pa.Table.from_pandas(out, schema=SCHEMA, preserve_index=False))
    if proc.returncode:
        raise RuntimeError(f"unzip failed with exit code {proc.returncode}")
    hh = pd.DataFrame(list(households.values()))
    hh = pd.DataFrame(
        {
            "household": _household_id(hh.LCLid),
            "lclid": hh.LCLid,
            "tariff": hh.stdorToU.str.strip(),  # "Std" or "ToU"
        }
    )
    hh.to_parquet(HOUSEHOLDS, index=False)


def load_tariffs() -> pd.DataFrame:
    """2013 dToU price signal: ts (GMT, start of the half-hour), signal (High / Low / Normal)."""
    t = pd.read_excel(RAW / "Tariffs.xlsx", sheet_name=0)
    return t.rename(columns={"TariffDateTime": "ts", "Tariff": "signal"})


def signal_days(dates: pd.DatetimeIndex) -> np.ndarray:
    """bool (D,): local days with any High or Low half-hour (the trial's "event days")."""
    t = load_tariffs()
    local = t.ts.dt.tz_localize("UTC").dt.tz_convert("Europe/London").dt.tz_localize(None)
    days = local[t.signal != "Normal"].dt.normalize().unique()
    return np.asarray(pd.DatetimeIndex(dates).isin(days))


SLOT_MEANS = OUT / "slot_means.parquet"
DAILY = OUT / "household_daily.parquet"


def build_aggregates(force: bool = False) -> None:
    """Two small tables from readings.parquet, one row group at a time to bound memory.

    - slot_means: per GMT half-hour (start) and tariff group, summed kWh and reading count
    - household_daily: per household and local date, summed kWh and reading count

    Timestamps in LCL are GMT throughout (48 slots on clock-change days). Readings off the
    half-hour grid (a few dozen) and duplicate (household, ts) rows are dropped.
    """
    if SLOT_MEANS.exists() and DAILY.exists() and not force:
        return
    hh = pd.read_parquet(HOUSEHOLDS)
    tou = pd.Series(False, index=range(hh.household.max() + 1))
    tou[hh.household] = hh.tariff.eq("ToU").to_numpy()
    f = pq.ParquetFile(READINGS)
    slots, days = [], []
    for i in range(f.num_row_groups):
        r = f.read_row_group(i).to_pandas().dropna(subset=["kwh"])
        r = r[(r.ts.dt.minute % 30 == 0) & (r.ts.dt.second == 0)]
        r = r.drop_duplicates(["household", "ts"])
        r["tou"] = tou.to_numpy()[r.household]
        slots.append(r.groupby(["ts", "tou"]).kwh.agg(["sum", "count"]))
        local = r.ts.dt.tz_localize("UTC").dt.tz_convert("Europe/London")
        r["date"] = local.dt.tz_localize(None).dt.normalize()
        days.append(r.groupby(["household", "date"]).kwh.agg(["sum", "count"]))
    # households can straddle row groups, so re-sum after concatenating
    pd.concat(slots).groupby(level=[0, 1]).sum().reset_index().to_parquet(SLOT_MEANS)
    pd.concat(days).groupby(level=[0, 1]).sum().reset_index().to_parquet(DAILY)


CUBE = OUT / "cube.npy"
CUBE_INDEX = OUT / "cube_index.npz"


def build_cube(n_std: int = 1500, seed: int = 0, force: bool = False) -> None:
    """Dense household × local day × half-hour slot array (kWh, float32, NaN = missing).

    All ToU homes plus a random sample of `n_std` Std homes, to fit in a few hundred MB.
    Slots are local clock time (0 = 00:00–00:30). Clock-change days don't fit a 48-slot
    grid; they are left in but should be treated as unusable (BL01 excludes them anyway).
    """
    if CUBE.exists() and CUBE_INDEX.exists() and not force:
        return
    hh = pd.read_parquet(HOUSEHOLDS)
    rng = np.random.default_rng(seed)
    std = hh[hh.tariff == "Std"].household.to_numpy()
    ids = np.sort(np.concatenate([hh[hh.tariff == "ToU"].household, rng.choice(std, n_std, False)]))
    tou = hh.set_index("household").tariff.reindex(ids).eq("ToU").to_numpy()
    row = np.full(hh.household.max() + 1, -1)
    row[ids] = np.arange(len(ids))

    daily = pd.read_parquet(DAILY, columns=["date"])
    d0, d1 = daily.date.min(), daily.date.max()
    dates = pd.date_range(d0, d1, freq="D")
    X = np.full((len(ids), len(dates), 48), np.nan, dtype="float32")
    f = pq.ParquetFile(READINGS)
    for i in range(f.num_row_groups):
        r = f.read_row_group(i).to_pandas().dropna(subset=["kwh"])
        r = r[row[r.household.to_numpy()] >= 0]
        r = r[(r.ts.dt.minute % 30 == 0) & (r.ts.dt.second == 0)]
        local = r.ts.dt.tz_localize("UTC").dt.tz_convert("Europe/London").dt.tz_localize(None)
        di = (local.dt.normalize() - d0).dt.days.to_numpy()
        ok = (di >= 0) & (di < len(dates))
        si = (local.dt.hour * 2 + local.dt.minute // 30).to_numpy()
        X[row[r.household.to_numpy()][ok], di[ok], si[ok]] = r.kwh.to_numpy()[ok]
    np.save(CUBE, X)
    np.savez(CUBE_INDEX, households=ids, tou=tou, dates=dates.to_numpy())


def load_cube():
    """Return (X, households, tou, dates) from `build_cube()`; X is memory-mapped."""
    idx = np.load(CUBE_INDEX)
    X = np.load(CUBE, mmap_mode="r")
    return X, idx["households"], idx["tou"], pd.DatetimeIndex(idx["dates"])


if __name__ == "__main__":
    build()
    build_aggregates()
    build_cube()
