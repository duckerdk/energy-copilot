"""Whole-horizon continuous battery flow used by Home Assistant dry_run.

The source implementation was first regression tested by Planner Lab. Energy
is continuous in kWh; the original independent simulate_candidate validates
battery physics, PV-only export and no simultaneous battery charge/discharge.
No external solver dependency or inverter write is introduced.
"""

import math
from heapq import heappop, heappush

from .planner import (
    DEGRADATION_DKK_PER_KWH_DC,
    MIN_SOC,
    PV_EXPORT_MIN_DKK_PER_KWH,
    Dispatch,
    InfeasibleCandidate,
    Plant,
    reference_no_battery,
    simulate_candidate,
)

class _FlowArc:
    """Residual edge in the lab-only continuous energy-flow network."""

    __slots__ = ("to", "reverse", "capacity", "cost", "original")

    def __init__(self, target, reverse, capacity, cost):
        self.to = target
        self.reverse = reverse
        self.capacity = max(0.0, capacity)
        self.original = self.capacity
        self.cost = cost


def optimize_continuous(plant, quarters, *, terminal_value_override=None, terminal_reserve_dc_kwh=None):
    """Optimize continuous battery energy (kWh) without an SOC lattice.

    Formulate quarter-by-quarter grid/PV charging, carrying and house supply
    as a capacitated minimum-cost flow. Every source->sink augmentation with
    negative marginal cost is useful; residual reverse arcs allow reallocating
    earlier decisions when later hours are more profitable. No external solver
    is needed, so the same code runs inside Pyodide on GitHub Pages.

    The charge/discharge/exchange constraints remain independently verified by
    the original production simulate_candidate(), not approximated here.
    This alternative algorithm is used by Planner Lab ONLY.
    """

    if not quarters:
        raise InfeasibleCandidate("horizon:empty")
    if plant.initial_soc_pct < MIN_SOC:
        raise InfeasibleCandidate("soc:below_minimum")
    terminal_price = min(q.buy_dkk_per_kwh for q in quarters)
    terminal_value = (max(0.0, terminal_price / plant.eta_grid_to_battery)
                      if terminal_value_override is None else terminal_value_override)
    calibrated = Plant(
        **{**vars(plant), "terminal_value_dkk_per_kwh_dc": terminal_value}
    )
    reference = reference_no_battery(calibrated, quarters)

    capacity = plant.battery_capacity_dc_kwh
    minimum = capacity * MIN_SOC / 100.0
    usable = capacity - minimum
    initial = capacity * plant.initial_soc_pct / 100.0 - minimum
    n = len(quarters)
    count = 3 * n + 3
    source, sink = 0, 1
    # B(t): energy at start of quarter t, A(t): after SOC capacity gate,
    # C(t): shared power-limit gate for PV and grid charging in quarter t.
    before = lambda t: 2 + 3 * t
    after = lambda t: 3 + 3 * t
    charge = lambda t: 4 + 3 * t
    network = [[] for _ in range(count)]

    def add_edge(fr, to, cap, price):
        forward = _FlowArc(to, len(network[to]), cap, price)
        reverse = _FlowArc(fr, len(network[fr]), 0.0, -price)
        network[fr].append(forward)
        network[to].append(reverse)
        return forward

    # A very large finite incentive forces the physically available initial
    # energy into the graph. It is only a bookkeeping term: the actual plan
    # cost is ALWAYS recomputed by the original independent simulator.
    initial_edge = add_edge(source, before(0), initial, -1_000_000.0)
    pv_edges = []
    grid_edges = []
    discharge_edges = []
    for i, q in enumerate(quarters):
        eta_pv = plant.eta_pv_to_ac
        pv_home = min(q.pv_dc_kwh, q.home_ac_kwh / eta_pv)
        surplus = max(0.0, q.pv_dc_kwh - pv_home)
        home_from_grid = max(0.0, q.home_ac_kwh - pv_home * eta_pv)
        pv_export_allowed = (
            q.pv_export_enabled
            and q.sell_dkk_per_kwh >= PV_EXPORT_MIN_DKK_PER_KWH
        )
        # Charging with PV replaces potential PV export, if enabled. This
        # opportunity cost must NOT be omitted when sell is above threshold.
        pv_charge_cost = (
            q.sell_dkk_per_kwh
            * plant.eta_pv_to_ac
            / plant.eta_pv_to_battery
            if pv_export_allowed
            else 0.0
        )
        max_charge = plant.battery_voltage_v * plant.charge_limit_a / 4000.0
        max_grid = plant.battery_voltage_v * plant.grid_charge_limit_a / 4000.0
        max_discharge = (
            plant.battery_voltage_v * plant.discharge_limit_a / 4000.0
        )
        # SOC gate limits carried + newly charged energy, not merely carry.
        add_edge(before(i), after(i), usable, 0.0)
        add_edge(after(i), before(i + 1), usable, 0.0)
        discharge_edges.append(
            add_edge(
                after(i),
                sink,
                min(max_discharge, home_from_grid / plant.eta_battery_to_ac),
                (
                    DEGRADATION_DKK_PER_KWH_DC
                    - q.buy_dkk_per_kwh * plant.eta_battery_to_ac
                ),
            )
        )
        pv_edges.append(
            add_edge(
                source, charge(i), surplus * plant.eta_pv_to_battery, pv_charge_cost
            )
        )
        grid_edges.append(
            add_edge(
                source,
                charge(i),
                max_grid,
                q.buy_dkk_per_kwh / plant.eta_grid_to_battery,
            )
        )
        add_edge(charge(i), before(i + 1), max_charge, 0.0)
    add_edge(before(n), sink, usable, -terminal_value)

    # The initial graph is acyclic: source -> time-ordered nodes -> sink.
    # Compute exact initial shortest-path potentials in one forward pass.
    distances = [float("inf")] * count
    distances[source] = 0.0
    tolerance = 1e-10
    for edge in network[source]:
        if edge.capacity > tolerance:
            distances[edge.to] = min(distances[edge.to], edge.cost)
    for u in range(2, count):
        if not math.isfinite(distances[u]):
            continue
        for edge in network[u]:
            if edge.capacity > tolerance:
                proposal = distances[u] + edge.cost
                if proposal < distances[edge.to]:
                    distances[edge.to] = proposal
    potential = [value if math.isfinite(value) else 0.0 for value in distances]

    iterations = 0
    while True:
        # Dijkstra on nonnegative reduced costs; the potential is updated
        # after each augmentation. Reverse arcs allow globally changing past
        # choices, rather than greedily assigning energy quarter by quarter.
        dist = [float("inf")] * count
        previous = [None] * count
        dist[source] = 0.0
        heap = [(0.0, source)]
        while heap:
            length, u = heappop(heap)
            if length > dist[u] + tolerance:
                continue
            for edge_index, edge in enumerate(network[u]):
                if edge.capacity <= tolerance:
                    continue
                reduced = edge.cost + potential[u] - potential[edge.to]
                if reduced < -1e-7:
                    raise InfeasibleCandidate(
                        "continuous:negative_reduced_cost"
                    )
                proposal = length + max(0.0, reduced)
                if proposal < dist[edge.to] - tolerance:
                    dist[edge.to] = proposal
                    previous[edge.to] = (u, edge_index)
                    heappush(heap, (proposal, edge.to))
        if previous[sink] is None:
            break
        marginal_cost = dist[sink] + potential[sink] - potential[source]
        if marginal_cost >= -1e-8:
            break

        current = sink
        flow = float("inf")
        while current != source:
            predecessor, edge_index = previous[current]
            edge = network[predecessor][edge_index]
            flow = min(flow, edge.capacity)
            current = predecessor
        if flow <= tolerance:
            raise InfeasibleCandidate("continuous:tiny_augmentation")

        for vertex, length in enumerate(dist):
            if math.isfinite(length):
                potential[vertex] += length
        current = sink
        while current != source:
            predecessor, edge_index = previous[current]
            edge = network[predecessor][edge_index]
            edge.capacity -= flow
            network[current][edge.reverse].capacity += flow
            current = predecessor
        iterations += 1
        if iterations > 20 * n + 100:
            raise InfeasibleCandidate("continuous:iteration_limit")

    if abs(initial_edge.original - initial_edge.capacity - initial) > 1e-7:
        raise InfeasibleCandidate("continuous:initial_energy_unrouted")

    dispatches = []
    for q, pv_edge, grid_edge, discharge_edge in zip(
        quarters, pv_edges, grid_edges, discharge_edges, strict=True
    ):
        pv_home = min(q.pv_dc_kwh, q.home_ac_kwh / plant.eta_pv_to_ac)
        pv_surplus = max(0.0, q.pv_dc_kwh - pv_home)
        pv_to_battery = max(
            0.0,
            (pv_edge.original - pv_edge.capacity) / plant.eta_pv_to_battery,
        )
        grid_to_battery = max(
            0.0,
            (grid_edge.original - grid_edge.capacity) / plant.eta_grid_to_battery,
        )
        battery_to_home = max(
            0.0, discharge_edge.original - discharge_edge.capacity
        )
        unused_pv = max(0.0, pv_surplus - pv_to_battery)
        can_export = (
            q.pv_export_enabled
            and q.sell_dkk_per_kwh >= PV_EXPORT_MIN_DKK_PER_KWH
        )
        pv_export = unused_pv if can_export else 0.0
        dispatches.append(
            Dispatch(
                pv_to_home_dc_kwh=pv_home,
                pv_to_battery_dc_kwh=pv_to_battery,
                pv_to_export_dc_kwh=pv_export,
                pv_curtailed_dc_kwh=unused_pv - pv_export,
                grid_to_battery_ac_kwh=grid_to_battery,
                battery_to_home_dc_kwh=battery_to_home,
            )
        )

    validated = simulate_candidate(calibrated, quarters, tuple(dispatches))
    from .horizon_optimizer import HorizonResult

    return HorizonResult(
        candidate=validated,
        reference=reference,
        dispatches=tuple(dispatches),
        terminal_value_dkk_per_kwh_dc=terminal_value,
        evaluated_transitions=iterations,
        soc_resolution_dc_kwh=0.0,
        method="continuous_min_cost_flow_no_soc_lattice",
    )

