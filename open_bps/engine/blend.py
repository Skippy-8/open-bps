"""Building emissions limits for mixed-use buildings, from a policy's limit table and blending rule.

  gfa_weighted         (NYC, 1 RCNY §103-14 Eq. 103-14.1)   limit = Σ space_gfa_i × limit_i
  largest_primary_use  (Boston default)                      limit = total sq ft × limit of the largest use
  primary_use_blend    (Boston, opt-in, P&P §6)              uses with >= 10% of the sq ft are primary; the
                                                             rest is added to the largest primary use

Every space is mapped through the policy's property-type map. A type the policy cannot map is never given
a default: under gfa_weighted it stops the calculation; under Boston's rules a non-primary space (< 10% of
the building) is folded into the largest primary use, which is what the regulation does with it anyway.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from open_bps.inputs import Space
from open_bps.policy import JurisdictionPolicy


@dataclass(frozen=True)
class SpaceLimit:
    property_type: str
    statutory_class: str | None
    gfa: float
    applied_class: str | None          # the class whose limit this space's sq ft is counted at
    threshold: float | None            # tCO2e per sq ft per year
    contribution: float | None         # tCO2e per year
    primary: bool | None = None


@dataclass(frozen=True)
class Limit:
    year: int
    method: str
    limit_t: float | None              # tCO2e per year; None when it cannot be computed
    total_gfa: float
    spaces: tuple[SpaceLimit, ...]
    problems: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    estimated: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def blended_cap(self) -> float | None:
        """The limit per sq ft (tCO2e/sf/yr)."""
        return None if self.limit_t is None else self.limit_t / self.total_gfa

    def frame(self) -> pd.DataFrame:
        """One row per space: the audit trail behind the limit."""
        return pd.DataFrame([s.__dict__ for s in self.spaces])


def limit(policy: JurisdictionPolicy, spaces: list[Space], year: int, blend: bool = False) -> Limit:
    """The building's emissions limit for `year`. `blend=True` uses the policy's optional blended standard
    (Boston); the default is the policy's default method."""
    if policy.thresholds is None or policy.blending is None:
        raise ValueError(f"{policy.id} has no property-type limit table (its targets come from building data)")
    method = policy.blending.method
    if blend:
        if policy.blending.optional_method is None:
            raise ValueError(f"{policy.id} has no optional blended standard; its method is {method}")
        method = policy.blending.optional_method
    total = sum(s.gfa for s in spaces)
    mapped = [(s, policy.statutory_class(s.property_type)) for s in spaces]
    est = policy.threshold_estimated(year)
    if policy.period_for(year) is None:
        return Limit(year, method, None, total, (), (f"{year} is before the first compliance period",))
    if method == "gfa_weighted":
        return _gfa_weighted(policy, mapped, year, total, est)
    return _primary_uses(policy, mapped, year, total, est, blend=method == "primary_use_blend")


def _unmapped_reason(policy: JurisdictionPolicy, t: str) -> str:
    why = policy.unassignable_types.get(t)
    return f"property type {t!r} has no limit under {policy.id}" + (f" ({why})" if why else "")


def _gfa_weighted(policy, mapped, year, total, est) -> Limit:
    rows, problems = [], []
    for s, cls in mapped:
        thr = policy.threshold(cls, year) if cls else None
        if cls is None:
            problems.append(_unmapped_reason(policy, s.property_type))
        rows.append(SpaceLimit(s.property_type, cls, s.gfa, cls, thr, None if thr is None else s.gfa * thr))
    lim = None if problems else sum(r.contribution for r in rows)
    return Limit(year, "gfa_weighted", lim, total, tuple(rows), tuple(problems), estimated=est)


def _primary_uses(policy, mapped, year, total, est, blend: bool) -> Limit:
    share = policy.blending.primary_use_min_share or 0.0
    by_class: dict[str, float] = {}
    for s, cls in mapped:
        if cls:
            by_class[cls] = by_class.get(cls, 0.0) + s.gfa
    problems, notes = [], []
    for s, cls in mapped:
        if cls is None and s.gfa / total >= share:
            problems.append(_unmapped_reason(policy, s.property_type) + f"; it is {s.gfa / total:.0%} of the building")
        elif cls is None:
            notes.append(f"{s.property_type!r} ({s.gfa / total:.1%}) is not a primary use; counted with the largest use")
    if not by_class:
        problems.append("no space maps to a building use")
    if problems:
        rows = tuple(SpaceLimit(s.property_type, c, s.gfa, None, None, None) for s, c in mapped)
        return Limit(year, "primary_use_blend" if blend else "largest_primary_use", None, total, rows,
                     tuple(problems), tuple(notes), est)
    largest = max(by_class, key=by_class.get)
    primary = {c for c, a in by_class.items() if a / total >= share} | {largest}
    rows = []
    for s, cls in mapped:
        applied = cls if (blend and cls in primary) else largest
        thr = policy.threshold(applied, year)
        rows.append(SpaceLimit(s.property_type, cls, s.gfa, applied, thr, s.gfa * thr, cls in primary))
    if blend and len(primary) == 1:
        notes.append("only one primary use, so the blended standard equals the default")
    if blend:
        notes.append("primary uses judged by sq ft only; a use can also qualify on >10% of energy or emissions")
    lim = sum(r.contribution for r in rows)
    return Limit(year, "primary_use_blend" if blend else "largest_primary_use", lim, total, tuple(rows), (),
                 tuple(notes), est, {"largest_use": largest, "primary_uses": sorted(primary)})
