"""Command line.

  open-bps fetch  {dc,denver,all}        download a dated raw snapshot (with manifest) into <root>/raw/
  open-bps score  {dc,denver,all}        build <root>/scored/<city>.parquet|csv|meta.json from the latest snapshot
  open-bps lookup {dc,denver} TEXT       find buildings by id, name or address in the scored data
  open-bps excel  {dc,denver} ID         write a one-building workbook (live formulas, Checks tab)
  open-bps validate                      how well the DC rule reproduces DOEE's published verdicts
  open-bps rules                         rule versions and their primary sources

Every number is a screening estimate; see DISCLAIMER.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from open_bps import DISCLAIMER, dataset, excel
from open_bps import rules as _rules
from open_bps.sources import dc as dc_src
from open_bps.sources import denver as denver_src

CITIES = ("dc", "denver")


def _cities(which: str) -> tuple[str, ...]:
    return CITIES if which == "all" else (which,)


def _scored(root: Path, city: str) -> pd.DataFrame:
    p = Path(root) / "scored" / f"{city}.parquet"
    if not p.exists():
        raise SystemExit(f"{p} not found; run `open-bps fetch {city}` and `open-bps score {city}` first")
    return pd.read_parquet(p)


def cmd_fetch(a) -> None:
    for c in _cities(a.city):
        folder = (dc_src if c == "dc" else denver_src).fetch(a.root)
        print(f"{c}: {folder}")


def cmd_score(a) -> None:
    for c in _cities(a.city):
        meta = dataset.build(a.root, c)
        print(f"{c}: {meta['rows']} buildings, {meta['screen_status_counts']} (rules {meta['rule_version']})")
        if "validation" in meta:
            v = meta["validation"]
            print(f"  verdicts matching DOEE: {v['verdicts_matching']}/{v['verdicts_compared']}")
    print(f"summary: {dataset.summary(a.root)}")
    print(DISCLAIMER)


def cmd_lookup(a) -> None:
    df = _scored(a.root, a.city)
    q = a.text.lower()
    hit = df[df["building_id"].str.lower().eq(q)
             | df["property_name"].fillna("").str.lower().str.contains(q, regex=False)
             | df["address"].fillna("").str.lower().str.contains(q, regex=False)]
    cols = (["building_id", "property_name", "address", "property_type", "gfa", "screen_status"]
            + (["eui", "target_final", "extended_2028_penalty", "extended_2032_penalty"] if a.city == "denver"
               else ["metric_type", "standard", "metric", "official_meets_beps", "pathway", "payment_est_performance"]))
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
    print((excel.denver_workbook if a.city == "denver" else excel.dc_workbook)(r, out))


def cmd_validate(a) -> None:
    meta = Path(a.root) / "scored" / "dc.meta.json"
    if not meta.exists():
        raise SystemExit("run `open-bps score dc` first")
    print(json.dumps(json.loads(meta.read_text())["validation"], indent=1))


def cmd_rules(a) -> None:
    for c in CITIES:
        r = _rules.load(c)
        print(f"{c}: {r['program']} | {r['rule_version']} | checked {r['checked_on']}")
        for k, s in r["sources"].items():
            print(f"   {k}: {s['url']}")


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
    sub.add_parser("validate", help="DC rule vs DOEE's published verdicts").set_defaults(fn=cmd_validate)
    sub.add_parser("rules", help="rule versions and sources").set_defaults(fn=cmd_rules)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
