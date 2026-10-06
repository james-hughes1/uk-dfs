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

## To-do

Section numbers follow the report (`reports/report/report.tex`). For each analysis, the three stages are **explore** (notebook), **code** (move into `src/uk_dfs` with tests) and **write up** (report section).

### Part A: national check
- [ ] **A1. 2022/23 events** (step test 45%, curve fit 71% of claim)
  - [ ] Explore (notebook 02, charts 11–15)
  - [ ] Code: demand/DFS/weather loaders out of `notebooks/_common.py` into `data/`; event study into `evaluation/`
  - [ ] Write up, including the comparison with Centre for Net Zero's ~87%
- [ ] **A2. Events since Oct 2023** (not verifiable: interconnector confound)
  - [ ] Explore (chart 15b)
  - [ ] Code: matched-day correction and same-day placebo
  - [ ] Write up
- [ ] **A3. How many events would it take?** (regional slope 0.90, SE 1.05)
  - [ ] Explore: GSP → DFS zone regression
  - [ ] Formal simulation-based power analysis
  - [ ] Code and write up

### Part B: household baselines (Low Carbon London)
- [ ] **B1. Placebo accuracy**
  - [ ] Explore (notebook 04, charts `bl_01`, `bl_02`)
  - [ ] Code: BL01 in `models/bl01.py`, unit tests in `tests/test_bl01.py`
  - [ ] Extend beyond the single 17:00–18:00 window (2-hour, DFS-style windows)
  - [ ] Write up
- [ ] **B2. When is it biased?**
  - [ ] Explore (charts `bl_03`, `bl_04`)
  - [ ] One regression of error on all conditions together
  - [ ] Code and write up
- [ ] **B3. Known true effect (ToU vs control)**
  - [ ] Explore (chart `bl_05`)
  - [ ] Event-level CIs that allow for correlated events
  - [ ] Code and write up
- [ ] **B4. Selection (NESO days, household opt-in)**
  - [ ] Explore (chart `bl_06`)
  - [ ] Calibrate ρ (how predictable households' own evening use is)
  - [ ] Replace stylised day pools with NESO's real event-calling pattern (sunset, wind, import drops)
  - [ ] Code and write up
- [ ] **B5. Settlement floor**
  - [ ] Explore (+25% phantom delivery, assuming a per-meter floor)
  - [ ] **Confirm how settlement applies the floor** (per meter per half-hour?) with NESO or a provider
  - [ ] Find the share of manual vs auto opt-in homes
  - [ ] Write up
- [ ] **B6. Better baselines**
  - [ ] Explore (chart `bl_07`: temperature scaling, gradient boosting)
  - [ ] Switch to historical weather *forecasts* (Open-Meteo)
  - [ ] Fix gradient boosting's +1.6% bias
  - [ ] Hierarchical Bayesian baseline
  - [ ] Code and write up

### Optional extensions
- [ ] **C. Price and value:** supply curve as prices fell from £3,000/MWh; DFS vs Balancing Mechanism cost
- [ ] **£ scenario:** apply Part B bias ranges to settled volumes, as labelled scenarios
- [ ] Small dashboard of results by event

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
- [ ] Summary, written last
- [ ] README rewrite that leads with the findings

### Engineering
- [ ] Move remaining notebook logic into `features/`, `evaluation/`, `reporting/`
- [ ] Tests for loaders and evaluation code
- [ ] Docker image
- [ ] Add `reports/` to the Layout above
- [ ] Regenerate all charts from a clean checkout to check reproducibility

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
