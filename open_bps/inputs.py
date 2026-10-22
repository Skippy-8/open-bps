"""Input contracts for analysing your own buildings: `BuildingRecord` and `PortfolioInput`.

A portfolio file has one row per building:

    building_id, name, gross_floor_area,
    property_type_1, gfa_1, property_type_2, gfa_2, ...      (one pair per use; at least one)
    electricity_kwh,                                          (required: blank is missing data, not zero)
    natural_gas_therms or natural_gas_kbtu, district_steam_kbtu, fuel_oil_2_kbtu, ...   (blank = not used)

`PortfolioInput.from_csv` reads every row, collects every problem, and raises one `PortfolioValidationError`
that lists them by row, for example:

    Row 12 (Building 'One Main'): missing 'electricity_kwh'; 'gross_floor_area' must be > 0

Row numbers are the spreadsheet's: the header is row 1, so the first building is row 2. Nothing is filled
in or guessed; a value that cannot be read is an error.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

GFA_TOLERANCE = 0.01          # the spaces must add up to the building's GFA within 1%
KBTU_PER_THERM = 100.0

UTILITY_COLUMNS = (
    "electricity_kwh", "renewable_electricity_kwh", "natural_gas_kbtu", "natural_gas_therms",
    "district_steam_kbtu", "district_hot_water_kbtu", "district_chilled_water_kbtu", "fuel_oil_1_kbtu",
    "fuel_oil_2_kbtu", "fuel_oil_4_kbtu", "fuel_oil_5_6_kbtu", "diesel_kbtu", "propane_kbtu", "kerosene_kbtu",
)
_SPACE_COL = re.compile(r"^(property_type|gfa)_(\d+)$")


class PortfolioValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"{len(errors)} row(s) failed validation:\n" + "\n".join(errors))


class Space(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    property_type: str = Field(min_length=1)
    gfa: float = Field(gt=0)


class Utilities(BaseModel):
    """Annual use. Electricity in kWh, everything else in kBtu; natural gas may be given in therms instead."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    electricity_kwh: float = Field(ge=0)
    renewable_electricity_kwh: float = Field(default=0, ge=0)
    natural_gas_kbtu: float | None = Field(default=None, ge=0)
    natural_gas_therms: float | None = Field(default=None, ge=0)
    district_steam_kbtu: float = Field(default=0, ge=0)
    district_hot_water_kbtu: float = Field(default=0, ge=0)
    district_chilled_water_kbtu: float = Field(default=0, ge=0)
    fuel_oil_1_kbtu: float = Field(default=0, ge=0)
    fuel_oil_2_kbtu: float = Field(default=0, ge=0)
    fuel_oil_4_kbtu: float = Field(default=0, ge=0)
    fuel_oil_5_6_kbtu: float = Field(default=0, ge=0)
    diesel_kbtu: float = Field(default=0, ge=0)
    propane_kbtu: float = Field(default=0, ge=0)
    kerosene_kbtu: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _one_gas_unit(self):
        if self.natural_gas_kbtu is not None and self.natural_gas_therms is not None:
            raise ValueError("give natural gas in kBtu or therms, not both")
        return self

    def by_fuel(self) -> dict[str, float]:
        """Use per fuel in the units the policies expect (kWh for electricity, kBtu otherwise)."""
        gas = self.natural_gas_kbtu if self.natural_gas_kbtu is not None else (self.natural_gas_therms or 0) * KBTU_PER_THERM
        out = {"electricity": self.electricity_kwh, "natural_gas": gas}
        for f in ("district_steam", "district_hot_water", "district_chilled_water", "fuel_oil_1", "fuel_oil_2",
                  "fuel_oil_4", "fuel_oil_5_6", "diesel", "propane", "kerosene"):
            out[f] = getattr(self, f + "_kbtu")
        return out


class BuildingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    building_id: str = Field(min_length=1)
    name: str = ""
    gross_floor_area: float = Field(gt=0)
    spaces: list[Space] = Field(min_length=1)
    utilities: Utilities

    @model_validator(mode="after")
    def _spaces_add_up(self):
        total = sum(s.gfa for s in self.spaces)
        if abs(total - self.gross_floor_area) > GFA_TOLERANCE * self.gross_floor_area:
            raise ValueError(f"the spaces add up to {total:,.0f} sq ft, but gross_floor_area is "
                             f"{self.gross_floor_area:,.0f} (they must agree within {GFA_TOLERANCE:.0%})")
        return self


class PortfolioInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    buildings: list[BuildingRecord] = Field(min_length=1)

    @classmethod
    def from_csv(cls, path: str | Path, allowed_property_types=None) -> PortfolioInput:
        return cls.from_dataframe(pd.read_csv(path, dtype=str, keep_default_na=False), allowed_property_types)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, allowed_property_types=None) -> PortfolioInput:
        """Validate every row; raise one PortfolioValidationError listing every problem. `allowed_property_types`
        (e.g. the ESPM types a policy knows) makes an unknown type an error that lists the allowed values."""
        buildings, errors = validate_rows(df, allowed_property_types)
        if errors:
            raise PortfolioValidationError(errors)
        return cls(buildings=[b for _, b in buildings])


def validate_rows(df: pd.DataFrame, allowed_property_types=None) -> tuple[list[tuple[int, BuildingRecord]], list[str]]:
    """The lenient form: (spreadsheet row number, record) for every valid row, and the errors for the rest."""
    allowed = sorted(allowed_property_types) if allowed_property_types is not None else None
    errors, buildings, seen = [], [], {}
    unknown_cols = [c for c in df.columns if c not in _KNOWN and not _SPACE_COL.match(str(c))]
    if unknown_cols:
        errors.append(f"Header: unknown column(s) {unknown_cols}; expected building_id, name, gross_floor_area, "
                      f"property_type_N, gfa_N and {list(UTILITY_COLUMNS)}")
    for i, row in enumerate(df.to_dict("records")):
        rownum = i + 2
        problems: list[str] = []
        data = _row_to_record(row, problems)
        if allowed is not None:
            for s in data.get("spaces", []):
                t = s.get("property_type")
                if t and t not in allowed:
                    problems.append(f"property type {t!r} is not one this jurisdiction maps; allowed: {allowed}")
        bid = data.get("building_id")
        if bid:
            if bid in seen:
                problems.append(f"building_id {bid!r} repeats row {seen[bid]}")
            seen.setdefault(bid, rownum)
        try:
            record = BuildingRecord.model_validate(data)
        except ValidationError as e:
            unreadable = {m.split("'")[1] for m in problems if " is not a number " in m}
            problems += [m for m in (_message(err) for err in e.errors())
                         if m not in problems and not (m.startswith("missing '") and m.split("'")[1] in unreadable)]
        else:
            if not problems:
                buildings.append((rownum, record))
        if problems:
            errors.append(f"Row {rownum} ({_label(row)}): " + "; ".join(problems))
    if not len(df):
        errors.append("the file has no buildings")
    return buildings, errors


_KNOWN = {"building_id", "name", "gross_floor_area", *UTILITY_COLUMNS}


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v.strip())


def _label(row: dict) -> str:
    name, bid = row.get("name"), row.get("building_id")
    if not _blank(name):
        return f"Building {str(name).strip()!r}"
    if not _blank(bid):
        return f"Building {str(bid).strip()!r}"
    return "Building with no id"


def _number(row: dict, col: str, problems: list[str]):
    v = row.get(col)
    if _blank(v):
        return None
    try:
        x = float(str(v).replace(",", "").strip())
    except ValueError:
        problems.append(f"{col!r} is not a number ({v!r})")
        return None
    if math.isnan(x) or math.isinf(x):
        problems.append(f"{col!r} is not a number ({v!r})")
        return None
    return x


def _row_to_record(row: dict, problems: list[str]) -> dict:
    data: dict = {}
    for col in ("building_id", "name"):
        if not _blank(row.get(col)):
            data[col] = str(row[col]).strip()
    gfa = _number(row, "gross_floor_area", problems)
    if gfa is not None:
        data["gross_floor_area"] = gfa
    idx = sorted({int(m.group(2)) for c in row if (m := _SPACE_COL.match(str(c)))})
    spaces = []
    for n in idx:
        t, area = row.get(f"property_type_{n}"), _number(row, f"gfa_{n}", problems)
        if _blank(t) and area is None:
            continue
        if _blank(t):
            problems.append(f"'gfa_{n}' has no 'property_type_{n}'")
            continue
        if area is None:
            problems.append(f"'property_type_{n}' ({str(t).strip()}) has no 'gfa_{n}'")
            continue
        spaces.append({"property_type": str(t).strip(), "gfa": area})
    if spaces:
        data["spaces"] = spaces
    util = {}
    for col in UTILITY_COLUMNS:
        x = _number(row, col, problems)
        if x is not None:
            util[col] = x
    data["utilities"] = util
    return data


_FIELD_NAMES = {"gross_floor_area", "building_id", *UTILITY_COLUMNS}


def _message(err: dict) -> str:
    loc = [str(p) for p in err["loc"]]
    field = next((p for p in reversed(loc) if p in _FIELD_NAMES or p in ("gfa", "property_type")), None)
    if loc[:1] == ["spaces"] and len(loc) > 1 and loc[1].isdigit():
        field = f"{loc[2] if len(loc) > 2 else 'space'}_{int(loc[1]) + 1}" if len(loc) > 2 else field
    if err["type"] == "missing" and loc == ["spaces"]:
        return "no property_type_1 / gfa_1"
    if err["type"] == "missing":
        return f"missing {field or loc[-1]!r}"
    if err["type"] == "greater_than":
        return f"{field!r} must be > {err['ctx']['gt']:g}"
    if err["type"] == "greater_than_equal":
        return f"{field!r} must be >= {err['ctx']['ge']:g}"
    if err["type"] == "too_short" and loc[-1] == "spaces":
        return "no property_type_1 / gfa_1"
    msg = err["msg"].removeprefix("Value error, ")
    return f"{field!r}: {msg}" if field else msg
