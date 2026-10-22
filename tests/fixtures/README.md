# Test fixtures

Small samples of real public data, so the tests run offline. `scripts/make_fixtures.py` regenerates them from a full snapshot (seeded).

| File | Source | Licence / terms |
|---|---|---|
| `dc_performance.parquet` | DOEE Building Energy Performance Data (Open Data DC, DC GIS FeatureServer layer 75). The sample always includes the 9 buildings whose published verdict the plain rule does not reproduce. | CC BY 4.0. Attribution: District of Columbia Department of Energy & Environment (DOEE). |
| `dc_benchmarking.parquet` | DOEE Building Energy Benchmarks (layer 45), all years, for the sampled buildings. Only the columns the code reads. | CC BY 4.0, as above. |
| `denver_master.parquet` | Energize Denver 2025 Master Dataset (City and County of Denver, CASR), a sample covering every screen status. | Provided "as is", without warranty, at the user's own risk; not for engineering purposes. |
| `nyc_ll84.csv` | NYC Building Energy and Water Data Disclosure for Local Law 84, CY2024 (NYC Open Data 5zyy-y8am): the first 400 properties by id, only the columns the ESPM adapter reads. | NYC Open Data terms of use. Attribution: City of New York. |
| `boston_berdo.parquet` | BERDO 2026 disclosure (2025 data), sheet "Buildings & Campuses" (data.boston.gov): every "Action Needed" building plus samples of each other status, blended standards and district steam users. | Open Data Commons PDDL. Attribution: City of Boston Environment Department. |

DC and Denver snapshots taken on 2026-10-20; NYC and Boston on 2026-10-22.
