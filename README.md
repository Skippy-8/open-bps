<div align="center">

# open-bps

**Multi-Jurisdiction Building Performance Standards (BPS) Penalty Engine & Retrofit Underwriting**

[![PyPI version](https://img.shields.io/pypi/v/open-bps.svg)](https://pypi.org/project/open-bps/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-emerald.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/Skippy-8/open-bps/actions/workflows/ci.yml/badge.svg)](https://github.com/Skippy-8/open-bps/actions/workflows/ci.yml)
[![MCP Ready](https://img.shields.io/badge/MCP-FastMCP%20Server-00ADD8)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-slate.svg)](LICENSE)
[![Data: CC BY 4.0](https://img.shields.io/badge/data-CC%20BY%204.0-lightgrey.svg)](DATA_LICENSE.md)

[Quickstart](#quickstart) • [Citywide Empirical Validation](#citywide-empirical-validation) • [Supported Jurisdictions](#supported-jurisdictions) • [Retrofit Underwriting](#green-capital-stack--retrofit-underwriting) • [MCP Server](#mcp-server-claude-desktop) • [Open Data](#the-public-datasets)

</div>

---

`open-bps` is an open-source regulatory calculation engine, Python SDK, CLI and MCP server. It quantifies
**statutory carbon and energy penalty exposure** under U.S. building performance standards, and underwrites
decarbonization retrofits with formula-driven Excel models.

Instead of approximating fines with rules of thumb, `open-bps` encodes each standard from the regulator's own
documents: property-type limits, mixed-use blending, fuel and grid emission factors, compliance periods and
penalty schedules, together with the retrofit capital stack (**IRC §179D** and **C-PACE**). The public
datasets it publishes cover **33,878 scored buildings** in four cities, and its verdicts are checked against
the cities' own published determinations wherever a city publishes them.

> **Disclaimer.** Every figure is a screening estimate under the cited rules. It is not a compliance
> determination, and not legal, engineering, tax or investment advice. Official figures come only from the
> jurisdiction (DC DOEE, Denver CASR, NYC DOB, Boston Environment Department).

---

## Citywide Empirical Validation

Each release is run against the live municipal disclosures (`open-bps fetch all && open-bps score all`). Where a
city publishes its own compliance verdicts, open-bps is scored against them. Figures below are from the
2026-10-22 data release.

| Jurisdiction | Statute / rule | Buildings scored | Check against the city's own figures |
| :--- | :--- | ---: | :--- |
| **New York City** | Local Law 97 (Article 320, 1 RCNY §103-14) | **27,741** *(of 39,090)* | NYC publishes no LL97 verdicts. The engine reproduces DOB's worked examples (one to the cent; the other differs only where DOB's guide rounds a limit) and all 60 × 5 limits of the rule. Self-reported LL84 outliers above 100 kgCO2e/sq ft are flagged, not priced. 2024-2029 exposure if use is unchanged: **~$253M a year**. |
| **Denver** | Energize Denver | **2,325** | Denver publishes targets but no performance verdicts. Weather-normalized site EUI is priced against each building's published interim and final targets, on both the original (2025/2027/2030) and extended (2028/2032) schedules; Denver's own worked examples are reproduced in the tests. |
| **Boston** | BERDO 2.0 | **2,005** | **901 / 901** compliance verdicts match (100%); **1,755 / 1,756** building emissions match the city's published figures. |
| **Washington, D.C.** | BEPS, Compliance Cycle 1 | **1,807** | **1,797 / 1,806** compliance verdicts match DOEE's published determinations (99.5%); the 9 exceptions are listed in `dc.meta.json`, not fitted away. |

*No building is dropped silently: every unscored building keeps a `screen_status` saying why (for example
`implausible_use`, `no_floor_area`, `exempt` or `portfolio_member`).* The monthly refresh publishes nothing if
the DC or Boston match rates fall below 97%, or most Denver or NYC buildings stop scoring.

Known limits, also stated in every output:
- **Denver figures are upper bounds.** The city subtracts renewable, transportation and electrification
  credits before comparing EUI to target, and those credits are not public.
- **Denver schedule.** Whether a building opted into the 2028/2032 extension is not public, so both
  schedules are shown.
- **DC Performance Pathway.** DOEE evaluates it on Adjusted Site EUI, which is published only on the
  owner portal. The estimate uses public site EUI (the 2018–2019 average against the latest year) and is
  labelled Estimated.
- **DC Standard Target Pathway.** Payments for buildings scored on ENERGY STAR need DOEE's own conversion
  models, so they are left blank, not guessed.
- **NYC and Boston.** Deductions (RECs, offsets, beneficial electrification) and flexibility measures
  (blended standards, portfolios, individual schedules) are not applied to the public data. NYC's 2035+
  electricity and steam coefficients are DOB projections, flagged Estimated.
- **Exposure assumes energy use stays at the latest reported value** ("cost of inaction"). Retrofit costs,
  rates and savings are your inputs; open-bps never estimates them.

---

## Quickstart

### Zero-install CLI (`uvx`)

```bash
# Your own portfolio: exposure, a C-PACE retrofit, and a formula-driven Excel model
uvx open-bps analyze portfolio.csv --jurisdiction nyc_ll97 \
    --eui-reduction 0.3 --capex-per-sqft 25 --financing cpace --rate 0.065 --term 20 --output model.xlsx

# The same from an ENERGY STAR Portfolio Manager export
uvx open-bps analyze espm_export.xlsx --espm --jurisdiction nyc_ll97 --output model.xlsx

# Fetch and score all four live municipal benchmarking datasets
uvx open-bps fetch all
uvx open-bps score all
```

`portfolio.csv` has one row per building (`open_bps/inputs.py` documents the columns; the app has a template):

```
building_id,name,gross_floor_area,property_type_1,gfa_1,property_type_2,gfa_2,electricity_kwh,natural_gas_therms
B1,Office tower,250000,Office,220000,Retail Store,30000,5200000,90000
```

Every bad row is reported with the reason; nothing is filled in.

### Python SDK

```python
from open_bps import PortfolioAnalyzer
from open_bps.underwriting.capital_stack import Financing

pa = PortfolioAnalyzer("boston_berdo")
portfolio = pa.load("portfolio.csv")        # or pa.load("espm_export.xlsx", espm=True)
exposure = pa.analyze(portfolio)            # penalties with use unchanged, first year over the limit
deals = pa.underwrite(portfolio, eui_reduction=0.3, capex_per_sqft=25,
                      financing=Financing.debt(ltc=0.6, rate=0.07, term_years=10))
pa.to_excel("model.xlsx")                   # Spaces, Exposure, Underwriting and Checks sheets
```

---

## Key Capabilities

### 1. Native ENERGY STAR Portfolio Manager (ESPM) ingestion
Commercial real estate teams keep their energy data in ESPM. `open_bps.adapters.espm.from_espm()` reads
standard ESPM exports (CSV or Excel, matching column names regardless of case and units) and maps each property
use type (e.g. *Financial Office*, *Multifamily Housing*, *Supermarket/Grocery Store*, *Data Center*) to the
jurisdiction's statutory class. A type the jurisdiction does not know is a row error, never a default.

### 2. Mixed-use cap blending
Real assets rarely have a single use. For NYC LL97 the building limit is area-weighted across its
$N$ space uses (1 RCNY §103-14, Equation 103-14.1):

$$\text{Blended Cap}_t = \frac{\sum_{i=1}^{N} \text{GFA}_i \times \text{Limit}_{i,t}}{\sum_{i=1}^{N} \text{GFA}_i}$$

Boston applies the standard of the largest primary use by default, with an opt-in blend over primary uses
(at least 10% of the floor area). DC and Denver publish each building's own target, so no blending is needed
there. The Python results and the Excel Spaces sheet show each space's contribution to the cap.

### 3. Green capital stack & retrofit underwriting
Underwriting a retrofit compares the **do-nothing penalty baseline** with the post-retrofit path, both priced
by the same engine:
* **IRC §179D deduction:** the IRS sliding scale (from 25% savings up to the cap, base and prevailing-wage
  tiers) for tax years 2024-2026, and **zero unless construction began by 2026-06-30** (One Big Beautiful Bill
  Act §70507).
* **C-PACE vs. commercial debt:** a level C-PACE assessment, a debt/equity split, or cash; NPV, unlevered and
  levered IRR, payback and the annual cash flows.
* **Grid toggle:** the law's own emission factors, or a cleaner-grid scenario (a stated annual decline),
  labelled as a scenario. Boston's statutory method already credits the Massachusetts RPS Class I share each
  year.

### 4. Declarative policy registry
Every statutory rule (property-type limits, fuel and grid emission factors, compliance periods, and penalties
in $/tCO2e or $/kBtu) lives in YAML rule files under `open_bps/jurisdictions/`, validated by a Pydantic schema
and cited to the regulator's primary documents.

---

## Supported Jurisdictions

<!-- coverage:start (generated from open_bps/jurisdictions by open_bps.registry.coverage_markdown) -->
| Jurisdiction | Program | Metric | Compliance periods | Penalty | Rules (checked) |
|---|---|---|---|---|---|
| Boston, MA (`boston_berdo`) | BERDO 2.0 (building emissions standards) | ghg intensity | 2025-2029, 2030-2034, 2035-2039, 2040-2044, 2045-2049, 2050+ | $234 per tCO2e over the limit | `boston_berdo_2.0_pp_v5_2026-09` (2026-10-22) |
| Washington, DC (`dc_beps`) | BEPS | energy star score, weather normalized source eui, source eui | cycle1 (2021-2026) | up to $10/sq ft, capped at $7,500,000 | `dc_beps_cycle1_guidebook_v1.2` (2026-10-20) |
| Denver, CO (`denver_energize`) | Energize Denver (performance requirements, buildings >= 25,000 sq ft) | weather normalized site eui | interim (2025-2029), final (2030+) | $0.15/kBtu (original) or $0.23/kBtu (extended) over target | `denver_tg_25k_v3_2025-04` (2026-10-20) |
| New York City, NY (`nyc_ll97`) | Local Law 97 (Article 320 building emissions limits) | ghg intensity | 2024-2029, 2030-2034, 2035-2039, 2040-2049, 2050+ | $268 per tCO2e over the limit | `nyc_ll97_rcny_103-14_2024` (2026-10-22) |
<!-- coverage:end -->

Boston's per-ton figure is the Alternative Compliance Payment, which covers the excess; a building that neither
complies nor pays faces daily fines instead. DC and Denver publish each building's target, so they are
screened from the city data (`open-bps lookup`), not from your own inputs.

### What the public datasets contain

| | DC: BEPS Compliance Cycle 1 | Denver: Energize Denver (25,000 sq ft and up) |
|---|---|---|
| Buildings | Every building in DOEE's BEPS disclosure | Every building in the Energize Denver Master Dataset |
| Gap | BEPS standard vs the building's metric; DOEE's verdict, reproduced and checked | Weather-normalized site EUI vs the interim and final targets |
| Exposure | Maximum alternative compliance payment ($10/sq ft, capped at $7.5M); estimated Performance Pathway payment; Standard Target Pathway payment for EUI-metric buildings | Penalty = kBtu over target x $/kBtu, by target year, for the extended (2028/2032) and original (2025/2027/2030) schedules |
| Rules | DOEE BEPS Guidebook v1.2 (Aug 2026) | Energize Denver Technical Guidance v3 (Apr 2025) |

| | NYC: Local Law 97 | Boston: BERDO 2.0 |
|---|---|---|
| Buildings | Every property in the LL84 benchmarking disclosure (an ESPM export) | Every building in the BERDO disclosure |
| Gap | Emissions (fuel use × 1 RCNY §103-14 coefficients) vs the limit summed over every property type | Emissions intensity (grid kWh net of the Massachusetts RPS share) vs the standard for the largest use |
| Exposure | (emissions − limit) × $268, each compliance period from 2024 to 2050 | Alternative Compliance Payment (excess × $234), each year from 2025 to 2050 |
| Rules | 1 RCNY §103-14 (60 property types, 5 periods); DOB guidance | Ordinance §7-2.2, 2026 Regulations, Policies and Procedures v5 (Sept 2026) |

Outputs:
- **Data:** `dc`, `denver`, `nyc` and `boston` tables (Parquet and CSV), each with a `.meta.json` recording the rule version,
  the source snapshot (URL, retrieval time, SHA-256) and the attribution, plus a `SUMMARY.md` of headline
  figures. Released monthly: **[data-latest](https://github.com/Skippy-8/open-bps/releases/tag/data-latest)**,
  with dated archives that include the raw snapshot.
- **A workbook per building:** inputs with their sources, every calculation a live formula, and a Checks tab
  that confirms the workbook reproduces the engine.
- **An app** (`streamlit run app.py`): look up any building, or underwrite retrofits across an uploaded
  portfolio and download the audited model.

---

## Green Capital Stack & Retrofit Underwriting

For a GHG standard (NYC, Boston), `underwrite` holds each building's use flat, cuts every fuel by the retrofit's
share, and prices both paths:
- **avoided penalties**, year by year, plus energy cost savings if you give them;
- **section 179D:** IRS amounts for 2024-2026 with the Form 7205 sliding scale, gated at a 2026-06-30
  construction start;
- **financing:** C-PACE (a level annual assessment), debt/equity (loan-to-cost) or cash; a balance outstanding
  at the end of the hold is repaid then;
- **results:** NPV, unlevered and levered IRR, simple payback, and the annual cash flows.

The workbook's Underwriting sheet rebuilds all of it in `SUM`, `NPV`, `IRR`, `IF`, `PMT` and `FV`, and its
Checks sheet confirms it matches the engine to the cent (IRR to 1e-6). Retrofit costs, rates and savings are
your inputs; open-bps never estimates them.

---

## MCP Server (Claude Desktop)

Connect `open-bps` to Claude Desktop so an AI assistant runs the statutory math and retrofit IRRs through tested
code (`pip install "open-bps[mcp]"`):

```json
{
  "mcpServers": {
    "open-bps": {
      "command": "uvx",
      "args": ["--from", "open-bps[mcp]", "open-bps-mcp"]
    }
  }
}
```

**Exposed MCP tools:**
* `list_supported_jurisdictions()`: each standard's metric, compliance periods, penalty basis and sources.
* `calculate_building_bps_exposure(...)`: emissions, limit, excess and penalty for a single- or mixed-use
  building under NYC LL97 or Boston BERDO, by year.
* `underwrite_retrofit_capital_stack(...)`: computes the baseline from the building's details, then
  post-retrofit penalty avoidance, §179D, C-PACE or debt service, NPV and IRR.

Each result carries the rule version, the sources and the disclaimer.

---

## The public datasets

```bash
pip install open-bps

open-bps fetch all          # dated raw snapshots of DC, Denver, NYC and Boston open data, with manifests
open-bps score all          # data/scored/{dc,denver,nyc,boston}.parquet|csv|meta.json and SUMMARY.md
open-bps lookup denver "union station"
open-bps excel denver 2428 --out one_union_station.xlsx
open-bps excel nyc 7365 --out building.xlsx
open-bps validate           # the rules vs DOEE's and Boston's published verdicts
open-bps rules              # rule versions and their primary sources
```

Use it from Python:

```python
from open_bps.engine import denver, dc

denver.kbtu_not_achieved(eui=52.0, target_eui=48.3, gfa=150_000)    # 555,000 kBtu (Denver TG v3, Table 16)
dc.performance_payment(gfa=100_000, reduction_achieved=0.10)         # $500,000: half of the $1M maximum
```

To run the app: `pip install "open-bps[app]"`, then `streamlit run app.py`. Without local data, the lookup
reads the latest release.

## How it is built

```
open_bps/jurisdictions/   the law as validated policies (open_bps/policy.py); every value cites its source
open_bps/sources/         fetchers: DOEE (DC GIS), Denver open data hub, NYC Open Data (LL84), data.boston.gov
open_bps/inputs.py        your buildings: BuildingRecord / PortfolioInput with row-level errors
open_bps/adapters/        ENERGY STAR Portfolio Manager exports
open_bps/canonical.py     one schema per city; every building keeps a screen_status, none dropped silently
open_bps/engine/          verdicts, gaps and penalties; blend.py (mixed use) and ghg.py (any GHG standard)
open_bps/underwriting/    capital stack, 179D, finance functions
open_bps/analyzer.py      PortfolioAnalyzer
open_bps/mcp_server.py    the MCP tools
open_bps/dataset.py       scored tables, metadata, quality gate, SUMMARY.md
open_bps/excel.py         workbooks: live formulas and a Checks tab
app/                      Streamlit lookup and portfolio underwriting
tests/                    offline; fixtures are samples of the real public data
```

See [docs/methodology.md](docs/methodology.md) for the rules and assumptions, and
[docs/data_dictionary.md](docs/data_dictionary.md) for every output column.

## Data sources and licences

- **DC:** District of Columbia Department of Energy & Environment (DOEE), via Open Data DC, licensed
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- **Denver:** City and County of Denver, Climate Action, Sustainability & Resiliency (CASR), Energize Denver
  Master Dataset. Provided as is, without warranty; not for engineering purposes.
- **NYC:** City of New York, Building Energy and Water Data Disclosure for Local Law 84 (NYC Open Data),
  under the NYC Open Data terms of use.
- **Boston:** City of Boston Environment Department, BERDO data disclosure (Analyze Boston), ODC PDDL.
- **open-bps code:** MIT ([LICENSE](LICENSE)).
- **open-bps scored datasets:** CC BY 4.0, keeping the upstream attributions above
  ([DATA_LICENSE.md](DATA_LICENSE.md)).

## Adding a jurisdiction

Colorado's Building Performance Colorado standard is next. [CONTRIBUTING.md](CONTRIBUTING.md) describes the
four pieces a new city needs:
1. a rule file citing primary sources, which the policy registry validates;
2. a fetcher;
3. a canonical mapping;
4. an engine with the regulator's worked examples as tests.

## Citing

See [CITATION.cff](CITATION.cff). Please cite the data release you used (its tag carries the date).
