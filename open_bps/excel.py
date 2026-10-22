"""One-building Excel workbook: inputs with sources, live-formula exposure, and a Checks tab.

Every calculation is a formula over named input cells (no typed numbers in calculations other than 0 and
1), so a reader can audit or change any assumption. The engine's own results sit on the Checks tab as
labelled reference values; a check passes when the workbook's formulas reproduce them.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName

from open_bps import DISCLAIMER
from open_bps import rules as _rules

BLUE, BOLD, GREY = Font(color="0000FF"), Font(bold=True), Font(color="808080", italic=True)
WARN = PatternFill("solid", fgColor="FFF2CC")
TOL = 0.01


def _name(wb: Workbook, name: str, sheet: str, cell: str) -> None:
    wb.defined_names[name] = DefinedName(name, attr_text=f"'{sheet}'!${cell[0]}${cell[1:]}")


def _head(ws, title: str, attribution: str) -> int:
    ws["A1"] = DISCLAIMER
    ws["A1"].font, ws["A1"].fill = BOLD, WARN
    ws["A2"] = title
    ws["A2"].font = Font(bold=True, size=13)
    ws["A3"] = f"Data: {attribution}"
    ws["A3"].font = GREY
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 70
    return 5


def _inputs(wb, ws, start: int, items: list[tuple[str, str, object, str, str]]) -> int:
    """items: (defined name, label, value, number format, source). Returns the next free row."""
    for j, h in enumerate(["Input", "Value", "Source"]):
        ws.cell(start, 1 + j, h).font = BOLD
    r = start
    for name, label, value, fmt, source in items:
        r += 1
        ws.cell(r, 1, label)
        c = ws.cell(r, 2, value)
        c.font, c.number_format = BLUE, fmt
        ws.cell(r, 3, source).font = GREY
        _name(wb, name, ws.title, f"B{r}")
    return r + 2


def _checks(wb, rows: list[tuple[str, str, float]]) -> None:
    """rows: (label, formula giving the workbook value, engine value)."""
    ws = wb.create_sheet("Checks")
    for j, h in enumerate(["Check", "Workbook", "Engine (reference)", "Result"]):
        ws.cell(1, 1 + j, h).font = BOLD
    _name(wb, "Tolerance", "Checks", f"B{len(rows) + 4}")
    for i, (label, formula, engine_value) in enumerate(rows, start=2):
        ws.cell(i, 1, label)
        ws.cell(i, 2, formula).number_format = "#,##0.00"
        c = ws.cell(i, 3, engine_value)
        c.font, c.number_format = BLUE, "#,##0.00"
        ws.cell(i, 4, f'=IF(ABS(B{i}-C{i})<=Tolerance,"PASS","FAIL")').font = BOLD
    n = len(rows) + 2
    ws.cell(n, 1, "All checks pass").font = BOLD
    ws.cell(n, 4, f'=IF(COUNTIF(D2:D{n - 1},"PASS")=ROWS(D2:D{n - 1}),"PASS","FAIL")').font = BOLD
    ws.cell(n + 2, 1, "Tolerance ($ or kBtu)")
    ws.cell(n + 2, 2, TOL).font = BLUE
    ws.column_dimensions["A"].width = 44
    for col in "BC":
        ws.column_dimensions[col].width = 18


def _sources(wb, r: dict) -> None:
    ws = wb.create_sheet("Sources")
    ws["A1"], ws["A1"].font = f"Rules: {r['rule_version']} (checked {r['checked_on']})", BOLD
    for i, (key, src) in enumerate(r["sources"].items(), start=3):
        ws.cell(i, 1, key)
        ws.cell(i, 2, src.get("title", src.get("section", "")))
        ws.cell(i, 3, src["url"])
    ws.column_dimensions["B"].width = 70


def denver_workbook(row: dict, out: Path, through: int = 2035) -> Path:
    """`row`: one scored Denver building (canonical + engine columns)."""
    r = _rules.load("denver")
    wb = Workbook()
    ws = wb.active
    ws.title = "Building"
    start = _head(ws, f"Energize Denver exposure: {row['property_name']} (Building ID {row['building_id']})",
                  "Energize Denver Master Dataset (City and County of Denver), as is; not for engineering purposes")
    tg = "Energize Denver Technical Guidance v3 (April 2025)"
    ext, orig = r["schedules"]["extended"], r["schedules"]["original"]
    nxt = _inputs(wb, ws, start, [
        ("GFA", "Gross floor area (sq ft)", row["gfa"], "#,##0", "Master Dataset: Master Sq Ft"),
        ("EUI", "Weather-normalized site EUI (kBtu/sq ft), held flat", row["eui"], "0.0",
         f"Master Dataset, data year {int(row['data_year']) if row.get('data_year') == row.get('data_year') else 'n/a'}; before city credits, so an upper bound"),
        ("T_First", "First interim target EUI", row["target_first_interim"], "0.0", "Master Dataset"),
        ("T_Second", "Second interim target EUI", row["target_second_interim"], "0.0", "Master Dataset"),
        ("T_Final", "Adjusted final target EUI", row["target_final"], "0.0", "Master Dataset"),
        ("Rate_Ext", "Penalty rate, extended schedule ($/kBtu)", ext["rate_per_kbtu"], "$0.00", f"{tg}, Table 17 (two periods)"),
        ("Rate_Orig", "Penalty rate, original schedule ($/kBtu)", orig["rate_per_kbtu"], "$0.00", f"{tg}, Table 17 (three periods)"),
    ])
    ws.cell(nxt, 1, "Exposure if EUI stays at its latest value").font = BOLD
    hdr = nxt + 1
    for j, h in enumerate(["Schedule", "Year", "Target EUI", "kBtu over target", "Penalty ($)"]):
        ws.cell(hdr, 1 + j, h).font = BOLD
    lines = [("Extended (2028/2032)", ext["target_years"]["first_interim"], "T_First", "Rate_Ext"),
             ("Extended (2028/2032)", ext["target_years"]["final"], "T_Final", "Rate_Ext")]
    lines += [("Extended, annual after final", y, "T_Final", "Rate_Ext") for y in range(ext["target_years"]["final"] + 1, through + 1)]
    lines += [("Original (2025/2027/2030)", orig["target_years"][k], t, "Rate_Orig")
              for k, t in (("first_interim", "T_First"), ("second_interim", "T_Second"), ("final", "T_Final"))]
    first = hdr + 1
    for i, (label, year, target, rate) in enumerate(lines, start=first):
        ws.cell(i, 1, label)
        ws.cell(i, 2, year)
        ws.cell(i, 3, f"={target}").number_format = "0.0"
        ws.cell(i, 4, f"=MAX(0,(EUI-C{i})*GFA)").number_format = "#,##0"
        ws.cell(i, 5, f"=D{i}*{rate}").number_format = "$#,##0"
    n_ext = 2 + (through - ext["target_years"]["final"])
    last_ext = first + n_ext - 1
    tot = first + len(lines) + 1
    ws.cell(tot, 1, f"Extended schedule, cumulative through {through}").font = BOLD
    ws.cell(tot, 5, f"=SUM(E{first}:E{last_ext})").number_format = "$#,##0"
    ws.cell(tot + 1, 1, "Reduction needed to reach the final target").font = BOLD
    ws.cell(tot + 1, 5, "=MAX(0,1-T_Final/EUI)").number_format = "0.0%"
    _name(wb, "Cum_Ext", "Building", f"E{tot}")

    yrs = ext["target_years"]
    _checks(wb, [
        (f"Penalty {yrs['first_interim']} (extended)", f"=Building!E{first}", row[f"extended_{yrs['first_interim']}_penalty"]),
        (f"Penalty {yrs['final']} (extended)", f"=Building!E{first + 1}", row[f"extended_{yrs['final']}_penalty"]),
        (f"Cumulative through {through} (extended)", "=Cum_Ext", row[f"extended_cumulative_penalty_through_{through}"]),
        (f"Penalty {orig['target_years']['final']} (original)", f"=Building!E{first + len(lines) - 1}",
         row[f"original_{orig['target_years']['final']}_penalty"]),
    ])
    _sources(wb, r)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out


def dc_workbook(row: dict, out: Path) -> Path:
    """`row`: one scored DC building."""
    r = _rules.load("dc")
    wb = Workbook()
    ws = wb.active
    ws.title = "Building"
    start = _head(ws, f"DC BEPS Cycle 1 exposure: {row['property_name']} (Portfolio Manager ID {row['building_id']})",
                  "DOEE via Open Data DC (CC BY 4.0)")
    gb = "DOEE BEPS Guidebook v1.2 (Aug 2026)"
    num = lambda v: None if v != v else v  # noqa: E731  (NaN -> blank cell)
    nxt = _inputs(wb, ws, start, [
        ("GFA", "Gross floor area (sq ft)", row["gfa"], "#,##0", "DOEE disclosure (reported GFA)"),
        ("Metric_Type", "BEPS metric type", row["metric_type"], "@", "DOEE disclosure"),
        ("Standard", "BEPS standard for the property type", num(row["standard"]), "0.0", "DOEE disclosure"),
        ("Metric", "Building's BEPS metric (metric year)", num(row["metric"]), "0.0", "DOEE disclosure (frozen baseline)"),
        ("Base_EUI", "Site EUI, average of 2018-2019", num(row["site_eui_baseline"]), "0.0", "DOEE benchmarking; Estimated proxy for Adjusted Site EUI"),
        ("Latest_EUI", "Site EUI, latest reported year", num(row["site_eui_latest"]), "0.0", "DOEE benchmarking"),
        ("Req_Cut", "Performance Pathway required site EUI reduction", r["pathways"]["performance"]["required_reduction"], "0%", f"{gb}, Ch. 3.1"),
        ("Pay_PSF", "Maximum payment per sq ft ($)", r["max_payment"]["per_sq_ft_gfa"], "$0.00", f"{gb}, Ch. 7"),
        ("Pay_Cap", "Maximum payment cap per building ($)", r["max_payment"]["cap_per_building"], "$#,##0", f"{gb}, Ch. 7"),
    ])
    ws.cell(nxt, 1, "Results").font = BOLD
    rows = [("Meets the BEPS standard (metric year)", '=IF(Metric_Type="ENERGYSTARSCORE",Metric>=Standard,Metric<=Standard)', "General"),
            ("Maximum alternative compliance payment", "=MIN(GFA*Pay_PSF,Pay_Cap)", "$#,##0"),
            ("Site EUI reduction so far (Estimated)", "=IF(Base_EUI>0,1-Latest_EUI/Base_EUI,0)", "0.0%"),
            ("Performance Pathway payment if latest year held (Estimated)",
             "=MIN(GFA*Pay_PSF,Pay_Cap)*(1-MIN(1,MAX(0,IF(Base_EUI>0,1-Latest_EUI/Base_EUI,0))/Req_Cut))", "$#,##0")]
    for i, (label, f, fmt) in enumerate(rows, start=nxt + 1):
        ws.cell(i, 1, label)
        ws.cell(i, 2, f).number_format = fmt
    _name(wb, "Max_Pay", "Building", f"B{nxt + 2}")
    _name(wb, "PP_Pay", "Building", f"B{nxt + 4}")
    checks = [("Maximum payment", "=Max_Pay", row["max_payment"])]
    if row.get("payment_est_performance") == row.get("payment_est_performance"):
        checks.append(("Performance Pathway payment (Estimated)", "=PP_Pay", row["payment_est_performance"]))
    _checks(wb, checks)
    _sources(wb, r)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out



# ---- GHG jurisdictions (NYC LL97, Boston BERDO) -------------------------------------------------------------
def _col(i: int) -> str:
    s = ""
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def building_workbook(jurisdiction: str, building, out: Path, first: int, last: int, blend_standard: bool = False,
                      overrides: dict | None = None, data_note: str = "your data") -> Path:
    """A GHG building's exposure year by year, every figure a formula over named inputs.

    Spaces: each space's sq ft times its class's limit per compliance period, summed into the building limit.
    Exposure: per year, fuel use times that year's factors (electricity after the zero-emission share and any
    renewable kWh), the limit for the year's period, the excess and the penalty. Checks: the engine's figures.
    Years run from `first` to `last`, stopping before any year the policy cannot price (e.g. no factor yet).
    """
    from open_bps.engine import blend, ghg
    from open_bps.policy import FACTOR_UNITS
    from open_bps.registry import get_policy

    p = get_policy(jurisdiction)
    use = {f: v for f, v in building.utilities.by_fuel().items() if v}
    results = []
    for y in range(first, last + 1):
        r = ghg.assess(p, building, y, blend_standard=blend_standard, overrides=overrides)
        if r.problems:
            if not results:
                raise ValueError(f"cannot price {y}: " + "; ".join(r.problems))
            break
        results.append(r)
    years = [r.year for r in results]
    periods = [q for q in p.compliance_periods if any(q.covers(y) for y in years)]

    wb = Workbook()
    ws = wb.active
    ws.title = "Building"
    start = _head(ws, f"{p.program} exposure: {building.name or building.building_id} (ID {building.building_id})", data_note)
    src = lambda key: p.sources[key].title or key  # noqa: E731
    items = [("GFA", "Gross floor area (sq ft)", building.gross_floor_area, "#,##0", data_note),
             ("Rate", "Penalty per tCO2e over the limit ($)", ghg.penalty_rate(p), "$#,##0",
              f"{src(p.penalty.source)}; {p.penalty.section or ''}"),
             ("Renew", "Renewable electricity deducted (kWh)", building.utilities.renewable_electricity_kwh
              if p.electricity and p.electricity.subtract_renewable_kwh else 0, "#,##0",
              data_note if p.electricity and p.electricity.subtract_renewable_kwh else f"{p.id} has no such deduction")]
    for f, v in use.items():
        items.append((f"Use_{f}", f"{f.replace('_', ' ').capitalize()} ({'kWh' if f == 'electricity' else 'kBtu'} a year), held flat",
                      v, "#,##0", data_note))
    _inputs(wb, ws, start, items)

    # Spaces: limits by period for the class each space is counted at
    sp = wb.create_sheet("Spaces")
    lim0 = blend.limit(p, list(building.spaces), years[0], blend=blend_standard)
    head = ["Property type", "Law's class", "Counted at", "Sq ft"] + [f"Limit {q.id} (t/sf)" for q in periods] \
        + [f"Contribution {q.id} (t)" for q in periods]
    for j, h in enumerate(head, start=1):
        sp.cell(1, j, h).font = BOLD
    n = len(lim0.spaces)
    for i, s in enumerate(lim0.spaces, start=2):
        sp.cell(i, 1, s.property_type)
        sp.cell(i, 2, s.statutory_class)
        sp.cell(i, 3, s.applied_class)
        c = sp.cell(i, 4, s.gfa)
        c.font, c.number_format = BLUE, "#,##0"
        for k, q in enumerate(periods):
            c = sp.cell(i, 5 + k, p.threshold(s.applied_class, q.start_year))
            c.font, c.number_format = BLUE, "0.000000000"
            lc = _col(5 + k)
            sp.cell(i, 5 + len(periods) + k, f"=D{i}*{lc}{i}").number_format = "#,##0.00"
    tot = n + 3
    sp.cell(tot, 1, "Building limit (tCO2e a year)").font = BOLD
    for k in range(len(periods)):
        cc = _col(5 + len(periods) + k)
        sp.cell(tot, 5 + len(periods) + k, f"=SUM({cc}2:{cc}{n + 1})").number_format = "#,##0.00"
        _name(wb, f"Limit_P{k + 1}", "Spaces", f"{cc}{tot}")
    th = p.thresholds
    sp.cell(tot + 2, 1, f"Limits: {src(th.source)}, {th.section or ''} (converted from {th.unit} to t/sf)").font = GREY
    sp.cell(tot + 3, 1, f"Method: {lim0.method}. " + " ".join(lim0.notes)).font = GREY
    sp.column_dimensions["A"].width = 44

    # Exposure: one row per year
    ex = wb.create_sheet("Exposure")
    fuels = list(use)
    head = ["Year", "Period", "Zero-emission share of grid kWh"] + [f"Factor: {f} (t per {'kWh' if f == 'electricity' else 'kBtu'})" for f in fuels] \
        + ["Electricity counted (kWh)", "Emissions (tCO2e)", "Limit (tCO2e)", "Excess (tCO2e)", "Penalty ($)", "Estimated"]
    for j, h in enumerate(head, start=1):
        ex.cell(1, j, h).font = BOLD
    fc = {f: _col(4 + j) for j, f in enumerate(fuels)}
    c_cnt, c_em, c_lim, c_exc, c_pen = (_col(4 + len(fuels) + k) for k in range(5))
    for i, r in enumerate(results, start=2):
        y = r.year
        ex.cell(i, 1, y)
        ex.cell(i, 2, r.period)
        c = ex.cell(i, 3, p.rps_share(y))
        c.font, c.number_format = BLUE, "0%"
        terms = []
        for f in fuels:
            fac = (overrides or {}).get(f)
            if fac is None:
                fac = p.factor(f, y)[0]
            c = ex.cell(i, 4 + fuels.index(f), fac)
            c.font, c.number_format = BLUE, "0.000000000"
            terms.append(f"{c_cnt}{i}*{fc[f]}{i}" if f == "electricity" else f"Use_{f}*{fc[f]}{i}")
        ex.cell(i, 4 + len(fuels), "=MAX(0,Use_electricity*(1-C{0})-Renew)".format(i) if "electricity" in use else 0)
        ex.cell(i, 5 + len(fuels), "=" + ("+".join(terms) or "0")).number_format = "#,##0.00"
        k = next(j for j, q in enumerate(periods) if q.covers(y))
        ex.cell(i, 6 + len(fuels), f"=Limit_P{k + 1}").number_format = "#,##0.00"
        ex.cell(i, 7 + len(fuels), f"=MAX(0,{c_em}{i}-{c_lim}{i})").number_format = "#,##0.00"
        ex.cell(i, 8 + len(fuels), f"={c_exc}{i}*Rate").number_format = "$#,##0"
        ex.cell(i, 9 + len(fuels), "Estimated" if r.estimated else "")
    last_row = len(results) + 1
    ex.cell(last_row + 2, 1, f"Cumulative penalty {years[0]}-{years[-1]}").font = BOLD
    ex.cell(last_row + 2, 8 + len(fuels), f"=SUM({c_pen}2:{c_pen}{last_row})").number_format = "$#,##0"
    _name(wb, "Cum_Penalty", "Exposure", f"{c_pen}{last_row + 2}")
    notes = [f"{f}: {src(p.emission_factors[f].source)}, {p.emission_factors[f].section or ''} "
             f"(converted from {p.emission_factors[f].unit}; {FACTOR_UNITS[p.emission_factors[f].unit][0]} basis)"
             for f in fuels if f in p.emission_factors and f not in (overrides or {})]
    notes += [f"{f}: factor supplied by the user" for f in (overrides or {}) if f in use]
    if p.electricity:
        notes.append(f"Zero-emission share: {src(p.electricity.source)}, {p.electricity.section or ''}")
    notes.append("Use is held at the latest values ('cost of inaction'). 'Estimated' rows use factors from guidance, not law.")
    for j, t in enumerate(notes):
        ex.cell(last_row + 4 + j, 1, t).font = GREY
    ex.column_dimensions["A"].width = 10

    pick = sorted({0, len(results) // 2, len(results) - 1})
    checks = [(f"Limit {results[0].year} (t)", f"=Exposure!{c_lim}2", results[0].limit_t)]
    for j in pick:
        r = results[j]
        checks.append((f"Emissions {r.year} (t)", f"=Exposure!{c_em}{j + 2}", r.emissions_t))
        checks.append((f"Penalty {r.year} ($)", f"=Exposure!{c_pen}{j + 2}", r.penalty))
    checks.append((f"Cumulative penalty {years[0]}-{years[-1]} ($)", "=Cum_Penalty", sum(r.penalty for r in results)))
    _checks(wb, checks)
    ws_s = wb.create_sheet("Sources")
    ws_s["A1"], ws_s["A1"].font = f"Rules: {p.rule_version} (checked {p.checked_on})", BOLD
    for i, (key, s) in enumerate(p.sources.items(), start=3):
        ws_s.cell(i, 1, key)
        ws_s.cell(i, 2, s.title or s.section or "")
        ws_s.cell(i, 3, s.url)
    ws_s.column_dimensions["B"].width = 70
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
