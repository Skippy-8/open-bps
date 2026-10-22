"""NYC Local Law 97: score canonical LL84 rows (see canonical.nyc) with the generic GHG engine.

Limits and coefficients are constant within each compliance period, so one assessment per period gives
every year's figure: the 2024 result holds for 2024-2029, the 2030 result for 2030-2034, and so on. Use is
held at the latest reported year ("cost of inaction").
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from open_bps.canonical import FUEL_COLUMNS
from open_bps.engine import ghg
from open_bps.inputs import BuildingRecord
from open_bps.registry import get_policy

PERIOD_YEARS = (2024, 2030, 2035, 2040, 2050)      # the first year of each LL97 compliance period
CUMULATIVE_THROUGH = 2034
# LL84 is self-reported. Above 100 kgCO2e/sf (about 4x the highest LL97 limit, 23.8 kg/sf, and above the 99.9th
# percentile of the CY2024 data, 41 kg/sf) the figure is almost always a unit or meter error: such rows are
# flagged "implausible_use" and kept out of totals rather than reported as penalties.
MAX_PLAUSIBLE_KG_PER_SQFT = 100.0


def record(row: dict) -> BuildingRecord:
    spaces = [{"property_type": t.rsplit(": ", 1)[0], "gfa": float(t.rsplit(": ", 1)[1])}
              for t in row["property_uses"].split("; ")]
    util = {c: row[c] for c in FUEL_COLUMNS if row.get(c) == row.get(c) and row.get(c) is not None}
    return BuildingRecord(building_id=row["building_id"], name=row.get("property_name") or "",
                          gross_floor_area=row["gfa"], spaces=spaces, utilities=util)


def score(df: pd.DataFrame) -> pd.DataFrame:
    p = get_policy("nyc_ll97")
    out = df.copy()
    cols = {f"{k}_{y}": [] for y in PERIOD_YEARS for k in ("emissions_t", "limit_t", "penalty")}
    problems = []
    for row in out.to_dict("records"):
        if row["screen_status"] != "scored":
            for v in cols.values():
                v.append(np.nan)
            problems.append(row.get("problems"))
            continue
        b = record(row)
        res = {y: ghg.assess(p, b, y) for y in PERIOD_YEARS}
        for y, r in res.items():
            cols[f"emissions_t_{y}"].append(r.emissions_t if r.emissions_t is not None else np.nan)
            cols[f"limit_t_{y}"].append(r.limit_t if r.limit_t is not None else np.nan)
            cols[f"penalty_{y}"].append(r.penalty if r.penalty is not None else np.nan)
        probs = sorted({x for r in res.values() for x in r.problems})
        problems.append("; ".join(probs) if probs else None)
    for k, v in cols.items():
        out[k] = v
    out["problems"] = problems
    ok = out["screen_status"].eq("scored")
    has_limit = out["limit_t_2024"].notna()
    no_factor = out["problems"].fillna("").str.contains("emission factor")
    out.loc[ok & ~has_limit, "screen_status"] = "unmapped_property_type"
    out.loc[ok & has_limit & no_factor & out["emissions_t_2024"].isna(), "screen_status"] = "no_emission_factor"
    out["limit_per_sqft_2024"] = out["limit_t_2024"] / out["gfa"]
    out["emissions_per_sqft_2024"] = out["emissions_t_2024"] / out["gfa"]
    implausible = out["screen_status"].eq("scored") & (out["emissions_per_sqft_2024"] * 1000 > MAX_PLAUSIBLE_KG_PER_SQFT)
    out.loc[implausible, "screen_status"] = "implausible_use"
    out.loc[implausible, "problems"] = (out.loc[implausible, "emissions_per_sqft_2024"] * 1000).map(
        lambda k: f"emissions of {k:,.0f} kgCO2e/sf exceed {MAX_PLAUSIBLE_KG_PER_SQFT:.0f}: likely a reporting error")
    # constant within periods: 2024-2029 is six years, 2030-2034 five
    out[f"cumulative_penalty_2024_{CUMULATIVE_THROUGH}"] = 6 * out["penalty_2024"] + 5 * out["penalty_2030"]
    first = pd.Series(np.nan, index=out.index)
    for y in reversed(PERIOD_YEARS):
        first[out[f"penalty_{y}"] > 0] = y
    out["first_period_over_limit"] = first
    out["estimated_from"] = 2035                    # 2035+ electricity and steam coefficients are DOB projections
    out["rule_version"] = p.rule_version
    return out
