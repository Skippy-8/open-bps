"""The data dictionary lists exactly the columns the scored tables have."""
from __future__ import annotations

import re
from pathlib import Path

DOC = (Path(__file__).resolve().parents[1] / "docs" / "data_dictionary.md").read_text()


def test_dictionary_matches_columns(dc_scored, denver_scored):
    documented = {name for cell in re.findall(r"^\| ([^|]+) \|", DOC, flags=re.M)
                  for name in re.split(r",\s*", cell.strip()) if re.fullmatch(r"[a-z][a-z_0-9]*", name)}
    columns = set(dc_scored.columns) | set(denver_scored.columns)
    assert not columns - documented, f"undocumented columns: {sorted(columns - documented)}"
    assert not documented - columns, f"documented but absent: {sorted(documented - columns)}"
