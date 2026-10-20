# Test fixtures

Small samples of real public data, so the tests run offline. `scripts/make_fixtures.py` regenerates them from a full snapshot (seeded).

| File | Source | Licence / terms |
|---|---|---|
| `dc_performance.parquet` | DOEE Building Energy Performance Data (Open Data DC, DC GIS FeatureServer layer 75). The sample always includes the 9 buildings whose published verdict the plain rule does not reproduce. | CC BY 4.0. Attribution: District of Columbia Department of Energy & Environment (DOEE). |
| `dc_benchmarking.parquet` | DOEE Building Energy Benchmarks (layer 45), all years, for the sampled buildings. Only the columns the code reads. | CC BY 4.0, as above. |
| `denver_master.parquet` | Energize Denver 2025 Master Dataset (City and County of Denver, CASR), a sample covering every screen status. | Provided "as is", without warranty, at the user's own risk; not for engineering purposes. |

Snapshot taken on 2026-10-20.
