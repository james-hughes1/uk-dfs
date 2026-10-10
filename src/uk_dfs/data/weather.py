"""Open-Meteo historical weather for Great Britain.

One hourly series per city from the Open-Meteo archive (reanalysis observations, not
forecasts), averaged with rough metro-population weights into a single GB series. Fine for
exploration and for matching days by temperature; models that predict demand should train
on historical *forecasts* instead, to avoid leakage.

`fetch_weather()` caches the raw JSON in data/raw/open_meteo/ and is idempotent: a file
already on disk is left alone unless `force=True`.
"""

import json
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from uk_dfs.config import RAW_DIR

WEATHER_DIR = RAW_DIR / "open_meteo"
HOURLY_FILE = WEATHER_DIR / "hourly_2022_2026.json"
API = "https://archive-api.open-meteo.com/v1/archive"
START, END = "2022-01-01", "2026-09-30"
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


def fetch_weather(force: bool = False) -> bool:
    """Cache hourly weather for the GB cities. Returns True if it downloaded."""
    if HOURLY_FILE.exists() and HOURLY_FILE.stat().st_size > 0 and not force:
        return False
    WEATHER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = HOURLY_FILE.with_suffix(".json.part")  # so a failed download never looks complete
    with urllib.request.urlopen(weather_url(), timeout=300) as r:
        tmp.write_bytes(r.read())
    tmp.replace(HOURLY_FILE)
    return True


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
