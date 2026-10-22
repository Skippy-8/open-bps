"""Greenhouse-gas building performance standards (NYC LL97, Boston BERDO), driven entirely by the policy.

  emissions  = Σ fuel use × factor(fuel, year)                                    tCO2e
               electricity: max(0, kWh × (1 − zero-emission share) − renewable kWh) × factor
               (the share and the renewable deduction are 0 unless the policy has them: Boston)
  limit      = engine.blend.limit(...)                                             tCO2e
  excess     = max(0, emissions − limit)
  penalty    = excess × rate                                                       $ (NYC $268; Boston's ACP $234)

A fuel the building uses but the policy has no factor for is never estimated: the year's emissions, and so
its penalty, are left blank and the reason is returned. Factors the policy marks as guidance rather than law
(NYC's 2035+ electricity and steam) make the result `estimated`.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from open_bps.engine import blend
from open_bps.inputs import BuildingRecord
from open_bps.policy import FUEL_UNITS, JurisdictionPolicy


@dataclass(frozen=True)
class Emissions:
    year: int
    total_t: float | None
    by_fuel: dict
    factors: dict                      # fuel -> tCO2e per kWh / kBtu actually applied
    estimated: bool
    problems: tuple[str, ...] = ()
    electricity_kwh_counted: float | None = None


@dataclass(frozen=True)
class YearResult:
    year: int
    period: str | None
    emissions_t: float | None
    limit_t: float | None
    excess_t: float | None
    penalty: float | None
    estimated: bool
    problems: tuple[str, ...]
    notes: tuple[str, ...] = ()


def emissions(policy: JurisdictionPolicy, use: dict, year: int, renewable_kwh: float = 0.0,
              overrides: dict | None = None) -> Emissions:
    """`use`: fuel -> annual use (kWh for electricity, kBtu otherwise). `overrides`: fuel -> tCO2e per unit,
    for factors the user knows better (e.g. a district steam system's own verified factor)."""
    overrides = overrides or {}
    by_fuel, factors, problems, est = {}, {}, [], False
    counted = None
    for fuel, amount in use.items():
        if fuel not in FUEL_UNITS:
            raise ValueError(f"unknown fuel {fuel!r}")
        if not amount:
            continue
        if fuel in overrides:
            f, e = overrides[fuel], False
        else:
            got = policy.factor(fuel, year)
            if got is None:
                problems.append(f"{policy.id} has no {year} emission factor for {fuel}")
                continue
            f, e = got
        est = est or e
        qty = amount
        if fuel == "electricity":
            share = policy.rps_share(year)
            if share is None:
                problems.append(f"{policy.id} has no {year} zero-emission electricity share")
                continue
            sub = renewable_kwh if (policy.electricity and policy.electricity.subtract_renewable_kwh) else 0.0
            qty = counted = max(0.0, amount * (1 - share) - sub)
        factors[fuel] = f
        by_fuel[fuel] = qty * f
    total = None if problems else sum(by_fuel.values())
    return Emissions(year, total, by_fuel, factors, est, tuple(problems), counted)


def penalty_rate(policy: JurisdictionPolicy) -> float:
    p = policy.penalty
    if getattr(p, "unit", None) != "tCO2e" or p.rate is None:
        raise ValueError(f"{policy.id} is not a per-tCO2e standard")
    return p.rate


def assess(policy: JurisdictionPolicy, building: BuildingRecord, year: int, blend_standard: bool = False,
           overrides: dict | None = None, use: dict | None = None) -> YearResult:
    """One building, one calendar year. `use` replaces the building's own utilities (e.g. post-retrofit)."""
    u = building.utilities
    em = emissions(policy, use if use is not None else u.by_fuel(), year, u.renewable_electricity_kwh, overrides)
    lim = blend.limit(policy, list(building.spaces), year, blend=blend_standard)
    period = policy.period_for(year)
    problems = em.problems + lim.problems
    excess = pen = None
    if em.total_t is not None and lim.limit_t is not None:
        excess = max(0.0, em.total_t - lim.limit_t)
        pen = excess * penalty_rate(policy)
    return YearResult(year, period.id if period else None, em.total_t, lim.limit_t, excess, pen,
                      em.estimated or lim.estimated, problems, lim.notes)


def schedule(policy: JurisdictionPolicy, building: BuildingRecord, first: int, last: int, **kw) -> pd.DataFrame:
    """Year-by-year exposure with use held at the building's latest values ("cost of inaction")."""
    rows = [assess(policy, building, y, **kw) for y in range(first, last + 1)]
    return pd.DataFrame([r.__dict__ for r in rows])
