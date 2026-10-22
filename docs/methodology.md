# Methodology

Every rate, year and formula comes from the rule files in `open_bps/jurisdictions/`. Each rule file cites the
regulator's own document and records the date it was checked. When a city changes its rules, a new rule
file version is added; outputs carry the `rule_version` they used.

The policy registry (`open_bps/policy.py`) validates every file when it is loaded:
- every number names a declared source;
- compliance periods are ordered and do not overlap;
- every limit table covers every period;
- units fit the metric (a GHG standard needs factors per kWh or kBtu, and a per-ton penalty).

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

## New York City: Local Law 97

Sources:
- **1 RCNY §103-14 (DOB rule):** limits for 60 ESPM property types in each period, and the 2030-2034
  coefficients.
- **DOB's "Calculating building emissions" (June 2024):** quotes Admin Code §28-320.3.1.1 for the 2024-2029
  coefficients.
- **DOB's Article 320 Info Guide (rev. 06/30/2025).**

The method:
- **Emissions** = Σ fuel use × coefficient. Electricity is in kWh; gas, steam and oils are in kBtu.
- **Limit** = Σ floor area of each property type × its limit (Equation 103-14.1). Every use counts.
- **Penalty** = (emissions − limit) × $268 per ton, every year (§28-320.6).

Checks against DOB's own examples:
- **Slide 25 example:** 287.00 t against a 302.41 t limit. Reproduced to the cent.
- **Article 320 guide example:** 225.6 t against 207 t. The guide rounds the retail limit (45.48 t) to 45 t.
  open-bps keeps the exact figure, so its penalty is $4,853.91 rather than the guide's $4,984.80. The test
  checks both.

How property types are handled:
- **Not assignable:** "Other" and "Mixed Use" may not be assigned (§103-14(c)(2)), so such a building is not
  priced.
- **Missing from the rule:** where an ESPM type has no limit row, open-bps uses DOB's suggested equivalent type
  (Article 320 guide pp.73-75), marked `suggested`.
- **Renamed by ESPM:** current ESPM names (e.g. "Vehicle Dealership" for "Automobile Dealership") are marked
  `rename`.

Not modelled:
- **The CY2024-2025 occupancy-group election.** It is not in public data, so the true 2024-2025 limit can be
  higher.
- **Deductions:** RECs, offsets, beneficial electrification, and solar and storage.
- **Time-of-use electricity.**
- **#5/#6 oil.** The rule has no coefficient for it (the owner proposes one), so it is flagged.

**2035 onwards:** DOB's projected electricity and steam coefficients are guidance, not law, so every figure
that uses them is flagged Estimated.

**Public data:** the LL84 disclosure (an ESPM export). Rows above 100 kgCO2e/sq ft (about four times the highest
limit, and above the 99.9th percentile of the CY2024 data) are flagged `implausible_use`, not priced.

## Boston: BERDO 2.0

Sources:
- **City of Boston Code §7-2.2:** Table 1 standards in kgCO2e/sq ft for 2025-2050, and the $234/t
  Alternative Compliance Payment (ACP).
- **The 2026 BERDO Regulations.**
- **Policies and Procedures v5 (adopted 2026-09-14):**
  - §5, emissions;
  - §6, the blended standard;
  - Appendix A, ESPM type to Building Use;
  - Appendix B, projected grid factors.
- **The city's Emissions Factors List (June 2024).**

How emissions are calculated:
- **Electricity:** kWh × (1 − Massachusetts RPS Class I share) × grid factor, less any renewable kWh the city
  records. The RPS share is 24% in 2024, then +3 points a year to 2029 and +1 a year after that (M.G.L. c.25A
  §11F). The grid factor is the projected factor, which by regulation caps the annual one.
- **Fuels:** the city's list (natural gas 53.11 kg/MMBtu, and so on).
- **District steam:** the factor the city applied to that building where it publishes one; otherwise the 66.40
  default.

Which standard applies:
- **Default:** the standard of the building's largest primary use, applied to its whole floor area.
- **Blended (opt-in):** uses with at least 10% of the floor area are primary, and the rest counts with the
  largest. This is available in `blend.limit(..., blend=True)` and `--blend`.

**Exposure** is the ACP that would cover the excess. A building that neither complies nor pays faces daily fines
of $1,000 or $300 instead.

**Validation** against the city's 2026 disclosure (2025 data):
- verdicts: 901 of 901;
- emissions: 1,755 of 1,756;
- default standard: 1,101 of 1,104.

**Not modelled:** individual compliance schedules, hardship plans, building portfolios, campus district
energy, and EV and backup-generation exemptions.

## Mixed-use buildings

`open_bps/engine/blend.py` applies each policy's rule:
- **NYC:** the floor-area-weighted sum.
- **Boston:** the largest primary use by default, or the opt-in blend.

A use the policy cannot map is never given a default:
- under NYC's rule it stops the calculation;
- under Boston's, a non-primary use (under 10%) is folded into the largest use, as the regulation does.

The engine returns the space-by-space audit trail, and the workbook's Spaces sheet shows it.

## Retrofit underwriting

`open_bps/underwriting/capital_stack.py`, for GHG standards. Every input is the user's assumption.

How a retrofit is priced:
- **The retrofit:** it cuts every fuel's use by the same share and is in service at the start of the first year.
  Capex is paid at t = 0.
- **The flows:** avoided penalty = baseline penalty − post-retrofit penalty, with both computed by the same
  engine. Unlevered flow = avoided penalty + energy cost savings + the §179D cash value (in year 1).
- **Financing:** C-PACE is a level annual assessment (PMT); debt is loan-to-cost at a rate and term. A balance
  still owed at the end of the hold is repaid then. In practice a C-PACE assessment can usually transfer on
  sale.
- **Results:** NPV uses Excel's convention (the first flow is discounted one year). IRR is reported unlevered,
  and levered when equity is put in. Payback is the first year in which cumulative unlevered flow covers capex.

**Grid scenario:** the start year's electricity factor declining at a stated rate. It is labelled a scenario, not
law, and has no effect on energy (EUI) standards.

**Section 179D:**
- **Amounts:** for tax years 2024-2026, from the IRS (Form 7205 instructions; Rev. Proc. 2025-32 §4.25). That is
  a base or prevailing-wage rate at 25% savings, plus a per-point amount up to a cap.
- **Savings measure:** the percentage is rounded to two decimals, as on the Form 7205 worksheet. The retrofit's
  EUI reduction stands in for the certified percentage (the retrofit-property route), which needs a qualified
  professional's certification.
- **Limit:** the deduction cannot exceed the retrofit's cost.
- **Cash value:** the deduction × the stated tax rate.
- **Termination:** the One Big Beautiful Bill Act (§70507) ends §179D for property whose construction begins
  after 2026-06-30. Without a start date on or before it, the deduction is zero.
- **Later tax years:** the 2026 amounts are used, and labelled as such.

**The workbook:** the Underwriting sheet rebuilds every figure in SUM, NPV, IRR, IF, PMT and FV over the Exposure
sheet. The Checks sheet reconciles it to the engine to the cent, and IRR to 1e-6.

## Exposure, not a forecast

All exposure figures hold each building's latest reported energy use constant: what missing the target
would cost if nothing changed. They do not estimate retrofit costs. They are not predictions of what a
building will pay.

## Data refresh and quality gate

A monthly GitHub Action downloads fresh data, scores it and publishes the results with the raw snapshot.
It publishes nothing if:
- the DC verdict match rate falls below 97%;
- Boston's emissions or verdict match rate falls below 97%; or
- fewer than half of Denver's or NYC's buildings score.

Any of these would suggest the upstream data changed shape.
