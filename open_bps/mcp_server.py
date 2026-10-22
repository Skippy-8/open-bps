"""MCP server: open-bps as deterministic tools for an AI assistant.

    pip install "open-bps[mcp]"
    open-bps-mcp                      # stdio; add it to Claude Desktop or any MCP client

Tools compute; they do not guess. Every result carries the rule version, the primary sources and the
disclaimer, and a building the standard cannot price comes back with the reason instead of a number.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from open_bps import DISCLAIMER
from open_bps.engine import ghg
from open_bps.inputs import BuildingRecord, Space, Utilities
from open_bps.registry import get_policy, list_jurisdictions
from open_bps.underwriting.capital_stack import Financing, underwrite_building

try:
    from fastmcp import FastMCP
except ImportError as e:            # pragma: no cover - exercised only without the extra
    raise ImportError('the MCP server needs the mcp extra: pip install "open-bps[mcp]"') from e

mcp = FastMCP("open-bps", instructions=(
    "Building performance standard screening (NYC Local Law 97, Boston BERDO; DC BEPS and Denver for listing). "
    "Use list_supported_jurisdictions first. Figures are screening estimates under the cited rules, not "
    "compliance determinations or advice; report the problems field when a value is missing."))


def _provenance(jurisdiction: str) -> dict:
    p = get_policy(jurisdiction)
    return {"jurisdiction": p.id, "rule_version": p.rule_version, "checked_on": str(p.checked_on),
            "sources": {k: s.url for k, s in p.sources.items()}, "disclaimer": DISCLAIMER}


def _ghg_policy(jurisdiction: str):
    p = get_policy(jurisdiction)
    if "ghg_intensity" not in p.metrics:
        raise ValueError(f"{p.id} sets each building's target in its own published data; these tools cover "
                         "nyc_ll97 and boston_berdo")
    return p


@mcp.tool
def list_supported_jurisdictions() -> list[dict]:
    """Every standard open-bps encodes: its metric, compliance periods, penalty basis and sources."""
    out = []
    for j in list_jurisdictions():
        p = get_policy(j)
        out.append({"id": p.id, "jurisdiction": p.jurisdiction, "program": p.program, "metrics": p.metrics,
                     "compliance_periods": [{"id": q.id, "start_year": q.start_year, "end_year": q.end_year}
                                            for q in p.compliance_periods],
                     "penalty": p.penalty.model_dump(exclude={"source"}),
                     "building_inputs": "ghg_intensity" in p.metrics, **_provenance(j)})
    return out


@mcp.tool
def calculate_building_bps_exposure(jurisdiction: str, gross_floor_area: float, spaces: list[Space],
                                    utilities: Utilities, years: list[int] | None = None,
                                    blend_standard: bool = False) -> dict:
    """Emissions, limit, excess and penalty for one building under a GHG standard (nyc_ll97, boston_berdo),
    for each requested year (default: the first year of each compliance period). Use is held at the values
    given: electricity in kWh a year, other fuels in kBtu (natural gas may be in therms). Spaces are ESPM
    property types with their floor areas; they must add up to the gross floor area within 1%."""
    p = _ghg_policy(jurisdiction)
    b = BuildingRecord(building_id="building", gross_floor_area=gross_floor_area, spaces=spaces, utilities=utilities)
    years = years or [q.start_year for q in p.compliance_periods]
    results = [ghg.assess(p, b, y, blend_standard=blend_standard).__dict__ for y in years]
    for r in results:
        r["problems"], r["notes"] = list(r["problems"]), list(r["notes"])
    return {"results": results, **_provenance(p.id)}


@mcp.tool
def underwrite_retrofit_capital_stack(jurisdiction: str, gross_floor_area: float, spaces: list[Space],
                                      utilities: Utilities, capex: float, eui_reduction_pct: float,
                                      financing_type: Literal["cpace", "debt", "cash"] = "cpace",
                                      financing_rate: float = 0.07, financing_term_years: int = 20,
                                      financed_share: float = 1.0, start_year: int | None = None,
                                      hold_years: int = 10, discount_rate: float = 0.08,
                                      energy_cost_savings: float = 0.0,
                                      grid: Literal["static_statutory", "dynamic_grid_projection"] = "static_statutory",
                                      grid_decline: float = 0.0, construction_start: str | None = None,
                                      pwa: bool = False, tax_rate: float = 0.21) -> dict:
    """Underwrite a retrofit that cuts every fuel's use by `eui_reduction_pct` (a percentage, e.g. 30): the
    baseline and post-retrofit penalties each year, energy cost savings (if given), section 179D (only if
    construction began by 2026-06-30; give construction_start as YYYY-MM-DD), and C-PACE, debt (financed_share
    = loan-to-cost) or cash. Returns NPV, IRR, payback and the annual cash flows. Rates, savings and capex are
    the caller's assumptions."""
    p = _ghg_policy(jurisdiction)
    b = BuildingRecord(building_id="building", gross_floor_area=gross_floor_area, spaces=spaces, utilities=utilities)
    fin = {"cpace": lambda: Financing.cpace(financing_rate, financing_term_years, financed_share),
           "debt": lambda: Financing.debt(financed_share, financing_rate, financing_term_years),
           "cash": Financing.cash}[financing_type]()
    start = start_year or max(date.today().year, p.compliance_periods[0].start_year)
    u = underwrite_building(p.id, b, capex, eui_reduction_pct / 100, fin, start, hold_years, discount_rate,
                            energy_cost_savings, grid, grid_decline,
                            date.fromisoformat(construction_start) if construction_start else None, pwa, tax_rate)
    nan = lambda v: None if v != v else v  # noqa: E731
    return {"summary": {"capex": u.capex, "financed": u.financed, "equity": u.equity, "incentive_179d": u.incentive,
                        "net_capex": u.net_capex, "npv_benefits": u.npv_benefits, "npv_unlevered": u.npv_unlevered,
                        "irr_unlevered": nan(u.irr_unlevered), "npv_levered": u.npv_levered,
                        "irr_levered": nan(u.irr_levered), "payback_year": u.payback_year},
            "annual": u.table.to_dict("records"), "notes": list(u.notes), **_provenance(p.id)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
