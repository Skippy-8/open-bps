"""Denver: Energize Denver Master Dataset, published by the City and County of Denver (CASR).

Each yearly Master Dataset carries every covered building's benchmarking results and its Baseline, First
Interim, Second Interim and Adjusted Final Target EUI. Denver publishes the data "as is", at the user's
own risk and "not for engineering purposes"; that notice travels with every output built from it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from open_bps.sources import get, snapshot_dir, write_manifest

HUB = "https://opendata-geospatialdenver.hub.arcgis.com/api/v3/datasets"
ITEM_DATA = "https://www.arcgis.com/sharing/rest/content/items/{id}/data"
ATTRIBUTION = ("City and County of Denver, Climate Action, Sustainability & Resiliency (CASR), Energize Denver "
               "Master Dataset. Provided as is, without warranty; not for engineering purposes.")


def find_latest() -> tuple[str, str, int]:
    """(item id, title, year) of the newest 'Energize Denver <year> Master Dataset' Excel item."""
    d = json.loads(get(HUB, {"q": "Energize Denver Master Dataset", "page[size]": 50}))
    best = None
    for item in d.get("data", []):
        a = item["attributes"]
        name = a.get("name") or ""
        if "Master Dataset" not in name or "Anonymized" in name or a.get("type") != "Microsoft Excel":
            continue
        years = [int(w) for w in name.split() if w.isdigit() and len(w) == 4]
        if years and (best is None or years[0] > best[2]):
            best = (item["id"], name, years[0])
    if best is None:
        raise RuntimeError("no Energize Denver Master Dataset found on the Denver hub")
    return best


def fetch(root: Path, item_id: str | None = None) -> Path:
    if item_id is None:
        item_id, _, _ = find_latest()
    folder = snapshot_dir(root, "denver")
    url = ITEM_DATA.format(id=item_id)
    (folder / "master.xlsx").write_bytes(get(url))
    write_manifest(folder, {"master.xlsx": url})
    return folder


def load(folder: Path) -> pd.DataFrame:
    return pd.read_excel(Path(folder) / "master.xlsx", dtype=str)
