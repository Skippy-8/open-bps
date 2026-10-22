"""Command line.

  open-bps fetch  {dc,denver,nyc,boston,all}   download a dated raw snapshot (with manifest) into <root>/raw/
  open-bps score  {dc,denver,nyc,boston,all}   build <root>/scored/<city>.parquet|csv|meta.json from the latest snapshot
  open-bps lookup CITY TEXT                    find buildings by id, name or address in the scored data
  open-bps excel  CITY ID                      write a one-building workbook (live formulas, Checks tab)
  open-bps validate                            how well the rules reproduce DOEE's and Boston's published verdicts
  open-bps rules                               rule versions and their primary sources

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
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
