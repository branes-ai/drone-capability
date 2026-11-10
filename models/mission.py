"""Mission capability of one (airframe, compute option, mission profile).

The speed a mission can use is the smallest of its speed limits:

  v_mission = min(v_energy, v_stop, v_turn, v_agility, v_max [, v_track])

- v_energy:  v_r or v_e from the power curve, including compute power and
             mass (no limit for speed missions)
- v_stop:    stop within the sensing range d after the perception latency tau,
             braking at a:  v tau + v^2 / (2 a) = d
- v_turn:    hold the mission's tightest turn radius R at the available
             horizontal acceleration:  v = sqrt(a R)
- v_agility: keep the phase lost to latency within a budget at the turn rate
             v / R:  v = PHASE_BUDGET R / tau
- v_max:     level-flight top speed at full thrust
- v_track:   worst case only, when the stack does not predict its own motion
             over the latency:  v = e / tau

Compute enters through power (v_energy, endurance, range), through mass (all
limits, via hover power and thrust-to-weight), and through latency (v_stop,
v_agility, v_track).

v_track replaces the plan's original tracking limit for missions with latency
compensation; see docs/benchmarks/optimal-speed.md, Phase 1 results.
"""

import json
from pathlib import Path

import pen_and_paper as pp
import power_curve as pc

DATA = Path(__file__).resolve().parent / "data"

# Phase lost to latency at the turn rate, as a share of the loop's phase
# margin: 0.5 rad (about 30 degrees) leaves the rest for the plant and filters.
PHASE_BUDGET_RAD = 0.5


def load(name):
    with open(DATA / f"{name}.json") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def v_agility(tau, turn_radius, phase_budget=PHASE_BUDGET_RAD):
    """Highest speed whose turn rate v / R loses at most phase_budget [rad] to latency tau [s]."""
    return phase_budget * turn_radius / tau


def v_turn(accel, turn_radius):
    """Highest speed that holds turn radius R [m] at horizontal acceleration a [m/s^2]."""
    return (accel * turn_radius) ** 0.5


def capability(airframe, compute, mission):
    """Speeds, endurance, range, and the binding speed limit. Units: SI."""
    m = airframe["m"] + compute["m_compute"]
    pipe = mission.get("pipeline")
    # Phase 2 measurements are per pipeline; fall back to the option's default.
    p_c = compute.get("p_compute_by_pipeline_w", {}).get(pipe, compute["p_compute"])
    s, cap = airframe["n_series"], airframe["capacity_ah"]

    curve = pc.PowerCurve(m, airframe["r"], airframe["n_rotors"], airframe["area_cm2"])
    v_e, v_r = pc.optimal_speeds(curve, s, cap, p_c)
    drag = airframe.get("drag_coefficient") or curve.drag_coefficient()
    tw = airframe["max_thrust_n"] / (m * pp.G)
    accel = mission["maneuver_fraction"] * pc.max_horizontal_accel(m, airframe["max_thrust_n"])

    limits = {"v_max": pc.top_speed(m, airframe["max_thrust_n"], drag)}
    if mission["objective"] == "range":
        limits["v_energy"] = v_r
    elif mission["objective"] == "endurance":
        limits["v_energy"] = v_e
    if mission["turn_radius_m"] is not None:
        limits["v_turn"] = v_turn(accel, mission["turn_radius_m"])

    tau = compute.get("latency_by_pipeline_s", {}).get(pipe, compute["latency_s"])
    if tau is not None:
        if mission["sensing_range_m"] is not None:
            limits["v_stop"] = pp.v_stop(tau, mission["sensing_range_m"], accel)
        if mission["turn_radius_m"] is not None:
            limits["v_agility"] = v_agility(tau, mission["turn_radius_m"])
        if mission["uncompensated_latency"] and mission["corridor_m"] is not None:
            limits["v_track"] = pp.v_track(tau, mission["corridor_m"])

    # Every mission profile here is autonomous and needs onboard perception.
    feasible = tau is not None
    binding = min(limits, key=limits.get)
    v_mission = limits[binding] if feasible else 0.0
    out = {
        "mass_kg": m, "thrust_to_weight": tw, "maneuver_accel": accel,
        "v_e": v_e, "v_r": v_r,
        "endurance_s": pc.flight_time(curve, v_e, s, cap, p_c),
        "range_m": pc.distance(curve, v_r, s, cap, p_c),
        "limits": limits, "binding": binding if feasible else "no onboard perception",
        "feasible": feasible, "v_mission": v_mission,
    }
    if feasible:
        # What the mission actually gets at v_mission, rather than at the energy optimum.
        out["range_at_v_mission_m"] = pc.distance(curve, v_mission, s, cap, p_c)
        out["flight_time_at_v_mission_s"] = pc.flight_time(curve, v_mission, s, cap, p_c)
    return out


def latency_budget(cap, mission):
    """Largest latency [s] at which no latency limit binds yet, or None if the mission uses none.

    Below this budget, a faster perception pipeline does not raise v_mission;
    only lighter or lower-power compute does.
    """
    v0 = min(v for k, v in cap["limits"].items() if k in ("v_energy", "v_turn", "v_max"))
    budgets = []
    if mission["turn_radius_m"] is not None:
        budgets.append(PHASE_BUDGET_RAD * mission["turn_radius_m"] / v0)
    if mission["sensing_range_m"] is not None:
        budgets.append(max(0.0, (mission["sensing_range_m"] - v0 * v0 / (2 * cap["maneuver_accel"])) / v0))
    if mission["uncompensated_latency"] and mission["corridor_m"] is not None:
        budgets.append(mission["corridor_m"] / v0)
    return min(budgets) if budgets else None


def mission_value(cap, mission):
    """The quantity the mission's objective maximizes, at v_mission."""
    if not cap["feasible"]:
        return 0.0
    return {"range": cap["range_at_v_mission_m"],
            "endurance": cap["flight_time_at_v_mission_s"],
            "speed": cap["v_mission"]}[mission["objective"]]


def sensitivities(airframe, compute, mission):
    """Change in the mission value per +1 W, +100 g, and +10 ms of compute (finite differences)."""
    base = mission_value(capability(airframe, compute, mission), mission)
    out = {}
    for key, field, step in (("per_watt", "p_compute", 1.0), ("per_100g", "m_compute", 0.1),
                             ("per_10ms", "latency_s", 0.01)):
        if compute[field] is None:
            continue
        # Bump the value the mission actually uses, per-pipeline or default.
        by = {"p_compute": "p_compute_by_pipeline_w", "latency_s": "latency_by_pipeline_s"}.get(field)
        bumped = {**compute, field: compute[field] + step}
        if by and mission.get("pipeline") in compute.get(by, {}):
            bumped[by] = {**compute[by], mission["pipeline"]: compute[by][mission["pipeline"]] + step}
        out[key] = mission_value(capability(airframe, bumped, mission), mission) - base
    return out


def capability_by_name(mission_name, compute_name, airframe_name=None):
    missions, computes, airframes = load("missions"), load("compute"), load("airframes")
    mission = missions[mission_name]
    return capability(airframes[airframe_name or mission["airframe"]], computes[compute_name], mission)
