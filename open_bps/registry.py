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
