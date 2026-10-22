"""The policy registry: every rule file validates, corrupted copies are refused, and the 0.1.0 interface holds."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from open_bps import registry, rules
from open_bps.policy import JurisdictionPolicy

FIX = Path(__file__).parent / "fixtures"


def test_every_rule_file_validates():
    assert registry.list_jurisdictions() == ["boston_berdo", "dc_beps", "denver_energize", "nyc_ll97"]
    for j in registry.list_jurisdictions():
        p = registry.get_policy(j)
        assert p.id == j and p.sources and p.compliance_periods
    assert registry.get_policy("nyc") is registry.get_policy("nyc_ll97")
    with pytest.raises(registry.PolicyError, match="unknown jurisdiction"):
        registry.get_policy("chicago")


def test_shim_returns_the_0_1_0_dicts_exactly():
    snap = json.loads((FIX / "rules_v0_1_0.json").read_text())
    for j in ("dc", "denver"):
        assert json.dumps(rules.load(j), default=str, sort_keys=True) == json.dumps(snap[j], sort_keys=True)
    assert rules.versions() == {"dc": "dc_beps_cycle1_guidebook_v1.2", "denver": "denver_tg_25k_v3_2025-04"}


# ---- each validator refuses a corrupted copy --------------------------------------------------------
def _corrupt(j, edit):
    data = copy.deepcopy(registry.raw(j))
    edit(data)
    return data


@pytest.mark.parametrize("j, edit, message", [
    ("nyc_ll97", lambda d: d["thresholds"].update(source="nowhere"), "not declared in sources"),
    ("boston_berdo", lambda d: d["emission_factors"]["natural_gas"].update(source="a_blog"), "not declared in sources"),
    ("nyc_ll97", lambda d: d["compliance_periods"][1].update(start_year=2029), "overlap"),
    ("nyc_ll97", lambda d: d["compliance_periods"].reverse(), "overlap"),
    ("nyc_ll97", lambda d: d["thresholds"]["by_class"]["Office"].pop("2035-2039"), "must cover exactly"),
    ("boston_berdo", lambda d: d["property_type_map"]["Hotel"].update(to="Hotels"), "has no thresholds"),
    ("nyc_ll97", lambda d: d["emission_factors"]["electricity"].update(unit="tCO2e/kBtu"), "measured in kWh"),
    ("nyc_ll97", lambda d: d["penalty"].update(unit="kBtu"), "per tCO2e"),
    ("denver_energize", lambda d: d.update(metrics=["energy_star_score"]), "needs an EUI metric"),
    ("nyc_ll97", lambda d: d["emission_factors"]["natural_gas"]["values"].update({"2030": 0.1}), "overlaps"),
    ("boston_berdo", lambda d: d["electricity"]["rps_exempt_share"].update({"2031": 1.4}), "fractions"),
    ("nyc_ll97", lambda d: d["thresholds"]["by_class"]["Office"].update({"2030-2034": -0.001}), "negative"),
    ("dc_beps", lambda d: d["sources"]["timeline"].update(url="http://example.com"), "https"),
    ("dc_beps", lambda d: d["penalty"].update(kind="per_unit_over_limit"), "unit"),
])
def test_validators_reject_corrupted_copies(j, edit, message):
    with pytest.raises(ValidationError, match=message):
        JurisdictionPolicy.model_validate(_corrupt(j, edit))


def test_registry_names_the_bad_file(tmp_path, monkeypatch):
    bad = _corrupt("nyc_ll97", lambda d: d["penalty"].update(rate=-5))
    (tmp_path / "nyc_ll97.yaml").write_text(json.dumps(bad, default=str))
    monkeypatch.setattr(registry, "JURISDICTIONS_DIR", tmp_path)
    registry.raw.cache_clear()
    registry._policy.cache_clear()
    try:
        with pytest.raises(registry.PolicyError, match="nyc_ll97.yaml is not a valid policy"):
            registry.get_policy("nyc_ll97")
    finally:
        registry.raw.cache_clear()
        registry._policy.cache_clear()


# ---- the encoded numbers match the primary documents ------------------------------------------------
def test_nyc_limits_match_1_rcny_103_14():
    p = registry.get_policy("nyc_ll97")
    assert len(p.thresholds.by_class) == 60
    # typed from the rule PDF, §103-14(c)(3)(i)-(v)
    assert [p.threshold("Office", y) for y in (2024, 2030, 2035, 2040, 2050)] == \
        [0.00758, 0.002690852, 0.00165234, 0.000581893, 0.0]
    assert p.threshold("Multifamily Housing", 2027) == 0.00675
    assert p.threshold("Data Center", 2032) == 0.014791131
    assert [t for t in p.thresholds.by_class if p.threshold(t, 2045) == 0] == ["Parking", "Performing Arts"]
    assert p.threshold("Personal Services (Health/Beauty, Dry Cleaning, etc.)", 2045) == 0.002421519
    assert p.statutory_class("Vehicle Dealership") == "Automobile Dealership"
    assert p.statutory_class("Police Station") == "Hotel"                     # DOB suggested type
    assert p.statutory_class("Other") is None and "Other" in p.unassignable_types
    assert p.factor("electricity", 2026) == (0.000288962, False)
    assert p.factor("electricity", 2036) == (0.0000866886, True)            # DOB projection, not law
    assert p.factor("fuel_oil_5_6", 2026) is None                           # no coefficient in the rule
    assert p.factor("propane", 2036) is None


def test_boston_standards_and_factors_match_the_ordinance_and_pp():
    p = registry.get_policy("boston_berdo")
    assert p.threshold("Office", 2025) == pytest.approx(0.0053)              # 5.3 kgCO2e/sf
    assert p.threshold("Multifamily Housing", 2031) == pytest.approx(0.0024)
    assert p.threshold("Technology/Science", 2047) == pytest.approx(0.0025)
    assert p.threshold("Assembly", 2050) == 0.0
    assert p.statutory_class("Laboratory") == "Technology/Science"
    assert p.statutory_class("Manufacturing/Industrial Plant") == "Manufacturing/Industrial"
    assert p.factor("natural_gas", 2025)[0] == pytest.approx(53.11e-6)      # tCO2e per kBtu
    assert p.factor("electricity", 2025)[0] == pytest.approx(249e-6)        # tCO2e per kWh
    assert p.factor("electricity", 2051) is None
    assert [p.rps_share(y) for y in (2024, 2025, 2029, 2030, 2050)] == [0.24, 0.27, 0.39, 0.40, 0.60]
    assert p.rps_share(2051) is None
    assert p.penalty.rate == 234 and p.blending.primary_use_min_share == 0.10
