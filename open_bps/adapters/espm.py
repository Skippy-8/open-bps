"""Read ENERGY STAR Portfolio Manager (ESPM) exports into a portfolio.

ESPM is what most US owners already use to benchmark, and city disclosure files (NYC LL84 among them) are
ESPM exports. Columns are found by their standard ESPM names, ignoring case, spacing, punctuation and the
ft²/ft2 spelling; NYC Open Data's API field names are accepted too.

Spaces come from "List of All Property Use Types (GFA)" when present (it sums to the property's GFA), and
otherwise from the largest, 2nd and 3rd largest use columns. Uses with zero floor area are dropped.
"Not Available" means blank. Property types the jurisdiction does not know are row errors, never defaults.

    from open_bps.adapters.espm import from_espm
    portfolio = from_espm("espm_export.xlsx", jurisdiction="nyc_ll97")
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from open_bps.inputs import (
    BuildingRecord,
    PortfolioInput,
    PortfolioValidationError,
    validate_rows,
)
from open_bps.registry import get_policy

BLANKS = {"", "not available", "not applicable", "n/a", "na", "none"}

# canonical template column -> ESPM display names and NYC Open Data field names, in order of preference
COLUMNS = {
    "building_id": ["Property Id", "Portfolio Manager Property ID", "property_id"],
    "name": ["Property Name", "property_name"],
    "gross_floor_area": ["Property GFA - Calculated (Buildings and Parking) (ft²)", "property_gfa_calculated",
                         "Property GFA - Self-Reported (ft²)", "property_gfa_self_reported"],
    "electricity_kwh": ["Electricity Use - Grid Purchase (kWh)", "electricity_use_grid_purchase_1"],
    "natural_gas_kbtu": ["Natural Gas Use (kBtu)", "natural_gas_use_kbtu"],
    "natural_gas_therms": ["Natural Gas Use (therms)", "natural_gas_use_therms_"],
    "district_steam_kbtu": ["District Steam Use (kBtu)", "district_steam_use_kbtu"],
    "district_hot_water_kbtu": ["District Hot Water Use (kBtu)", "district_hot_water_use_kbtu"],
    "district_chilled_water_kbtu": ["District Chilled Water Use (kBtu)", "district_chilled_water_use_kbtu"],
    "fuel_oil_1_kbtu": ["Fuel Oil #1 Use (kBtu)", "fuel_oil_1_use_kbtu"],
    "fuel_oil_2_kbtu": ["Fuel Oil #2 Use (kBtu)", "fuel_oil_2_use_kbtu"],
    "fuel_oil_4_kbtu": ["Fuel Oil #4 Use (kBtu)", "fuel_oil_4_use_kbtu"],
    "fuel_oil_5_6_kbtu": ["Fuel Oil #5 & 6 Use (kBtu)", "fuel_oil_5_6_use_kbtu"],
    "diesel_kbtu": ["Diesel #2 Use (kBtu)", "Diesel Use (kBtu)", "diesel_2_use_kbtu"],
    "propane_kbtu": ["Propane Use (kBtu)", "propane_use_kbtu"],
    "kerosene_kbtu": ["Kerosene Use (kBtu)", "kerosene_use_kbtu"],
}
ALL_USES = ["List of All Property Use Types (GFA) (ft²)", "list_of_all_property_use"]
TOP_USES = [
    (["Largest Property Use Type", "largest_property_use_type"],
     ["Largest Property Use Type - Gross Floor Area (ft²)", "largest_property_use_type_1"]),
    (["2nd Largest Property Use Type", "_2nd_largest_property_use"],
     ["2nd Largest Property Use Type - Gross Floor Area (ft²)", "_2nd_largest_property_use_1"]),
    (["3rd Largest Property Use Type", "_3rd_largest_property_use"],
     ["3rd Largest Property Use Type - Gross Floor Area (ft²)", "_3rd_largest_property_use_1"]),
]
_USE_ITEM = re.compile(r"\s*(.+?)\s*\(([\d.,]+)\)\s*(?:,|$)")


def _norm(s: str) -> str:
    s = str(s).lower().replace("²", "2").replace("–", "-").replace("ft2", "")
    return re.sub(r"[^a-z0-9#&]+", "", s)


def _find(df: pd.DataFrame, names: list[str]) -> str | None:
    cols = {_norm(c): c for c in df.columns}
    return next((cols[_norm(n)] for n in names if _norm(n) in cols), None)


def _clean(v):
    if v is None or (isinstance(v, float) and v != v):
        return ""
    s = str(v).strip()
    return "" if s.lower() in BLANKS else s


def parse_use_list(text: str) -> list[tuple[str, float]]:
    """'Office (668602.0), Retail Store (4840.0)' -> [('Office', 668602.0), ('Retail Store', 4840.0)]."""
    return [(t, float(a.replace(",", ""))) for t, a in _USE_ITEM.findall(text or "")]


def to_template(df: pd.DataFrame) -> pd.DataFrame:
    """An ESPM export as the generic portfolio template (see open_bps.inputs)."""
    found = {k: _find(df, v) for k, v in COLUMNS.items()}
    for need in ("building_id", "gross_floor_area", "electricity_kwh"):
        if found[need] is None:
            raise PortfolioValidationError([f"Header: no ESPM column for {need!r} (looked for {COLUMNS[need]})"])
    if found["natural_gas_kbtu"]:
        found["natural_gas_therms"] = None
    all_uses = _find(df, ALL_USES)
    top = [(_find(df, t), _find(df, a)) for t, a in TOP_USES]
    out = pd.DataFrame({k: df[c].map(_clean) for k, c in found.items() if c is not None})
    spaces = []
    for _, row in df.iterrows():
        uses = parse_use_list(_clean(row[all_uses])) if all_uses else []
        if not uses:
            uses = [(_clean(row[t]), _clean(row[a])) for t, a in top if t and a and _clean(row[t])]
        spaces.append([(t, a) for t, a in uses if _area(a) != 0])
    width = max((len(s) for s in spaces), default=0)
    for n in range(width):
        out[f"property_type_{n + 1}"] = [s[n][0] if n < len(s) else "" for s in spaces]
        out[f"gfa_{n + 1}"] = [str(s[n][1]) if n < len(s) else "" for s in spaces]
    return out


def _area(a) -> float | None:
    try:
        return float(str(a).replace(",", ""))
    except ValueError:
        return None


def _allowed(jurisdiction: str | None):
    if jurisdiction is None:
        return None
    p = get_policy(jurisdiction)
    if not p.property_type_map:
        raise ValueError(f"{p.id} has no property-type table; ESPM input is for NYC LL97 and Boston BERDO")
    return set(p.property_type_map) | set(p.unassignable_types)


def _read(src) -> pd.DataFrame:
    if isinstance(src, pd.DataFrame):
        return src.astype(str).where(src.notna(), "")
    path = Path(src)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=str, keep_default_na=False)
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding_errors="replace")


@dataclass(frozen=True)
class EspmRead:
    buildings: list[tuple[int, BuildingRecord]]      # (row number in the file, record)
    errors: list[str]
    template: pd.DataFrame


def read_espm(src, jurisdiction: str | None = None) -> EspmRead:
    """Lenient: every valid building plus the errors for the rest (used to score whole city files)."""
    template = to_template(_read(src))
    buildings, errors = validate_rows(template, _allowed(jurisdiction))
    return EspmRead(buildings, errors, template)


def from_espm(src, jurisdiction: str | None = None) -> PortfolioInput:
    """Strict: a PortfolioInput, or one PortfolioValidationError listing every bad row."""
    r = read_espm(src, jurisdiction)
    if r.errors:
        raise PortfolioValidationError(r.errors)
    return PortfolioInput(buildings=[b for _, b in r.buildings])
