"""Boston BERDO: score canonical disclosure rows (see canonical.boston) with the generic GHG engine.

The default standard is the one for the building's largest primary use (the city's "Largest Property Type",
mapped through P&P Appendix A), applied to the whole gross floor area. Exposure is the Alternative Compliance
Payment that would cover the excess: max(0, emissions − standard × GFA) × $234 per tCO2e.

Validation against the city's own figures (the answer key):
  emissions_matches_official   our total within 0.5% of the city's
  standard_matches_official    our default standard equals the city's applicable standard (no flexibility measure)
  verdict_matches_official     our intensity vs the city's applicable standard agrees with "In Compliance" /
                               "Action Needed"
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from open_bps.engine import ghg
from open_bps.inputs import BuildingRecord
from open_bps.registry import get_policy

YEARS = tuple(range(2025, 2051))
REPORT_YEARS = (2025, 2030, 2035, 2040, 2050)
CUMULATIVE_THROUGH = 2034
FUELS = ("electricity", "natural_gas", "district_steam", "district_hot_water", "district_chilled_water",
         "fuel_oil_1", "fuel_oil_2", "fuel_oil_4", "fuel_oil_5_6", "propane", "diesel", "kerosene")


def _use(row: dict) -> dict:
    """Fuel -> annual use from a canonical row (blank = not used)."""
    use = {}
    for f in FUELS:
        v = row.get(f + ("_kwh" if f == "electricity" else "_kbtu"))
        if v is not None and v == v:
            use[f] = v
    return use


def record(row: dict) -> BuildingRecord:
    """A scored row as a one-space building at its largest use: the default standard over the whole GFA."""
    util = {f"{f}_{'kwh' if f == 'electricity' else 'kbtu'}": v for f, v in _use(row).items()}
    ren = row.get("renewable_electricity_kwh")
    if ren is not None and ren == ren:
        util["renewable_electricity_kwh"] = ren
    return BuildingRecord(building_id=row["building_id"], name=row.get("property_name") or "",
                          gross_floor_area=row["gfa"], spaces=[{"property_type": row["property_type"], "gfa": row["gfa"]}],
                          utilities={"electricity_kwh": 0.0, **util})


def overrides(row: dict) -> dict | None:
    steam = row.get("district_steam_factor_t_per_kbtu")
    return {"district_steam": steam} if steam is not None and steam == steam else None


def score(df: pd.DataFrame) -> pd.DataFrame:
    p = get_policy("boston_berdo")
    rate = ghg.penalty_rate(p)
    out = df.copy()
    pen = {y: [] for y in YEARS}
    em_y = {y: [] for y in REPORT_YEARS}
    std_y = {y: [] for y in REPORT_YEARS}
    for row in out.to_dict("records"):
        ok = row["screen_status"] == "scored"
        ov = overrides(row)
        ren = row.get("renewable_electricity_kwh")
        ren = 0.0 if ren is None or ren != ren else ren
        start = row["first_compliance_year"] if row["first_compliance_year"] == row["first_compliance_year"] else 2025
        for y in YEARS:
            v = e = s = np.nan
            if ok:
                em = ghg.emissions(p, _use(row), y, ren, ov)
                thr = p.threshold(row["building_use"], y)
                if em.total_t is not None and thr is not None:
                    e, s = em.total_t, thr * 1000
                    if y >= start:
                        v = max(0.0, e - thr * row["gfa"]) * rate
            pen[y].append(v)
            if y in em_y:
                em_y[y].append(e)
                std_y[y].append(s)
    for y in REPORT_YEARS:
        out[f"emissions_t_{y}"] = em_y[y]
        out[f"standard_kg_per_sqft_{y}"] = std_y[y]
        out[f"acp_{y}"] = pen[y]
    out[f"cumulative_acp_2025_{CUMULATIVE_THROUGH}"] = pd.DataFrame({y: pen[y] for y in range(2025, CUMULATIVE_THROUGH + 1)},
                                                                    index=out.index).sum(axis=1, min_count=1)
    first = pd.Series(np.nan, index=out.index)
    for y in reversed(YEARS):
        first[pd.Series(pen[y], index=out.index) > 0] = y
    out["first_year_over_standard"] = first
    out["emissions_intensity_kg_2025"] = out["emissions_t_2025"] * 1000 / out["gfa"]

    sc = out["screen_status"].eq("scored")
    official = out["official_ghg_tco2e"]
    out["emissions_matches_official"] = ((out["emissions_t_2025"] - official).abs() <= np.maximum(0.001, 0.005 * official)
                                         ).where(sc & official.notna() & out["emissions_t_2025"].notna())
    plain = out["flexibility_measures"].isna() & out["official_standard_kg"].notna()
    out["standard_matches_official"] = (out["standard_kg_per_sqft_2025"].round(1) == out["official_standard_kg"]).where(sc & plain)
    verdict = out["official_status"].map({"In Compliance": True, "Action Needed": False})
    ours = out["emissions_intensity_kg_2025"].round(1) <= out["official_standard_kg"]
    out["verdict_matches_official"] = (ours == verdict).where(sc & verdict.notna() & out["official_standard_kg"].notna()
                                                              & out["emissions_t_2025"].notna())
    out["rule_version"] = p.rule_version
    return out


def validate(scored: pd.DataFrame) -> dict:
    res = {}
    for k in ("emissions", "standard", "verdict"):
        v = scored[f"{k}_matches_official"].dropna().astype(bool)
        res[f"{k}_compared"] = int(len(v))
        res[f"{k}_matching"] = int(v.sum())
        res[f"{k}_match_rate"] = round(float(v.mean()), 4) if len(v) else None
    res["standard_exceptions"] = scored.loc[scored["standard_matches_official"].eq(False), "building_id"].tolist()
    res["verdict_exceptions"] = scored.loc[scored["verdict_matches_official"].eq(False), "building_id"].tolist()
    return res
