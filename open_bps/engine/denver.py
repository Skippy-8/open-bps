"""Energize Denver performance requirements (buildings >= 25,000 sq ft), Technical Guidance v3 (April 2025).

  kBtu not achieved = max(0, (EUI - target EUI) x gross floor area)        (TG v3 s. 9.4)
  penalty           = kBtu not achieved x rate per kBtu                    (TG v3 s. 10.2.1.2.1, Table 17)

EUI is the weather-normalized site EUI. The city subtracts renewable credits, transportation energy and an
electrification incentive before comparing; public data has none of these, so the public-data EUI is an
upper bound and so is the penalty. Which buildings opted into the 2028/2032 extension is not public, so both
schedules are computed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from open_bps import rules as _rules

TARGET_COLUMNS = {"first_interim": "target_first_interim", "second_interim": "target_second_interim",
                  "final": "target_final"}


@dataclass(frozen=True)
class YearResult:
    year: int
    target_eui: float
    kbtu_not_achieved: float
    penalty: float


def kbtu_not_achieved(eui: float, target_eui: float, gfa: float) -> float:
    return max(0.0, (eui - target_eui) * gfa)


def schedule_for(building: dict, schedule: str, through: int | None = None, r: dict | None = None) -> list[YearResult]:
    """Year-by-year results for one building, EUI held at its latest value.

    After the final target year the city evaluates annually (Table 17: "then annually if the building has
    not met the final target"); `through` extends the schedule to that year.
    """
    r = r or _rules.load("denver")
    s = r["schedules"][schedule]
    rate = s["rate_per_kbtu"]
    out = []
    for key, year in s["target_years"].items():
        t = building[TARGET_COLUMNS[key]]
        k = kbtu_not_achieved(building["eui"], t, building["gfa"])
        out.append(YearResult(year, t, k, k * rate))
    final_year = s["target_years"]["final"]
    for year in range(final_year + 1, (through or final_year) + 1):
        t = building["target_final"]
        k = kbtu_not_achieved(building["eui"], t, building["gfa"])
        out.append(YearResult(year, t, k, k * rate))
    return out


def score(df: pd.DataFrame, through: int = 2035) -> pd.DataFrame:
    """Score canonical Denver rows (see canonical.denver). Adds, for each schedule, the shortfall and penalty
    in each target year and the cumulative penalty through `through`, plus the reduction needed."""
    r = _rules.load("denver")
    out = df.copy()
    ok = out["screen_status"].eq("scored")
    eui, gfa = out["eui"], out["gfa"]
    out["reduction_needed_final"] = np.where(ok, np.clip(1 - out["target_final"] / eui, 0, None), np.nan)
    for name in ("extended", "original"):
        s = r["schedules"][name]
        rate = s["rate_per_kbtu"]
        for key, year in s["target_years"].items():
            k = np.clip(eui - out[TARGET_COLUMNS[key]], 0, None) * gfa
            out[f"{name}_{year}_kbtu_over"] = np.where(ok, k, np.nan)
            out[f"{name}_{year}_penalty"] = np.where(ok, k * rate, np.nan)
        final_year = s["target_years"]["final"]
        k_final = np.clip(eui - out["target_final"], 0, None) * gfa
        cum = sum(out[f"{name}_{y}_penalty"].fillna(0) for y in s["target_years"].values())
        cum = cum + k_final * rate * max(0, through - final_year)
        out[f"{name}_cumulative_penalty_through_{through}"] = np.where(ok, cum, np.nan)
    # buildings that never filed a data-verified report owe a per-square-foot penalty instead (Table 17)
    nr = out["compliance_status"].eq("not submitted")
    out["no_report_penalty"] = np.where(nr, out["gfa"] * r["no_report_penalty_per_sq_ft"], np.nan)
    out["rule_version"] = r["rule_version"]
    return out
