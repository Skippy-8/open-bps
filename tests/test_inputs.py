"""Portfolio input contracts: good rows load; every bad row is reported, by spreadsheet row, in plain words."""
from __future__ import annotations

import io

import pandas as pd
import pytest

from open_bps.inputs import BuildingRecord, PortfolioInput, PortfolioValidationError

GOOD = """building_id,name,gross_floor_area,property_type_1,gfa_1,property_type_2,gfa_2,electricity_kwh,natural_gas_therms,fuel_oil_2_kbtu
B1,One Main,100000,Office,70000,Retail Store,30000,1200000,15000,
B2,Two Main,50000,Multifamily Housing,50000,,,400000,,250000
"""


def _csv(text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)


def test_good_portfolio_loads_and_converts_units():
    pf = PortfolioInput.from_dataframe(_csv(GOOD))
    b1, b2 = pf.buildings
    assert [s.property_type for s in b1.spaces] == ["Office", "Retail Store"]
    assert b1.utilities.by_fuel()["natural_gas"] == 1_500_000              # therms x 100 = kBtu
    assert b2.utilities.by_fuel()["natural_gas"] == 0                      # blank gas = not used
    assert b2.utilities.by_fuel()["fuel_oil_2"] == 250_000


def test_from_csv_reads_a_file(tmp_path):
    (tmp_path / "p.csv").write_text(GOOD)
    assert len(PortfolioInput.from_csv(tmp_path / "p.csv").buildings) == 2


def test_errors_are_collected_by_row_in_plain_words():
    bad = GOOD + "B3,Three Main,0,Office,40000,,,,,\n" + "B4,,40000,Office,40000,,,abc,,\n" + \
        "B5,Five Main,100000,Office,50000,,,10,,\n" + "B1,Dup,1000,Office,1000,,,1,,\n"
    with pytest.raises(PortfolioValidationError) as e:
        PortfolioInput.from_dataframe(_csv(bad))
    errs = e.value.errors
    assert errs[0] == "Row 4 (Building 'Three Main'): 'gross_floor_area' must be > 0; missing 'electricity_kwh'"
    assert errs[1] == "Row 5 (Building 'B4'): 'electricity_kwh' is not a number ('abc')"
    assert errs[2].startswith("Row 6 (Building 'Five Main'): the spaces add up to 50,000 sq ft")
    assert errs[3] == "Row 7 (Building 'Dup'): building_id 'B1' repeats row 2"
    assert len(errs) == 4


def test_unmapped_property_types_list_the_allowed_values():
    with pytest.raises(PortfolioValidationError) as e:
        PortfolioInput.from_dataframe(_csv(GOOD), allowed_property_types={"Office", "Multifamily Housing"})
    assert e.value.errors == ["Row 2 (Building 'One Main'): property type 'Retail Store' is not one this "
                              "jurisdiction maps; allowed: ['Multifamily Housing', 'Office']"]


def test_space_and_header_problems():
    text = "building_id,name,gross_floor_area,property_type_1,gfa_1,gfa_2,electricity_kwh,steam\nX,,100,Office,100,5,1,2\n"
    with pytest.raises(PortfolioValidationError) as e:
        PortfolioInput.from_dataframe(_csv(text))
    assert e.value.errors[0].startswith("Header: unknown column(s) ['steam']")
    assert e.value.errors[1] == "Row 2 (Building 'X'): 'gfa_2' has no 'property_type_2'"


def test_no_spaces_and_negative_use():
    with pytest.raises(PortfolioValidationError) as e:
        PortfolioInput.from_dataframe(_csv("building_id,gross_floor_area,electricity_kwh,propane_kbtu\nX,100,1,-4\n"))
    assert e.value.errors == ["Row 2 (Building 'X'): no property_type_1 / gfa_1; 'propane_kbtu' must be >= 0"]


def test_building_record_directly():
    b = BuildingRecord(building_id="A", gross_floor_area=1000, spaces=[{"property_type": "Office", "gfa": 995}],
                       utilities={"electricity_kwh": 0})
    assert b.utilities.by_fuel()["electricity"] == 0
