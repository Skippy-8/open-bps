"""Retrofit capital stack: what a retrofit avoids in penalties, what it costs, how it is financed, what it returns.

  avoided penalty_t   = baseline penalty_t − post-retrofit penalty_t     (from the engine, use held flat)
  unlevered flow_t    = avoided penalty_t + energy cost savings + §179D cash value (year 1)
  levered flow_t      = unlevered flow_t − debt service_t − balance repaid at the end of the hold
  NPV                 = −capex + NPV(discount rate, flows)               (Excel's NPV: flow 1 discounted a year)
  IRR                 = IRR([−capex or −equity, flows...])
  payback             = first year in which cumulative unlevered flow (net of capex) reaches zero

The retrofit is placed in service at the start of the first year; capex is paid at t = 0. Financing is either
C-PACE (a fixed-rate level annual assessment, usually 100% of capex) or a debt/equity split (loan-to-cost, rate,
term); any balance still owed at the end of the hold is repaid then. Every assumption is an input with a label;
nothing about tariffs, rates or costs is guessed.

§179D is gated by the One Big Beautiful Bill Act: no deduction for property whose construction begins after
June 30, 2026, and none unless a construction start date is given.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import yaml

from open_bps.underwriting.finance import fv, irr_or_nan, npv, pmt

RULES_179D = Path(__file__).parent / "section_179d.yaml"


@lru_cache(maxsize=1)
def rules_179d() -> dict:
    return yaml.safe_load(RULES_179D.read_text())


@dataclass(frozen=True)
class Financing:
    kind: Literal["cpace", "debt", "cash"]
    share: float = 0.0            # share of capex financed (C-PACE usually 1.0; debt: loan-to-cost)
    rate: float = 0.0             # annual interest rate
    term_years: int = 1

    def __post_init__(self):
        if not 0 <= self.share <= 1:
            raise ValueError("financed share must be between 0 and 1")
        if self.kind != "cash" and not (self.share > 0 and self.rate >= 0 and 1 <= self.term_years <= 40):
            raise ValueError(f"{self.kind} needs a financed share > 0, a rate >= 0 and a term of 1-40 years")

    @classmethod
    def cpace(cls, rate: float, term_years: int, share: float = 1.0) -> Financing:
        return cls("cpace", share, rate, term_years)

    @classmethod
    def debt(cls, ltc: float, rate: float, term_years: int) -> Financing:
        return cls("debt", ltc, rate, term_years)

    @classmethod
    def cash(cls) -> Financing:
        return cls("cash")


@dataclass(frozen=True)
class Deduction179D:
    eligible: bool
    tax_year: int
    savings: float
    per_sqft: float
    amount: float                 # the deduction ($)
    cash_value: float             # amount x tax rate
    note: str


def deduction_179d(sqft: float, savings: float, tax_year: int, construction_start: date | None, pwa: bool = False,
                   tax_rate: float = 0.21, cost_basis: float | None = None) -> Deduction179D:
    """§179D for a retrofit: the per-sq-ft amount for `tax_year` on the sliding scale (IRS Form 7205 worksheet),
    times the building's sq ft, limited to the property's cost, and its cash value at `tax_rate`."""
    r = rules_179d()
    cutoff = r["termination"]["construction_begins_after"]
    def none(note):
        return Deduction179D(False, tax_year, savings, 0.0, 0.0, 0.0, note)
    if construction_start is None:
        return none("no construction start date given; §179D needs construction to begin by 2026-06-30")
    if construction_start > cutoff:
        return none(f"construction begins {construction_start}, after {cutoff}: §179D terminated (P.L. 119-21 §70507)")
    pct = round(savings, 2)                                   # Form 7205 worksheet line 2a
    if pct < r["min_savings"]:
        return none(f"savings of {pct:.0%} are below the {r['min_savings']:.0%} minimum")
    years = sorted(r["rates"])
    if tax_year < years[0]:
        raise ValueError(f"§179D amounts are encoded from tax year {years[0]}")
    t = r["rates"][min(tax_year, years[-1])]
    points = (pct - r["min_savings"]) * 100
    key = "pwa_" if pwa else ""
    per = min(t[f"{key}cap"], t[f"{key}base"] + t[f"{key}per_point"] * points)
    amount = per * sqft if cost_basis is None else min(per * sqft, cost_basis)
    note = (f"tax year {tax_year}: ${per:.2f}/sq ft ({'prevailing wage and apprenticeship' if pwa else 'base'} rate, "
            f"{r['sources'][t['source']]['title']})")
    if tax_year > years[-1]:
        note += f"; the IRS has published amounts only through {years[-1]}, so {years[-1]}'s are used"
    if cost_basis is not None and per * sqft > cost_basis:
        note += "; limited to the retrofit's cost"
    return Deduction179D(True, tax_year, pct, per, amount, amount * tax_rate, note)


@dataclass(frozen=True)
class Underwriting:
    table: pd.DataFrame
    capex: float
    financed: float
    equity: float
    incentive: float
    discount_rate: float
    npv_benefits: float           # PV of avoided penalties + savings + incentive
    npv_unlevered: float
    irr_unlevered: float
    npv_levered: float
    irr_levered: float            # NaN when no equity is put in (e.g. 100% C-PACE)
    payback_year: int | None
    financing: Financing
    notes: tuple[str, ...] = ()
    inputs: dict = field(default_factory=dict)

    @property
    def net_capex(self) -> float:
        return self.capex - self.incentive


def underwrite(years, baseline_penalty, retrofit_penalty, capex: float, financing: Financing, discount_rate: float,
               energy_savings: float = 0.0, incentive: float = 0.0, notes=(), inputs: dict | None = None) -> Underwriting:
    """The capital stack for any standard, given the penalty schedules with and without the retrofit."""
    years = list(years)
    base, post = np.asarray(baseline_penalty, float), np.asarray(retrofit_penalty, float)
    if not (len(years) == len(base) == len(post)) or not years:
        raise ValueError("years, baseline_penalty and retrofit_penalty must have the same, non-zero length")
    if np.isnan(base).any() or np.isnan(post).any():
        raise ValueError("a penalty is missing for some year; the standard cannot price it, so neither can this")
    if capex <= 0:
        raise ValueError("capex must be positive")
    h = len(years)
    avoided = base - post
    inc = np.zeros(h)
    inc[0] = incentive
    unlev = avoided + energy_savings + inc
    financed = capex * financing.share if financing.kind != "cash" else 0.0
    pay = pmt(financing.rate, financing.term_years, -financed) if financed else 0.0
    service = np.array([pay if t <= financing.term_years else 0.0 for t in range(1, h + 1)])
    balloon = np.zeros(h)
    if financed and financing.term_years > h:
        balloon[-1] = fv(financing.rate, h, pay, -financed)
    lev = unlev - service - balloon
    equity = capex - financed
    cum = -capex + np.cumsum(unlev)
    paid = np.nonzero(cum >= 0)[0]
    table = pd.DataFrame({"year": years, "baseline_penalty": base, "retrofit_penalty": post, "avoided_penalty": avoided,
                          "energy_savings": energy_savings, "incentive_179d": inc, "unlevered_flow": unlev,
                          "debt_service": service, "balance_repaid": balloon, "levered_flow": lev,
                          "cumulative_unlevered": cum})
    return Underwriting(
        table=table, capex=capex, financed=financed, equity=equity, incentive=incentive, discount_rate=discount_rate,
        npv_benefits=npv(discount_rate, unlev), npv_unlevered=-capex + npv(discount_rate, unlev),
        irr_unlevered=irr_or_nan([-capex, *unlev]), npv_levered=-equity + npv(discount_rate, lev),
        irr_levered=irr_or_nan([-equity, *lev]) if equity > 0 else float("nan"),
        payback_year=int(years[paid[0]]) if len(paid) else None, financing=financing, notes=tuple(notes),
        inputs=inputs or {})


def underwrite_building(jurisdiction: str, building, capex: float, eui_reduction: float, financing: Financing,
                        start_year: int, hold_years: int = 10, discount_rate: float = 0.08,
                        energy_cost_savings: float = 0.0, grid: str = "static_statutory", grid_decline: float = 0.0,
                        construction_start: date | None = None, pwa: bool = False, tax_rate: float = 0.21,
                        blend_standard: bool = False, overrides: dict | None = None) -> Underwriting:
    """Underwrite a retrofit of one building under a GHG standard (NYC LL97, Boston BERDO).

    `eui_reduction` cuts every fuel's use by the same share. `grid="dynamic_grid_projection"` replaces the
    policy's electricity factor with the start year's factor declining by `grid_decline` a year: a scenario,
    not law. The §179D savings percentage is taken to be `eui_reduction` (the retrofit-property route, which
    needs a qualified professional's certification).
    """
    from open_bps.engine import ghg
    from open_bps.registry import get_policy

    p = get_policy(jurisdiction)
    if "ghg_intensity" not in p.metrics:
        raise ValueError(f"{p.id} is an energy standard; pass its penalty schedules to underwrite() instead "
                         "(the grid setting has no effect there)")
    if not 0 < eui_reduction <= 1:
        raise ValueError("eui_reduction must be a fraction between 0 and 1")
    if grid not in ("static_statutory", "dynamic_grid_projection"):
        raise ValueError("grid must be static_statutory or dynamic_grid_projection")
    years = list(range(start_year, start_year + hold_years))
    base_use = building.utilities.by_fuel()
    post_use = {f: v * (1 - eui_reduction) for f, v in base_use.items()}
    notes = []
    base_pen, post_pen = [], []
    for y in years:
        ov = dict(overrides or {})
        if grid == "dynamic_grid_projection" and "electricity" not in ov:
            f0 = p.factor("electricity", start_year)
            if f0 is None:
                raise ValueError(f"{p.id} has no {start_year} electricity factor to project from")
            ov["electricity"] = f0[0] * (1 - grid_decline) ** (y - start_year)
        b = ghg.assess(p, building, y, blend_standard=blend_standard, overrides=ov)
        a = ghg.assess(p, building, y, blend_standard=blend_standard, overrides=ov, use=post_use)
        if b.problems or a.problems:
            raise ValueError(f"cannot price {y}: " + "; ".join(b.problems or a.problems))
        base_pen.append(b.penalty)
        post_pen.append(a.penalty)
        if b.estimated:
            notes.append(f"{y}: uses factors from guidance, not law (Estimated)")
    if grid == "dynamic_grid_projection":
        notes.append(f"grid scenario: electricity factor declines {grid_decline:.1%} a year from {start_year}; not law")
    d = deduction_179d(building.gross_floor_area, eui_reduction, start_year, construction_start, pwa, tax_rate,
                       cost_basis=capex)
    notes.append(f"§179D: {d.note}" + (f"; cash value at a {tax_rate:.0%} tax rate" if d.eligible else ""))
    if not energy_cost_savings:
        notes.append("no energy cost savings given: returns count avoided penalties (and §179D) only")
    if financing.kind != "cash" and financing.term_years > hold_years:
        notes.append(f"the {financing.kind} balance outstanding after {hold_years} years is repaid at the end of the hold"
                     + (" (a C-PACE assessment can usually transfer with the property on sale)" if financing.kind == "cpace" else ""))
    inputs = {"jurisdiction": p.id, "rule_version": p.rule_version, "building_id": building.building_id,
              "gross_floor_area": building.gross_floor_area, "eui_reduction": eui_reduction, "start_year": start_year,
              "hold_years": hold_years, "grid": grid, "grid_decline": grid_decline,
              "construction_start": construction_start, "pwa": pwa, "tax_rate": tax_rate,
              "deduction_179d": d.amount, "deduction_179d_per_sqft": d.per_sqft}
    return underwrite(years, base_pen, post_pen, capex, financing, discount_rate, energy_cost_savings,
                      d.cash_value, list(dict.fromkeys(notes)), inputs)
