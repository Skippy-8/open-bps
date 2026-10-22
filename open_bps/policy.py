"""The policy registry's schema: one validated `JurisdictionPolicy` per rule file in `open_bps/jurisdictions/`.

A policy holds what a building performance standard says in a form an engine can run: the metric, the
compliance periods, the limits by property type, the emission factors, how property types map to the
law's classes, how mixed-use buildings are blended, and the penalty. Every number names a declared source,
and the validators refuse a file that is internally inconsistent (periods that overlap, a limit missing for
a period, units that do not fit the metric).

DC and Denver publish each building's target in their data, so their files set `threshold_basis:
building_data` and carry no limit table; their full 0.1.0 rule content stays alongside as extra keys.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MetricName = Literal[
    "ghg_intensity", "site_eui", "weather_normalized_site_eui", "source_eui",
    "weather_normalized_source_eui", "energy_star_score",
]
EUI_METRICS = {"site_eui", "weather_normalized_site_eui", "source_eui", "weather_normalized_source_eui"}

# Fuels an engine understands, and the input unit each is measured in.
FUEL_UNITS = {
    "electricity": "kWh", "natural_gas": "kBtu", "district_steam": "kBtu", "district_hot_water": "kBtu",
    "district_chilled_water": "kBtu", "fuel_oil_1": "kBtu", "fuel_oil_2": "kBtu", "fuel_oil_4": "kBtu",
    "fuel_oil_5_6": "kBtu", "diesel": "kBtu", "propane": "kBtu", "kerosene": "kBtu",
}
# Multipliers to tCO2e per input unit (kWh for electricity, kBtu otherwise).
FACTOR_UNITS = {
    "tCO2e/kWh": ("kWh", 1.0), "kgCO2e/kWh": ("kWh", 1e-3), "kgCO2e/MWh": ("kWh", 1e-6),
    "tCO2e/kBtu": ("kBtu", 1.0), "kgCO2e/MMBtu": ("kBtu", 1e-6),
}
THRESHOLD_UNITS = {"tCO2e/sf/yr": 1.0, "kgCO2e/sf/yr": 1e-3}

_KEY = re.compile(r"^(\d{4})(?:-(\d{4})|(\+))?$")


def year_range(key: str) -> tuple[int, int | None]:
    """'2025' -> (2025, 2025); '2024-2029' -> (2024, 2029); '2050+' -> (2050, None)."""
    m = _KEY.match(str(key))
    if not m:
        raise ValueError(f"year key {key!r} must look like 2025, 2024-2029 or 2050+")
    start = int(m.group(1))
    end = None if m.group(3) else int(m.group(2) or start)
    if end is not None and end < start:
        raise ValueError(f"year key {key!r} ends before it starts")
    return start, end


def _in(year: int, rng: tuple[int, int | None]) -> bool:
    return rng[0] <= year and (rng[1] is None or year <= rng[1])


def _check_disjoint(keys, where: str) -> None:
    spans = sorted((year_range(k), k) for k in keys)
    for (a, ka), (b, kb) in zip(spans, spans[1:], strict=False):
        if a[1] is None or a[1] >= b[0]:
            raise ValueError(f"{where}: {ka!r} overlaps {kb!r}")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(_Strict):
    url: str
    title: str | None = None
    section: str | None = None
    note: str | None = None
    checked_on: date | None = None
    archived: str | None = None

    @field_validator("url", "archived")
    @classmethod
    def _https(cls, v):
        if v is not None and not v.startswith(("https://", "http://web.archive.org/")):
            raise ValueError(f"source url must be https: {v!r}")
        return v


class Period(_Strict):
    id: str
    start_year: int
    end_year: int | None = None
    source: str
    note: str | None = None

    def covers(self, year: int) -> bool:
        return _in(year, (self.start_year, self.end_year))


class Thresholds(_Strict):
    unit: Literal["tCO2e/sf/yr", "kgCO2e/sf/yr"]
    source: str
    section: str | None = None
    by_class: dict[str, dict[str, float]]     # statutory class -> compliance period id -> limit
    estimated: list[str] = []                 # period ids whose limits are not codified


class EmissionFactor(_Strict):
    unit: str
    source: str
    section: str | None = None
    values: dict[str, float]                  # year key (2025, 2024-2029, 2050+) -> factor
    estimated: list[str] = []                 # year keys taken from guidance, not from the law
    note: str | None = None

    @field_validator("unit")
    @classmethod
    def _unit(cls, v):
        if v not in FACTOR_UNITS:
            raise ValueError(f"unknown factor unit {v!r}; use one of {sorted(FACTOR_UNITS)}")
        return v

    @model_validator(mode="after")
    def _keys(self):
        _check_disjoint(self.values, f"factor ({self.unit})")
        for k in self.estimated:
            if k not in self.values:
                raise ValueError(f"estimated key {k!r} has no value")
        return self


class Electricity(_Strict):
    """Electricity accounting beyond kWh x factor (Boston: the Massachusetts RPS Class I share is zero-emission)."""
    rps_exempt_share: dict[str, float] | None = None   # year key -> share of grid kWh treated as zero-emission
    subtract_renewable_kwh: bool = False               # reported renewable kWh come off after the RPS share
    source: str
    section: str | None = None
    note: str | None = None


class TypeMapEntry(_Strict):
    to: str                                           # the statutory class (a key of thresholds.by_class)
    basis: Literal["rule", "rename", "suggested"] = "rule"
    source: str
    note: str | None = None


class Blending(_Strict):
    method: Literal["gfa_weighted", "largest_primary_use"]
    optional_method: Literal["primary_use_blend"] | None = None
    primary_use_min_share: float | None = Field(default=None, gt=0, lt=1)
    source: str
    section: str | None = None


class PerUnitOverLimit(_Strict):
    kind: Literal["per_unit_over_limit"]
    unit: Literal["tCO2e", "kBtu"]
    rate: float | None = Field(default=None, gt=0)
    rates_by_schedule: dict[str, float] | None = None
    source: str
    section: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _one_rate(self):
        if (self.rate is None) == (self.rates_by_schedule is None):
            raise ValueError("per_unit_over_limit needs exactly one of rate or rates_by_schedule")
        if self.rates_by_schedule and min(self.rates_by_schedule.values()) <= 0:
            raise ValueError("rates_by_schedule must be positive")
        return self


class CappedPaymentPathway(_Strict):
    kind: Literal["capped_payment_pathway"]
    per_sq_ft: float = Field(gt=0)
    cap: float = Field(gt=0)
    source: str
    section: str | None = None


Penalty = Annotated[PerUnitOverLimit | CappedPaymentPathway, Field(discriminator="kind")]


class JurisdictionPolicy(BaseModel):
    """One jurisdiction's standard. Unknown keys are kept: they are the jurisdiction-specific rule text."""
    model_config = ConfigDict(extra="allow", frozen=True)

    id: str
    jurisdiction: str
    program: str
    rule_version: str
    effective_from: date
    checked_on: date
    sources: dict[str, Source]
    metrics: list[MetricName] = Field(min_length=1)
    threshold_basis: Literal["building_data", "property_type_table"]
    compliance_periods: list[Period] = Field(min_length=1)
    thresholds: Thresholds | None = None
    emission_factors: dict[str, EmissionFactor] = {}
    electricity: Electricity | None = None
    property_type_map: dict[str, TypeMapEntry] = {}
    unassignable_types: dict[str, str] = {}           # ESPM type -> why the law gives it no limit
    blending: Blending | None = None
    penalty: Penalty
    notes: list[str] = []

    @model_validator(mode="after")
    def _consistent(self):
        self._sources_declared()
        self._periods_ordered()
        self._thresholds_cover_periods()
        self._units_fit_metric()
        self._numbers_non_negative()
        return self

    # ---- validators -----------------------------------------------------------------------------
    def _sources_declared(self) -> None:
        refs = [("compliance period " + p.id, p.source) for p in self.compliance_periods]
        refs.append(("penalty", self.penalty.source))
        if self.thresholds:
            refs.append(("thresholds", self.thresholds.source))
        refs += [(f"emission factor {f}", ef.source) for f, ef in self.emission_factors.items()]
        if self.electricity:
            refs.append(("electricity", self.electricity.source))
        refs += [(f"property type {t!r}", e.source) for t, e in self.property_type_map.items()]
        if self.blending:
            refs.append(("blending", self.blending.source))
        for what, ref in refs:
            if ref not in self.sources:
                raise ValueError(f"{self.id}: {what} cites source {ref!r}, which is not declared in sources")

    def _periods_ordered(self) -> None:
        ps = self.compliance_periods
        if len({p.id for p in ps}) != len(ps):
            raise ValueError(f"{self.id}: compliance period ids must be unique")
        for p in ps:
            if p.end_year is not None and p.end_year < p.start_year:
                raise ValueError(f"{self.id}: period {p.id} ends before it starts")
        for a, b in zip(ps, ps[1:], strict=False):
            if a.end_year is None or a.end_year >= b.start_year:
                raise ValueError(f"{self.id}: periods {a.id} and {b.id} are out of order or overlap")

    def _thresholds_cover_periods(self) -> None:
        if self.threshold_basis == "building_data":
            if self.thresholds is not None:
                raise ValueError(f"{self.id}: threshold_basis building_data takes no thresholds table")
            return
        if self.thresholds is None:
            raise ValueError(f"{self.id}: threshold_basis property_type_table needs thresholds")
        ids = [p.id for p in self.compliance_periods]
        for cls, row in self.thresholds.by_class.items():
            missing, extra = set(ids) - set(row), set(row) - set(ids)
            if missing or extra:
                raise ValueError(f"{self.id}: thresholds for {cls!r} must cover exactly the compliance periods "
                                 f"(missing {sorted(missing)}, unknown {sorted(extra)})")
        for t, e in self.property_type_map.items():
            if e.to not in self.thresholds.by_class:
                raise ValueError(f"{self.id}: property type {t!r} maps to {e.to!r}, which has no thresholds")
        if self.blending is None:
            raise ValueError(f"{self.id}: a property type table needs a blending rule")

    def _units_fit_metric(self) -> None:
        ghg = "ghg_intensity" in self.metrics
        if ghg and len(self.metrics) > 1:
            raise ValueError(f"{self.id}: ghg_intensity cannot be combined with other metrics")
        unit = getattr(self.penalty, "unit", None)
        if ghg:
            if not self.emission_factors:
                raise ValueError(f"{self.id}: ghg_intensity needs emission_factors")
            if unit != "tCO2e":
                raise ValueError(f"{self.id}: ghg_intensity penalties must be per tCO2e, not {unit!r}")
            for fuel, ef in self.emission_factors.items():
                if fuel not in FUEL_UNITS:
                    raise ValueError(f"{self.id}: unknown fuel {fuel!r}; use one of {sorted(FUEL_UNITS)}")
                if FACTOR_UNITS[ef.unit][0] != FUEL_UNITS[fuel]:
                    raise ValueError(f"{self.id}: {fuel} is measured in {FUEL_UNITS[fuel]}, so its factor "
                                     f"cannot be in {ef.unit}")
        else:
            if self.emission_factors or self.electricity:
                raise ValueError(f"{self.id}: emission factors only apply to a ghg_intensity metric")
            if unit == "tCO2e":
                raise ValueError(f"{self.id}: an energy metric cannot have a per-tCO2e penalty")
            if unit == "kBtu" and not set(self.metrics) & EUI_METRICS:
                raise ValueError(f"{self.id}: a per-kBtu penalty needs an EUI metric")

    def _numbers_non_negative(self) -> None:
        nums = [v for ef in self.emission_factors.values() for v in ef.values.values()]
        if self.thresholds:
            nums += [v for row in self.thresholds.by_class.values() for v in row.values()]
        if self.electricity and self.electricity.rps_exempt_share:
            shares = self.electricity.rps_exempt_share
            _check_disjoint(shares, f"{self.id} rps_exempt_share")
            if any(not 0 <= s <= 1 for s in shares.values()):
                raise ValueError(f"{self.id}: rps_exempt_share values must be fractions")
        if any(v < 0 for v in nums):
            raise ValueError(f"{self.id}: limits and factors cannot be negative")

    # ---- lookups the engines use ----------------------------------------------------------------
    def period_for(self, year: int) -> Period | None:
        return next((p for p in self.compliance_periods if p.covers(year)), None)

    def statutory_class(self, property_type: str) -> str | None:
        """The law's class for an ESPM property type, or None if the policy does not map it."""
        e = self.property_type_map.get(property_type)
        return e.to if e else None

    def threshold(self, statutory_class: str, year: int) -> float | None:
        """The limit in tCO2e per sq ft per year, or None if there is none for that class or year."""
        p = self.period_for(year)
        if self.thresholds is None or p is None:
            return None
        v = self.thresholds.by_class.get(statutory_class, {}).get(p.id)
        return None if v is None else v * THRESHOLD_UNITS[self.thresholds.unit]

    def threshold_estimated(self, year: int) -> bool:
        p = self.period_for(year)
        return bool(self.thresholds and p and p.id in self.thresholds.estimated)

    def factor(self, fuel: str, year: int) -> tuple[float, bool] | None:
        """(tCO2e per kWh or kBtu, estimated?) for a fuel in a year, or None if the policy has none."""
        ef = self.emission_factors.get(fuel)
        if ef is None:
            return None
        for k, v in ef.values.items():
            if _in(year, year_range(k)):
                return v * FACTOR_UNITS[ef.unit][1], k in ef.estimated
        return None

    def rps_share(self, year: int) -> float | None:
        """Share of grid kWh the policy treats as zero-emission; 0 if it has no such rule, None if the
        rule exists but does not reach `year` (the caller must flag it, not assume a share)."""
        shares = self.electricity.rps_exempt_share if self.electricity else None
        if not shares:
            return 0.0
        for k, v in shares.items():
            if _in(year, year_range(k)):
                return v
        return None
