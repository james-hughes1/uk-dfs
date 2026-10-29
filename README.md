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
| `features.events` | DFS turn-down events, one row each, split into A1 (2022/23, in-day adjustment on) and A2 (from 27 Oct 2023) |
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

`web/` is a static site with no build step. It has ten cards you swipe or arrow through, each with one chart (six have controls, all have hover readouts), a short caption and a "show the numbers" table. It works on a phone and in light or dark mode.

```bash
open web/index.html                      # or: python -m http.server -d web 8000
```

The data comes from `web/data/*.js`, which the analyses above write, so rerunning a module updates its card. The page loads Observable Plot and d3 from jsDelivr (pinned versions). Everything else is local, so the folder can be served as-is, e.g. with GitHub Pages pointed at `web/`.

| # | Card | Data from |
| --- | --- | --- |
| 1 | £ settled for turn-down, by period | `overpayment` |
| 2 | One home's day: baseline vs actual, current vs 2022/23 rules (interactive) | `baseline_error` |
| 3 | National event study, A1 / A2 (interactive) | `event_study` |
| 4 | One home vs the portfolio: noise vs bias | `baseline_error` |
| 5 | Daily error vs temperature change (interactive) | `baseline_error`, `dfs_conditions` |
| 6 | Better baselines: bias by temperature change | `better_baselines` |
| 7 | Reality check: claim as % of a real, randomised effect | `reality_check` |
| 8 | The settlement floor: true saving and foresight sliders (interactive) | `floor` |
| 9 | Overpayment scenarios S1–S4 (interactive) | `overpayment` |
| 10 | Electrification: EV phantom delivery calculator, recommendations | arithmetic in the page |

The headline numbers from all of these are gathered on one page at the front of the report: `reports/report/key_results.tex`.

## To-do

Section numbers follow the report (`reports/report/report.tex`). For each analysis, the three stages are **explore** (notebook), **code** (move into `src/uk_dfs` with tests) and **write up** (report section). Uncertainty throughout: bootstrap over events for Part A, moving-block bootstrap over days (weeks for price events) for Part B.

### Part A: national check
- [ ] **A1. 2022/23 events** (difference-in-differences: 1.11× claim, CI −0.63 to 3.25)
  - [x] Code: demand/DFS/weather loaders out of `notebooks/_common.py` into `data/`; event study into `evaluation/`
  - [ ] Write up, including the comparison with Centre for Net Zero's ~87%
- [ ] **A2. Events since Oct 2023** (not verifiable: −0.01× claim, CI −3.51 to 2.81)
  - [x] Code: matched-day correction and same-day placebo
  - [ ] Write up
- [ ] **A3. How many events would it take?** (pilot zone regression: slope 0.90, SE 1.05)
  - [ ] Simulation: add known effects to non-event days, rerun A1's estimator, record the detection rate by effect size and number of events
  - [ ] Code and write up

### Part B: household baselines (Low Carbon London)
In three steps: measure baseline error with nobody responding, build a better baseline, then add the settlement rules and participant behaviour on top of it.

**Step 1: baseline error**
- [ ] **B1. Placebo accuracy**
  - [ ] Code: BL01 in `models/bl01.py`, unit tests in `tests/test_bl01.py`
  - [x] Fix the LCL half-hour offset (raw readings are end-labelled; `lcl.build()` relabels to the start)
  - [x] Code: placebo errors, per-meter and portfolio accuracy, block bootstrap (`evaluation/baseline_error.py`, `tests/test_baseline_error.py`)
  - [x] DFS-length windows (1–2 h, starts 16:00–19:00), scored per half-hour
  - [x] Block-bootstrap CIs
  - [x] Windows at each real DFS event's time and length (C1)
  - [ ] Write up
- [ ] **B2. When is it biased?**
  - [x] One regression of daily error on temperature change, temperature, day type and start time (block-bootstrap CIs; `baseline_error.bias_regression`)
  - [ ] Write up

**Step 2: a better baseline**
- [ ] **B3. Better baselines** (only inputs participants can't influence: no same-day usage before the event)
  - [x] Code: `models/baselines.py`, `evaluation/better_baselines.py`, `tests/test_better_baselines.py`
  - [x] Full seasonal years: train Mar 2012 – Feb 2013, test Mar 2013 – Feb 2014; home size from the training year only (was leaking)
  - [x] Score on per-meter error as well as portfolio bias (the floor acts on per-meter noise)
  - [x] Paired block-bootstrap CIs on the change in MAE against BL01
  - [x] Fix gradient boosting's bias (level-free corrections: +0.6%)
  - [x] Forecast-error sensitivity (archived forecasts don't reach 2012–14; adds SD 1.5 °C noise)
  - [ ] Write up

**Step 3: rules and behaviour**
- [ ] **B4. Reality check: a real, randomised response (ToU vs control)** (kept short: the trial isn't DFS)
  - [x] Code: first hour of each High event; true effect, BL01 claim, share of meters negative (`evaluation/reality_check.py`, `tests/test_reality_check.py`)
  - [ ] Write up
- [ ] **B5. Household opt-in** (reported over a range of ρ)
  - [x] Code: ρ sweep with per-home foresight, both BL01 variants, opt-in rate sensitivity, block-bootstrap CIs (`evaluation/opt_in.py`, `tests/test_opt_in.py`)
  - [x] Default opt-in share 80% of events (NESO 2022/23 saw ~83%, Octopus 61–70%); 25/50/95% as sensitivities
  - [ ] Write up
- [ ] **B6. Settlement floor**
  - [x] Code: share negative and floored claim by condition and start time, opt-in × true-saving grid, block-bootstrap CIs (`evaluation/floor.py`, `tests/test_floor.py`; ToU response from `reality_check`)
  - [x] Find the rule: per meter per settlement period (Guidance V11 Appendix 2 rule 7; V18 §3.6, Table 2)
  - [x] Rule is binding: Procurement Rules v3/v5 "DFS Settlement Volume"; also Guidance V6 (2022/23)
  - [ ] Confirm with NESO or a provider that settlement files follow it in practice (NESO collects negatives since 2026; ask for the share)
  - [x] Share of manual vs auto opt-in: >99% manual in 2023/24, auto uptake "low" in 2026 (no exact recent figure)
  - [x] Published share negative: 40% of opted-in meters in 2022/23 (NESO smart meter evaluation); CrowdFlex RCT clipping inflation 8.2× / 1.48×
  - [ ] Write up
- [ ] **B7. Alternative rules** (settled against the Step 2 baseline)
  - [ ] One or two rules, e.g. netting negatives across a unit's meters; judged on placebo claims ≈ 0 and ToU claims ≈ true effect
  - [ ] Code and write up

### Part C: what it means for DFS
- [ ] **C1. Transfer to DFS conditions**
  - [x] Describe every DFS turn-down event: start, length, day type, season, GB temperature, temperature change vs its own BL01 baseline days, rules regime (turn-up out of scope)
  - [x] Placebo windows on the LCL homes at each event's clock time and length
  - [x] Post-stratify: match each event to LCL days in its cell (temperature-change band × day type × season; coarsens where thin), for each rules regime (replaces B5's stylised day pools)
  - [x] Code: `evaluation/dfs_conditions.py`, `tests/test_dfs_conditions.py`; England & Wales bank holidays to 2026 in `models/bl01.py`; `temperature_change` accepts 5–9 working baseline days, as BL01 does
  - [ ] Refresh GB weather past 30 Sep 2026 (one October event has no temperature)
  - [ ] Opt-in (ρ) and the floor on DFS conditions: rerun B5/B6's opt-in at each event's window, then post-stratify as above, so C2's waterfall layers share one footing (A2's median event is 3 h, not B5's 1 h at 17:00)
  - [ ] Write up
- [ ] **C2. Overpayment scenarios**
  - [x] Four labelled scenarios on settled cost (`evaluation/overpayment.py`, `tests/test_overpayment.py`)
  - [x] Waterfall-style chart: true saving, baseline error, floor, opt-in selection per 100 MWh settled (`reports/figures/overpayment.png`); floor and selection split order-free (Shapley), since foresight shrinks the floor
  - [x] Cross-check against Part A, Centre for Net Zero's ~13%, NESO's 2022/23 evaluation and CrowdFlex
  - [x] Write up (first draft)
- [ ] **C3. Who bears it** (one paragraph: BSUoS on final demand → bill payers; cite the charging rules)
- [ ] **C4. DFS among NESO's other tools** (first draft: scale, break-even real share vs NESO's claimed saving and BM offer prices, reliability, learning, explicit vs implicit flex)
  - [ ] Cite the Elexon MHHS timeline; check BM comparison against 2024/25 prices
- [ ] **C5. Electrification** (first draft: national trends, household kWh, heat pump weather bias and EV floor back-of-envelope)
  - [ ] Read NESO EMAC Sept 2026 in full; link the DESNZ Q2 2026 smart meter release
  - [ ] Optional: test the EV/heat pump arithmetic on real electrified-home data (e.g. Electrification of Heat, SERL)

### Further work (out of scope for now)
- Hierarchical Bayesian baseline
- Calibrating ρ from how predictable households' evening use is
- A mix of always-join and occasional opt-in households (34% of NESO's 2022/23 survey said they always opt in)
- A fitted bias model with Monte Carlo uncertainty and a Shapley split across all causes
- Price response and value for money against the Balancing Mechanism
- Small dashboard of results by event

### Literature review
- [ ] Find and confirm sources (section 2 of the report)
- [ ] Read in full: Centre for Net Zero, Wijaya et al. 2014, KEMA/PJM 2011, Mohajeryami et al. 2016, the LCL trial reports
- [ ] Fix TBD references: Borenstein original source and date, authors of arXiv 1605.08078, KEMA link
- [ ] Search for any academic work on DFS since 2023 and Elexon's P376 consultation evidence
- [ ] Confirm the "what this report adds" claim once read

### Report and write-up
- [ ] Draft structure (question, data, method, result, limitations for each analysis)
- [ ] Embed the 3–5 key charts (currently `[Figure: …]` placeholders)
- [ ] Background section: how DFS pays, BL01, rule timeline
- [ ] Recommendations and overall limitations
- [ ] Finalise at the end
- [ ] README rewrite that leads with the findings

### Engineering
- [ ] Move remaining notebook logic into `features/`, `evaluation/`, `reporting/`
- [ ] Tests for loaders and evaluation code
- [ ] Docker image
- [x] Add `reports/` to the Layout above
- [ ] Regenerate all charts from a clean checkout to check reproducibility
- [ ] At the end: run all notebooks top to bottom, regenerate every chart and output, and commit them in one go

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
