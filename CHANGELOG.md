# Changelog

## 0.2.0 (2026-10-22)

New jurisdictions, your own portfolio, retrofit underwriting. Every 0.1.0 interface and output is unchanged.

**Jurisdictions**
- **Policy registry.** The rule files moved to `open_bps/jurisdictions/` and are validated by a Pydantic
  `JurisdictionPolicy`. `rules.load()` still returns the 0.1.0 dicts.
- **NYC Local Law 97:** 1 RCNY §103-14 limits for 60 property types and 5 periods, with DOB coefficients.
  The engine reproduces DOB's worked examples. A scored LL84 dataset is added.
- **Boston BERDO 2.0:** Table 1 standards, the Appendix A type map, projected grid factors, RPS shares and
  the ACP. A scored disclosure dataset reproduces the city's verdicts for 901 of 901 buildings.
- **Mixed-use buildings:** blending for NYC's floor-area-weighted limit, and for Boston's default and opt-in
  blend.
- **Generic GHG engine.** A fuel or property type the rule cannot price is flagged, never estimated.

**Your own buildings**
- **Inputs:** `BuildingRecord` and `PortfolioInput` with row-level errors, and an ENERGY STAR Portfolio Manager
  adapter.
- **Underwriting:** avoided penalties, energy savings and §179D (gated at a 2026-06-30 construction start),
  financed with C-PACE, debt or cash. Results are NPV, IRR and payback, with a statutory or cleaner-grid
  scenario.
- **Workbooks:** an Underwriting sheet, and a multi-building portfolio workbook. Every figure is a live formula,
  reconciled on the Checks sheet.

**Tools**
- `open_bps.PortfolioAnalyzer` and `open-bps analyze`.
- An MCP server, `open-bps-mcp` (`pip install "open-bps[mcp]"`).
- The app has a portfolio underwriting tab, and `streamlit run app.py` works.

## 0.1.0 (2026-10-20)

First release: Washington, DC (BEPS Compliance Cycle 1) and Denver (Energize Denver, buildings 25,000 sq ft and larger).

- **Rule files** from DOEE's BEPS Guidebook v1.2 (Aug 2026) and Energize Denver Technical Guidance v3 (Apr 2025).
- **Fetchers** that write dated raw snapshots with SHA-256 manifests.
- **Scored datasets** with metadata, a quality gate and `SUMMARY.md`.
- **DC validation:** the encoded rule reproduces 1,797 of 1,806 published DOEE verdicts.
- **One-building Excel workbooks** with live formulas and a Checks tab.
- **A Streamlit lookup app.**
- **A monthly data refresh** published as GitHub releases.
