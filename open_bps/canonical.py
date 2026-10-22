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


# ---- GHG jurisdictions -----------------------------------------------------------------------------------
FUEL_COLUMNS = ("electricity_kwh", "natural_gas_kbtu", "district_steam_kbtu", "district_hot_water_kbtu",
                "district_chilled_water_kbtu", "fuel_oil_1_kbtu", "fuel_oil_2_kbtu", "fuel_oil_4_kbtu",
                "fuel_oil_5_6_kbtu", "diesel_kbtu", "propane_kbtu", "kerosene_kbtu")


def nyc(ll84: pd.DataFrame) -> pd.DataFrame:
    """LL84 rows (an ESPM export) -> one canonical row per property, validated by the portfolio contract.

    `property_uses` keeps every use and its floor area ("Office: 70000; Retail Store: 30000"); fuels are in
    kWh (electricity) and kBtu. Invalid rows stay, with screen_status "invalid_input" and the reason.
    """
    from open_bps.adapters import espm
    from open_bps.inputs import validate_rows
    from open_bps.registry import get_policy

    p = get_policy("nyc_ll97")
    template = espm.to_template(ll84)
    valid, errors = validate_rows(template, set(p.property_type_map) | set(p.unassignable_types))
    err_by_row = {int(e.split()[1]): e.split("): ", 1)[1] for e in errors if e.startswith("Row ")}
    rec = {n - 2: b for n, b in valid}
    m = ll84
    out = pd.DataFrame({
        "jurisdiction": "nyc",
        "building_id": m["property_id"].astype("string").str.strip(),
        "property_name": m["property_name"],
        "address": m["address_1"],
        "postal_code": m.get("postal_code"),
        "bbl": m["nyc_borough_block_and_lot"],
        "bin": m["nyc_building_identification"],
        "parent_property_id": m["parent_property_id"],
        "data_year": _num(m["report_year"]),
        "property_type": m["largest_property_use_type"],
        "gfa": _num(template["gross_floor_area"]),
    })
    out["property_uses"] = [
        "; ".join(f"{s.property_type}: {s.gfa:g}" for s in rec[i].spaces) if i in rec else None for i in range(len(m))]
    for col in FUEL_COLUMNS:
        out[col] = [rec[i].utilities.by_fuel()[col.rsplit("_", 1)[0]] if i in rec else None for i in range(len(m))]
    out["problems"] = [err_by_row.get(i + 2) for i in range(len(m))]
    out = _text(out)
    status = pd.Series("scored", index=out.index)
    status[out["problems"].notna()] = "invalid_input"
    parent = out["parent_property_id"].fillna("")
    child = ~parent.str.startswith("Not Applicable") & parent.ne("") & parent.ne(out["building_id"])
    status[child] = "campus_member"           # the campus's parent row carries the whole campus
    out["screen_status"] = status
    return out


BOSTON_FUELS = {"natural_gas": "Natural Gas", "district_steam": "District Steam",
                "district_hot_water": "District Hot Water", "district_chilled_water": "District Chilled Water",
                "fuel_oil_1": "Fuel Oil 1", "fuel_oil_2": "Fuel Oil 2", "fuel_oil_4": "Fuel Oil 4",
                "fuel_oil_5_6": "Fuel Oil 5 and 6", "propane": "Propane", "diesel": "Diesel", "kerosene": "Kerosene"}
BOSTON_NOT_SCORED = {      # the city's emissions compliance status -> why a building-level figure would mislead
    "Emissions Compliance at Portfolio Level": "portfolio_member",
    "Emissions Compliance at Campus Level": "campus_member",
    "Campus - Share Water Only": "campus_member",
    "Vacant": "vacant",
    "State": "state_owned",
}


def boston(berdo: pd.DataFrame) -> pd.DataFrame:
    """The BERDO disclosure -> one canonical row per building, keeping the city's own figures for checking.

    District steam: where the city reports both steam use and steam emissions, the factor it applied
    (usually a system's verified factor, e.g. Vicinity's) is kept as `district_steam_factor_t_per_kbtu`.
    """
    from open_bps.registry import get_policy

    p = get_policy("boston_berdo")
    b = berdo
    out = pd.DataFrame({
        "jurisdiction": "boston",
        "building_id": b["BERDO ID"].astype("string").str.strip(),
        "property_name": b["Building Address"].fillna(b["Parcel Address"]),     # BERDO publishes no building names
        "owner_name": b["Parcel Owner Name"],
        "address": b["Building Address"].fillna(b["Parcel Address"]),
        "postal_code": b["Building Address Zip Code"],
        "tax_parcel_id": b["Tax Parcel ID"],
        "gfa": _num(b["Gross Floor Area (sq ft)"]),
        "property_type": b["Largest Property Type"],
        "property_uses": b["All Property Types and GFAs (sq ft)"],
        "electricity_kwh": _num(b["Electricity Usage (kWh)"]),
        "renewable_electricity_kwh": _num(b["Renewable Electricity Usage (kWh)"]),
    })
    for f, c in BOSTON_FUELS.items():
        out[f"{f}_kbtu"] = _num(b[f"{c} Usage (kBtu)"])
    steam_e = _num(b["District Steam Emissions (kgCO2e)"])
    out["district_steam_factor_t_per_kbtu"] = (steam_e / 1000 / out["district_steam_kbtu"]).where(out["district_steam_kbtu"] > 0)
    out["building_use"] = out["property_type"].map(lambda t: p.statutory_class(t) if isinstance(t, str) else None)
    out["first_compliance_year"] = _num(b["First Emissions Compliance Year"])
    out["official_ghg_tco2e"] = _num(b["Total GHG Emissions (kgCO2e)"]) / 1000
    out["official_ghg_intensity_kg"] = _num(b["GHG Emissions Intensity (kgCO2e/sq ft)"])
    out["official_standard_kg"] = _num(b["Applicable Emissions Compliance Standard (kgCO2e/sq ft)"])
    out["official_status"] = b["Emissions Compliance Status"]
    out["flexibility_measures"] = b["Flexibility Measures"]
    out = _text(out)
    status = pd.Series("scored", index=out.index)
    status[out["electricity_kwh"].isna() & out["official_ghg_tco2e"].isna()] = "no_data"
    status[out["building_use"].isna()] = "unmapped_property_type"
    status[out["gfa"].isna() | out["gfa"].le(0)] = "no_floor_area"
    for official, s in BOSTON_NOT_SCORED.items():
        status[out["official_status"].eq(official)] = s
    out["screen_status"] = status
    return out
