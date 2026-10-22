"""Write the offline test fixtures in tests/fixtures/ from a full raw snapshot.

    python scripts/make_fixtures.py --root data

DC: a seeded sample of the BEPS disclosure that always includes every building whose published verdict
the plain rule does not reproduce, buildings with EUI distances, and buildings on each pathway, plus all
benchmarking years for those buildings. Denver: a seeded sample covering every screen_status. NYC: the first
400 LL84 rows by property id, only the columns the ESPM adapter reads. Boston: every "Action Needed" building,
a sample of "In Compliance", blended standards, steam users, the standard exceptions and each other status.
Sources and licences: tests/fixtures/README.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from open_bps import canonical
from open_bps.adapters.espm import ALL_USES, COLUMNS, TOP_USES
from open_bps.engine import boston as boston_engine
from open_bps.engine import dc as dc_engine
from open_bps.sources import boston as boston_src
from open_bps.sources import dc as dc_src
from open_bps.sources import denver as denver_src
from open_bps.sources import latest_snapshot
from open_bps.sources import nyc as nyc_src

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SEED = 20261020


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--root", type=Path, default=Path("data"))
    root = a.parse_args().root
    OUT.mkdir(parents=True, exist_ok=True)

    perf, bench = dc_src.load(latest_snapshot(root, "dc"))
    scored = dc_engine.score(canonical.dc(perf, bench))
    ids = set(scored.loc[scored["verdict_matches_official"].eq(False), "building_id"])
    ids |= set(scored.loc[scored["eui_distance"].notna(), "building_id"].sample(40, random_state=SEED))
    for pw in scored["pathway"].dropna().unique():
        grp = scored[scored["pathway"].eq(pw)]
        ids |= set(grp["building_id"].sample(min(25, len(grp)), random_state=SEED))
    ids |= set(scored["building_id"].sample(320, random_state=SEED))
    pid = perf["PMPROPERTYID"].astype("string").str.strip()
    perf[pid.isin(ids)].to_parquet(OUT / "dc_performance.parquet", index=False)
    bid = bench["PMPROPERTYID"].astype("string").str.strip()
    used = ["PMPROPERTYID", "REPORTINGYEAR", "LASTUPDATE", "SITEEUI_KBTU_FT", *canonical.DC_METRIC_COLUMNS.values()]
    bench.loc[bid.isin(ids), used].to_parquet(OUT / "dc_benchmarking.parquet", index=False)   # only the columns used

    master = denver_src.load(latest_snapshot(root, "denver"))
    status = canonical.denver(master)["screen_status"]
    keep = pd.concat([master[status.eq(s)].sample(min(len(master[status.eq(s)]), 25 if s != "scored" else 200),
                                                  random_state=SEED) for s in status.unique()])
    keep.to_parquet(OUT / "denver_master.parquet", index=False)
    print(f"dc: {len(ids)} buildings | denver: {len(keep)} rows -> {OUT}")

    ll84 = nyc_src.load(latest_snapshot(root, "nyc")).sort_values("property_id", key=lambda s: s.astype(int)).head(400)
    names = {n for v in COLUMNS.values() for n in v} | set(ALL_USES) | {n for t, a in TOP_USES for n in t + a}
    cols = ["report_year", "property_id", "property_name", "parent_property_id", "address_1", "postal_code",
            "nyc_borough_block_and_lot", "nyc_building_identification", *[c for c in ll84.columns if c in names]]
    ll84[list(dict.fromkeys(c for c in cols if c in ll84.columns))].to_csv(OUT / "nyc_ll84.csv", index=False)

    b = boston_src.load(latest_snapshot(root, "boston"))
    st = b["Emissions Compliance Status"]
    exceptions = boston_engine.validate(boston_engine.score(canonical.boston(b)))["standard_exceptions"]
    parts = [b[st.eq("Action Needed")], b[st.eq("In Compliance")].sample(220, random_state=SEED),
             b[b["Flexibility Measures"].eq("Blended Emissions Standard")].head(15), b[b["BERDO ID"].isin(exceptions)],
             b[pd.to_numeric(b["District Steam Usage (kBtu)"], errors="coerce") > 0].head(25),
             b[b["Largest Property Type"].isin(["Other", "Electric Vehicle Charging Station"])].head(4)]
    for s, n in [("Emissions Compliance at Portfolio Level", 40), ("N/A until 2030", 30), ("Pending Reporting", 30),
                 ("Pending Review from BERDO Team", 30), ("State", 8), ("Vacant", 5),
                 ("Emissions Compliance at Campus Level", 4)]:
        parts.append(b[st.eq(s)].head(n))
    keep = pd.concat(parts).drop_duplicates("BERDO ID")
    keep.to_parquet(OUT / "boston_berdo.parquet", index=False)
    print(f"nyc: {len(ll84)} rows | boston: {len(keep)} rows")


if __name__ == "__main__":
    main()
