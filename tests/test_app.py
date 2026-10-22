"""The Streamlit lookup app runs on the scored fixture data (no network)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


def test_app_lookup_and_download(root, built, denver_scored, monkeypatch):
    monkeypatch.setenv("OPEN_BPS_DATA", str(root / "scored"))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    at.selectbox[0].select("Denver (Energize Denver)").run()
    bid = denver_scored[denver_scored["screen_status"].eq("scored")]["building_id"].iloc[0]
    at.text_input[0].input(bid).run()
    assert not at.exception
    assert any(m.label.startswith("2032 penalty") for m in at.metric)
    assert len(at.get("download_button")) == 1
    at.selectbox[0].select("Washington, DC (BEPS)").run()
    assert not at.exception


def test_app_nyc_boston_lookup(root, built, nyc_scored, boston_scored, monkeypatch):
    monkeypatch.setenv("OPEN_BPS_DATA", str(root / "scored"))
    at = AppTest.from_file(APP, default_timeout=60).run()
    for label, df in (("New York City (Local Law 97)", nyc_scored), ("Boston (BERDO 2.0)", boston_scored)):
        at.selectbox[0].select(label).run()
        bid = df[df["screen_status"].eq("scored")]["building_id"].iloc[0]
        at.text_input[0].input(bid).run()
        assert not at.exception
        assert len(at.get("download_button")) >= 1


def test_portfolio_tab_sample_run(monkeypatch, root, built):
    monkeypatch.setenv("OPEN_BPS_DATA", str(root / "scored"))
    for entry in (APP, str(Path(APP).parents[1] / "app.py")):
        at = AppTest.from_file(entry, default_timeout=120).run()
        assert not at.exception
        at.checkbox(key="pf_179d").check()
        at.button(key="pf_run").click().run()
        assert not at.exception, at.exception
        assert len(at.dataframe) == 1 and len(at.dataframe[0].value) == 3
        assert any(b.label.startswith("Download audited Excel") for b in at.get("download_button"))
