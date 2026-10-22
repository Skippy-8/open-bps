"""Portfolio underwriting tab: upload buildings (template CSV or an ESPM export), set a retrofit and its financing,
see the stranded-asset table, and download the audited workbook. Files stay in this session."""
from __future__ import annotations

import io
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from open_bps.analyzer import PortfolioAnalyzer
from open_bps.inputs import PortfolioInput, PortfolioValidationError
from open_bps.underwriting.capital_stack import Financing

JURISDICTIONS = {"New York City (Local Law 97)": "nyc_ll97", "Boston (BERDO 2.0)": "boston_berdo"}
SAMPLE = """building_id,name,gross_floor_area,property_type_1,gfa_1,property_type_2,gfa_2,electricity_kwh,natural_gas_therms,fuel_oil_2_kbtu
B1,Sample office tower,250000,Office,220000,Retail Store,30000,5200000,90000,
B2,Sample apartments,120000,Multifamily Housing,120000,,,1100000,95000,450000
B3,Sample lab,80000,Laboratory,80000,,,4800000,60000,
"""
ESPM_SAMPLE = ("Property Id,Property Name,Property GFA - Calculated (Buildings and Parking) (ft²),"
               "List of All Property Use Types (GFA) (ft²),Electricity Use - Grid Purchase (kWh),"
               "Natural Gas Use (kBtu),District Steam Use (kBtu),Fuel Oil #2 Use (kBtu)\n"
               '1001,Sample office tower,250000,"Office (220000.0), Retail Store (30000.0)",5200000,9000000,,\n'
               "1002,Sample apartments,120000,Multifamily Housing (120000.0),1100000,9500000,,450000\n")


def _read(upload, espm: bool, pa: PortfolioAnalyzer):
    suffix = Path(upload.name).suffix.lower() or ".csv"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(upload.getvalue())
    return pa.load(f.name, espm=espm)


def portfolio_tab() -> None:
    st.subheader("Underwrite retrofits across your buildings")
    if st.toggle("Show file templates", key="pf_templates"):
        c = st.columns(2)
        c[0].download_button("Portfolio template (CSV)", SAMPLE, file_name="open_bps_portfolio_template.csv")
        c[1].download_button("ESPM export example (CSV)", ESPM_SAMPLE, file_name="espm_export_example.csv")
        st.caption("Template: one row per building; property_type_N / gfa_N pairs use ENERGY STAR Portfolio Manager "
                   "property types and must add up to gross_floor_area within 1%. Electricity in kWh is required "
                   "(blank is missing data, not zero); other fuels in kBtu, natural gas in kBtu or therms.")
    label = st.selectbox("Standard", list(JURISDICTIONS), key="pf_jurisdiction")
    upload = st.file_uploader("Your portfolio (template CSV, or an ESPM export as CSV/XLSX)", type=["csv", "xlsx"])
    espm = st.checkbox("The file is an ENERGY STAR Portfolio Manager export", key="pf_espm")
    use_sample = st.checkbox("Use the built-in sample portfolio", value=upload is None, key="pf_sample")

    st.markdown("**Retrofit and financing** (your assumptions)")
    a = st.columns(4)
    cut = a[0].number_input("Cut in energy use (%)", 1.0, 100.0, 30.0, key="pf_cut") / 100
    capex = a[1].number_input("Capex ($ per sq ft)", 0.5, 500.0, 25.0, key="pf_capex")
    savings = a[2].number_input("Energy cost savings ($ per sq ft a year)", 0.0, 50.0, 0.0, key="pf_savings")
    disc = a[3].number_input("Discount rate (%)", 0.0, 30.0, 8.0, key="pf_disc") / 100
    b = st.columns(4)
    kind = b[0].selectbox("Financing", ["cpace", "debt", "cash"], key="pf_fin",
                          format_func={"cpace": "C-PACE", "debt": "Debt / equity", "cash": "Cash"}.get)
    rate = b[1].number_input("Financing rate (%)", 0.0, 25.0, 7.0, key="pf_rate") / 100
    term = int(b[2].number_input("Term (years)", 1, 40, 20, key="pf_term"))
    share = b[3].number_input("Share financed / loan-to-cost (%)", 1.0, 100.0, 100.0 if kind == "cpace" else 60.0,
                              key="pf_share") / 100
    d = st.columns(4)
    start = int(d[0].number_input("First year", 2024, 2045, max(date.today().year, 2025), key="pf_start"))
    hold = int(d[1].number_input("Hold (years)", 1, 25, 10, key="pf_hold"))
    grid = d[2].selectbox("Grid", ["static_statutory", "dynamic_grid_projection"], key="pf_grid",
                          format_func={"static_statutory": "Statutory factors",
                                       "dynamic_grid_projection": "Cleaner-grid scenario"}.get)
    decline = d[3].number_input("Scenario: grid factor decline (% a year)", 0.0, 20.0, 3.0, key="pf_decline") / 100
    e = st.columns(2)
    started = e[0].checkbox("Retrofit construction began by 2026-06-30 (section 179D)", key="pf_179d")
    pwa = e[1].checkbox("Prevailing wage and apprenticeship met", key="pf_pwa")

    if not st.button("Run", key="pf_run"):
        return
    pa = PortfolioAnalyzer(JURISDICTIONS[label])
    try:
        if use_sample or upload is None:
            sample = pd.read_csv(io.StringIO(SAMPLE), dtype=str, keep_default_na=False)
            portfolio = PortfolioInput.from_dataframe(sample, pa.allowed_property_types)
        else:
            portfolio = _read(upload, espm, pa)
    except PortfolioValidationError as err:
        st.error(f"{len(err.errors)} problem(s) in the file. Nothing was guessed; fix these and upload again.")
        st.code("\n".join(err.errors))
        return
    fin = {"cpace": lambda: Financing.cpace(rate, term, share), "debt": lambda: Financing.debt(share, rate, term),
           "cash": Financing.cash}[kind]()
    exposure = pa.analyze(portfolio, first=start, hold_years=hold)
    deals = pa.underwrite(portfolio, cut, fin, capex_per_sqft=capex, start_year=start, hold_years=hold,
                          discount_rate=disc, energy_cost_savings_per_sqft=savings, grid=grid, grid_decline=decline,
                          construction_start=date(2026, 6, 1) if started else None, pwa=pwa)
    table = exposure[["building_id", "name", "gross_floor_area", "first_year_over_limit",
                      f"cumulative_penalty_{hold}y", "problems"]].merge(
        deals[[c for c in ("building_id", "capex", "incentive_179d", "npv_unlevered", "irr_unlevered", "payback_year")
               if c in deals]], on="building_id", how="left")
    table = table.rename(columns={"first_year_over_limit": "first year over limit",
                                  f"cumulative_penalty_{hold}y": f"penalties over {hold} years, unchanged ($)",
                                  "npv_unlevered": "retrofit NPV ($)", "irr_unlevered": "retrofit IRR",
                                  "incentive_179d": "179D cash value ($)", "payback_year": "payback year"})
    st.markdown("**Stranded-asset risk**")
    st.dataframe(table, hide_index=True)
    st.caption(f"Rules {pa.policy.rule_version}. Use held flat; figures are screening estimates.")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = pa.to_excel(Path(tmp) / "underwriting.xlsx")
            st.download_button("Download audited Excel underwriting model", path.read_bytes(),
                               file_name=f"open_bps_{pa.policy.id}_underwriting.xlsx", key="pf_download")
    except ValueError as err:
        st.info(f"No workbook: {err}")
