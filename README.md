# uk-dfs: Measuring Britain's Demand Flexibility Service

Does the flexibility NESO pays for through the Demand Flexibility Service (DFS) show up in the data?

- **National check:** does claimed delivery appear as a dip in GB demand?
- **Household check:** how biased is the official BL01 baseline, and when?

> Work in progress. Findings will lead this README once we have them.

## Setup

```bash
uv sync                      # create .venv and install everything
uv run pre-commit install    # run lint/format on every commit
uv run pytest                # run tests
```

## Layout

```
src/uk_dfs/
  config.py      paths shared by all modules
  data/          loaders: download + cache raw data (idempotent)
  features/      calendar, weather, solar, event-window features
  models/        BL01, national demand model, ML/Bayesian baselines
  evaluation/    bias/MAE, event study, power analysis
  reporting/     charts and tables
data/            raw/ interim/ processed/ (not committed)
notebooks/       exploration and figures only
tests/
```
