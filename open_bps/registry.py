"""The policy registry: every jurisdiction open-bps supports, validated when it is loaded.

    from open_bps.registry import list_jurisdictions, get_policy
    get_policy("nyc_ll97").threshold("Office", 2030)    # 0.002690852 tCO2e per sq ft

A rule file that fails validation raises `PolicyError` naming the file and the problem. Nothing is guessed.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from open_bps.policy import JurisdictionPolicy

JURISDICTIONS_DIR = Path(__file__).parent / "jurisdictions"
ALIASES = {"dc": "dc_beps", "denver": "denver_energize", "nyc": "nyc_ll97", "boston": "boston_berdo"}


class PolicyError(ValueError):
    pass


def list_jurisdictions() -> list[str]:
    """Policy ids, one per rule file."""
    return sorted(p.stem for p in JURISDICTIONS_DIR.glob("*.yaml"))


def resolve(jurisdiction: str) -> str:
    j = ALIASES.get(jurisdiction, jurisdiction)
    if j not in list_jurisdictions():
        raise PolicyError(f"unknown jurisdiction {jurisdiction!r}; available: {list_jurisdictions()} "
                          f"(aliases: {sorted(ALIASES)})")
    return j


@lru_cache(maxsize=None)
def raw(jurisdiction: str) -> dict:
    """The rule file as parsed YAML. Use `get_policy` unless you need the file exactly as written."""
    j = resolve(jurisdiction)
    return yaml.safe_load((JURISDICTIONS_DIR / f"{j}.yaml").read_text())


def get_policy(jurisdiction: str) -> JurisdictionPolicy:
    """The validated policy for a jurisdiction id (or alias)."""
    return _policy(resolve(jurisdiction))


@lru_cache(maxsize=None)
def _policy(j: str) -> JurisdictionPolicy:
    data = raw(j)
    if data.get("id") != j:
        raise PolicyError(f"{j}.yaml: id is {data.get('id')!r}; it must match the file name")
    try:
        return JurisdictionPolicy.model_validate(data)
    except ValidationError as e:
        raise PolicyError(f"{j}.yaml is not a valid policy:\n{e}") from None


def coverage_markdown() -> str:
    """The README's supported-jurisdictions table, generated from the rule files (a test keeps it in sync)."""
    rows = ["| Jurisdiction | Program | Metric | Compliance periods | Penalty | Rules (checked) |",
            "|---|---|---|---|---|---|"]
    for j in list_jurisdictions():
        p = get_policy(j)
        periods = ", ".join(q.id if q.id[:1].isdigit() else f"{q.id} ({q.start_year}{'-' + str(q.end_year) if q.end_year else '+'})"
                            for q in p.compliance_periods)
        pen = p.penalty
        if pen.kind == "capped_payment_pathway":
            pay = f"up to ${pen.per_sq_ft:g}/sq ft, capped at ${pen.cap:,.0f}"
        elif pen.rate is not None:
            pay = f"${pen.rate:g} per {pen.unit} over the limit"
        else:
            pay = " or ".join(f"${r:g}/{pen.unit} ({k})" for k, r in pen.rates_by_schedule.items()) + " over target"
        metric = ", ".join(m.replace("_", " ") for m in p.metrics)
        rows.append(f"| {p.jurisdiction} (`{p.id}`) | {p.program} | {metric} | {periods} | {pay} | "
                    f"`{p.rule_version}` ({p.checked_on}) |")
    return "\n".join(rows)
