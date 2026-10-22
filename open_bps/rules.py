"""Rule files: one dated YAML per jurisdiction and rule version, every value tied to a primary source.

Rules change (Denver rewrote its schedule and rates in April 2025), so the engines never hard-code a
rate or a year: they read it from here, and every output row carries the `rule_version` it used.

Since 0.2.0 the files live in `open_bps/jurisdictions/` and are validated by the policy registry
(`open_bps.registry`). `load()` is kept for the DC and Denver engines: it validates through the registry and
returns the file without the registry header, exactly the dict 0.1.0 returned.
"""
from __future__ import annotations

from functools import lru_cache

from open_bps import registry
from open_bps.policy import JurisdictionPolicy

RULES_DIR = registry.JURISDICTIONS_DIR
FILES = {"dc": "dc_beps.yaml", "denver": "denver_energize.yaml"}
REQUIRED = ("jurisdiction", "program", "rule_version", "effective_from", "checked_on", "sources")
# Keys the registry added in 0.2.0; everything else in a DC or Denver file is the 0.1.0 rule text.
REGISTRY_KEYS = frozenset(JurisdictionPolicy.model_fields) - set(REQUIRED)


class RuleError(ValueError):
    pass


@lru_cache(maxsize=None)
def load(jurisdiction: str) -> dict:
    """The rule set for `jurisdiction` ("dc" or "denver"), validated."""
    if jurisdiction not in FILES:
        raise RuleError(f"unknown jurisdiction {jurisdiction!r}; available: {sorted(FILES)}")
    name = FILES[jurisdiction]
    try:
        registry.get_policy(jurisdiction)
    except registry.PolicyError as e:
        raise RuleError(str(e)) from None
    rules = {k: v for k, v in registry.raw(jurisdiction).items() if k not in REGISTRY_KEYS}
    missing = [k for k in REQUIRED if k not in rules]
    if missing:
        raise RuleError(f"{name}: missing {missing}")
    for src_name, src in rules["sources"].items():
        if not isinstance(src, dict) or not src.get("url"):
            raise RuleError(f"{name}: source {src_name!r} needs a url")
    _check(jurisdiction, rules, name)
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
