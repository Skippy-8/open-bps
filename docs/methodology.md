# Methodology

Every rate, year and formula comes from the rule files in `open_bps/jurisdictions/`. Each rule file cites the
regulator's own document and records the date it was checked. When a city changes its rules, a new rule
file version is added; outputs carry the `rule_version` they used.

## Washington, DC: BEPS Compliance Cycle 1

Source: DOEE, *BEPS Compliance and Enforcement Guidebook, Compliance Cycle 1*, version 1.2 (published
2026-08-11). It is the plain-language explanation of the Clean Energy DC Omnibus Act (2018) and 20 DCMR
Chapter 35.

**Standards and verdicts.** DOEE set a standard per property type on 2021-01-01. A building meets it if its
metric in the metric year (2019 for nearly all buildings) is at least the standard, for an ENERGY STAR
score, or at most the standard, for an EUI metric. DOEE publishes the standard, the building's metric and
the verdict, and open-bps reproduces the verdict.
- The rule agrees with DOEE for 99.5% of buildings.
- The disagreements sit at the boundary (for example, a metric of 185.5 against a standard of 185 marked
  "Meets") or reflect later corrections. open-bps reports them and does not adjust the rule to fit them.

**Frozen baselines.** DOEE fixed each building's 2019 metric when it set the standards. Rebuilding that
metric from today's benchmarking records matches for 94% of buildings; the rest were revised afterwards.
open-bps always uses DOEE's frozen value for the verdict.

**Cycle.** Compliance Cycle 1 runs to 2026-12-31, with end-of-cycle reporting due 2027-05-03. Buildings
that missed the standard follow an approved pathway.

**Alternative compliance payment (Guidebook Chapter 7, Table 21):**
- maximum = min($10 × gross floor area, $7.5M); campuses have a single $7.5M maximum;
- Performance Pathway: maximum × (1 − min(1, site EUI reduction achieved / 20%)), comparing the
  2018–2019 average with 2026;
- Standard Target Pathway: maximum × distance remaining / distance of a same-type building 20% less
  efficient than the standard;
- Prescriptive Pathway: maximum × (1 − points earned / points needed);
- if required information is not submitted: the full maximum.

**Estimates and their limits:**
- **Performance Pathway.** DOEE evaluates it on Adjusted Site EUI, which it publishes only on the owner
  portal. open-bps uses public site EUI as a proxy (the 2018–2019 average against the latest reported
  year) and assumes the latest year holds to 2026.
- **Standard Target Pathway.** It is estimated only for EUI-metric buildings, where "20% less efficient"
  means 20% of the standard. For score-metric buildings DOEE converts with its own models (Guidebook
  Appendix E), so open-bps leaves the field blank.
- **Not modelled:** delays, exemptions and alternative compliance pathway agreements.

## Denver: Energize Denver, buildings 25,000 sq ft and larger

Source: City and County of Denver (CASR), *Energize Denver Technical Guidance, Buildings 25,000 sq ft or
larger*, v3 (April 2025).

**Metric.** Weather-normalized site EUI, less any renewable credit, transportation energy and
electrification incentive (TG v3 s. 9.4). The credits are not public, so the public-data EUI is an upper
bound, and so are the penalties.

**Targets.** Denver publishes each building's baseline, first interim, second interim and adjusted final
target EUI.

**Schedules (TG v3 s. 1.3 and 4).**
- **Extended:** the 2024/2025/2026 interim target is due in 2028, the 2027 interim target is dropped, and
  the final target moves from 2030 to 2032.
- **Original:** 2025, 2027 and 2030.
- **Which one applies is not public.** Owners opt in when they submit their 2025 benchmarking report, so
  open-bps computes both.

**Penalty (TG v3 s. 9.4, 10.2.1.2.1, Table 17).** kBtu not achieved = max(0, (EUI − target) × gross floor
area); penalty = kBtu not achieved × rate. The rate depends on the number of target-year measurement
periods:

| Measurement periods | Rate |
|---|---|
| Three (original schedule) | $0.15/kBtu |
| Two (extended schedule) | $0.23/kBtu |
| One (other timeline extension) | $0.35/kBtu |

The penalty then recurs every year the final target is missed.
- A building with no data-verified report owes $5 per sq ft.
- Maintenance penalties ($0.05 or $0.15/kBtu) apply after a final target has been met.
- **Enforcement start:** "No penalties will be levied until late 2029" (TG v3 s. 1.3.4).
- **Rates were halved in early 2025.** Several third-party pages still quote the earlier rates and years;
  the rule file follows the April 2025 guidance.

**Not modelled:** custom targets, timeline extensions beyond 2032, compliance holds, and the
manufacturing, agricultural and industrial (MAI) option. MAI buildings are flagged
`mai_production_targets` and not scored.

## Exposure, not a forecast

All exposure figures hold each building's latest reported energy use constant: what missing the target
would cost if nothing changed. They do not estimate retrofit costs. They are not predictions of what a
building will pay.

## Data refresh and quality gate

A monthly GitHub Action downloads fresh data, scores it and publishes the results with the raw snapshot.
It publishes nothing if:
- the DC verdict match rate falls below 97%, or
- fewer than half of Denver's buildings score.

Either would suggest the upstream data changed shape.
