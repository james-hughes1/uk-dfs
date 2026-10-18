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

Section numbers follow the report (`reports/report/report.tex`). For each analysis, the three stages are **explore** (notebook), **code** (move into `src/uk_dfs` with tests) and **write up** (report section). Uncertainty throughout: bootstrap over events for Part A, moving-block bootstrap over days (weeks for price events) for Part B.

### Part A: national check
- [ ] **A1. 2022/23 events** (step test 45%, curve fit 71% of claim)
  - [x] Explore (notebook 02, charts 11–15)
  - [x] Code: demand/DFS/weather loaders out of `notebooks/_common.py` into `data/`; event study into `evaluation/`
  - [ ] Write up, including the comparison with Centre for Net Zero's ~87%
- [ ] **A2. Events since Oct 2023** (not verifiable: interconnector confound)
  - [x] Explore (chart 15b)
  - [x] Code: matched-day correction and same-day placebo
  - [ ] Write up
- [ ] **A3. How many events would it take?** (pilot zone regression: slope 0.90, SE 1.05)
  - [ ] Simulation: add known effects to non-event days, rerun A1's estimator, record the detection rate by effect size and number of events
  - [ ] Code and write up

### Part B: household baselines (Low Carbon London)
In three steps: measure baseline error with nobody responding, build a better baseline, then add the settlement rules and participant behaviour on top of it. Notebook 04's section labels predate this order.

**Step 1: baseline error**
- [ ] **B1. Placebo accuracy**
  - [ ] Explore (notebook 04, charts `bl_01`, `bl_02`)
  - [ ] Code: BL01 in `models/bl01.py`, unit tests in `tests/test_bl01.py`
  - [x] Fix the LCL half-hour offset (raw readings are end-labelled; `lcl.build()` relabels to the start)
  - [x] Code: placebo errors, per-meter and portfolio accuracy, block bootstrap (`evaluation/baseline_error.py`, `tests/test_baseline_error.py`)
  - [x] DFS-length windows (1–2 h, starts 16:00–19:00), scored per half-hour
  - [x] Block-bootstrap CIs
  - [ ] Windows at each real DFS event's time and length (C1)
  - [ ] Write up
- [ ] **B2. When is it biased?**
  - [ ] Explore (charts `bl_03`, `bl_04`)
  - [x] One regression of daily error on temperature change, temperature, day type and start time (block-bootstrap CIs; `baseline_error.bias_regression`)
  - [ ] Write up

**Step 2: a better baseline**
- [ ] **B3. Better baselines** (only inputs participants can't influence: no same-day usage before the event)
  - [ ] Explore (chart `bl_07`: temperature scaling, gradient boosting)
  - [ ] Score on per-meter error as well as portfolio bias (the floor acts on per-meter noise)
  - [ ] Block-bootstrap CIs on the difference in MAE against BL01
  - [ ] Switch to historical weather *forecasts* (Open-Meteo)
  - [ ] Fix gradient boosting's +1.2% bias
  - [ ] Code and write up

**Step 3: rules and behaviour**
- [ ] **B4. The in-day adjustment, against a known true effect (ToU vs control)**
  - [ ] Explore (chart `bl_05`)
  - [ ] Bootstrap by week (nearby events are correlated)
  - [ ] Code and write up
- [ ] **B5. Household opt-in** (reported over a range of ρ)
  - [ ] Explore (chart `bl_06`, right panel)
  - [ ] Code and write up
- [ ] **B6. Settlement floor**
  - [ ] Explore (+24% phantom delivery per hour, +27% per half-hour, assuming a per-meter floor)
  - [ ] Explore how opt-in and the floor interact via the share of negative meters (notebook 04 B6b, chart `bl_06b`: ~40% negative with no response)
  - [x] Find the rule: per meter per settlement period (Guidance V11 Appendix 2 rule 7; V18 §3.6, Table 2)
  - [ ] Confirm with NESO or a provider that settlement follows the guidance in practice
  - [ ] Find the share of manual vs auto opt-in homes
  - [ ] Look for a published share of DFS meters with negative delivery
  - [ ] Write up
- [ ] **B7. Alternative rules** (settled against the Step 2 baseline)
  - [ ] One or two rules, e.g. netting negatives across a unit's meters; judged on placebo claims ≈ 0 and ToU claims ≈ true effect
  - [ ] Code and write up

### Part C: what it means for DFS
- [ ] **C1. Transfer to DFS conditions**
  - [ ] Describe every live DFS event: start, length, day type, GB temperature, temperature change vs its own BL01 baseline days, rules regime
  - [ ] Placebo windows on the LCL homes at each event's clock time and length
  - [ ] Post-stratify: weight LCL cells (temperature-change band × day type × start time) by their share of DFS events, for each rules regime (replaces B5's stylised day pools)
  - [ ] Code and write up
- [ ] **C2. Overpayment scenarios**
  - [ ] Three or four labelled scenarios on settled volumes × prices, capped at the volume bid
  - [ ] Waterfall chart: baseline error, then the floor, then participant behaviour (stated order)
  - [ ] Cross-check against Part A and Centre for Net Zero's ~13%
  - [ ] Write up
- [ ] **C3. Who bears it** (one paragraph: BSUoS on final demand → bill payers; cite the charging rules)

### Further work (out of scope for now)
- Hierarchical Bayesian baseline
- Calibrating ρ from how predictable households' evening use is
- A fitted bias model with Monte Carlo uncertainty and a Shapley split by cause
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
- [ ] Summary, written last
- [ ] README rewrite that leads with the findings

### Engineering
- [ ] Move remaining notebook logic into `features/`, `evaluation/`, `reporting/`
- [ ] Tests for loaders and evaluation code
- [ ] Docker image
- [ ] Add `reports/` to the Layout above
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
