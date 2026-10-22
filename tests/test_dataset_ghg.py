"""NYC and Boston scored datasets, built offline from samples of the real disclosures."""
from __future__ import annotations

import json

import numpy as np
import pytest

from open_bps import DISCLAIMER
from open_bps.dataset import DataQualityError, quality_gate


def test_boston_reproduces_the_citys_own_figures(built):
    """The answer key: the city's emissions, applicable standard and compliance verdict for each building.
    On the full 2026 disclosure: emissions 1,755/1,756, standard 1,101/1,104, verdicts 901/901."""
    v = built["boston"]["validation"]
    assert v["verdict_compared"] >= 250 and v["verdict_match_rate"] == 1.0
    assert v["emissions_compared"] >= 250 and v["emissions_match_rate"] >= 0.99
    assert set(v["standard_exceptions"]) == {"104522", "104523", "105367"}      # listed, not fitted away


def test_boston_statuses_and_acp(boston_scored):
    s = boston_scored
    assert s["screen_status"].notna().all()
    assert {"scored", "portfolio_member", "no_data", "state_owned", "vacant"} <= set(s["screen_status"])
    assert s.loc[s["screen_status"].ne("scored"), "acp_2025"].isna().all()
    sc = s[s["screen_status"].eq("scored") & s["acp_2025"].notna()]
    expect = np.clip(sc["emissions_t_2025"] - sc["standard_kg_per_sqft_2025"] / 1000 * sc["gfa"], 0, None) * 234
    assert np.allclose(sc["acp_2025"], expect)
    later = s[s["first_compliance_year"].eq(2030) & s["screen_status"].eq("scored")]
    assert later["acp_2025"].isna().all() and later["acp_2030"].notna().any()     # small buildings start in 2030
    assert (s.loc[s["official_status"].eq("Action Needed") & s["screen_status"].eq("scored"), "acp_2025"] > 0).all()


def test_nyc_scores_every_property_or_says_why(nyc_scored):
    n = nyc_scored
    assert n["screen_status"].notna().all() and len(n) == 400
    assert {"scored", "invalid_input", "unmapped_property_type", "campus_member"} <= set(n["screen_status"])
    assert n.loc[n["screen_status"].eq("invalid_input"), "problems"].notna().all()
    s = n[n["screen_status"].eq("scored")]
    assert s[["emissions_t_2024", "limit_t_2024", "penalty_2024", "penalty_2030"]].notna().all().all()
    assert np.allclose(s["penalty_2024"], np.clip(s["emissions_t_2024"] - s["limit_t_2024"], 0, None) * 268)
    assert (s["penalty_2030"] >= s["penalty_2024"]).mean() > 0.95          # limits tighten, coefficients fall less
    assert np.allclose(s["cumulative_penalty_2024_2034"], 6 * s["penalty_2024"] + 5 * s["penalty_2030"])


def test_ghg_metadata(root, built):
    for city in ("nyc", "boston"):
        meta = json.loads((root / "scored" / f"{city}.meta.json").read_text())
        assert meta["disclaimer"] == DISCLAIMER and meta["attribution"]
        assert meta["rule_version"].startswith(city)
    from open_bps import dataset
    summary = dataset.summary(root).read_text()
    assert "## New York City" in summary and "## Boston" in summary


def test_ghg_quality_gates(nyc_scored, boston_scored, built):
    quality_gate("boston", boston_scored, built["boston"])
    with pytest.raises(DataQualityError):
        quality_gate("boston", boston_scored, {"validation": {**built["boston"]["validation"], "verdict_match_rate": 0.9}})
    quality_gate("nyc", nyc_scored, {})
    with pytest.raises(DataQualityError):
        quality_gate("nyc", nyc_scored.assign(screen_status="invalid_input"), {})


def test_nyc_flags_implausible_reported_use():
    """LL84 is self-reported; 2,500 kgCO2e/sf (seen in CY2024) is a reporting error, not a penalty."""
    import pandas as pd

    from open_bps import canonical
    from open_bps.engine import nyc

    raw = pd.read_csv("tests/fixtures/nyc_ll84.csv", dtype=str, keep_default_na=False).head(3)
    raw.loc[0, "natural_gas_use_kbtu"] = str(float(raw.loc[0, "property_gfa_calculated"]) * 50_000)
    s = nyc.score(canonical.nyc(raw))
    assert s.loc[0, "screen_status"] == "implausible_use" and "likely a reporting error" in s.loc[0, "problems"]
