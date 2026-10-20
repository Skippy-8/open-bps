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

