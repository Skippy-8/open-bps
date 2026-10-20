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

from open_bps import DISCLAIMER, __version__, canonical
from open_bps import rules as _rules
from open_bps.engine import dc as dc_engine
from open_bps.engine import denver as denver_engine
from open_bps.sources import dc as dc_src
from open_bps.sources import denver as denver_src
from open_bps.sources import latest_snapshot


def score_dc(folder: Path) -> tuple[pd.DataFrame, dict]:
    perf, bench = dc_src.load(folder)
    scored = dc_engine.score(canonical.dc(perf, bench))
    return scored, {"attribution": dc_src.ATTRIBUTION, "validation": validate_dc(scored)}


def score_denver(folder: Path, through: int = 2035) -> tuple[pd.DataFrame, dict]:
    scored = denver_engine.score(canonical.denver(denver_src.load(folder)), through=through)
    return scored, {"attribution": denver_src.ATTRIBUTION, "cumulative_through": through}


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


def quality_gate(jurisdiction: str, scored: pd.DataFrame, extra: dict) -> None:
    if jurisdiction == "dc":
        rate = extra["validation"]["verdict_match_rate"]
        if rate is None or rate < MIN_DC_VERDICT_MATCH:
            raise DataQualityError(f"DC verdict match {rate} < {MIN_DC_VERDICT_MATCH}: check DOEE's disclosure")
    else:
        share = scored["screen_status"].eq("scored").mean()
        if share < MIN_DENVER_SCORED_SHARE:
            raise DataQualityError(f"only {share:.0%} of Denver buildings scored: check the Master Dataset columns")


def build(root: Path, jurisdiction: str) -> dict:
    root = Path(root)
    folder = latest_snapshot(root, jurisdiction)
    scored, extra = (score_dc if jurisdiction == "dc" else score_denver)(folder)
    quality_gate(jurisdiction, scored, extra)
    out = root / "scored"
    out.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(out / f"{jurisdiction}.parquet", index=False)
    scored.to_csv(out / f"{jurisdiction}.csv", index=False)
    meta = {
        "jurisdiction": jurisdiction,
        "open_bps_version": __version__,
        "rule_version": _rules.load(jurisdiction)["rule_version"],
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
    path = out / "SUMMARY.md"
    path.write_text("\n".join(lines))
    return path

