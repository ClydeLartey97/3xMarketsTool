"""Phase-E.2 tests: DC-OPF solver."""
from __future__ import annotations

import time

import pytest

from app.grid.dc_opf import Bus, GridTopology, Line, solve_dc_opf


def test_three_bus_no_congestion_clears_at_cheap_gen() -> None:
    """Classic 3-bus example. With no binding line limits, the cheapest
    generator serves the entire load and LMPs converge to the marginal
    cost of that generator."""
    topo = GridTopology(
        buses=[
            Bus(name="A", gen_min_mw=0, gen_max_mw=200, gen_cost_per_mwh=20.0, is_reference=True),
            Bus(name="B", gen_min_mw=0, gen_max_mw=200, gen_cost_per_mwh=40.0),
            Bus(name="C", load_mw=100.0),
        ],
        lines=[
            Line(from_bus="A", to_bus="B", susceptance=10.0, limit_mw=1000.0),
            Line(from_bus="B", to_bus="C", susceptance=10.0, limit_mw=1000.0),
            Line(from_bus="A", to_bus="C", susceptance=10.0, limit_mw=1000.0),
        ],
    )
    result = solve_dc_opf(topo)
    assert result.success
    # Total gen = total load
    assert abs(sum(result.gen_mw.values()) - 100.0) < 1e-6
    # Cheap gen at A should dominate
    assert result.gen_mw["A"] > 50.0
    assert result.gen_mw["B"] < 50.0
    # LMPs equal marginal price at the only producing generator (£20/MWh)
    for bus, lmp in result.lmps.items():
        assert abs(lmp - 20.0) < 1e-3, f"{bus} LMP {lmp} != 20"
    assert result.binding_lines == []


def test_three_bus_with_congestion_splits_lmps() -> None:
    """Force line A→C to bind so generation must shift to expensive B
    and LMPs diverge between A and C."""
    topo = GridTopology(
        buses=[
            Bus(name="A", gen_min_mw=0, gen_max_mw=200, gen_cost_per_mwh=20.0, is_reference=True),
            Bus(name="B", gen_min_mw=0, gen_max_mw=200, gen_cost_per_mwh=40.0),
            Bus(name="C", load_mw=120.0),
        ],
        lines=[
            Line(from_bus="A", to_bus="B", susceptance=10.0, limit_mw=1000.0),
            Line(from_bus="B", to_bus="C", susceptance=10.0, limit_mw=1000.0),
            Line(from_bus="A", to_bus="C", susceptance=10.0, limit_mw=40.0),
        ],
    )
    result = solve_dc_opf(topo)
    assert result.success
    # Some load must come from the expensive generator at B
    assert result.gen_mw["B"] > 1.0
    # And the limited line should be binding
    assert ("A", "C") in result.binding_lines
    # LMP at C should be strictly greater than at A
    assert result.lmps["C"] > result.lmps["A"] - 1e-6


def test_infeasible_when_demand_exceeds_capacity() -> None:
    topo = GridTopology(
        buses=[
            Bus(name="A", gen_min_mw=0, gen_max_mw=50, gen_cost_per_mwh=10.0, is_reference=True),
            Bus(name="B", load_mw=100.0),
        ],
        lines=[Line(from_bus="A", to_bus="B", susceptance=10.0, limit_mw=1000.0)],
    )
    result = solve_dc_opf(topo)
    assert result.success is False


def test_runs_under_50ms_for_small_grid() -> None:
    """FRONTIER.md E.2 acceptance: < 50ms for a small network."""
    topo = GridTopology(
        buses=[
            Bus(name=f"N{i}", gen_min_mw=0, gen_max_mw=200,
                gen_cost_per_mwh=20.0 + i * 0.5, is_reference=(i == 0))
            for i in range(10)
        ]
        + [Bus(name="LOAD", load_mw=500.0)],
        lines=[
            Line(from_bus=f"N{i}", to_bus="LOAD", susceptance=5.0, limit_mw=200.0)
            for i in range(10)
        ],
    )
    t0 = time.perf_counter()
    result = solve_dc_opf(topo)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert result.success
    assert elapsed_ms < 50.0, f"DC-OPF took {elapsed_ms:.2f}ms (> 50ms target)"


def test_flow_directions_are_consistent() -> None:
    topo = GridTopology(
        buses=[
            Bus(name="A", gen_min_mw=0, gen_max_mw=200, gen_cost_per_mwh=10.0, is_reference=True),
            Bus(name="B", load_mw=80.0),
        ],
        lines=[Line(from_bus="A", to_bus="B", susceptance=10.0, limit_mw=1000.0)],
    )
    result = solve_dc_opf(topo)
    assert result.success
    flow = result.flows_mw[("A", "B")]
    # Generation at A flows to load at B → positive in the (A,B) direction
    assert flow > 0
    assert abs(flow - 80.0) < 1e-6
