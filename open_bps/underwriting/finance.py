"""Excel-equivalent finance functions, so the engine and the Underwriting sheet use the same definitions.

Ported from climate-asset-underwriting (cau/engine/finance.py, same author, MIT).
"""
from __future__ import annotations

import numpy as np


def pmt(rate: float, nper: float, pv: float) -> float:
    """Excel PMT(rate, nper, pv) with fv = 0, type = 0."""
    if rate == 0:
        return -pv / nper
    return -pv * rate / (1 - (1 + rate) ** -nper)


def fv(rate: float, nper: float, payment: float, pv: float) -> float:
    """Excel FV(rate, nper, pmt, pv) with type = 0."""
    if rate == 0:
        return -(pv + payment * nper)
    g = (1 + rate) ** nper
    return -(pv * g + payment * (g - 1) / rate)


def npv(rate: float, flows) -> float:
    """Excel NPV: the first flow is discounted one period."""
    f = np.asarray(flows, float)
    return float(np.sum(f / (1 + rate) ** np.arange(1, len(f) + 1)))


def irr(flows, guess: float = 0.1, tol: float = 1e-12) -> float:
    """IRR with flows[0] at t = 0, the root nearest the guess (as Excel's IRR, which iterates from 10%)."""
    f = np.asarray(flows, float)
    t = np.arange(len(f))

    def v(r):
        return float(np.sum(f / (1 + r) ** t))

    def nearest_bracket(step: float, limit: int):
        a = guess
        for _ in range(limit):
            b = a + step
            if b <= -0.99:
                return None
            if v(a) * v(b) <= 0:
                return (min(a, b), max(a, b))
            a = b
        return None

    brackets = [x for x in (nearest_bracket(0.005, 400), nearest_bracket(-0.005, 200)) if x]
    if not brackets:
        raise ValueError("IRR not bracketed")
    lo, hi = min(brackets, key=lambda x: min(abs(x[0] - guess), abs(x[1] - guess)))
    f_lo = v(lo)
    for _ in range(300):
        mid = (lo + hi) / 2
        f_mid = v(mid)
        if abs(f_mid) < tol:
            break
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def irr_or_nan(flows, guess: float = 0.1) -> float:
    """IRR, or NaN when none exists (e.g. no money is put in); the workbook shows "n/m" through IFERROR."""
    try:
        return irr(flows, guess)
    except ValueError:
        return float("nan")
