"""DC Optimal Power Flow solver.

Implements a vanilla DC-OPF LP. Lossless, single-period, linear power flow
on a directed graph of buses/lines. Minimises generation cost subject to:

    - generation lower/upper bounds per bus
    - DC power balance at each bus (sum_in - sum_out = load - gen)
    - thermal limit per line (|flow| <= limit)
    - reference bus phase angle = 0 (handled implicitly by dropping its row)

Solver: `scipy.optimize.linprog` (HiGHS). Returns flows, generation
schedule, and locational marginal prices (LMPs) derived from the dual
variables on the power-balance constraints. Designed to run in
< 50ms for sub-networks of < 50 buses, which is the FRONTIER.md
E.2 acceptance target.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.optimize import linprog


# ── Inputs ────────────────────────────────────────────────────────────────


@dataclass
class Bus:
    name: str
    load_mw: float = 0.0
    gen_min_mw: float = 0.0
    gen_max_mw: float = 0.0
    gen_cost_per_mwh: float = 0.0  # marginal cost; the dispatch objective
    is_reference: bool = False


@dataclass
class Line:
    from_bus: str
    to_bus: str
    susceptance: float = 1.0        # b in the DC linearisation
    limit_mw: float = float("inf")  # thermal capacity (symmetric: ±limit)


@dataclass
class GridTopology:
    buses: list[Bus]
    lines: list[Line]

    def bus_index(self, name: str) -> int:
        for i, b in enumerate(self.buses):
            if b.name == name:
                return i
        raise KeyError(f"bus {name!r} not found")

    @property
    def reference_index(self) -> int:
        for i, b in enumerate(self.buses):
            if b.is_reference:
                return i
        return 0  # default: bus 0 is reference if none flagged


# ── Outputs ───────────────────────────────────────────────────────────────


@dataclass
class DCOPFResult:
    success: bool
    objective_cost: float
    gen_mw: dict[str, float] = field(default_factory=dict)
    flows_mw: dict[tuple[str, str], float] = field(default_factory=dict)
    angles_rad: dict[str, float] = field(default_factory=dict)
    lmps: dict[str, float] = field(default_factory=dict)
    binding_lines: list[tuple[str, str]] = field(default_factory=list)
    message: str = ""


# ── Core solver ───────────────────────────────────────────────────────────


def solve_dc_opf(topology: GridTopology) -> DCOPFResult:
    """Solve a single-period DC OPF.

    Variables (in this order): [g_0, …, g_{n-1}, θ_0, …, θ_{n-1}]
        where g_i is generation MW at bus i and θ_i is voltage angle (rad).

    Constraints:
        - For each non-reference bus i:
            g_i − sum_j b_ij (θ_i − θ_j) = load_i        (equality)
        - For the reference bus:
            θ_ref = 0                                     (equality)
        - For each line (i → j):
            b_ij (θ_i − θ_j) ≤ limit_ij                  (inequality)
            −b_ij (θ_i − θ_j) ≤ limit_ij                 (inequality)
        - g_i ∈ [gen_min_i, gen_max_i]
        - θ_i unbounded (modelled with large bounds for HiGHS stability)

    Objective: minimise sum_i cost_i * g_i.
    """
    n = len(topology.buses)
    m = len(topology.lines)
    if n == 0:
        return DCOPFResult(success=False, objective_cost=0.0, message="no buses")

    # Variable layout
    g_slice = slice(0, n)
    th_slice = slice(n, 2 * n)
    num_vars = 2 * n

    # Objective: cost_i * g_i ; θ_i carries 0 cost
    c = np.zeros(num_vars)
    for i, b in enumerate(topology.buses):
        c[i] = b.gen_cost_per_mwh

    # Equality constraints
    A_eq_rows: list[np.ndarray] = []
    b_eq_rows: list[float] = []

    # Reference angle = 0
    ref_idx = topology.reference_index
    row = np.zeros(num_vars)
    row[n + ref_idx] = 1.0
    A_eq_rows.append(row)
    b_eq_rows.append(0.0)

    # Power balance at every bus (incl. reference, which becomes the slack
    # by construction since linprog will satisfy total generation = total
    # load through that one equation).
    name_to_idx = {b.name: i for i, b in enumerate(topology.buses)}
    incidence = np.zeros((n, m))  # +1 for from, −1 for to
    susceptances = np.array([ln.susceptance for ln in topology.lines])
    for k, ln in enumerate(topology.lines):
        i = name_to_idx[ln.from_bus]
        j = name_to_idx[ln.to_bus]
        incidence[i, k] = +1.0
        incidence[j, k] = -1.0

    # Line flow F_k = b_k * (θ_from − θ_to) — express as linear in θ:
    # F_k(θ) = b_k * (e_from − e_to)^T θ
    # Power-balance row i:  g_i − sum_k incidence[i,k] * F_k = load_i
    B_bus = incidence @ np.diag(susceptances) @ incidence.T  # nodal susceptance matrix
    for i, bus in enumerate(topology.buses):
        row = np.zeros(num_vars)
        row[i] = 1.0  # +g_i
        # − sum_j B_bus[i, j] * θ_j
        row[n: 2 * n] = -B_bus[i, :]
        A_eq_rows.append(row)
        b_eq_rows.append(bus.load_mw)

    A_eq = np.array(A_eq_rows)
    b_eq = np.array(b_eq_rows)

    # Inequality constraints: line flow limits.
    A_ub_rows: list[np.ndarray] = []
    b_ub_rows: list[float] = []
    line_keys: list[tuple[str, str]] = []
    for k, ln in enumerate(topology.lines):
        i = name_to_idx[ln.from_bus]
        j = name_to_idx[ln.to_bus]
        # +b_k (θ_i − θ_j) ≤ limit
        row = np.zeros(num_vars)
        row[n + i] = ln.susceptance
        row[n + j] = -ln.susceptance
        A_ub_rows.append(row)
        b_ub_rows.append(ln.limit_mw)
        # −b_k (θ_i − θ_j) ≤ limit
        A_ub_rows.append(-row)
        b_ub_rows.append(ln.limit_mw)
        line_keys.append((ln.from_bus, ln.to_bus))

    A_ub = np.array(A_ub_rows) if A_ub_rows else None
    b_ub = np.array(b_ub_rows) if b_ub_rows else None

    # Bounds: generation min/max; angles fully unbounded. DC-OPF voltage
    # angles can take any real value; physical "±π" intuitions only apply
    # to AC. HiGHS is happy with `None` for free variables.
    bounds: list[tuple[Optional[float], Optional[float]]] = []
    for b in topology.buses:
        bounds.append((b.gen_min_mw, b.gen_max_mw))
    for _ in topology.buses:
        bounds.append((None, None))

    res = linprog(
        c=c,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )

    if not res.success:
        return DCOPFResult(
            success=False,
            objective_cost=float("nan"),
            message=res.message or "linprog failed",
        )

    x = res.x
    gen_mw = {b.name: float(x[g_slice][i]) for i, b in enumerate(topology.buses)}
    angles_rad = {b.name: float(x[th_slice][i]) for i, b in enumerate(topology.buses)}

    flows_mw: dict[tuple[str, str], float] = {}
    binding_lines: list[tuple[str, str]] = []
    for k, ln in enumerate(topology.lines):
        flow = ln.susceptance * (angles_rad[ln.from_bus] - angles_rad[ln.to_bus])
        flows_mw[(ln.from_bus, ln.to_bus)] = float(flow)
        if np.isfinite(ln.limit_mw) and abs(flow) >= ln.limit_mw - 1e-6:
            binding_lines.append((ln.from_bus, ln.to_bus))

    # LMPs from the duals on the power-balance equalities.
    # linprog "ineqlin" / "eqlin" via res.eqlin.marginals: the *first*
    # equality is the reference-angle row (no economic meaning).
    lmps: dict[str, float] = {}
    eqlin = getattr(res, "eqlin", None)
    duals = None
    if eqlin is not None and getattr(eqlin, "marginals", None) is not None:
        duals = np.asarray(eqlin.marginals, dtype=float)
    if duals is not None and len(duals) == n + 1:
        # Skip the reference-angle row at index 0. HiGHS returns
        # marginals = d(obj)/d(rhs) for equality constraints under a
        # minimisation objective. Our power-balance RHS is the load at
        # each bus, so the LMP — defined as the marginal cost of
        # serving one more MW of load — is exactly the marginal.
        bus_marginals = duals[1:]
        for i, b in enumerate(topology.buses):
            lmps[b.name] = float(bus_marginals[i])
    else:
        # Fallback: dispatch-cost-based LMP at marginal generator.
        cost = float(res.fun)
        total_load = sum(b.load_mw for b in topology.buses)
        avg = cost / max(total_load, 1e-9)
        for b in topology.buses:
            lmps[b.name] = avg

    return DCOPFResult(
        success=True,
        objective_cost=float(res.fun),
        gen_mw=gen_mw,
        flows_mw=flows_mw,
        angles_rad=angles_rad,
        lmps=lmps,
        binding_lines=binding_lines,
        message=res.message,
    )
