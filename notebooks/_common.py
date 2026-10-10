"""Shared loaders and chart style for the exploration notebooks.

Stop-gap until proper loaders live in `uk_dfs.data`. Raw files:
- data/raw/neso_dfs/       NESO DFS releases 2022/23 → 2026/27 (`uk_dfs.data.neso.fetch_dfs`)
- data/raw/neso_demand/    NESO historic demand 2022–2026 (`uk_dfs.data.neso.fetch_demand`)
- data/raw/open_meteo/     hourly weather for 8 GB cities + Birmingham sunset times
"""

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uk_dfs.config import FIGURES_DIR, RAW_DIR

TZ = "Europe/London"
OUT = FIGURES_DIR / "explore"
OUT.mkdir(parents=True, exist_ok=True)

# Reference categorical palette, fixed order
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update(
    {
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
)


def save(fig, name):
    fig.savefig(OUT / f"{name}.png")


# --- DFS ---------------------------------------------------------------------------------

RENAME = {
    "Date": "date", "Delivery Date": "date",
    "From": "from", "From_Local": "from", "To": "to", "To_Local": "to",
    "Service Requirement Type": "type",
    "DFS Required": "req", "DFS Required MW": "req", "Service Requirement MW": "req",
    "DFS Procured": "proc", "DFS Procured MW": "proc",
    "Bids Accepted Total Cost": "cost", "DFS Provider Bids Accepted Total Cost GBP": "cost",
    "Settled Volume": "settled", "Settled Volume MW": "settled",
    "Settled Cost": "settled_cost", "Settled Cost GBP": "settled_cost",
    "Event Type": "direction", "Event Tag": "tag", "Event ID": "event_id",
    "DFS Provider": "provider", "Registered DFS Participant": "provider",
    "DFS Volume": "mw", "DFS Volume MW": "mw",
    "Price": "price", "Utilisation Price GBP per MWh": "price", "Status": "status",
}  # fmt: skip

# file stem prefix -> release label; 2022/23 test and live were published separately
FILES = {
    "2223_live": ("2022/23", "Live"),
    "2223_test": ("2022/23", "Test"),
    "2325": ("2023/24", None),
    "2526": ("2024–26", None),
    "2627": ("2026/27", None),
}


def _read_dfs(stem, kind):
    release, typ = FILES[stem]
    df = pd.read_csv(RAW_DIR / "neso_dfs" / f"{stem}_{kind}.csv", encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    # 2026/27 utilisation has "DFS Procured MW" per bid; treat as bid volume
    if kind == "utilisation":
        df = df.rename(columns={"DFS Procured MW": "mw"})
    df = df.rename(columns=RENAME)
    df["release"] = release
    if typ:
        df["type"] = typ
    df["date"] = pd.to_datetime(df["date"], dayfirst=True)
    df["direction"] = df.get("direction", pd.Series("Downwards", index=df.index)).fillna(
        "Downwards"
    )
    # local wall-clock start of the half-hour
    df["start"] = pd.to_datetime(df["date"].dt.strftime("%Y-%m-%d") + " " + df["from"])
    return df


def load_dfs():
    """Return (summary, bids): one row per event half-hour, one row per bid."""
    summary = pd.concat([_read_dfs(s, "summary") for s in FILES], ignore_index=True)
    bids = pd.concat([_read_dfs(s, "utilisation") for s in FILES], ignore_index=True)
    return summary.sort_values("start").reset_index(drop=True), bids


# --- Demand ------------------------------------------------------------------------------


def load_demand():
    """Half-hourly NESO demand indexed by local wall-clock start (clock changes handled).

    `underlying` adds back embedded solar and wind, which national demand (ND) nets off.
    """
    dem = pd.concat(
        [pd.read_csv(f) for f in sorted((RAW_DIR / "neso_demand").glob("demand_*.csv"))],
        ignore_index=True,
    )
    day = pd.to_datetime(dem.SETTLEMENT_DATE, format="mixed")
    # SP1 starts at local midnight; count forward in UTC so 46/50-period days come out right
    midnight = day.dt.tz_localize(TZ).dt.tz_convert("UTC")
    utc = midnight + pd.to_timedelta((dem.SETTLEMENT_PERIOD - 1) * 30, unit="min")
    dem["start_utc"] = utc
    dem["start"] = utc.dt.tz_convert(TZ).dt.tz_localize(None)
    dem["date"] = day
    dem["underlying"] = dem.ND + dem.EMBEDDED_SOLAR_GENERATION + dem.EMBEDDED_WIND_GENERATION
    return dem.set_index("start").sort_index()


# --- Weather -----------------------------------------------------------------------------

# Rough metro-population weights for the 8 cities requested, in request order
CITIES = {
    "London": 9.0, "Birmingham": 2.9, "Manchester": 2.8, "Leeds": 2.3,
    "Glasgow": 1.8, "Bristol": 1.0, "Newcastle": 1.1, "Cardiff": 1.1,
}  # fmt: skip


def load_weather():
    """Population-weighted GB weather, half-hourly on local wall-clock time.

    Note: these are observations (reanalysis), not forecasts. Fine for exploration;
    the models should train on historical forecasts to avoid leakage.
    """
    raw = json.loads((RAW_DIR / "open_meteo" / "hourly_2022_2026.json").read_text())
    w = np.array(list(CITIES.values()))
    cols = ["temperature_2m", "cloud_cover", "shortwave_radiation", "wind_speed_10m"]
    idx = pd.to_datetime(raw[0]["hourly"]["time"]).tz_localize("UTC")
    out = pd.DataFrame(index=idx)
    for c in cols:
        m = np.array([loc["hourly"][c] for loc in raw], dtype=float)  # (city, hour)
        out[c] = np.average(m, axis=0, weights=w)
    out = out.dropna().resample("30min").interpolate()
    out.index = out.index.tz_convert(TZ).tz_localize(None)
    return (
        out.rename(
            columns={
                "temperature_2m": "temp",
                "cloud_cover": "cloud",
                "shortwave_radiation": "radiation",
                "wind_speed_10m": "wind",
            }
        )
        .groupby(level=0)
        .mean()
    )  # fold the duplicated hour at autumn clock change


def load_london_weather():
    """London (LCL era, 2011–14) daily mean temperature and sunset hour, local time.

    Raw file is GMT; observations, not forecasts.
    """
    raw = json.loads((RAW_DIR / "open_meteo" / "london_hourly_2011_2014.json").read_text())
    t = pd.Series(
        raw["hourly"]["temperature_2m"],
        index=pd.to_datetime(raw["hourly"]["time"]).tz_localize("UTC").tz_convert(TZ),
    )
    temp = t.groupby(t.index.tz_localize(None).normalize()).mean()
    sunset = pd.to_datetime(raw["daily"]["sunset"]).tz_localize("UTC").tz_convert(TZ)
    out = pd.DataFrame(
        {"sunset_h": sunset.hour + sunset.minute / 60},
        index=pd.to_datetime(raw["daily"]["time"]),
    )
    return out.join(temp.rename("temp"))


def load_sun():
    raw = json.loads((RAW_DIR / "open_meteo" / "daily_sun_birmingham.json").read_text())
    sun = pd.DataFrame(raw["daily"])
    sun["date"] = pd.to_datetime(sun.time)
    for c in ("sunrise", "sunset"):
        t = pd.to_datetime(sun[c])
        sun[c + "_h"] = t.dt.hour + t.dt.minute / 60
    return sun.set_index("date")[["sunrise_h", "sunset_h"]]
