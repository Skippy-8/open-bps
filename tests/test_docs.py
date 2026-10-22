"""The data dictionary lists exactly the columns the scored tables have."""
from __future__ import annotations

import re
from pathlib import Path

DOC = (Path(__file__).resolve().parents[1] / "docs" / "data_dictionary.md").read_text()


def test_dictionary_matches_columns(dc_scored, denver_scored, nyc_scored, boston_scored):
    documented = {name for cell in re.findall(r"^\| ([^|]+) \|", DOC, flags=re.M)
                  for name in re.split(r",\s*", cell.strip()) if re.fullmatch(r"[a-z][a-z_0-9]*", name)}
    columns = set(dc_scored.columns) | set(denver_scored.columns) | set(nyc_scored.columns) | set(boston_scored.columns)
    assert not columns - documented, f"undocumented columns: {sorted(columns - documented)}"
    assert not documented - columns, f"documented but absent: {sorted(documented - columns)}"


def test_readme_coverage_table_is_generated_from_the_registry():
    from open_bps.registry import coverage_markdown
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    block = readme.split("<!-- coverage:start", 1)[1].split("-->", 1)[1].split("<!-- coverage:end -->", 1)[0]
    assert block.strip() == coverage_markdown().strip(), "run coverage_markdown() and paste it into README.md"
