# uk-dfs: Measuring Britain's Demand Flexibility Service

Does the flexibility NESO pays for through the Demand Flexibility Service (DFS) show up in the data?

Contains code that runs statistical analysis on NESO's DFS data and the 2013 Low Carbon London study.

Link to the interactive website [here](http://localhost:8000/#image-0) which summarises the key findings.

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
reports/
  figures/       one chart per analysis (<module>.png), for the report
  results/       each analysis's printed tables, one .txt per module
  report/        LaTeX write-up (report.tex → build/report.pdf)
web/             "the study in ten images": static site (index.html, app.js, styles.css)
  data/          chart data written by the analyses, one .js per module
tests/
```

## What's in the code

Every analysis is a module you run with `uv run python -m uk_dfs.<module>`. Each one prints its tables to the terminal, saves its chart to `reports/figures/<module>.png` and writes the web app's data to `web/data/<module>.js` (via `reporting.outputs.save`). Loaders are idempotent, so the first run downloads or builds what it needs and later runs reuse the cache.

### Data (`data/`)

| Module | What it does | Writes |
| --- | --- | --- |
| `data.neso` | DFS requirements, accepted bids and per-half-hour summaries for every season; NESO historic demand. `fetch_dfs()`, `fetch_demand()`, `load_dfs()`, `load_demand()` | `data/raw/neso_dfs/`, `data/raw/neso_demand/` |
| `data.elexon` | 5-minute FUELINST generation (GB demand proxy); GP9 GSP volumes. `fetch_fuelinst()`, `load_fuelinst_total()` | `data/raw/elexon_fuelinst/` (one Parquet per month) |
| `data.weather` | Open-Meteo hourly weather: population-weighted GB 2022–26, and London 2011–14 with sunset. `fetch_weather()`, `fetch_london_weather()` | `data/raw/open_meteo/` |
| `data.lcl` | Low Carbon London smart meters: streams the 10 GB zip into Parquet, then a household × day × half-hour cube (all ToU homes + 1,500 Std). Run directly: `uv run python -m uk_dfs.data.lcl` | `data/interim/lcl/` |

The LCL raw files (`LCL-FullData.zip`, `Tariffs.xlsx`) are downloaded by hand into `data/raw/lcl/`; everything else is fetched automatically.

### Building blocks (`features/`, `models/`, `reporting/`)

| Module | What it is |
| --- | --- |
| `features.events` | DFS turn-down events, one row each; the phase names (launch winter, second winter, market phase) and the national check's two groups (launch winter vs since Oct 2023) |
| `features.conditions` | Temperature change against each day's BL01 baseline days (the main driver of BL01 bias) |
| `models.bl01` | BL01 baseline (Elexon P376), vectorised over households, with the optional in-day adjustment and bank holidays to 2026 |
| `models.baselines` | Alternative baselines from weather and calendar only: `TemperatureScaled`, `BoostedRatio` |
| `reporting.<module>` | One per analysis: its chart (`plot_*`), web data (`web_data`) and, where long, its text report |
| `reporting.outputs`, `reporting.style`, `reporting.text` | Saving charts and web data; the shared palette and chart style; plain-text tables |

### Analyses (`evaluation/`)

Report sections in brackets. Part B and C modules load the LCL cube (built on first run); `dfs_conditions` also needs the NESO and GB weather caches, which `event_study` fetches.

| Run | Answers | Outputs |
| --- | --- | --- |
| `python -m uk_dfs.evaluation.event_study [--offline]` | (A1, A2) Does claimed DFS delivery show up as a dip in 5-minute GB generation? Stacked difference-in-differences, placebos, alternative reference periods | Event funnel, detected ÷ claimed per group with CIs, MW per event, robustness table. Chart: event-study profiles, placebos, robustness |
| `python -m uk_dfs.evaluation.baseline_error` | (B1, B2) How wrong is BL01 when nobody responds, and when is it biased? | Per-meter and portfolio accuracy for 1–2 h windows 16:00–19:00; regression of daily error on temperature change, temperature, day type, start time. Chart: one home vs the portfolio; daily error vs temperature change |
| `python -m uk_dfs.evaluation.better_baselines` | (B3) Do weather/calendar baselines beat BL01 out of sample (train 2012/13, test 2013/14)? | MAE per meter and per portfolio, change vs BL01 with paired CIs, bias by temperature change; forecast-error sensitivity. Chart: bias by temperature change; MAE per baseline |
| `python -m uk_dfs.evaluation.reality_check` | (B4) Against a real randomised response (ToU vs Std), does BL01 credit it correctly? | True effect (W, %), BL01 and BL01 + in-day claim ÷ true, share of meters negative, what the floor adds. Chart: claim as % of the true effect per rule; share negative |
| `python -m uk_dfs.evaluation.opt_in` | (B5) How much do households overclaim if they opt in on evenings they expect to be quiet? | Claim and floored claim by foresight ρ, both BL01 variants; sensitivity to the opt-in rate. Chart: claim vs ρ, without and with the floor |
| `python -m uk_dfs.evaluation.floor` | (B6) How much "delivery" does the per-meter settlement floor create? | Share negative and floored claim by condition and start time; real-response view; opt-in × true-saving grid. Chart: by time of day, by temperature change, overclaim vs ρ |
| `python -m uk_dfs.evaluation.dfs_conditions` | (C1) How biased is BL01 under the conditions of real DFS events? | Event summary per rules period; placebo claim and floored claim, timing-only and post-stratified. Chart: every event's temperature change; placebo claim per period |
| `python -m uk_dfs.evaluation.overpayment` | (C2) How much of what NESO settled bought real delivery, under four labelled scenarios? | Settled MWh and £ per period; real share, inflation and the split into true saving / baseline error / floor / opt-in selection; £ overpaid per scenario × period. Chart: what 100 MWh settled consists of; £ overpaid |

To refresh every results file, chart and web data file (about 6 minutes; `dfs_conditions` is the slow one, at about 2 minutes):

```bash
for m in event_study baseline_error better_baselines reality_check opt_in floor dfs_conditions overpayment; do
  uv run python -m uk_dfs.evaluation.$m > reports/results/$m.txt
done
```

## Web app: the study in ten images

`web/` is a static site with no build step. It opens on a summary card (what the project asks, the three questions with expandable findings, and links to the repo and LinkedIn), followed by ten cards you swipe or arrow through, each with one chart (six have controls, all have hover readouts), a short caption with numbered, linked citations for outside facts, and a "show the numbers" table. It works on a phone and in light or dark mode.

```bash
open web/index.html                      # or: python -m http.server -d web 8000
```

The data comes from `web/data/*.js`, which the analyses above write, so rerunning a module updates its card. The page loads Observable Plot and d3 from jsDelivr (pinned versions). Everything else is local, so the folder can be served as-is, e.g. with GitHub Pages pointed at `web/`.

| # | Card | Data from |
| --- | --- | --- |
| 0 | Summary: the three questions, each expanding to its findings, with links to the cards behind them | text (total £ from `overpayment`) |
| 1 | Every turn-down event over time: accepted price and size; £ settled per phase | `overpayment` |
| 2 | One home's day: baseline vs actual, current vs 2022/23 rules (interactive) | `baseline_error` |
| 3 | National event study, launch winter / since Oct 2023 (interactive) | `event_study` |
| 4 | One home vs the portfolio: noise vs bias | `baseline_error` |
| 5 | Daily error vs temperature change, test year, for BL01, the 2022/23 in-day adjustment, BL01 × temperature and gradient boosting, with each one's MAE (interactive) | `better_baselines`, `dfs_conditions` |
| 6 | Reality check: claim as % of a real, randomised effect | `reality_check` |
| 7 | The settlement floor: true saving and foresight sliders (interactive) | `floor` |
| 8 | Market phase: £ paid under S1–S4, split into real delivery, baseline error, floor and selection; recommendations | `overpayment` |
| 9 | Electrification: one household's energy, gas and petrol vs heat pump and EV; UK uptake | figures in the page (sources in the caption) |
| 10 | Beyond DFS: smart time-of-use tariffs (Ofgem, Jan 2026), VPP scale, the limits of both | figures in the page (sources in the caption) |

The headline numbers from all of these are gathered on one page at the front of the report: `reports/report/key_results.tex`.

## AI Collaboration

This project utilises **Claude Code** as a coding assistant.

### Roles & Responsibilities
* **Human Data Scientist (Me):**
  * Problem definition.
  * Exploratory Data Analysis (EDA).
  * Auditing model predictions.
  * Git control - all commits done with a human in the loop.
* **Claude Code:**
  * Refactoring exploratory notebook code into modular `.py` scripts.
  * Generating unit testing suite (`pytest`).
  * Assisting with any other standard software engineering such as containerization or CI/CD setup.
