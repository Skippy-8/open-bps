"""Command line.

  open-bps fetch  {dc,denver,nyc,boston,all}   download a dated raw snapshot (with manifest) into <root>/raw/
  open-bps score  {dc,denver,nyc,boston,all}   build <root>/scored/<city>.parquet|csv|meta.json from the latest snapshot
  open-bps lookup CITY TEXT                    find buildings by id, name or address in the scored data
  open-bps excel  CITY ID                      write a one-building workbook (live formulas, Checks tab)
  open-bps validate                            how well the rules reproduce DOEE's and Boston's published verdicts
  open-bps rules                               rule versions and their primary sources
  open-bps analyze FILE --jurisdiction J       your own buildings: exposure, optional retrofit underwriting, workbook

Every number is a screening estimate; see DISCLAIMER.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from open_bps import DISCLAIMER, dataset, excel, registry
from open_bps.engine import boston as boston_engine
from open_bps.engine import nyc as nyc_engine
from open_bps.sources import boston as boston_src
from open_bps.sources import dc as dc_src
from open_bps.sources import denver as denver_src
from open_bps.sources import nyc as nyc_src

CITIES = ("dc", "denver", "nyc", "boston")
SOURCES = {"dc": dc_src, "denver": denver_src, "nyc": nyc_src, "boston": boston_src}
LOOKUP_COLUMNS = {
    "denver": ["eui", "target_final", "extended_2028_penalty", "extended_2032_penalty"],
    "dc": ["metric_type", "standard", "metric", "official_meets_beps", "pathway", "payment_est_performance"],
    "nyc": ["emissions_t_2024", "limit_t_2024", "penalty_2024", "penalty_2030"],
    "boston": ["emissions_t_2025", "standard_kg_per_sqft_2025", "official_status", "acp_2025", "acp_2030"],
}


def _cities(which: str) -> tuple[str, ...]:
    return CITIES if which == "all" else (which,)


def _scored(root: Path, city: str) -> pd.DataFrame:
    p = Path(root) / "scored" / f"{city}.parquet"
    if not p.exists():
        raise SystemExit(f"{p} not found; run `open-bps fetch {city}` and `open-bps score {city}` first")
    return pd.read_parquet(p)


def cmd_fetch(a) -> None:
    for c in _cities(a.city):
        folder = SOURCES[c].fetch(a.root)
        print(f"{c}: {folder}")


def cmd_score(a) -> None:
    for c in _cities(a.city):
        meta = dataset.build(a.root, c)
        print(f"{c}: {meta['rows']} buildings, {meta['screen_status_counts']} (rules {meta['rule_version']})")
        v = meta.get("validation")
        if isinstance(v, dict) and "verdicts_matching" in v:
            print(f"  verdicts matching DOEE: {v['verdicts_matching']}/{v['verdicts_compared']}")
        elif isinstance(v, dict):
            print(f"  verdicts matching the city: {v['verdict_matching']}/{v['verdict_compared']}; "
                  f"emissions {v['emissions_matching']}/{v['emissions_compared']}")
    print(f"summary: {dataset.summary(a.root)}")
    print(DISCLAIMER)


def cmd_lookup(a) -> None:
    df = _scored(a.root, a.city)
    q = a.text.lower()
    hit = df[df["building_id"].str.lower().eq(q)
             | df["property_name"].fillna("").str.lower().str.contains(q, regex=False)
             | df["address"].fillna("").str.lower().str.contains(q, regex=False)]
    cols = ["building_id", "property_name", "address", "property_type", "gfa", "screen_status"] + LOOKUP_COLUMNS[a.city]
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.max_colwidth", 40):
        print(hit[cols].head(a.limit).to_string(index=False) if len(hit) else "no match")
    print(DISCLAIMER)


def cmd_excel(a) -> None:
    df = _scored(a.root, a.city)
    row = df[df["building_id"].eq(str(a.building_id))]
    if row.empty:
        raise SystemExit(f"no {a.city} building with id {a.building_id}")
    r = row.iloc[0].to_dict()
    if r["screen_status"] != "scored":
        raise SystemExit(f"building {a.building_id} is not scored ({r['screen_status']})")
    out = Path(a.out or f"{a.city}_{a.building_id}.xlsx")
    if a.city == "nyc":
        print(excel.building_workbook("nyc_ll97", nyc_engine.record(r), out, 2024, 2050, data_note=nyc_src.ATTRIBUTION))
    elif a.city == "boston":
        start = int(r["first_compliance_year"]) if r["first_compliance_year"] == r["first_compliance_year"] else 2025
        print(excel.building_workbook("boston_berdo", boston_engine.record(r), out, start, 2050,
                                      overrides=boston_engine.overrides(r), data_note=boston_src.ATTRIBUTION))
    else:
        print((excel.denver_workbook if a.city == "denver" else excel.dc_workbook)(r, out))


def cmd_validate(a) -> None:
    found = False
    for city in ("dc", "boston"):
        meta = Path(a.root) / "scored" / f"{city}.meta.json"
        if meta.exists():
            found = True
            print(f"{city}: " + json.dumps(json.loads(meta.read_text())["validation"], indent=1))
    if not found:
        raise SystemExit("run `open-bps score dc` (or boston) first")


def cmd_rules(a) -> None:
    names = {v: k for k, v in registry.ALIASES.items()}
    for j in registry.list_jurisdictions():
        p = registry.get_policy(j)
        print(f"{names.get(j, j)}: {p.program} | {p.rule_version} | checked {p.checked_on}")
        for k, s in p.sources.items():
            print(f"   {k}: {s.url}")


def cmd_analyze(a) -> None:
    from datetime import date

    from open_bps.analyzer import PortfolioAnalyzer
    from open_bps.inputs import PortfolioValidationError
    from open_bps.underwriting.capital_stack import Financing

    try:
        pa = PortfolioAnalyzer(a.jurisdiction, blend_standard=a.blend)
        portfolio = pa.load(a.file, espm=a.espm)
    except (PortfolioValidationError, ValueError) as e:
        print(e)
        raise SystemExit(2) from None
    exposure = pa.analyze(portfolio, last=a.last_year, hold_years=a.hold)
    cols = ["building_id", "name", "gross_floor_area", "first_year_over_limit", f"cumulative_penalty_{a.hold}y", "status"]
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.max_colwidth", 40):
        print(exposure[cols].to_string(index=False))
    if a.eui_reduction is not None:
        if a.capex_per_sqft is None:
            raise SystemExit("--eui-reduction needs --capex-per-sqft")
        fin = {"cpace": lambda: Financing.cpace(a.rate, a.term, a.share),
               "debt": lambda: Financing.debt(a.share, a.rate, a.term), "cash": Financing.cash}[a.financing]()
        deals = pa.underwrite(portfolio, a.eui_reduction, fin, capex_per_sqft=a.capex_per_sqft, start_year=a.start_year,
                              hold_years=a.hold, discount_rate=a.discount, energy_cost_savings_per_sqft=a.savings_per_sqft,
                              grid=a.grid, grid_decline=a.grid_decline,
                              construction_start=date.fromisoformat(a.construction_start) if a.construction_start else None,
                              pwa=a.pwa)
        cols = ["building_id", "capex", "avoided_penalty_hold", "incentive_179d", "npv_unlevered", "irr_unlevered",
                "payback_year", "status"]
        with pd.option_context("display.width", 200, "display.max_columns", 20):
            print(deals[[c for c in cols if c in deals]].to_string(index=False))
    if a.output:
        print(pa.to_excel(a.output))
    print(DISCLAIMER)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="open-bps", description=__doc__.split("\n")[0])
    p.add_argument("--root", type=Path, default=Path("data"), help="data folder (default ./data)")
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="download a raw snapshot")
    f.add_argument("city", choices=[*CITIES, "all"])
    f.set_defaults(fn=cmd_fetch)
    s = sub.add_parser("score", help="build the scored dataset")
    s.add_argument("city", choices=[*CITIES, "all"])
    s.set_defaults(fn=cmd_score)
    lk = sub.add_parser("lookup", help="find buildings by id, name or address")
    lk.add_argument("city", choices=CITIES)
    lk.add_argument("text")
    lk.add_argument("--limit", type=int, default=20)
    lk.set_defaults(fn=cmd_lookup)
    x = sub.add_parser("excel", help="one-building workbook with live formulas")
    x.add_argument("city", choices=CITIES)
    x.add_argument("building_id")
    x.add_argument("--out")
    x.set_defaults(fn=cmd_excel)
    sub.add_parser("validate", help="the rules vs DOEE's and Boston's published verdicts").set_defaults(fn=cmd_validate)
    sub.add_parser("rules", help="rule versions and sources").set_defaults(fn=cmd_rules)
    an = sub.add_parser("analyze", help="your own buildings: exposure, retrofit underwriting, audited workbook")
    an.add_argument("file", help="portfolio CSV (see open_bps.inputs) or an ESPM export with --espm")
    an.add_argument("--jurisdiction", required=True, help="nyc_ll97 or boston_berdo (aliases nyc, boston)")
    an.add_argument("--espm", action="store_true", help="the file is an ENERGY STAR Portfolio Manager export")
    an.add_argument("--blend", action="store_true", help="use the opt-in blended standard (Boston)")
    an.add_argument("--last-year", type=int, default=2050)
    an.add_argument("--hold", type=int, default=10, help="hold period in years (default 10)")
    an.add_argument("--eui-reduction", type=float, help="retrofit: cut in every fuel's use, e.g. 0.3")
    an.add_argument("--capex-per-sqft", type=float, help="retrofit capex per sq ft ($)")
    an.add_argument("--financing", choices=["cpace", "debt", "cash"], default="cpace")
    an.add_argument("--rate", type=float, default=0.07, help="financing rate (assumption; default 7%%)")
    an.add_argument("--term", type=int, default=20, help="financing term in years (default 20)")
    an.add_argument("--share", type=float, default=1.0, help="share financed: C-PACE share or debt loan-to-cost")
    an.add_argument("--discount", type=float, default=0.08, help="discount rate (default 8%%)")
    an.add_argument("--savings-per-sqft", type=float, default=0.0, help="energy cost savings, $ per sq ft a year")
    an.add_argument("--start-year", type=int, help="first year of the hold (default: this year)")
    an.add_argument("--grid", choices=["static_statutory", "dynamic_grid_projection"], default="static_statutory")
    an.add_argument("--grid-decline", type=float, default=0.0, help="annual decline for the grid scenario")
    an.add_argument("--construction-start", help="retrofit construction start (YYYY-MM-DD), for section 179D")
    an.add_argument("--pwa", action="store_true", help="prevailing wage and apprenticeship requirements met (179D)")
    an.add_argument("--output", help="write the audited workbook here (.xlsx)")
    an.set_defaults(fn=cmd_analyze)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
