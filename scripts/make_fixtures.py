"""Write the offline test fixtures in tests/fixtures/ from a full raw snapshot.

    python scripts/make_fixtures.py --root data

DC: a seeded sample of the BEPS disclosure that always includes every building whose published verdict
the plain rule does not reproduce, buildings with EUI distances, and buildings on each pathway, plus all
benchmarking years for those buildings. Denver: a seeded sample covering every screen_status.
Sources and licences: tests/fixtures/README.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from open_bps import canonical
from open_bps.engine import dc as dc_engine
from open_bps.sources import dc as dc_src
from open_bps.sources import denver as denver_src
from open_bps.sources import latest_snapshot

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


if __name__ == "__main__":
    main()
