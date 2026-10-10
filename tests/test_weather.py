"""Open-Meteo weather: request, population weighting, local time, idempotent fetch."""

import json
import urllib.parse

import pandas as pd
import pytest

from uk_dfs.data import weather


def fake_response(temps: list[float], start="2022-06-01T00:00", hours=4) -> list[dict]:
    time = pd.date_range(start, periods=hours, freq="h").strftime("%Y-%m-%dT%H:%M").tolist()
    return [
        {"hourly": {"time": time, **{v: [t] * hours for v in weather.VARIABLES}}} for t in temps
    ]


def test_url_asks_for_every_city_and_variable():
    q = urllib.parse.parse_qs(urllib.parse.urlparse(weather.weather_url()).query)
    assert len(q["latitude"][0].split(",")) == len(weather.CITIES)
    assert q["hourly"][0].split(",") == list(weather.VARIABLES)
    assert q["timezone"] == ["GMT"]


def test_gb_weather_is_population_weighted_half_hourly_local_time():
    temps = [10.0] + [0.0] * (len(weather.CITIES) - 1)  # only London is warm
    w = weather.gb_weather(fake_response(temps))
    pops = [pop for _, _, pop in weather.CITIES.values()]
    assert w.temp.iloc[0] == pytest.approx(10 * pops[0] / sum(pops))
    assert w.index[0] == pd.Timestamp("2022-06-01 01:00")  # 00:00 GMT is 01:00 BST
    assert (w.index[1] - w.index[0]) == pd.Timedelta("30min")


def test_daily_temperature():
    w = weather.gb_weather(fake_response([5.0] * len(weather.CITIES), hours=48))
    assert weather.daily_temperature(w).iloc[0] == pytest.approx(5.0)


def test_fetch_is_idempotent(tmp_path, monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(fake_response([1.0] * len(weather.CITIES))).encode()

    def urlopen(url, timeout):
        calls.append(url)
        return Response()

    monkeypatch.setattr(weather, "WEATHER_DIR", tmp_path)
    monkeypatch.setattr(weather, "HOURLY_FILE", tmp_path / "hourly.json")
    monkeypatch.setattr(weather.urllib.request, "urlopen", urlopen)
    assert weather.fetch_weather() is True
    assert weather.fetch_weather() is False
    assert len(calls) == 1
    assert not list(tmp_path.glob("*.part"))
