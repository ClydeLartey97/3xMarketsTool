"""Materialise the grid topology bundle to backend/data/grid_topology.json.

The seed bundle is deterministic and covers every market we already
price. When `ENTSOE_TOKEN` is set, this script overlays live NTC values
for the European interfaces. Either way it produces a runnable
`grid_topology.json` so the downstream pieces (E.2 DC-OPF, E.3 basis
trades, E.4 congestion-aware risk, E.5 UI) have a single source of
truth on disk.
"""
from __future__ import annotations

import argparse
import logging

from app.grid.topology import (
    apply_ntc_overrides,
    fetch_entsoe_ntc_overrides,
    seed_topology_bundle,
    write_topology_bundle,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-network", action="store_true",
                        help="Skip ENTSO-E NTC enrichment even if a token is set.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    bundle = seed_topology_bundle()
    if not args.no_network:
        overrides = fetch_entsoe_ntc_overrides()
        bundle = apply_ntc_overrides(bundle, overrides)

    path = write_topology_bundle(override=bundle)
    print(f"wrote {path} — {len(bundle['buses'])} buses, {len(bundle['lines'])} lines")


if __name__ == "__main__":
    main()
