"""Open-Meteo historical weather: Great Britain (2022–26) and London (2011–14).

GB: one hourly series per city from the Open-Meteo archive (reanalysis observations, not
forecasts), averaged with rough metro-population weights into a single GB series. Fine for
exploration and for matching days by temperature; models that predict demand should train
on historical *forecasts* instead, to avoid leakage.

London: the single grid cell for the Low Carbon London homes, Nov 2011 – Feb 2014, with
daily sunset times.

`fetch_weather()` and `fetch_london_weather()` cache the raw JSON in data/raw/open_meteo/
and are idempotent: a file already on disk is left alone unless `force=True`.
"""

import json
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from uk_dfs.config import RAW_DIR

WEATHER_DIR = RAW_DIR / "open_meteo"
HOURLY_FILE = WEATHER_DIR / "hourly_2022_2026.json"
LONDON_FILE = WEATHER_DIR / "london_hourly_2011_2014.json"
API = "https://archive-api.open-meteo.com/v1/archive"
START, END = "2022-01-01", "2026-09-30"
LONDON_START, LONDON_END = "2011-11-01", "2014-03-01"
TZ = "Europe/London"

# city -> (latitude, longitude, rough metro population in millions). Coordinates are the
# Open-Meteo grid cells the cached file came back with, so a re-fetch hits the same cells.
CITIES = {
    "London": (51.493847, -0.1630249, 9.0),
    "Birmingham": (52.47803, -1.8401489, 2.9),
    "Manchester": (53.46221, -2.2328186, 2.8),
    "Leeds": (53.813705, -1.5606995, 2.3),
    "Glasgow": (55.85237, -4.2244873, 1.8),
    "Bristol": (51.42355, -2.6039734, 1.0),
    "Newcastle": (55.008785, -1.6135254, 1.1),
    "Cardiff": (51.493847, -3.2608643, 1.1),
}
VARIABLES = {
    "temperature_2m": "temp",
    "cloud_cover": "cloud",
    "shortwave_radiation": "radiation",
    "wind_speed_10m": "wind",
}


def weather_url(start: str = START, end: str = END) -> str:
    """One request for every city: Open-Meteo returns a list, one entry per location."""
    query = {
        "latitude": ",".join(str(lat) for lat, _, _ in CITIES.values()),
        "longitude": ",".join(str(lon) for _, lon, _ in CITIES.values()),
        "start_date": start,
        "end_date": end,
        "hourly": ",".join(VARIABLES),
        "timezone": "GMT",
    }
    return f"{API}?{urllib.parse.urlencode(query)}"


def london_url(start: str = LONDON_START, end: str = LONDON_END) -> str:
    """The London cell only, plus daily sunset."""
    lat, lon, _ = CITIES["London"]
    query = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "hourly": ",".join(VARIABLES),
        "daily": "sunset",
        "timezone": "GMT",
    }
    return f"{API}?{urllib.parse.urlencode(query)}"


def _download(url: str, path, force: bool) -> bool:
    if path.exists() and path.stat().st_size > 0 and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.part")  # so a failed download never looks complete
    with urllib.request.urlopen(url, timeout=300) as r:
        tmp.write_bytes(r.read())
    tmp.replace(path)
    return True


def fetch_weather(force: bool = False) -> bool:
    """Cache hourly weather for the GB cities. Returns True if it downloaded."""
    return _download(weather_url(), HOURLY_FILE, force)


def fetch_london_weather(force: bool = False) -> bool:
    """Cache hourly London weather for the LCL period. Returns True if it downloaded."""
    return _download(london_url(), LONDON_FILE, force)


def gb_weather(raw: list[dict]) -> pd.DataFrame:
    """Population-weighted GB weather, half-hourly on local wall-clock time.

    `raw` is the Open-Meteo response: one dict per city, in `CITIES` order.
    """
    weights = np.array([pop for _, _, pop in CITIES.values()])
    idx = pd.to_datetime(raw[0]["hourly"]["time"]).tz_localize("UTC")
    out = pd.DataFrame(index=idx)
    for var, name in VARIABLES.items():
        m = np.array([loc["hourly"][var] for loc in raw], dtype=float)  # (city, hour)
        out[name] = np.average(m, axis=0, weights=weights)
    out = out.dropna().resample("30min").interpolate()
    out.index = out.index.tz_convert(TZ).tz_localize(None)
    return out.groupby(level=0).mean()  # fold the repeated hour at the autumn clock change


def load_weather() -> pd.DataFrame:
    """GB weather from the cached file (run `fetch_weather()` first)."""
    return gb_weather(json.loads(HOURLY_FILE.read_text()))


def daily_temperature(weather: pd.DataFrame) -> pd.Series:
    """Mean GB temperature per local calendar day, °C."""
    return weather.temp.groupby(weather.index.normalize()).mean()


def london_daily(raw: dict) -> pd.DataFrame:
    """Per local calendar day: mean temperature (°C) and sunset (local hours)."""
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


def load_london_weather() -> pd.DataFrame:
    """London daily weather from the cached file (run `fetch_london_weather()` first)."""
    return london_daily(json.loads(LONDON_FILE.read_text()))
