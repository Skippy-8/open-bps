"""The MCP tools, through fastmcp's in-memory client (skipped without the mcp extra)."""
from __future__ import annotations

import asyncio
import json

import pytest

fastmcp = pytest.importorskip("fastmcp")


def _call(tool: str, args: dict | None = None):
    from fastmcp import Client

    from open_bps.mcp_server import mcp

    async def go():
        async with Client(mcp) as c:
            r = await c.call_tool(tool, args or {})
            return json.loads(r.content[0].text)
    return asyncio.run(go())


def test_mcp_tools():
    js = _call("list_supported_jurisdictions")
    assert {j["id"] for j in js} == {"boston_berdo", "dc_beps", "denver_energize", "nyc_ll97"}
    assert all(j["rule_version"] and j["disclaimer"] for j in js)
    bldg = {"jurisdiction": "nyc_ll97", "gross_floor_area": 30_000,
            "spaces": [{"property_type": "Multifamily Housing", "gfa": 24_000}, {"property_type": "Retail Store", "gfa": 6_000}],
            "utilities": {"electricity_kwh": 250_000, "natural_gas_kbtu": 1_560_000, "fuel_oil_2_kbtu": 950_000}}
    ex = _call("calculate_building_bps_exposure", {**bldg, "years": [2024]})
    assert round(ex["results"][0]["emissions_t"], 1) == 225.6 and ex["rule_version"].startswith("nyc")
    uw = _call("underwrite_retrofit_capital_stack", {**bldg, "capex": 600_000, "eui_reduction_pct": 40,
                                                     "start_year": 2026, "construction_start": "2026-05-01"})
    assert uw["summary"]["incentive_179d"] > 0 and len(uw["annual"]) == 10 and uw["sources"]
    with pytest.raises(Exception, match="sets each building's target"):
        _call("calculate_building_bps_exposure", {**bldg, "jurisdiction": "denver"})
