# Project Brief: Measuring Britain's Demand Flexibility Service

Sep 29, 2026 · @James

## Summary

We will test whether the flexibility NESO pays for through its Demand Flexibility Service (DFS) actually shows up in the data. The project has two parts: a national check (does claimed delivery appear as a dip in GB demand?) and a household check (how biased is the official BL01 baseline, and when?). The output is a public, company-neutral project: a tested Python repo plus a short write-up that leads with the findings.

## Background

DFS pays households and businesses, through suppliers and aggregators ("providers"), to shift electricity use when the grid needs it. Since April 2026 it covers demand turn-up as well as turn-down, and from 7 October 2026 NESO plans to use it for selected Scottish constraints.

**How payment works**

1. NESO publishes a requirement, e.g. 200 MW of reduction from 5–6pm tomorrow.
2. Providers bid a volume (MW) and a price (£/MWh). NESO accepts the cheapest bids until the requirement is met.
3. Settlement is pay-as-bid: each provider gets its own bid price × volume delivered, capped at the volume bid.
4. Providers pass part of the payment on to their customers.

**How delivery is measured: the BL01 baseline**

Delivery = baseline − actual metered use, per household meter, summed per provider. Providers calculate the baseline with a fixed industry rule (Elexon P376, method BL01):

1. Take the 10 most recent eligible working days (4 for weekends and holidays) within the last 60 days, excluding previous DFS event days.
2. Average the household's usage for each half-hour across those days.
3. For domestic units, when enabled: shift the profile by the average gap between actual and profile in the hours before the event (the in-day adjustment). This step has been switched on and off between service versions.

The baseline is not linked to suppliers' energy contracts. Suppliers forecast and buy energy separately; the DFS baseline only decides who gets paid.

**Why it matters:** if BL01 overstates normal usage, NESO pays for flexibility that never happened. Known risks include cold days (recent days are a poor guide) and predictable event timing (customers can raise usage before an event, inflating the in-day adjustment).

## Research questions

1. **National impact:** Does the delivery providers claim during DFS events show up as a measurable drop in GB national demand? If not, how many events would be needed to detect it?
2. **Baseline bias:** How accurate is BL01 at household level, and when is it biased (cold days, weekends, with vs without the in-day adjustment)?
3. **Better baselines:** Do weather-aware ML or Bayesian baselines cut that error, and by how much?
4. **Price and value (optional):** How did offered volume respond as accepted prices fell from the early £3,000/MWh guaranteed price? Was DFS cheaper than the Balancing Mechanism actions it replaced?

## Method

&#91;embedded content: method · two checks, one set of findings\]

The national check tests total claimed delivery; the household check explains where any gap comes from.

- **National model:** gradient-boosted or GAM demand model on weather forecasts, embedded solar and calendar, trained on non-event periods. Pooled event-study regression across all DFS windows, bootstrap confidence intervals, and a simulation-based power analysis.
- **Household baselines:** implement BL01 exactly as specified, then regression, gradient-boosted and hierarchical Bayesian alternatives. Score each on non-event days (true saving = 0) and against the trial's control group: mean bias, MAE, and error by temperature and day type.

## Data sources

| Source | What we use | For |
| --- | --- | --- |
| [NESO data portal](https://www.neso.energy/data-portal) | DFS events: requirements, accepted bids, prices, delivered volumes by provider; national demand and NESO day-ahead demand forecasts | National check, price analysis |
| [Elexon Insights](https://bmrs.elexon.co.uk/) | Half-hourly demand, system prices, Balancing Mechanism actions | National check, value for money |
| [Sheffield Solar PV\_Live](https://www.solar.sheffield.ac.uk/pvlive/) | Embedded solar estimates | National demand model |
| [Open-Meteo](https://open-meteo.com/) | Historical weather and historical weather forecasts | Both models (train on forecasts to avoid leakage) |
| Low Carbon London (London Datastore) | \~5,500 households, half-hourly smart meter data, randomised time-of-use trial with a control group | Household BL01 bias test |
| [Elexon P376 / NESO DFS service terms](https://www.neso.energy/industry-information/balancing-services/demand-flexibility-service-dfs) | Exact BL01 rules | Implementing the official baseline |

Open question: check whether Low Carbon London price events line up with typical DFS timing; if not, treat it as a test of the baseline method rather than of DFS itself.

## Deliverables and engineering standards

**Deliverables**

- [ ] Public GitHub repo: data loaders, BL01 implementation, models, analysis
- [ ] Write-up (blog post or README) that leads with the findings and their commercial meaning
- [ ] 3–5 key charts, e.g. claimed vs detected national delivery, BL01 error by temperature
- [ ] Optional: small dashboard showing results by event

**Standards**

- Python package structure, not notebooks only; notebooks for exploration and figures
- Unit tests, especially for BL01 (test against a worked example from the service terms)
- Reproducible environment (uv or poetry) and Docker
- Raw data cached locally; loaders are idempotent and re-runnable
- Clear separation: data → features → models → evaluation → reporting

## Risks, caveats and scope

- **Signal is small.** DFS events deliver hundreds of MW against tens of GW of national demand, and forecast errors are a similar size. Pool events and report a power analysis; "not detectable" is still a valid finding.
- **Rules change.** BL01's in-day adjustment has been switched on and off between service versions. Pin each event to the rules in force at the time.
- **Household data is older.** Low Carbon London predates DFS, so it tests the baseline method, not DFS participants.
- **Company-neutral.** No supplier or aggregator is singled out; provider-level data is used only in aggregate.
- **Out of scope:** supplier wholesale positions and imbalance, local (DNO) flexibility markets, the Scottish constraint events (possible follow-up).

## Suggested phasing

Each phase ends with something shareable, so the project is useful even if it stops early.

1. **Foundations:** repo, environment, data loaders for NESO DFS, Elexon demand, solar and weather. Output: a clean dataset of every DFS event with national context.
2. **National model:** counterfactual demand model, pooled event analysis, power analysis. Output: claimed vs detected delivery chart and a first write-up.
3. **Household baselines:** implement and test BL01 on Low Carbon London, then ML and Bayesian alternatives. Output: bias by condition, error reduction.
4. **Extensions (optional):** price and supply-curve analysis, value for money vs Balancing Mechanism.
5. **Polish:** tests, Docker, README, final write-up and charts.

## Sources

- [NESO: Demand Flexibility Service documents](https://www.neso.energy/industry-information/balancing-services/demand-flexibility-service-dfs)
- [NESO: evolved DFS announcement, March 2026](https://www.neso.energy/neso-announces-shakeup-new-look-demand-flexibility-service)
- [NESO: DFS participation guidance (BL01 worked example)](https://www.neso.energy/document/286981/download)
- [Elexon: P376 baselining methodology](https://www.elexon.co.uk/bsc/documents/groups/panel/2021-meeting/312-march/312-04-p376-utilising-a-baselining-methodology-to-set-physical-notifications-for-settlement-of-applicable-balancing-services/)
- [Carbon Brief: DFS 2022/23 Q&A](https://www.carbonbrief.org/qa-how-great-britains-demand-flexibility-service-is-cutting-costs-and-co2-emissions)
