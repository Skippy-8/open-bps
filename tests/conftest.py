"""Offline fixtures: a raw snapshot folder per city, built from tests/fixtures (samples of real public data)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from open_bps import dataset
from open_bps.sources import write_manifest

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("data")
    dc = root / "raw" / "dc" / "2026-10-20"
    dc.mkdir(parents=True)
    (dc / "performance.parquet").write_bytes((FIX / "dc_performance.parquet").read_bytes())
    (dc / "benchmarking.parquet").write_bytes((FIX / "dc_benchmarking.parquet").read_bytes())
    write_manifest(dc, {"performance.parquet": "fixture", "benchmarking.parquet": "fixture"})
    den = root / "raw" / "denver" / "2026-10-20"
    den.mkdir(parents=True)
    pd.read_parquet(FIX / "denver_master.parquet").to_excel(den / "master.xlsx", index=False)
    write_manifest(den, {"master.xlsx": "fixture"})
    nyc = root / "raw" / "nyc" / "2026-10-22"
    nyc.mkdir(parents=True)
    (nyc / "ll84.csv").write_bytes((FIX / "nyc_ll84.csv").read_bytes())
    write_manifest(nyc, {"ll84.csv": "fixture"})
    bos = root / "raw" / "boston" / "2026-10-22"
    bos.mkdir(parents=True)
    pd.read_parquet(FIX / "boston_berdo.parquet").to_excel(bos / "berdo.xlsx", sheet_name="Buildings & Campuses", index=False)
    write_manifest(bos, {"berdo.xlsx": "fixture"})
    return root


@pytest.fixture(scope="session")
def built(root) -> dict:
    return {c: dataset.build(root, c) for c in ("dc", "denver", "nyc", "boston")}


@pytest.fixture(scope="session")
def dc_scored(root, built) -> pd.DataFrame:
    return pd.read_parquet(root / "scored" / "dc.parquet")


@pytest.fixture(scope="session")
def denver_scored(root, built) -> pd.DataFrame:
    return pd.read_parquet(root / "scored" / "denver.parquet")


@pytest.fixture(scope="session")
def nyc_scored(root, built) -> pd.DataFrame:
    return pd.read_parquet(root / "scored" / "nyc.parquet")


@pytest.fixture(scope="session")
def boston_scored(root, built) -> pd.DataFrame:
    return pd.read_parquet(root / "scored" / "boston.parquet")
