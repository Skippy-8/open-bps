"""The GHG engine reproduces the regulators' own worked examples; blending is checked by hand."""
from __future__ import annotations

import pytest

from open_bps.engine import blend, ghg
from open_bps.inputs import BuildingRecord, Space
from open_bps.registry import get_policy

NYC, BOS = get_policy("nyc_ll97"), get_policy("boston_berdo")


def _bldg(spaces, **use):
    gfa = sum(a for _, a in spaces)
    return BuildingRecord(building_id="t", gross_floor_area=gfa,
                          spaces=[{"property_type": t, "gfa": a} for t, a in spaces], utilities=use)


# ---- NYC: DOB's worked examples -------------------------------------------------------------------
def test_nyc_dob_presentation_slide_25_mixed_use_2024():
    """DOB 'LL97: calculating building emissions' (June 2024), slide 25: 287.00 t vs a 302.41 t limit."""
    b = _bldg([("Multifamily Housing", 40_000), ("Personal Services (Health/Beauty, Dry Cleaning, etc)", 1_900),
               ("Vehicle Repair Services", 600), ("Retail Store", 2_500)],
              electricity_kwh=310_000, natural_gas_kbtu=2_250_000, fuel_oil_2_kbtu=1_050_000)
    em = ghg.emissions(NYC, b.utilities.by_fuel(), 2024)
    assert round(em.by_fuel["natural_gas"], 2) == 119.50
    assert round(em.by_fuel["fuel_oil_2"], 2) == 77.92
    assert round(em.by_fuel["electricity"], 2) == 89.58
    assert round(em.total_t, 2) == 287.00
    lim = blend.limit(NYC, list(b.spaces), 2024)
    assert [round(s.contribution, 2) for s in lim.spaces] == [270.00, 10.91, 2.56, 18.95]
    assert round(lim.limit_t, 2) == 302.41
    r = ghg.assess(NYC, b, 2024)
    assert r.excess_t == 0 and r.penalty == 0 and not r.problems and not r.estimated


def test_nyc_article_320_guide_example_penalty():
    """DOB Article 320 Info Guide (rev. 06/30/2025) pp.122-123: 225.6 t vs 207 t; 18.6 t x $268 = $4,984.80.

    The guide prints the retail limit as 45 (6,000 x 0.00758 = 45.48) and does its arithmetic on the rounded
    207 t. The engine keeps the exact limit, 207.48 t, so its penalty is $4,853.91."""
    b = _bldg([("Multifamily Housing", 24_000), ("Retail Store", 6_000)],
              electricity_kwh=250_000, natural_gas_kbtu=1_560_000, fuel_oil_2_kbtu=950_000)
    r = ghg.assess(NYC, b, 2024)
    em = ghg.emissions(NYC, b.utilities.by_fuel(), 2024).by_fuel
    assert [round(em[f], 4) for f in ("natural_gas", "fuel_oil_2", "electricity")] == [82.8516, 70.4995, 72.2405]
    assert round(r.emissions_t, 1) == 225.6 and round(r.limit_t) == 207
    assert (round(r.emissions_t, 1) - round(r.limit_t)) * 268 == pytest.approx(4_984.80)   # the guide's figures
    assert r.limit_t == pytest.approx(207.48) and r.penalty == pytest.approx(4_853.91, abs=0.01)


def test_nyc_blend_70_20_10_by_hand():
    """70% office / 20% retail / 10% data center, 100,000 sq ft, CY2030 (§103-14(c)(3)(iii) limits)."""
    lim = blend.limit(NYC, [Space(property_type="Office", gfa=70_000), Space(property_type="Retail Store", gfa=20_000),
                            Space(property_type="Data Center", gfa=10_000)], 2030)
    by_hand = 70_000 * 0.002690852 + 20_000 * 0.00210449 + 10_000 * 0.014791131
    assert lim.limit_t == pytest.approx(by_hand)                          # 378.66 t
    assert lim.blended_cap == pytest.approx(by_hand / 100_000)
    assert list(lim.frame()["statutory_class"]) == ["Office", "Retail Store", "Data Center"]


def test_nyc_refuses_to_guess():
    b = _bldg([("Office", 90_000), ("Other", 10_000)], electricity_kwh=1_000_000, fuel_oil_5_6_kbtu=50_000)
    r = ghg.assess(NYC, b, 2026)
    assert r.penalty is None and r.emissions_t is None and r.limit_t is None
    assert any("fuel_oil_5_6" in p for p in r.problems)
    assert any("'Other' has no limit" in p and "may not be assigned" in p for p in r.problems)


def test_nyc_estimated_after_2035_and_formula_identity():
    b = _bldg([("Office", 100_000)], electricity_kwh=2_000_000, natural_gas_kbtu=3_000_000)
    df = ghg.schedule(NYC, b, 2024, 2050)
    assert not df.loc[df["year"] < 2035, "estimated"].any() and df.loc[df["year"] >= 2035, "estimated"].all()
    assert (df["penalty"] == (df["emissions_t"] - df["limit_t"]).clip(lower=0) * 268).all()
    assert df.loc[df["year"] == 2050, "limit_t"].iloc[0] == 0
    assert df.loc[df["year"] == 2030, "emissions_t"].iloc[0] == pytest.approx(2e6 * 0.000145 + 3e6 * 0.00005311)


# ---- Boston ---------------------------------------------------------------------------------------
def test_boston_electricity_worked_example_2025():
    """BERDO Renewable Energy guide: 100,000 kWh in 2025 with RPS 27% -> 18,177 kgCO2e."""
    em = ghg.emissions(BOS, {"electricity": 100_000}, 2025)
    assert em.total_t * 1000 == pytest.approx(18_177)
    assert em.electricity_kwh_counted == pytest.approx(73_000)


def test_boston_renewable_kwh_come_off_after_the_rps_share():
    b = _bldg([("Office", 100_000)], electricity_kwh=372_578, renewable_electricity_kwh=57_276)
    em = ghg.emissions(BOS, b.utilities.by_fuel(), 2025, b.utilities.renewable_electricity_kwh)
    assert em.total_t * 1000 == pytest.approx(53_461.8, abs=0.1)       # a row of the 2026 disclosure


def test_boston_default_is_largest_primary_use_and_blend_is_opt_in():
    spaces = [Space(property_type="Office", gfa=70_000), Space(property_type="Retail Store", gfa=20_000),
              Space(property_type="Laboratory", gfa=10_000)]
    default = blend.limit(BOS, spaces, 2025)
    assert default.blended_cap == pytest.approx(0.0053)                 # office's 5.3 kg/sf for the whole building
    blended = blend.limit(BOS, spaces, 2025, blend=True)
    assert blended.blended_cap * 1000 == pytest.approx(0.7 * 5.3 + 0.2 * 7.1 + 0.1 * 19.2)   # 7.05 kg/sf
    assert blended.extra["primary_uses"] == ["Office", "Retail", "Technology/Science"]


def test_boston_non_primary_space_goes_to_the_largest_use():
    """P&P §6.B: non-primary sq ft (here retail at 5%) is added to the largest primary use."""
    spaces = [Space(property_type="Office", gfa=80_000), Space(property_type="Laboratory", gfa=15_000),
              Space(property_type="Retail Store", gfa=5_000)]
    blended = blend.limit(BOS, spaces, 2025, blend=True)
    assert blended.blended_cap * 1000 == pytest.approx(0.85 * 5.3 + 0.15 * 19.2)               # 7.385 kg/sf
    small_other = blend.limit(BOS, spaces[:2] + [Space(property_type="Other", gfa=5_000)], 2025)
    assert small_other.limit_t == pytest.approx(100_000 * 0.0053) and small_other.notes
    big_other = blend.limit(BOS, [Space(property_type="Office", gfa=60_000), Space(property_type="Other", gfa=40_000)], 2025)
    assert big_other.limit_t is None and "40% of the building" in big_other.problems[0]


def test_boston_acp_exposure_and_unreached_years():
    b = _bldg([("Office", 100_000)], electricity_kwh=1_500_000, natural_gas_kbtu=6_000_000)
    r = ghg.assess(BOS, b, 2030)
    em = 1_500_000 * 0.60 * 259e-6 + 6_000_000 * 53.11e-6
    assert r.emissions_t == pytest.approx(em) and r.limit_t == pytest.approx(100_000 * 0.0032)
    assert r.penalty == pytest.approx((em - 320) * 234)
    assert ghg.assess(BOS, b, 2051).problems                             # no grid factor or RPS share after 2050
    assert blend.limit(BOS, list(b.spaces), 2024).problems == ("2024 is before the first compliance period",)


def test_factor_override_replaces_policy_factor():
    em = ghg.emissions(BOS, {"district_steam": 1_000_000}, 2025, overrides={"district_steam": 58.1e-6})
    assert em.total_t == pytest.approx(58.1)
