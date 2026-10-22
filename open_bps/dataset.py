"""Build the published scored datasets from the latest raw snapshots.

Outputs, per jurisdiction, in <root>/scored/:
  <city>.parquet, <city>.csv   one row per building, canonical fields + estimates + screen_status
  <city>.meta.json             rule version, source snapshot (url, retrieved_at, sha256), attribution,
                               disclaimer, counts and (DC) validation against DOEE's published verdicts
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from open_bps import DISCLAIMER, __version__, canonical, registry
from open_bps import rules as _rules
from open_bps.engine import boston as boston_engine
from open_bps.engine import dc as dc_engine
from open_bps.engine import denver as denver_engine
from open_bps.engine import nyc as nyc_engine
from open_bps.sources import boston as boston_src
from open_bps.sources import dc as dc_src
from open_bps.sources import denver as denver_src
from open_bps.sources import latest_snapshot
from open_bps.sources import nyc as nyc_src


def score_dc(folder: Path) -> tuple[pd.DataFrame, dict]:
    perf, bench = dc_src.load(folder)
    scored = dc_engine.score(canonical.dc(perf, bench))
    return scored, {"attribution": dc_src.ATTRIBUTION, "validation": validate_dc(scored)}


def score_denver(folder: Path, through: int = 2035) -> tuple[pd.DataFrame, dict]:
    scored = denver_engine.score(canonical.denver(denver_src.load(folder)), through=through)
    return scored, {"attribution": denver_src.ATTRIBUTION, "cumulative_through": through}


def score_nyc(folder: Path) -> tuple[pd.DataFrame, dict]:
    scored = nyc_engine.score(canonical.nyc(nyc_src.load(folder)))
    years = scored["data_year"].dropna().unique().tolist()
    return scored, {"attribution": nyc_src.ATTRIBUTION, "data_years": years,
                    "validation": "no published LL97 verdicts; the engine reproduces DOB's worked examples (tests)"}


def score_boston(folder: Path) -> tuple[pd.DataFrame, dict]:
    scored = boston_engine.score(canonical.boston(boston_src.load(folder)))
    return scored, {"attribution": boston_src.ATTRIBUTION, "validation": boston_engine.validate(scored)}


SCORERS = {"dc": score_dc, "denver": score_denver, "nyc": score_nyc, "boston": score_boston}


def validate_dc(scored: pd.DataFrame) -> dict:
    """How well the encoded rule reproduces DOEE's own published verdicts and distances."""
    v = scored["verdict_matches_official"].dropna()
    d = scored[["eui_distance", "official_eui_distance"]].dropna()
    return {
        "verdicts_compared": int(len(v)),
        "verdicts_matching": int(v.sum()),
        "verdict_match_rate": round(float(v.mean()), 4) if len(v) else None,
        "verdict_exceptions": scored.loc[scored["verdict_matches_official"].eq(False), "building_id"].tolist(),
        "eui_distances_compared": int(len(d)),
        "eui_distance_max_abs_diff": round(float((d.iloc[:, 0] - d.iloc[:, 1]).abs().max()), 4) if len(d) else None,
    }


class DataQualityError(RuntimeError):
    """Raised instead of publishing when the upstream data no longer behaves like the data the rules were
    validated on (e.g. a renamed column or a changed disclosure)."""


MIN_DC_VERDICT_MATCH = 0.97
MIN_DENVER_SCORED_SHARE = 0.5
MIN_NYC_SCORED_SHARE = 0.5
MIN_BOSTON_MATCH = 0.97          # emissions and verdicts reproduced from the city's own figures


def quality_gate(jurisdiction: str, scored: pd.DataFrame, extra: dict) -> None:
    if jurisdiction == "dc":
        rate = extra["validation"]["verdict_match_rate"]
        if rate is None or rate < MIN_DC_VERDICT_MATCH:
            raise DataQualityError(f"DC verdict match {rate} < {MIN_DC_VERDICT_MATCH}: check DOEE's disclosure")
    elif jurisdiction == "boston":
        v = extra["validation"]
        for k in ("emissions_match_rate", "verdict_match_rate"):
            if v[k] is None or v[k] < MIN_BOSTON_MATCH:
                raise DataQualityError(f"Boston {k} {v[k]} < {MIN_BOSTON_MATCH}: check the BERDO disclosure")
    elif jurisdiction == "nyc":
        share = scored["screen_status"].eq("scored").mean()
        if share < MIN_NYC_SCORED_SHARE:
            raise DataQualityError(f"only {share:.0%} of NYC properties scored: check the LL84 columns")
    else:
        share = scored["screen_status"].eq("scored").mean()
        if share < MIN_DENVER_SCORED_SHARE:
            raise DataQualityError(f"only {share:.0%} of Denver buildings scored: check the Master Dataset columns")


def build(root: Path, jurisdiction: str) -> dict:
    root = Path(root)
    folder = latest_snapshot(root, jurisdiction)
    scored, extra = SCORERS[jurisdiction](folder)
    quality_gate(jurisdiction, scored, extra)
    out = root / "scored"
    out.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(out / f"{jurisdiction}.parquet", index=False)
    scored.to_csv(out / f"{jurisdiction}.csv", index=False)
    meta = {
        "jurisdiction": jurisdiction,
        "open_bps_version": __version__,
        "rule_version": (_rules.load(jurisdiction)["rule_version"] if jurisdiction in _rules.FILES
                         else registry.get_policy(jurisdiction).rule_version),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_snapshot": json.loads((folder / "manifest.json").read_text()),
        "rows": int(len(scored)),
        "screen_status_counts": scored["screen_status"].value_counts().to_dict(),
        "disclaimer": DISCLAIMER,
        **extra,
    }
    (out / f"{jurisdiction}.meta.json").write_text(json.dumps(meta, indent=1, default=str))
    return meta


def summary(root: Path) -> Path:
    """Write <root>/scored/SUMMARY.md: headline figures from whichever scored files exist, with the
    assumptions stated next to every number. Published with each data release."""
    out = Path(root) / "scored"
    lines = ["# open-bps summary", "", f"_{DISCLAIMER}_", ""]
    m = lambda v: f"${v / 1e6:,.1f}M"  # noqa: E731
    if (out / "denver.parquet").exists():
        d = pd.read_parquet(out / "denver.parquet")
        meta = json.loads((out / "denver.meta.json").read_text())
        s = d[d["screen_status"].eq("scored")]
        over_i, over_f = s["extended_2028_kbtu_over"] > 0, s["extended_2032_kbtu_over"] > 0
        lines += [
            "## Denver (Energize Denver, buildings 25,000 sq ft and larger)", "",
            f"Rules `{meta['rule_version']}`; data retrieved {meta['source_snapshot']['retrieved_at'][:10]}. "
            f"{len(s):,} of {len(d):,} buildings scored (others: {', '.join(f'{k} {v}' for k, v in meta['screen_status_counts'].items() if k != 'scored')}).",
            "",
            "Assumes each building's latest weather-normalized site EUI stays unchanged and ignores the city's "
            "renewable, transportation and electrification credits (not public), so figures are upper bounds.",
            "",
            "| | Value |", "|---|---:|",
            f"| Above the first interim target (due 2028 on the extended schedule) | {over_i.sum():,} ({over_i.mean():.0%}) |",
            f"| Above the final target (2032) | {over_f.sum():,} ({over_f.mean():.0%}) |",
            f"| Penalties if unchanged, extended schedule: 2028 | {m(s['extended_2028_penalty'].sum())} |",
            f"| Penalties if unchanged, extended schedule: 2032 (then yearly) | {m(s['extended_2032_penalty'].sum())} |",
            f"| Median 2032 penalty among buildings above target | ${s.loc[over_f, 'extended_2032_penalty'].median():,.0f} |",
            f"| Latest report not submitted (would owe $5/sq ft if still missing in a target year) | {int(d['no_report_penalty'].notna().sum()):,} |",
            "",
        ]
    if (out / "dc.parquet").exists():
        c = pd.read_parquet(out / "dc.parquet")
        meta = json.loads((out / "dc.meta.json").read_text())
        v = meta["validation"]
        pp = c[c["pathway"].eq("Performance Pathway") & c["site_eui_reduction_est"].notna()]
        lines += [
            "## Washington, DC (BEPS Compliance Cycle 1, ends 2026-12-31)", "",
            f"Rules `{meta['rule_version']}`; data retrieved {meta['source_snapshot']['retrieved_at'][:10]}.", "",
            f"Validation: the encoded rule reproduces DOEE's published verdict for {v['verdicts_matching']:,} of "
            f"{v['verdicts_compared']:,} buildings ({v['verdict_match_rate']:.1%}); EUI distances match DOEE's to "
            f"{v['eui_distance_max_abs_diff']} on {v['eui_distances_compared']} buildings.", "",
            "Performance Pathway estimates use public site EUI (2018-2019 average vs the latest year) as a proxy "
            "for DOEE's Adjusted Site EUI, and assume the latest year holds to 2026.", "",
            "| | Value |", "|---|---:|",
            f"| Buildings not meeting their standard (DOEE verdict) | {int(c['official_meets_beps'].eq('Does Not Meet BEPS').sum()):,} |",
            f"| Performance Pathway buildings with public data | {len(pp):,} |",
            f"| ... already at a 20%+ site EUI cut | {int((pp['site_eui_reduction_est'] >= 0.2).sum()):,} ({(pp['site_eui_reduction_est'] >= 0.2).mean():.0%}) |",
            f"| Estimated Performance Pathway payments if the latest year held | {m(pp['payment_est_performance'].sum())} |",
            "",
        ]
    if (out / "nyc.parquet").exists():
        n = pd.read_parquet(out / "nyc.parquet")
        meta = json.loads((out / "nyc.meta.json").read_text())
        s = n[n["screen_status"].eq("scored")]
        lines += [
            "## New York City (Local Law 97)", "",
            f"Rules `{meta['rule_version']}`; LL84 data year {', '.join(str(int(y)) for y in meta['data_years'])}, "
            f"retrieved {meta['source_snapshot']['retrieved_at'][:10]}. {len(s):,} of {len(n):,} properties scored "
            f"({', '.join(f'{k} {v:,}' for k, v in meta['screen_status_counts'].items() if k != 'scored')}).", "",
            "Assumes the latest year's energy use stays unchanged; ignores deductions (RECs, offsets) and the "
            "CY2024-2025 occupancy-group election. 2035+ figures use DOB's projected coefficients (Estimated).", "",
            "| | Value |", "|---|---:|",
            f"| Over the 2024-2029 limit | {int((s['penalty_2024'] > 0).sum()):,} ({(s['penalty_2024'] > 0).mean():.0%}) |",
            f"| Over the 2030-2034 limit | {int((s['penalty_2030'] > 0).sum()):,} ({(s['penalty_2030'] > 0).mean():.0%}) |",
            f"| Annual penalties if unchanged, 2024-2029 | {m(s['penalty_2024'].sum())} |",
            f"| Annual penalties if unchanged, 2030-2034 | {m(s['penalty_2030'].sum())} |",
            "",
        ]
    if (out / "boston.parquet").exists():
        b = pd.read_parquet(out / "boston.parquet")
        meta = json.loads((out / "boston.meta.json").read_text())
        v = meta["validation"]
        s = b[b["screen_status"].eq("scored")]
        lines += [
            "## Boston (BERDO 2.0)", "",
            f"Rules `{meta['rule_version']}`; data retrieved {meta['source_snapshot']['retrieved_at'][:10]}. "
            f"{len(s):,} of {len(b):,} buildings scored (portfolio and campus members are left to their group).", "",
            f"Validation: emissions reproduced for {v['emissions_matching']:,} of {v['emissions_compared']:,} buildings; "
            f"the city's compliance verdict reproduced for {v['verdict_matching']:,} of {v['verdict_compared']:,}.", "",
            "Exposure is the Alternative Compliance Payment ($234/tCO2e) that would cover the excess under the default "
            "standard, energy use unchanged; grid factors after 2025 are the city's projections.", "",
            "| | Value |", "|---|---:|",
            f"| Over the 2025-2029 standard | {int((s['acp_2025'] > 0).sum()):,} |",
            f"| ACP if unchanged, 2025 | {m(s['acp_2025'].sum())} |",
            f"| ACP if unchanged, 2030 | {m(s['acp_2030'].sum())} |",
            "",
        ]
    path = out / "SUMMARY.md"
    path.write_text("\n".join(lines))
    return path

