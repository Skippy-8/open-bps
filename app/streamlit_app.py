"""open-bps: look up a building's exposure, or underwrite retrofits across your own portfolio.

    streamlit run app.py            (or app/streamlit_app.py)

Building lookup reads $OPEN_BPS_DATA or data/scored/<city>.parquet when present (after `open-bps score all`),
otherwise the latest published release on GitHub. Portfolio underwriting runs on the file you upload (or the
built-in sample) and never sends it anywhere.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st

from open_bps import DISCLAIMER, excel

try:                                  # both entry points: `streamlit run app.py` and `streamlit run app/streamlit_app.py`
    from portfolio_tab import portfolio_tab
except ImportError:
    from app.portfolio_tab import portfolio_tab

RELEASE = "https://github.com/Skippy-8/open-bps/releases/download/data-latest/{name}"
LOCAL = Path(os.environ.get("OPEN_BPS_DATA", Path(__file__).resolve().parents[1] / "data" / "scored"))
CITY = {"Washington, DC (BEPS)": "dc", "Denver (Energize Denver)": "denver", "New York City (Local Law 97)": "nyc",
        "Boston (BERDO 2.0)": "boston"}


@st.cache_data(ttl=6 * 3600)
def load(city: str) -> tuple[pd.DataFrame, dict]:
    p, m = LOCAL / f"{city}.parquet", LOCAL / f"{city}.meta.json"
    if p.exists():
        return pd.read_parquet(p), json.loads(m.read_text()) if m.exists() else {}
    data = urllib.request.urlopen(RELEASE.format(name=f"{city}.parquet"), timeout=60).read()
    meta = json.loads(urllib.request.urlopen(RELEASE.format(name=f"{city}.meta.json"), timeout=60).read())
    return pd.read_parquet(io.BytesIO(data)), meta


def money(v) -> str:
    return "n/a" if v != v or v is None else f"${v:,.0f}"


def lookup_tab() -> None:
    label = st.selectbox("Jurisdiction", list(CITY))
    city = CITY[label]
    df, meta = load(city)
    if meta:
        st.caption(f"Rules: {meta.get('rule_version')} | built {meta.get('built_at', '')[:10]} | "
                   f"source retrieved {meta.get('source_snapshot', {}).get('retrieved_at', '')[:10]} | {meta.get('attribution', '')}")

    q = st.text_input("Search by building ID, name or address").strip().lower()
    if q:
        hits = df[df["building_id"].str.lower().eq(q)
                  | df["property_name"].fillna("").str.lower().str.contains(q, regex=False)
                  | df["address"].fillna("").str.lower().str.contains(q, regex=False)]
    else:
        hits = df.head(0)
    st.write(f"{len(hits)} match(es)")
    if len(hits):
        pick = st.selectbox("Building", hits.index,
                            format_func=lambda i: f"{hits.at[i, 'property_name']} | {hits.at[i, 'address']} | {hits.at[i, 'building_id']}")
        row = df.loc[pick].to_dict()
        st.subheader(row["property_name"])
        st.write(f"{row['property_type']} | {row['gfa']:,.0f} sq ft | status: **{row['screen_status']}**")
        if row["screen_status"] != "scored":
            st.info("No estimate for this building: " + row["screen_status"].replace("_", " "))
        elif city == "nyc":
            c = st.columns(4)
            c[0].metric("Emissions, 2024 coefficients (t)", f"{row['emissions_t_2024']:,.0f}")
            c[1].metric("Limit 2024-2029 (t)", f"{row['limit_t_2024']:,.0f}")
            c[2].metric("Penalty a year, 2024-2029", money(row["penalty_2024"]))
            c[3].metric("Penalty a year, 2030-2034", money(row["penalty_2030"]))
            st.write(f"Uses: {row['property_uses']}")
            st.caption("LL84 use held flat; 2035+ figures use DOB's projected coefficients (Estimated). Deductions and "
                       "the CY2024-2025 occupancy-group election are not modelled.")
        elif city == "boston":
            c = st.columns(4)
            c[0].metric("Emissions intensity 2025 (kg/sq ft)", f"{row['emissions_intensity_kg_2025']:.1f}")
            c[1].metric("Standard 2025-2029 (kg/sq ft)", f"{row['standard_kg_per_sqft_2025']:.1f}")
            c[2].metric("City's status", str(row["official_status"]))
            c[3].metric("ACP if unchanged, 2030", money(row["acp_2030"]))
            st.write(f"ACP that would cover 2025's excess: **{money(row['acp_2025'])}** ($234 per tCO2e)")
        elif city == "denver":
            c = st.columns(4)
            c[0].metric("Weather-normalized site EUI", f"{row['eui']:.1f}")
            c[1].metric("Final target EUI", f"{row['target_final']:.1f}")
            c[2].metric("Reduction needed", f"{row['reduction_needed_final']:.0%}")
            c[3].metric("2032 penalty if unchanged (extended)", money(row["extended_2032_penalty"]))
            st.table(pd.DataFrame({
                "Schedule": ["Extended", "Extended", "Original", "Original", "Original"],
                "Year": [2028, 2032, 2025, 2027, 2030],
                "Penalty if EUI unchanged": [money(row[k]) for k in ("extended_2028_penalty", "extended_2032_penalty",
                                                                     "original_2025_penalty", "original_2027_penalty",
                                                                     "original_2030_penalty")]}))
            st.caption("Which schedule applies depends on whether the owner opted into the 2028/2032 extension, which is not public.")
        else:
            c = st.columns(4)
            c[0].metric("BEPS standard", f"{row['standard']:.0f}" if row["standard"] == row["standard"] else "n/a")
            c[1].metric("Building metric (2019)", f"{row['metric']:.1f}" if row["metric"] == row["metric"] else "n/a")
            c[2].metric("DOEE verdict", str(row["official_meets_beps"]))
            c[3].metric("Maximum payment", money(row["max_payment"]))
            st.write(f"Pathway: **{row['pathway']}**")
            if row["payment_est_performance"] == row["payment_est_performance"]:
                st.write(f"Estimated Performance Pathway payment if the latest year's site EUI held: "
                         f"**{money(row['payment_est_performance'])}** (site EUI change so far: {row['site_eui_reduction_est']:.1%})")
        if row["screen_status"] == "scored":
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / "building.xlsx"
                if city == "nyc":
                    from open_bps.engine import nyc as nyc_engine
                    path = excel.building_workbook("nyc_ll97", nyc_engine.record(row), out, 2024, 2050)
                elif city == "boston":
                    from open_bps.engine import boston as boston_engine
                    fy = row["first_compliance_year"]
                    path = excel.building_workbook("boston_berdo", boston_engine.record(row), out,
                                                   int(fy) if fy == fy else 2025, 2050,
                                                   overrides=boston_engine.overrides(row))
                else:
                    path = (excel.denver_workbook if city == "denver" else excel.dc_workbook)(row, out)
                st.download_button("Download the workbook (live formulas, Checks tab)", path.read_bytes(),
                                   file_name=f"{city}_{row['building_id']}.xlsx")


st.set_page_config(page_title="open-bps", layout="wide")
st.title("Building performance standard exposure")
st.warning(DISCLAIMER)
tab_lookup, tab_portfolio = st.tabs(["Building lookup", "Portfolio underwriting"])
with tab_lookup:
    lookup_tab()
with tab_portfolio:
    portfolio_tab()
st.caption("Source code, methods and rule files: https://github.com/Skippy-8/open-bps")
