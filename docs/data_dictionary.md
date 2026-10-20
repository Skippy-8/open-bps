# Data dictionary

One row per building. `tests/test_docs.py` fails if a column here is missing from the scored tables, or the
other way round. Units: square feet (sq ft), kBtu, kBtu/sq ft/year, US dollars.

## Both cities

| Column | Meaning |
|---|---|
| jurisdiction | `dc` or `denver` |
| building_id | The city's building identifier (DC: ENERGY STAR Portfolio Manager property ID; Denver: Energize Denver Building ID) |
| property_name, address, postal_code | As published by the city |
| property_type | Primary property type (DC: Portfolio Manager EPA-calculated; Denver: Master Property Type) |
| gfa | Gross floor area, sq ft (DC: reported GFA, else tax-record floor area; Denver: Master Sq Ft) |
| year_built | As published |
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
