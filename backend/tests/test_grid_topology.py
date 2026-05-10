"""Phase-E.1 tests: grid topology loader and DC-OPF compatibility."""
from __future__ import annotations

from pathlib import Path

from app.grid.dc_opf import solve_dc_opf
from app.grid.topology import (
    apply_ntc_overrides,
    bundle_to_topology,
    load_topology_bundle,
    market_to_bus,
    seed_topology_bundle,
    write_topology_bundle,
)


def test_seed_bundle_has_every_priced_market() -> None:
    bundle = seed_topology_bundle()
    market_codes = {b.get("market_code") for b in bundle["buses"]}
    market_codes.discard(None)
    expected = {
        "ERCOT_NORTH", "ERCOT_HOUSTON",
        "PJM_WESTERN_HUB",
        "NYISO_ZONE_J",
        "ISONE_MASS_HUB",
        "GB_POWER",
        "EPEX_DE", "EPEX_FR",
        "NORDPOOL_SE3",
    }
    assert expected <= market_codes


def test_seed_bundle_buses_and_lines_are_referentially_consistent() -> None:
    bundle = seed_topology_bundle()
    bus_names = {b["name"] for b in bundle["buses"]}
    for line in bundle["lines"]:
        assert line["from_bus"] in bus_names
        assert line["to_bus"] in bus_names
        assert float(line["susceptance"]) > 0
        assert float(line["limit_mw"]) > 0


def test_seed_bundle_solves_with_dc_opf(tmp_path: Path) -> None:
    bundle = seed_topology_bundle()
    # Stress the network with a 4 GW load lifted at GB and PJM nodes.
    for b in bundle["buses"]:
        if b["name"] in {"GB_POWER", "PJM_WESTERN_HUB"}:
            b["load_mw"] = 2000.0
    topo = bundle_to_topology(bundle)
    result = solve_dc_opf(topo)
    assert result.success
    # Total dispatched gen must match total load (within numerical tol)
    total_load = sum(b.load_mw for b in topo.buses)
    total_gen = sum(result.gen_mw.values())
    assert abs(total_gen - total_load) < 1e-3


def test_write_and_load_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "grid.json"
    path = write_topology_bundle(target)
    assert path == target
    assert target.exists()
    loaded = load_topology_bundle(target)
    seed = seed_topology_bundle()
    assert loaded["version"] == seed["version"]
    assert {b["name"] for b in loaded["buses"]} == {b["name"] for b in seed["buses"]}


def test_load_falls_back_to_seed_when_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"
    loaded = load_topology_bundle(missing)
    assert loaded == seed_topology_bundle()


def test_market_to_bus_resolves_known_markets() -> None:
    bundle = seed_topology_bundle()
    assert market_to_bus(bundle, "GB_POWER") == "GB_POWER"
    assert market_to_bus(bundle, "PJM_WESTERN_HUB") == "PJM_WESTERN_HUB"
    assert market_to_bus(bundle, "NOT_A_MARKET") is None


def test_apply_ntc_overrides_replaces_known_interface() -> None:
    bundle = seed_topology_bundle()
    overrides = {("GB_POWER", "EPEX_FR"): 4500.0}
    out = apply_ntc_overrides(bundle, overrides)
    for line in out["lines"]:
        if line["from_bus"] == "GB_POWER" and line["to_bus"] == "EPEX_FR":
            assert line["limit_mw"] == 4500.0
            assert "live" in line["source"].lower()
            break
    else:
        raise AssertionError("GB-FR line not found in seed bundle")


def test_apply_ntc_overrides_handles_reverse_direction() -> None:
    bundle = seed_topology_bundle()
    overrides = {("EPEX_FR", "GB_POWER"): 3200.0}
    out = apply_ntc_overrides(bundle, overrides)
    for line in out["lines"]:
        if line["from_bus"] == "GB_POWER" and line["to_bus"] == "EPEX_FR":
            assert line["limit_mw"] == 3200.0
            break
    else:
        raise AssertionError("GB-FR line not found in seed bundle")
