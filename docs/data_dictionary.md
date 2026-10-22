# Data dictionary

One row per building. `tests/test_docs.py` fails if a column here is missing from the scored tables, or the
other way round. Units: square feet (sq ft), kBtu, kBtu/sq ft/year, US dollars.

## Every city

| Column | Meaning |
|---|---|
| jurisdiction | `dc`, `denver`, `nyc` or `boston` |
| building_id | The city's building identifier (DC and NYC: ENERGY STAR Portfolio Manager property ID; Denver: Energize Denver Building ID; Boston: BERDO ID) |
| property_name, address, postal_code | As published by the city |
| property_type | Primary property type (DC: Portfolio Manager EPA-calculated; Denver: Master Property Type) |
| gfa | Gross floor area, sq ft (DC: reported GFA, else tax-record floor area; Denver: Master Sq Ft) |
| year_built | As published (DC and Denver) |
| screen_status | `scored`, or why no estimate is given (see below) |
| rule_version | The rule file the estimates used |

`screen_status` values:
- **DC:**
  - `scored`
  - `no_metric`: no standard or metric in DOEE's disclosure
  - `not_subject`: DOEE says not subject to BEPS
  - `no_floor_area`
- **Denver:**
  - `scored`
  - `no_data`: missing EUI or targets
  - `no_floor_area`
  - `below_threshold`: under 25,000 sq ft
  - `exempt`
  - `mai_production_targets`: manufacturing, agricultural or industrial buildings with production-based targets, not EUI targets

## DC (BEPS Compliance Cycle 1)

| Column | Meaning |
|---|---|
| ward, latitude, longitude, ubid | As published by DOEE |
| beps_property_group | DOEE's BEPS property group |
| metric_type | ENERGYSTARSCORE, or an EUI metric (weather-normalized source EUI, source EUI, blended custom EUI) |
| standard | The BEPS standard for the property type (score points or EUI) |
| metric | The building's frozen BEPS metric from DOEE's disclosure |
| metric_year | The year of that metric (2019 for nearly all) |
| official_meets_beps | DOEE's published verdict |
| official_eui_distance | DOEE's published distance from the standard (fraction; negative = worse than the standard) |
| pathway | DOEE's approved compliance pathway |
| site_eui_baseline | Average public site EUI for 2018–2019 (proxy for DOEE's Adjusted Site EUI baseline) |
| latest_year, site_eui_latest | Latest year with a reported site EUI, and that value |
| metric_latest | The building's BEPS metric in the latest reported year |
| our_meets_standard | The verdict from the encoded rule (score ≥ standard; EUI ≤ standard) |
| verdict_matches_official | Whether that equals DOEE's verdict |
| eui_distance | (standard − metric) / metric for EUI metrics |
| max_payment | min($10 × gfa, $7.5M) |
| site_eui_reduction_est | 1 − site_eui_latest / site_eui_baseline (Estimated) |
| payment_est_performance | Performance Pathway buildings: max_payment × (1 − min(1, reduction / 20%)) (Estimated) |
| payment_est_standard_target | Standard Target Pathway, EUI-metric buildings: max_payment × min(1, (metric_latest − standard) / (20% × standard)) (Estimated) |

## Denver (Energize Denver, 25,000 sq ft and up)

| Column | Meaning |
|---|---|
| data_year | Reporting year as labelled in the Master Dataset |
| compliance_status | Whether the benchmarking report was filed (`in compliance`, `not submitted`, `pending revisions`, `exempt`). It is not a performance verdict. |
| approved_mai | Approved for production-based (MAI) targets |
| energy_star_score, site_eui, ghg_tco2e | As published |
| eui | Weather-normalized site EUI: the metric Denver evaluates |
| baseline_eui, target_first_interim, target_second_interim, target_final | Denver's published per-building targets (target_final is the adjusted final target) |
| reduction_needed_final | max(0, 1 − target_final / eui) |
| extended_2028_kbtu_over, extended_2032_kbtu_over | max(0, (eui − target) × gfa), on the extended schedule: first interim target in 2028, final target in 2032 |
| extended_2028_penalty, extended_2032_penalty | kBtu over × $0.23 (two measurement periods) |
| original_2025_kbtu_over, original_2027_kbtu_over, original_2030_kbtu_over | kBtu over target on the original schedule |
| original_2025_penalty, original_2027_penalty, original_2030_penalty | kBtu over × $0.15 (three measurement periods); no penalties are levied before late 2029 |
| extended_cumulative_penalty_through_2035, original_cumulative_penalty_through_2035 | Target-year penalties plus the final-target penalty for each later year through 2035 |
| no_report_penalty | gfa × $5, for buildings whose latest report is `not submitted` (owed if still missing in a target year) |

## NYC (Local Law 97, from the LL84 disclosure)

Emissions in metric tons CO2e (t); limits in t/year; penalties in dollars a year, with use held at the LL84
year's values. Each `_2024`, `_2030`, `_2035`, `_2040`, `_2050` column holds for its whole compliance period
(2024-2029, 2030-2034, 2035-2039, 2040-2049, 2050 on).

`screen_status`: `scored`; `invalid_input` (the row fails the portfolio contract; see `problems`);
`campus_member` (a building inside a campus whose parent row carries the campus); `unmapped_property_type`
(a use the rule gives no limit, such as "Other"); `no_emission_factor` (a fuel the rule has no coefficient
for, such as #5/#6 oil); `implausible_use` (above 100 kgCO2e/sq ft, almost always a reporting error).

| Column | Meaning |
|---|---|
| bbl, bin, parent_property_id | As published in LL84 |
| data_year | The LL84 calendar year |
| property_uses | Every ESPM use and its floor area, "Type: sq ft; ..." (zero-area uses dropped) |
| electricity_kwh | Grid electricity, kWh |
| natural_gas_kbtu, district_steam_kbtu, district_hot_water_kbtu, district_chilled_water_kbtu | kBtu |
| fuel_oil_1_kbtu, fuel_oil_2_kbtu, fuel_oil_4_kbtu, fuel_oil_5_6_kbtu, diesel_kbtu, propane_kbtu, kerosene_kbtu | kBtu |
| problems | Why a row is not scored, in words |
| emissions_t_2024, emissions_t_2030, emissions_t_2035, emissions_t_2040, emissions_t_2050 | Σ fuel use × that period's coefficient |
| limit_t_2024, limit_t_2030, limit_t_2035, limit_t_2040, limit_t_2050 | Σ use floor area × that period's limit (1 RCNY §103-14) |
| penalty_2024, penalty_2030, penalty_2035, penalty_2040, penalty_2050 | max(0, emissions − limit) × $268 |
| limit_per_sqft_2024, emissions_per_sqft_2024 | The 2024 limit and emissions per sq ft of gfa (t/sq ft) |
| cumulative_penalty_2024_2034 | 6 × penalty_2024 + 5 × penalty_2030 |
| first_period_over_limit | The first period start year with a penalty |
| estimated_from | 2035: later figures use DOB's projected electricity and steam coefficients |

## Boston (BERDO 2.0, from the city's disclosure)

`screen_status`: `scored`; `no_data`; `no_floor_area`; `unmapped_property_type`; and, from the city's own
status, `portfolio_member`, `campus_member`, `vacant`, `state_owned` (their building-level figures would mislead).

| Column | Meaning |
|---|---|
| owner_name, tax_parcel_id | As published (BERDO publishes no building names; property_name is the address) |
| property_uses | The city's "All Property Types and GFAs" text |
| renewable_electricity_kwh | Renewable electricity the city deducts after the RPS share |
| building_use | The ordinance's Building Use for the largest property type (P&P Appendix A) |
| district_steam_factor_t_per_kbtu | The steam factor the city applied (its steam emissions ÷ steam use), used in place of the default |
| first_compliance_year | 2025, or 2030 for 20,000-35,000 sq ft / 15-34 units |
| official_ghg_tco2e, official_ghg_intensity_kg, official_standard_kg, official_status, flexibility_measures | The city's published figures, used as the answer key |
| emissions_t_2025, emissions_t_2030, emissions_t_2035, emissions_t_2040, emissions_t_2050 | Emissions with that year's grid factor and RPS share, use unchanged |
| standard_kg_per_sqft_2025, standard_kg_per_sqft_2030, standard_kg_per_sqft_2035, standard_kg_per_sqft_2040, standard_kg_per_sqft_2050 | The default standard (largest use), kgCO2e/sq ft |
| acp_2025, acp_2030, acp_2035, acp_2040, acp_2050 | max(0, emissions − standard × gfa) × $234; blank before the first compliance year |
| cumulative_acp_2025_2034 | Sum of the yearly ACP, 2025-2034 |
| first_year_over_standard | The first year with an ACP above zero |
| emissions_intensity_kg_2025 | 2025 emissions per sq ft, kgCO2e |
| emissions_matches_official | Our emissions within 0.5% of the city's |
| standard_matches_official | Our default standard equals the city's (buildings without a flexibility measure) |
| verdict_matches_official | Our verdict, against the city's applicable standard, equals the city's status |
