"""Map each city's raw columns to one canonical table per jurisdiction.

Every row gets a `screen_status`: buildings are never dropped silently. Only rows with status "scored"
receive estimates; the others say why (exempt, production-based targets, missing data, ...).
"""
from __future__ import annotations

import pandas as pd

DC_METRIC_COLUMNS = {   # DOEE metric type -> the benchmarking (layer 45) column holding it
    "ENERGYSTARSCORE": "ENERGYSTARSCORE",
    "WEATHERNORMALZEDSOUREUI_KBTUFT": "WEATHERNORMALZEDSOUREUI_KBTUFT",
    "SOURCEEUI_KBTU_FT": "SOURCEEUI_KBTU_FT",
}


def _text(df: pd.DataFrame) -> pd.DataFrame:
    """Plain object columns with None for missing text (sources may arrive as pandas "string" dtype, whose
    NA cannot be used in boolean masks)."""
    for c in df.columns:
        if isinstance(df[c].dtype, pd.StringDtype) or df[c].dtype == object:
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def _num(s: pd.Series) -> pd.Series:
    v = pd.to_numeric(s.astype("string").str.replace(",", "").str.rstrip("%"), errors="coerce")
    return v.astype("float64")


def dc(performance: pd.DataFrame, benchmarking: pd.DataFrame, baseline_years=(2018, 2019)) -> pd.DataFrame:
    p, b = performance.copy(), benchmarking.copy()
    b["pid"] = b["PMPROPERTYID"].astype("string").str.strip()
    b["year"] = _num(b["REPORTINGYEAR"])
    b["site_eui"] = _num(b["SITEEUI_KBTU_FT"])
    b = b.sort_values(["pid", "year", "LASTUPDATE"]).drop_duplicates(["pid", "year"], keep="last")

    out = pd.DataFrame({
        "jurisdiction": "dc",
        "building_id": p["PMPROPERTYID"].astype("string").str.strip(),
        "property_name": p["PROPERTYNAME"],
        "address": p["REPORTEDADDRESS"].fillna(p["ADDRESSOFRECORD"]),
        "postal_code": p["POSTALCODE"],
        "ward": p["WARD"],
        "property_type": p["PRIMARYPROPERTYTYPE_EPACALC"],
        "beps_property_group": p["BEPS_PROPERTY_GROUP"],
        "gfa": _num(p["REPORTEDBUILDINGGROSSFLOORAREA"]).fillna(_num(p["TAXRECORDFLOORAREA"])),
        "year_built": _num(p["YEARBUILT"]),
        "metric_type": p["BEPS_METRIC_TYPE"],
        "standard": _num(p["BEPS"]),
        "metric": _num(p["PROPERTY_BEPS_METRIC"]),
        "metric_year": _num(p["PROPERTY_BEPS_METRIC_YEAR"]),
        "official_meets_beps": p["MEETS_BEPS"],
        "official_eui_distance": _num(p["DISTANCE_FROM_BEPS_ESTIMATED"]) / 100,
        "pathway": p["APPROVED_COMPLIANCE_PATHWAY"],
        "latitude": _num(p["LATITUDE"]),
        "longitude": _num(p["LONGITUDE"]),
        "ubid": p["UBID"],
    })
    base = b[b["year"].isin(baseline_years)].groupby("pid")["site_eui"].mean()
    with_eui = b[b["site_eui"].notna()]
    latest = with_eui.sort_values("year").groupby("pid").tail(1).set_index("pid")
    out["site_eui_baseline"] = out["building_id"].map(base).astype("float64")
    out["latest_year"] = out["building_id"].map(latest["year"]).astype("float64")
    out["site_eui_latest"] = out["building_id"].map(latest["site_eui"]).astype("float64")

    def latest_metric(row):
        col = DC_METRIC_COLUMNS.get(row["metric_type"])
        if col is None or row["building_id"] not in latest.index:
            return pd.NA
        return latest.at[row["building_id"], col]
    out["metric_latest"] = _num(pd.Series([latest_metric(r) for _, r in out.iterrows()], index=out.index))

    out = _text(out)
    status = pd.Series("scored", index=out.index)
    status[out["official_meets_beps"].eq("Not subject to BEPS")] = "not_subject"
    status[out["standard"].isna() | out["metric"].isna()] = "no_metric"
    status[out["gfa"].isna()] = "no_floor_area"
    out["screen_status"] = status
    return out


def denver(master: pd.DataFrame, min_gfa: float = 25000) -> pd.DataFrame:
    m = master
    out = pd.DataFrame({
        "jurisdiction": "denver",
        "building_id": m["Building ID"].astype("string").str.strip(),
        "property_name": m["Property Name"],
        "address": m["Street"],
        "postal_code": m["Zipcode"],
        "property_type": m["Master Property Type"],
        "gfa": _num(m["Master Sq Ft"]),
        "year_built": _num(m["Year Built"]),
        "data_year": _num(m["Reporting Year"]),
        "compliance_status": m["Compliance Status"].astype("string").str.strip().str.lower(),
        "approved_mai": m["Approved Mai"].fillna("").astype(str).str.strip().eq("Yes"),
        "energy_star_score": _num(m["Energy Star Score"]),
        "site_eui": _num(m["Site EUI (kBtu/sq ft)"]),
        "eui": _num(m["Weather Normalized Site EUI (kBtu/sq ft)"]),
        "ghg_tco2e": _num(m["Total GHG Emissions (Metric Tons Co2e)"]),
        "baseline_eui": _num(m["Baseline EUI"]),
        "target_first_interim": _num(m["First Interim Target EUI"]),
        "target_second_interim": _num(m["Second Interim Target EUI"]),
        "target_final": _num(m["Adjusted Final Target EUI"]),
    })
    out = _text(out)
    status = pd.Series("scored", index=out.index)
    status[out[["eui", "target_first_interim", "target_second_interim", "target_final"]].isna().any(axis=1)] = "no_data"
    status[out["gfa"].isna()] = "no_floor_area"
    status[out["gfa"] < min_gfa] = "below_threshold"
    status[out["approved_mai"]] = "mai_production_targets"
    status[out["compliance_status"].eq("exempt")] = "exempt"
    out["screen_status"] = status
    return out
