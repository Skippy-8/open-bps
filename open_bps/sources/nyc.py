"""New York City: the Local Law 84 benchmarking disclosure, published on NYC Open Data.

Dataset 5zyy-y8am ("NYC Building Energy and Water Data Disclosure for Local Law 84, 2023 to present") is an
ENERGY STAR Portfolio Manager export: property uses with their floor areas and annual use of each fuel. It
carries no LL97 limit or verdict; open-bps computes those from 1 RCNY §103-14.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from open_bps.sources import get, snapshot_dir, write_manifest

RESOURCE = "https://data.cityofnewyork.us/resource/5zyy-y8am"
ATTRIBUTION = ("City of New York, Mayor's Office of Climate and Environmental Justice: NYC Building Energy and "
               "Water Data Disclosure for Local Law 84 (NYC Open Data 5zyy-y8am)")


def latest_year() -> int:
    d = json.loads(get(f"{RESOURCE}.json", {"$select": "max(report_year) AS y"}))
    return int(d[0]["y"])


def fetch(root: Path, year: int | None = None) -> Path:
    """The latest calendar year of LL84 data (all rows) into a dated snapshot folder."""
    year = year or latest_year()
    folder = snapshot_dir(root, "nyc")
    params = {"$where": f"report_year={year}", "$limit": 200000, "$order": "property_id"}
    url = f"{RESOURCE}.csv?" + "&".join(f"{k}={v}" for k, v in params.items())
    (folder / "ll84.csv").write_bytes(get(f"{RESOURCE}.csv", params, timeout=600))
    write_manifest(folder, {"ll84.csv": url})
    return folder


def load(folder: Path) -> pd.DataFrame:
    return pd.read_csv(Path(folder) / "ll84.csv", dtype=str, keep_default_na=False)
