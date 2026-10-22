"""Boston: the BERDO disclosure on Analyze Boston (data.boston.gov), Open Data Commons PDDL.

Each year's "<year> BERDO Data Disclosure" workbook has, per building, the use of every fuel, the emissions
the city computed from it, the applicable emissions standard and the city's emissions compliance status,
which open-bps uses as its answer key.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from open_bps.sources import USER_AGENT, get, snapshot_dir, write_manifest

PACKAGE = "https://data.boston.gov/api/3/action/package_show"
PACKAGE_ID = "building-emissions-reduction-and-disclosure-ordinance"
SHEET = "Buildings & Campuses"
ATTRIBUTION = ("City of Boston Environment Department, BERDO data disclosure, via Analyze Boston "
               "(Open Data Commons Public Domain Dedication and License)")


def find_latest() -> str:
    """URL of the newest '<year>-berdo-data-disclosure' workbook in the BERDO package."""
    d = json.loads(get(PACKAGE, {"id": PACKAGE_ID}))
    found = []
    for r in d["result"]["resources"]:
        m = re.search(r"/(\d{4})-berdo-data-disclosure[^/]*\.xlsx$", r.get("url") or "")
        if m:
            found.append((int(m.group(1)), r["url"]))
    if not found:
        raise RuntimeError("no BERDO data disclosure workbook found on data.boston.gov")
    return max(found)[1]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def resolve(url: str) -> str:
    """data.boston.gov answers downloads with a redirect to a signed S3 URL written with an explicit ':443'.
    urllib would send that port in the Host header and S3 would reject the signature, so follow it by hand."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        urllib.request.build_opener(_NoRedirect).open(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
            return e.headers["Location"].replace("amazonaws.com:443/", "amazonaws.com/")
        raise
    return url


def fetch(root: Path, url: str | None = None) -> Path:
    url = url or find_latest()
    folder = snapshot_dir(root, "boston")
    (folder / "berdo.xlsx").write_bytes(get(resolve(url), timeout=600))
    write_manifest(folder, {"berdo.xlsx": url})
    return folder


def load(folder: Path) -> pd.DataFrame:
    return pd.read_excel(Path(folder) / "berdo.xlsx", sheet_name=SHEET, dtype=str)
