"""DC Building Energy Performance Standards, Compliance Cycle 1 (DOEE Guidebook v1.2, August 2026).

Verdict (did the building meet its standard in the metric year?), reproduced from DOEE's disclosure:
  ENERGY STAR score metric: meets if score >= standard; EUI metrics: meets if EUI <= standard.
Distance from the standard (EUI metrics): (standard - metric) / metric, as DOEE publishes it.

Alternative compliance payment (Guidebook Chapter 7, Table 21):
  maximum  = min($10 x gross floor area, $7.5M)
  Performance Pathway: maximum x (1 - min(1, site EUI reduction achieved / 20%))
  Standard Target Pathway: maximum x distance remaining / distance of a building 20% less efficient than
  the standard. For EUI-metric buildings that reference distance is 20% of the standard; for score-metric
  buildings DOEE converts with its own models (Appendix E), so this package does not estimate it.

The Performance Pathway is evaluated by DOEE on Adjusted Site EUI, which is published only on the owner
portal. The estimate here uses public Site EUI (average of 2018-2019 vs the latest reported year) and is
labelled Estimated.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from open_bps import rules as _rules

SCORE = "ENERGYSTARSCORE"


def meets_standard(metric_type: str, metric: float, standard: float) -> bool:
    return metric >= standard if metric_type == SCORE else metric <= standard


def eui_distance(metric: float, standard: float) -> float:
    return (standard - metric) / metric


def max_payment(gfa: float, r: dict | None = None) -> float:
    mp = (r or _rules.load("dc"))["max_payment"]
    return min(gfa * mp["per_sq_ft_gfa"], mp["cap_per_building"])


def performance_payment(gfa: float, reduction_achieved: float, r: dict | None = None) -> float:
    r = r or _rules.load("dc")
    req = r["pathways"]["performance"]["required_reduction"]
    return max_payment(gfa, r) * (1 - min(1.0, max(0.0, reduction_achieved) / req))


def standard_target_payment(gfa: float, distance_remaining: float, reference_distance: float,
                            r: dict | None = None) -> float:
    """distance_remaining and reference_distance in the same units (score points or EUI)."""
    return max_payment(gfa, r) * min(1.0, max(0.0, distance_remaining) / reference_distance)


def prescriptive_payment(gfa: float, points_earned: float, points_needed: float, r: dict | None = None) -> float:
    return max_payment(gfa, r) * (1 - min(1.0, points_earned / points_needed))


def score(df: pd.DataFrame) -> pd.DataFrame:
    """Score canonical DC rows (see canonical.dc)."""
    r = _rules.load("dc")
    out = df.copy()
    has = out["standard"].notna() & out["metric"].notna() & out["metric_type"].notna()
    is_score = out["metric_type"].eq(SCORE)
    verdict = np.where(is_score, out["metric"] >= out["standard"], out["metric"] <= out["standard"])
    out["our_meets_standard"] = pd.array(np.where(has, verdict, pd.NA), dtype="boolean")
    official = out["official_meets_beps"].map({"Meets BEPS": True, "Does Not Meet BEPS": False})
    out["verdict_matches_official"] = pd.array(
        np.where(has & official.notna(), out["our_meets_standard"] == official, pd.NA), dtype="boolean")
    out["eui_distance"] = np.where(has & ~is_score, (out["standard"] - out["metric"]) / out["metric"], np.nan)

    mp = r["max_payment"]
    out["max_payment"] = np.minimum(out["gfa"] * mp["per_sq_ft_gfa"], mp["cap_per_building"])
    req = r["pathways"]["performance"]["required_reduction"]
    out["site_eui_reduction_est"] = np.where(out["site_eui_baseline"] > 0,
                                             1 - out["site_eui_latest"] / out["site_eui_baseline"], np.nan)
    on_pp = out["pathway"].eq("Performance Pathway")
    pp_pay = out["max_payment"] * (1 - np.clip(out["site_eui_reduction_est"] / req, 0, 1))
    out["payment_est_performance"] = np.where(on_pp & out["site_eui_reduction_est"].notna(), pp_pay, np.nan)

    on_st = out["pathway"].eq("Standard Target Pathway") & ~is_score & out["metric_latest"].notna()
    st_pay = out["max_payment"] * np.clip((out["metric_latest"] - out["standard"]) / (0.2 * out["standard"]), 0, 1)
    out["payment_est_standard_target"] = np.where(on_st, st_pay, np.nan)
    out["rule_version"] = r["rule_version"]
    return out
