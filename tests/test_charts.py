"""Every chart renders and every web export is valid, on small synthetic inputs."""

import json

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

from uk_dfs.evaluation import baseline_error as be  # noqa: E402
from uk_dfs.evaluation import floor, opt_in, overpayment  # noqa: E402
from uk_dfs.reporting import outputs  # noqa: E402

DATES = pd.date_range("2013-01-07", periods=120)


@pytest.fixture(scope="module")
def panel():
    rng = np.random.default_rng(3)
    X = 0.25 * rng.lognormal(0, 0.3, (30, len(DATES), 48))
    temp = pd.Series(rng.normal(5, 3, len(DATES)), index=DATES)
    return be.Panel.build(X.astype("float32"), DATES, np.ones(30, bool), temp)


def test_plain_handles_numpy_pandas_and_nan():
    df = pd.DataFrame({"a": [1.23456, np.nan], "d": pd.to_datetime(["2023-01-01", "2023-01-02"])})
    out = outputs.plain({"df": df, "x": np.float32(2.5), "n": np.int64(3), "b": np.bool_(True),
                         "inf": float("inf"), "arr": np.array([1.0, 2.0]),
                         "idx": pd.Index([1, 2])})  # fmt: skip
    assert out["df"][0]["a"] == 1.23456 and out["df"][1]["a"] is None
    assert out["df"][0]["d"] == "2023-01-01"
    assert out == json.loads(json.dumps(out)) and out["inf"] is None


def test_save_web_data_writes_a_script(tmp_path, monkeypatch):
    monkeypatch.setattr(outputs, "WEB_DATA_DIR", tmp_path)
    path = outputs.save_web_data("demo", {"x": np.array([1, 2])})
    text = path.read_text()
    assert text.startswith("window.STUDY = window.STUDY || {};")
    assert json.loads(text.split(" = ", 2)[-1].rstrip(";\n")) == {"x": [1, 2]}


def test_baseline_error_chart(panel):
    from uk_dfs.reporting.baseline_error import plot_baseline_error, web_data

    days = be.placebo_days(panel, min_homes=5)
    reg = be.bias_regression(panel, n_boot=20, min_homes=5)
    acc = be.accuracy(panel, n_boot=20, min_homes=5)
    meters = be.meter_errors(panel)
    examples = be.example_home_days(panel, n=2)
    assert len(examples) == 2 and len(examples[0]["actual"]) == 48
    assert plot_baseline_error(meters, days, reg).axes
    data = outputs.plain(web_data(meters, days, acc, examples))
    assert {"meter_hist", "portfolio_hist", "days", "fits", "examples"} <= set(data)


def test_opt_in_and_floor_charts(panel):
    from uk_dfs.reporting.floor import plot_floor
    from uk_dfs.reporting.floor import web_data as floor_web
    from uk_dfs.reporting.opt_in import plot_opt_in

    sweep = opt_in.sweep(panel, rhos=(0.0, 0.5, 1.0), n_boot=20)
    assert plot_opt_in(sweep).axes
    s = floor.by_start(panel, windows=(be.Window(32), be.Window(34)), n_boot=20)
    c = floor.by_condition(panel, n_boot=20)
    g = floor.grid(panel, savings=(0, 10), rhos=(0.0, 0.3), n_boot=20)
    assert plot_floor(s, c, g).axes
    assert len(outputs.plain(floor_web(s, c, g))["grid"]) == 4


def test_overpayment_chart():
    from uk_dfs.reporting.overpayment import plot_overpayment, text_report

    rows = [{"saving_pct": s, "rho": r, "claim_pct": s + 1, "floored_pct": s + 25 + 5 * r,
             "floored_pct_lo": s + 24, "floored_pct_hi": s + 26 + 5 * r}
            for s in (5, 10, 20, 40) for r in (0.0, 0.1, 0.3)]  # fmt: skip
    dec = overpayment.decompose(pd.DataFrame(rows))
    spend = pd.DataFrame(
        {"settled_mwh": [10.0, 20, 30], "cost": [5e6, 2e6, 1e6], "unsettled_hh": [0, 0, 2]},
        index=["2022/23", "2023/24", "Nov 2024 on"],
    )
    spend.loc["Total"] = spend.sum()
    spend["price"] = spend.cost / spend.settled_mwh
    over = overpayment.overpayment(dec, spend)
    assert "S4" in text_report(spend, dec, over)
    assert plot_overpayment(spend, dec, over).axes


def test_reality_check_and_better_baselines_charts():
    from uk_dfs.evaluation.reality_check import QUANTITIES
    from uk_dfs.reporting.better_baselines import plot_better_baselines
    from uk_dfs.reporting.reality_check import plot_reality_check

    s = pd.DataFrame({"estimate": [35, 7, 98, 173, 454, 40, 37, 27, 25]}, index=list(QUANTITIES))
    s["lo"], s["hi"] = s.estimate * 0.8, s.estimate * 1.2
    s.attrs["events"] = 53
    assert plot_reality_check(s).axes

    methods = ["BL01", "BL01 + in-day adj", "BL01 × temperature", "Gradient boosting"]
    scores = pd.DataFrame({"portfolio_mae_pct": [7.5, 4.5, 6.5, 5.5],
                           "portfolio_mae_change": [0, -3, -1, -2],
                           "portfolio_mae_change_lo": [0, -4, -2, -3],
                           "portfolio_mae_change_hi": [0, -2, 0, -1]}, index=methods)  # fmt: skip
    by_dT = pd.DataFrame(
        {m: np.linspace(-10, 10, 6) for m in methods},
        index=["< −4", "−4…−2", "−2…0", "0…2", "2…4", "> 4"],
    )
    by_dT.insert(0, "days", 30)
    assert plot_better_baselines(scores, by_dT, be.MAIN).axes


def test_dfs_conditions_chart():
    from uk_dfs.features.events import A1, A2
    from uk_dfs.reporting.dfs_conditions import plot_dfs_conditions, web_data

    ev = pd.DataFrame(
        {
            "date": pd.to_datetime(["2022-12-01", "2025-06-01"]),
            "group": [A1, A2],
            "minutes": [60, 180],
            "temp": [2.0, 15.0],
            "dT": [-3.0, 1.0],
        }
    )
    stat = {k: 1.0 for k in ("claim_pct", "floored_pct")}
    stat |= {f"{k}_{e}": v for k in list(stat) for e, v in (("lo", 0.5), ("hi", 1.5))}
    out = pd.DataFrame([{"group": A1, "in_force": True, **stat},
                        {"group": A2, "in_force": True, **stat}])  # fmt: skip
    ref = {"BL01": {"claim_pct": -0.6, "floored_pct": 26.8}}
    assert plot_dfs_conditions(ev, {"timing only": out}, ref).axes
    data = outputs.plain(web_data(ev, {"timing only": out}, ref))
    assert data["events"][0]["date"] == "2022-12-01"
