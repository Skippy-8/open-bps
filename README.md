# open-bps

[![PyPI](https://img.shields.io/pypi/v/open-bps)](https://pypi.org/project/open-bps/) [![ci](https://github.com/Skippy-8/open-bps/actions/workflows/ci.yml/badge.svg)](https://github.com/Skippy-8/open-bps/actions/workflows/ci.yml)

Open, auditable screening of **building performance standard (BPS)** gaps and penalty exposure, built from
the benchmarking data cities already publish, and **retrofit underwriting** for your own buildings. It covers
**Washington, DC (BEPS)**, **Denver (Energize Denver)**, **New York City (Local Law 97)** and **Boston (BERDO
2.0)**.

Cities with a BPS law publish each building's energy use, and some publish its target. None of them
publishes a ready answer to the question an owner, lender, buyer or reporter asks: *how far is this building
from its target, and what does missing it cost?* open-bps answers that for every covered building:
- **the law, encoded** in dated rule files that cite the regulator's own documents;
- **checked against the regulator's published verdicts** wherever they exist;
- **published as a refreshed open dataset,** with a one-building Excel workbook anyone can audit;
- **for your own portfolio:** upload a CSV or an ENERGY STAR Portfolio Manager export, model a retrofit with
  C-PACE or debt, and download an Excel underwriting model in which every figure is a live formula.

> **Disclaimer.** Every figure is a screening estimate under the cited rules. It is not a compliance
> determination, and not legal, engineering, tax or investment advice. Official figures come only from the
> jurisdiction (DC DOEE, Denver CASR, NYC DOB, Boston Environment Department).

## Quick start (60 seconds)

Python 3.11 or later. Try it without installing anything:

```bash
uvx open-bps analyze portfolio.csv --jurisdiction nyc_ll97 \
    --eui-reduction 0.3 --capex-per-sqft 25 --financing cpace --rate 0.065 --term 20 --output model.xlsx
```

`portfolio.csv` has one row per building (`open_bps/inputs.py` documents the columns; the app has a template):

```
building_id,name,gross_floor_area,property_type_1,gfa_1,property_type_2,gfa_2,electricity_kwh,natural_gas_therms
B1,Office tower,250000,Office,220000,Retail Store,30000,5200000,90000
```

Add `--espm` to read an ENERGY STAR Portfolio Manager export instead. Every bad row is reported, with the
reason; nothing is filled in.

From Python:

```python
from open_bps import PortfolioAnalyzer
from open_bps.underwriting.capital_stack import Financing

pa = PortfolioAnalyzer("boston_berdo")
portfolio = pa.load("portfolio.csv")
exposure = pa.analyze(portfolio)            # penalties with use unchanged, first year over the limit
deals = pa.underwrite(portfolio, eui_reduction=0.3, capex_per_sqft=25,
                      financing=Financing.debt(ltc=0.6, rate=0.07, term_years=10))
pa.to_excel("model.xlsx")                   # Spaces, Exposure, Underwriting and Checks sheets
```

As tools for an AI assistant (`pip install "open-bps[mcp]"`), for example in Claude Desktop's config:

```json
{"mcpServers": {"open-bps": {"command": "uvx", "args": ["--from", "open-bps[mcp]", "open-bps-mcp"]}}}
```

The server offers `list_supported_jurisdictions`, `calculate_building_bps_exposure` and
`underwrite_retrofit_capital_stack`. Each result carries the rule version, the sources and the disclaimer.

## Supported jurisdictions

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

## What you get from the public data

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

## How far you can trust it

- **DC verdicts.** DOEE publishes whether each building met its standard. The encoded rule reproduces that
  verdict for **1,797 of 1,806 buildings (99.5%)**. The 9 exceptions are boundary values and later
  corrections that DOEE decided outside the plain rule; they are listed in `dc.meta.json`, not fitted
  away.
- **DC distances.** DOEE's published distance from the standard is reproduced exactly for every
  EUI-metric building that has one.
- **Denver penalties.** The worked examples in Denver's own guidance are reproduced exactly by the tests.
  Denver publishes targets but no performance verdicts, so the gap and penalty figures are new information.
- **Boston.** The city publishes its own emissions, standard and verdict for every building. open-bps
  reproduces the verdict for **901 of 901 buildings** and the emissions for 1,755 of 1,756. Its default
  standard matches the city's for 1,101 of 1,104 buildings without a flexibility measure; the 3 exceptions
  are listed in `boston.meta.json`.
- **NYC.** NYC publishes no LL97 verdicts. The engine reproduces DOB's two worked examples and all
  60 × 5 limits of 1 RCNY §103-14. LL84 is self-reported, so rows above 100 kgCO2e/sq ft (about four times the
  highest limit) are flagged `implausible_use`, not priced.
- **Data quality.** The monthly refresh stops, and publishes nothing, if the DC or Boston match rates fall
  below 97%, or most Denver or NYC buildings stop scoring. Any of these would mean the upstream data changed
  shape.

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

## Retrofit underwriting

For a GHG standard (NYC, Boston), `underwrite` holds each building's use flat, cuts every fuel by the retrofit's
share, and prices both paths with the same engine:
- **avoided penalties**, year by year, plus energy cost savings if you give them;
- **section 179D:** IRS amounts for 2024-2026, base and prevailing-wage tiers, the Form 7205 sliding scale. It
  is **zero unless construction began by 2026-06-30** (One Big Beautiful Bill Act §70507);
- **financing:** C-PACE (a level annual assessment), debt/equity (loan-to-cost) or cash; a balance outstanding
  at the end of the hold is repaid then;
- **grid:** the law's factors, or a cleaner-grid scenario (a stated annual decline, labelled as a scenario);
- **results:** NPV, unlevered and levered IRR, simple payback, and the annual cash flows.

The workbook's Underwriting sheet rebuilds all of it in `SUM`, `NPV`, `IRR`, `IF`, `PMT` and `FV`, and its
Checks sheet confirms it matches the engine to the cent (IRR to 1e-6).

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
