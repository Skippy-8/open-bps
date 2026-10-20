"""Rule files: one dated YAML per jurisdiction and rule version, every value tied to a primary source.

Rules change (Denver rewrote its schedule and rates in April 2025), so the engines never hard-code a
rate or a year: they read it from here, and every output row carries the `rule_version` it used.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).parent / "rules"
FILES = {"dc": "dc_beps_cycle1.yaml", "denver": "denver_energize_25k.yaml"}
REQUIRED = ("jurisdiction", "program", "rule_version", "effective_from", "checked_on", "sources")


class RuleError(ValueError):
    pass


@lru_cache(maxsize=None)
def load(jurisdiction: str) -> dict:
    """The rule set for `jurisdiction` ("dc" or "denver"), validated."""
    if jurisdiction not in FILES:
        raise RuleError(f"unknown jurisdiction {jurisdiction!r}; available: {sorted(FILES)}")
    path = RULES_DIR / FILES[jurisdiction]
    rules = yaml.safe_load(path.read_text())
    missing = [k for k in REQUIRED if k not in rules]
    if missing:
        raise RuleError(f"{path.name}: missing {missing}")
    for name, src in rules["sources"].items():
        if not isinstance(src, dict) or not src.get("url"):
            raise RuleError(f"{path.name}: source {name!r} needs a url")
    _check(jurisdiction, rules, path.name)
    return rules


def _check(jurisdiction: str, r: dict, where: str) -> None:
    if jurisdiction == "dc":
        mp = r["max_payment"]
        if not (mp["per_sq_ft_gfa"] > 0 and mp["cap_per_building"] > 0):
            raise RuleError(f"{where}: max_payment must be positive")
        if not 0 < r["pathways"]["performance"]["required_reduction"] < 1:
            raise RuleError(f"{where}: performance required_reduction must be a fraction")
    if jurisdiction == "denver":
        for name, s in r["schedules"].items():
            if name == "open_question":
                continue
            years = list(s["target_years"].values())
            if years != sorted(years):
                raise RuleError(f"{where}: schedule {name} target years must increase")
            if s["rate_per_kbtu"] <= 0:
                raise RuleError(f"{where}: schedule {name} needs a positive rate")


def versions() -> dict[str, str]:
    return {j: load(j)["rule_version"] for j in FILES}
