# open-bps

[![PyPI](https://img.shields.io/pypi/v/open-bps)](https://pypi.org/project/open-bps/) [![ci](https://github.com/Skippy-8/open-bps/actions/workflows/ci.yml/badge.svg)](https://github.com/Skippy-8/open-bps/actions/workflows/ci.yml)

Open, auditable screening of **building performance standard (BPS)** gaps and penalty exposure, built from
the benchmarking data cities already publish. It starts with **Washington, DC (BEPS)** and **Denver
(Energize Denver)**.

Cities with a BPS law publish each building's energy use, and some publish its target. None of them
publishes a ready answer to the question an owner, lender, buyer or reporter asks: *how far is this building
from its target, and what does missing it cost?* open-bps answers that for every covered building:
- **the law, encoded** in dated rule files that cite the regulator's own documents;
- **checked against the regulator's published verdicts** wherever they exist;
- **published as a refreshed open dataset,** with a one-building Excel workbook anyone can audit.

> **Disclaimer.** Every figure is a screening estimate from public data under the cited rules. It is not a
> compliance determination, and not legal, engineering or investment advice. Official figures come only from
> the jurisdiction (DC DOEE, Denver CASR).

## What you get

| | DC: BEPS Compliance Cycle 1 | Denver: Energize Denver (25,000 sq ft and up) |
|---|---|---|
| Buildings | Every building in DOEE's BEPS disclosure | Every building in the Energize Denver Master Dataset |
| Gap | BEPS standard vs the building's metric; DOEE's verdict, reproduced and checked | Weather-normalized site EUI vs the interim and final targets |
| Exposure | Maximum alternative compliance payment ($10/sq ft, capped at $7.5M); estimated Performance Pathway payment; Standard Target Pathway payment for EUI-metric buildings | Penalty = kBtu over target x $/kBtu, by target year, for the extended (2028/2032) and original (2025/2027/2030) schedules |
| Rules | DOEE BEPS Guidebook v1.2 (Aug 2026) | Energize Denver Technical Guidance v3 (Apr 2025) |

Outputs:
- **Data:** `dc` and `denver` tables (Parquet and CSV), each with a `.meta.json` recording the rule version,
  the source snapshot (URL, retrieval time, SHA-256) and the attribution, plus a `SUMMARY.md` of headline
  figures. Released monthly: **[data-latest](https://github.com/Skippy-8/open-bps/releases/tag/data-latest)**,
  with dated archives that include the raw snapshot.
- **A workbook per building:** inputs with their sources, every calculation a live formula, and a Checks tab
  that confirms the workbook reproduces the engine.
- **A lookup app:** search by building ID, name or address (`app/streamlit_app.py`).

## How far you can trust it

- **DC verdicts.** DOEE publishes whether each building met its standard. The encoded rule reproduces that
  verdict for **1,797 of 1,806 buildings (99.5%)**. The 9 exceptions are boundary values and later
  corrections that DOEE decided outside the plain rule; they are listed in `dc.meta.json`, not fitted
  away.
- **DC distances.** DOEE's published distance from the standard is reproduced exactly for every
  EUI-metric building that has one.
- **Denver penalties.** The worked examples in Denver's own guidance are reproduced exactly by the tests.
  Denver publishes targets but no performance verdicts, so the gap and penalty figures are new information.
- **Data quality.** The monthly refresh stops, and publishes nothing, if the DC match rate falls below
  97% or most Denver buildings stop scoring. Either would mean the upstream data changed shape.

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
- **Exposure assumes energy use stays at the latest reported value** ("cost of inaction"). Retrofit costs
  are not estimated in v0.1.

## Quick start

Python 3.11 or later.

```bash
pip install open-bps

open-bps fetch all          # dated raw snapshot of DOEE and Denver open data, with a manifest
open-bps score all          # data/scored/{dc,denver}.parquet|csv|meta.json and SUMMARY.md
open-bps lookup denver "union station"
open-bps excel denver 2428 --out one_union_station.xlsx
open-bps validate           # DC rule vs DOEE's published verdicts
open-bps rules              # rule versions and their primary sources
```

Use it from Python:

```python
from open_bps.engine import denver, dc

denver.kbtu_not_achieved(eui=52.0, target_eui=48.3, gfa=150_000)    # 555,000 kBtu (Denver TG v3, Table 16)
dc.performance_payment(gfa=100_000, reduction_achieved=0.10)         # $500,000: half of the $1M maximum
```

To run the app: `pip install "open-bps[app]"`, then
`streamlit run app/streamlit_app.py`. Without local data, it reads the latest release.

## How it is built

```
open_bps/rules/*.yaml     the law, by jurisdiction and version; every value cites its primary source
open_bps/sources/         fetchers: DC GIS FeatureServer (DOEE), Denver open data hub (CASR)
open_bps/canonical.py     one schema per city; every building keeps a screen_status, none dropped silently
open_bps/engine/          pure functions per jurisdiction: verdicts, gaps, payments, penalties
open_bps/dataset.py       scored tables, metadata, quality gate, SUMMARY.md
open_bps/excel.py         one-building workbooks: live formulas and a Checks tab
app/                      Streamlit lookup
tests/                    offline; fixtures are samples of the real public data
```

See [docs/methodology.md](docs/methodology.md) for the rules and assumptions, and
[docs/data_dictionary.md](docs/data_dictionary.md) for every output column.

## Data sources and licences

- **DC:** District of Columbia Department of Energy & Environment (DOEE), via Open Data DC, licensed
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- **Denver:** City and County of Denver, Climate Action, Sustainability & Resiliency (CASR), Energize Denver
  Master Dataset. Provided as is, without warranty; not for engineering purposes.
- **open-bps code:** MIT ([LICENSE](LICENSE)).
- **open-bps scored datasets:** CC BY 4.0, keeping the upstream attributions above
  ([DATA_LICENSE.md](DATA_LICENSE.md)).

## Adding a jurisdiction

NYC Local Law 97 and Boston BERDO are next. Both cities publish building-level data.
[CONTRIBUTING.md](CONTRIBUTING.md) describes the four pieces a new city needs:
1. a rule file citing primary sources;
2. a fetcher;
3. a canonical mapping;
4. an engine with the regulator's worked examples as tests.

## Citing

See [CITATION.cff](CITATION.cff). Please cite the data release you used (its tag carries the date).
