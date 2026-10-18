"""Alternative baselines that use only inputs participants can't influence.

Both start from unadjusted BL01 and correct it with the weather and calendar, never with
the household's own use on the day (which is what makes the in-day adjustment gameable).

- `TemperatureScaled`: BL01 × exp(k · dT), one parameter. dT is the day's temperature
  minus the mean over its BL01 baseline days. k is the slope of a regression on daily
  portfolio totals, log(Σ actual / Σ BL01) = c + k · dT; the intercept c is dropped, so the
  model only corrects for weather and never shifts BL01's overall level.
- `BoostedRatio`: gradient boosting of actual ÷ BL01 on weather, calendar and the home's
  typical use, weighted by BL01 so that errors count in kWh, not in ratios. By default it
  is rescaled so its correction averages exactly 1 over the training data (Σ prediction =
  Σ BL01): like the dropped intercept above, it may move BL01 with conditions but not
  shift its overall level, which differs from year to year by a couple of percent and
  can't be learned from one year.

Both take and return home-day tables (one row per home and day) with at least the
columns `bl01` and `actual` (kWh over the window) and the features they use.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

FEATURES = ("bl01", "size", "temp", "dT", "sunset", "dow", "working")


class TemperatureScaled:
    """BL01 scaled by a pooled factor for the temperature change."""

    name = "BL01 × temperature"

    def fit(self, hd: pd.DataFrame) -> "TemperatureScaled":
        day = hd.groupby("date").agg(actual=("actual", "sum"), bl01=("bl01", "sum"),
                                     dT=("dT", "first"))  # fmt: skip
        self.k = np.polyfit(day.dT, np.log(day.actual / day.bl01), 1)[0]
        return self

    def predict(self, hd: pd.DataFrame) -> np.ndarray:
        return hd.bl01.to_numpy() * np.exp(self.k * hd.dT.to_numpy())


class BoostedRatio:
    """Gradient-boosted correction factor on BL01."""

    name = "Gradient boosting"

    def __init__(self, features=FEATURES, level_free: bool = True, **params):
        self.features = list(features)
        self.level_free = level_free
        self.params = {"max_iter": 300, "learning_rate": 0.05, "max_leaf_nodes": 31,
                       "min_samples_leaf": 200, "random_state": 0} | params  # fmt: skip

    def fit(self, hd: pd.DataFrame) -> "BoostedRatio":
        cat = [f for f in self.features if f == "dow"]
        self.model = HistGradientBoostingRegressor(categorical_features=cat, **self.params)
        X = hd[self.features]
        self.model.fit(X, hd.actual / hd.bl01, sample_weight=hd.bl01)
        self.scale = 1.0
        if self.level_free:
            self.scale = hd.bl01.sum() / self.predict(hd).sum()
        return self

    def predict(self, hd: pd.DataFrame) -> np.ndarray:
        return hd.bl01.to_numpy() * self.model.predict(hd[self.features]) * self.scale
