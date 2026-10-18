"""Low Carbon London loader: raw CSV in a zip -> Parquet with start-of-half-hour timestamps."""

import shutil
import zipfile

import pandas as pd
import pytest

from uk_dfs.data import lcl

RAW_CSV = """LCLid,stdorToU,DateTime,KWH/hh (per half hour)
MAC000002,Std,2013-01-01 00:00:00.0000000, 0.219
MAC000002,Std,2013-01-01 00:30:00.0000000, 0.241
MAC000002,Std,2013-01-01 01:00:00.0000000,Null
MAC000123,ToU,2013-01-01 00:30:00.0000000, 0.100
"""  # noqa: W291 - the real file pads the header and values with spaces


@pytest.fixture
def built(tmp_path, monkeypatch):
    if shutil.which("unzip") is None:
        pytest.skip("needs the unzip CLI")
    raw, out = tmp_path / "raw", tmp_path / "interim"
    raw.mkdir()
    with zipfile.ZipFile(raw / "LCL-FullData.zip", "w") as z:
        z.writestr("CC_LCL-FullData.csv", RAW_CSV)
    monkeypatch.setattr(lcl, "RAW", raw)
    monkeypatch.setattr(lcl, "OUT", out)
    monkeypatch.setattr(lcl, "READINGS", out / "readings.parquet")
    monkeypatch.setattr(lcl, "HOUSEHOLDS", out / "households.parquet")
    lcl.build()
    return pd.read_parquet(lcl.READINGS), pd.read_parquet(lcl.HOUSEHOLDS)


def test_readings_are_relabelled_to_the_start_of_the_half_hour(built):
    readings, _ = built
    # the raw reading stamped 00:30 covers 00:00–00:30, like the tariff row stamped 00:00
    home2 = readings[readings.household == 2]
    assert home2.ts.tolist() == list(pd.to_datetime(["2012-12-31 23:30", "2013-01-01 00:00",
                                                     "2013-01-01 00:30"]))  # fmt: skip
    assert home2.kwh.iloc[1] == pytest.approx(0.241)
    assert home2.kwh.isna().iloc[2]  # "Null" -> NaN


def test_households_and_tariff_groups(built):
    _, homes = built
    assert homes.set_index("household").tariff.to_dict() == {2: "Std", 123: "ToU"}


def test_build_is_idempotent(built):
    mtime = lcl.READINGS.stat().st_mtime_ns
    lcl.build()
    assert lcl.READINGS.stat().st_mtime_ns == mtime
