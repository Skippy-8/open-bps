"""The scored datasets, built offline from samples of real data."""
from __future__ import annotations

import json

import numpy as np

from open_bps import DISCLAIMER

KNOWN_DC_EXCEPTIONS = {"12004276", "2706378", "3426697", "3283449", "3632510", "3663625", "5833257",
                       "6022881", "6225430"}


def test_dc_rule_reproduces_doee_verdicts(built, dc_scored):
    """The plain rule reproduces DOEE's verdicts except for 9 known cases decided outside it
    (boundary values and later corrections). On the full data: 1,797 of 1,806 (99.5%)."""
    v = built["dc"]["validation"]
    assert v["verdicts_compared"] > 200
    assert set(v["verdict_exceptions"]) == KNOWN_DC_EXCEPTIONS
    assert v["eui_distances_compared"] >= 25 and v["eui_distance_max_abs_diff"] == 0


def test_every_building_keeps_a_status(dc_scored, denver_scored):
    for df in (dc_scored, denver_scored):
        assert df["screen_status"].notna().all()
        assert df["building_id"].notna().all()
    assert {"exempt", "mai_production_targets", "no_data", "scored"} <= set(denver_scored["screen_status"])


def test_estimates_only_on_scored_rows(denver_scored):
    not_scored = denver_scored[denver_scored["screen_status"].ne("scored")]
    assert not_scored["extended_2032_penalty"].isna().all()
    scored = denver_scored[denver_scored["screen_status"].eq("scored")]
    assert scored["extended_2032_penalty"].notna().all() and (scored["extended_2032_penalty"] >= 0).all()


def test_denver_penalty_matches_formula(denver_scored):
    s = denver_scored[denver_scored["screen_status"].eq("scored")]
    expect = np.clip(s["eui"] - s["target_final"], 0, None) * s["gfa"] * 0.23
    assert np.allclose(s["extended_2032_penalty"], expect)
    cum = s["extended_2028_penalty"] + s["extended_2032_penalty"] + 3 * s["extended_2032_penalty"]
    assert np.allclose(s["extended_cumulative_penalty_through_2035"], cum)


def test_dc_payments_bounded_by_maximum(dc_scored):
    for col in ("payment_est_performance", "payment_est_standard_target"):
        v = dc_scored[[col, "max_payment"]].dropna()
        assert ((v[col] >= 0) & (v[col] <= v["max_payment"] + 1e-6)).all()
    assert (dc_scored["max_payment"].dropna() <= 7_500_000).all()
    # score-metric buildings on the Standard Target Pathway are not estimated (needs DOEE's models)
    st = dc_scored[dc_scored["pathway"].eq("Standard Target Pathway") & dc_scored["metric_type"].eq("ENERGYSTARSCORE")]
    assert st["payment_est_standard_target"].isna().all()


def test_metadata_traces_source_and_rules(root, built):
    for city in ("dc", "denver"):
        meta = json.loads((root / "scored" / f"{city}.meta.json").read_text())
        assert meta["disclaimer"] == DISCLAIMER
        assert meta["rule_version"] and meta["attribution"]
        assert all(len(f["sha256"]) == 64 for f in meta["source_snapshot"]["files"])
        assert (root / "scored" / f"{city}.csv").exists()


def test_quality_gate_blocks_bad_data(dc_scored, denver_scored):
    import pytest

    from open_bps.dataset import DataQualityError, quality_gate
    quality_gate("dc", dc_scored, {"validation": {"verdict_match_rate": 0.995}})
    with pytest.raises(DataQualityError):
        quality_gate("dc", dc_scored, {"validation": {"verdict_match_rate": 0.80}})
    broken = denver_scored.assign(screen_status="no_data")
    with pytest.raises(DataQualityError):
        quality_gate("denver", broken, {})
