"""Rule files load, cite their sources, and encode the published worked examples correctly."""
from __future__ import annotations

import pytest

from open_bps import rules
from open_bps.engine import dc, denver


def test_rule_files_load_with_sources():
    for city in ("dc", "denver"):
        r = rules.load(city)
        assert r["rule_version"] and r["checked_on"]
        assert all(s["url"].startswith("https://") for s in r["sources"].values())
    assert set(rules.versions()) == {"dc", "denver"}
    with pytest.raises(rules.RuleError):
        rules.load("nyc")


# ---- DC, BEPS Guidebook v1.2, Chapter 7, Table 21 -----------------------------------------------
def test_dc_maximum_payment_and_cap():
    assert dc.max_payment(74_000) == 740_000                 # $10 per sq ft
    assert dc.max_payment(2_000_000) == 7_500_000            # capped at $7.5M


def test_dc_table21_examples():
    m = dc.max_payment(100_000)
    assert dc.performance_payment(100_000, 0.10) == pytest.approx(0.5 * m)      # 10% of 20% -> reduced 50%
    assert dc.performance_payment(100_000, 0.25) == 0                           # target met
    assert dc.performance_payment(100_000, -0.05) == pytest.approx(m)          # got worse: full maximum
    assert dc.standard_target_payment(100_000, 6, 15) == pytest.approx(0.4 * m) # 6 / 15 = 40%
    assert dc.prescriptive_payment(100_000, 15, 25) == pytest.approx(0.4 * m)   # reduced by 15/25 = 60%


def test_dc_verdict_and_distance_semantics():
    assert dc.meets_standard("ENERGYSTARSCORE", 71, 71) and not dc.meets_standard("ENERGYSTARSCORE", 70, 71)
    assert dc.meets_standard("WEATHERNORMALZEDSOUREUI_KBTUFT", 185, 185)
    assert not dc.meets_standard("WEATHERNORMALZEDSOUREUI_KBTUFT", 185.5, 185)
    assert dc.eui_distance(646.8, 206) == pytest.approx(-0.6815, abs=5e-5)     # a library in DOEE's disclosure


# ---- Denver, Technical Guidance v3, sections 9.4 and 10.2 ---------------------------------------
def test_denver_worked_examples():
    # s. 10.2.1.2.1: 10 kBtu/sf over target x 100,000 sf x $0.35 = $350,000
    assert denver.kbtu_not_achieved(60, 50, 100_000) * rules.load("denver")["rates_per_kbtu"]["one_period"] == pytest.approx(350_000)
    # Table 16: 2032 target 48.3, actual 52, 150,000 sf -> 555,000 kBtu not achieved
    assert denver.kbtu_not_achieved(52, 48.3, 150_000) == pytest.approx(555_000)
    # Table 15: better than target -> nothing owed
    assert denver.kbtu_not_achieved(47.2, 48.3, 150_000) == 0


def test_denver_schedules():
    b = {"eui": 80.0, "gfa": 100_000, "target_first_interim": 70.0, "target_second_interim": 65.0, "target_final": 60.0}
    ext = denver.schedule_for(b, "extended", through=2034)
    assert [y.year for y in ext] == [2028, 2032, 2033, 2034]
    assert ext[0].penalty == pytest.approx(10 * 100_000 * 0.23)
    assert all(y.penalty == pytest.approx(20 * 100_000 * 0.23) for y in ext[1:])
    orig = denver.schedule_for(b, "original")
    assert [y.year for y in orig] == [2025, 2027, 2030]
    assert orig[1].penalty == pytest.approx(15 * 100_000 * 0.15)
