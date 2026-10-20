"""Washington, DC: DOEE's open data on DC GIS (CC BY 4.0).

Layer 75 "Building Energy Performance Data" is the BEPS Cycle 1 disclosure: each building's standard,
2019 metric, verdict and approved pathway. Layer 45 "Building Energy Benchmarks" is the annual
benchmarking record (2012 onward), used for baselines and the latest year's performance.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from open_bps.sources import get, snapshot_dir, write_manifest

SERVICE = "https://maps2.dcgis.dc.gov/DCGIS/rest/services/DCGIS_DATA/Environment_Energy_WebMercator/FeatureServer"
LAYERS = {"performance": 75, "benchmarking": 45}
ATTRIBUTION = "District of Columbia Department of Energy & Environment (DOEE), via Open Data DC, CC BY 4.0"


def fetch_layer(layer: int, page: int = 2000) -> pd.DataFrame:
    rows, offset = [], 0
    while True:
        params = {"where": "1=1", "outFields": "*", "f": "json", "returnGeometry": "false",
                  "orderByFields": "OBJECTID", "resultOffset": offset, "resultRecordCount": page}
        d = json.loads(get(f"{SERVICE}/{layer}/query", params))
        if "error" in d:
            raise RuntimeError(f"DC layer {layer}: {d['error']}")
        feats = d.get("features", [])
        rows += [f["attributes"] for f in feats]
        if not feats or not d.get("exceededTransferLimit"):
            return pd.DataFrame(rows)
        offset += len(feats)


def fetch(root: Path) -> Path:
    """Download both layers into a dated snapshot folder; returns the folder."""
    folder = snapshot_dir(root, "dc")
    files = {}
    for name, layer in LAYERS.items():
        df = fetch_layer(layer).astype("string")       # keep the source values exactly; typed in canonical.py
        df.to_parquet(folder / f"{name}.parquet", index=False)
        files[f"{name}.parquet"] = f"{SERVICE}/{layer}"
    write_manifest(folder, files)
    return folder


def load(folder: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    return (pd.read_parquet(Path(folder) / "performance.parquet"),
            pd.read_parquet(Path(folder) / "benchmarking.parquet"))
