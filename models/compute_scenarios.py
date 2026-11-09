"""First-order cost of onboard compute, per airframe class.

Reproduces the estimate tables in docs/benchmarks/optimal-speed.md:
  1. endurance, range, and thrust-to-weight for each compute option
  2. the endurance cost split into power-only and mass-only parts
  3. stopping-limited safe speed versus latency and sensing range

The compute options are illustrative, not measured. Phase 2 of the plan
replaces them with measured power, mass, and latency.
"""

from pen_and_paper import estimate, v_stop

# Airframes from the paper: Fig. 1 small drone, Table III Mavic 3 and Matrice 200.
# r is the propeller radius [m]; capacity_ah is the total pack capacity.
AIRFRAMES = {
    "racing  (0.75 kg, 4S 1.8 Ah, 5.1 in)": dict(m=0.75, r=0.0648, n_rotors=4, n_series=4, capacity_ah=1.8, area_cm2=200),
    "scout   (0.90 kg, 4S 5.0 Ah, Mavic 3)": dict(m=0.90, r=0.119, n_rotors=4, n_series=4, capacity_ah=5.0, area_cm2=215),
    "inspect (6.14 kg, 6S2P 15.3 Ah, M200)": dict(m=6.14, r=0.216, n_rotors=4, n_series=6, capacity_ah=15.3, area_cm2=1700),
}

# (name, electrical power [W], mass added over a flight-controller-only build [kg])
COMPUTE = [
    ("flight-controller MCU only", 0.5, 0.0),
    ("efficient companion", 7.0, 0.04),
    ("Orin NX 15 W class", 15.0, 0.12),
    ("AGX Orin 40 W class", 40.0, 0.35),
]


def with_mass(airframe, extra_kg):
    return {**airframe, "m": airframe["m"] + extra_kg}


def compute_cost_table():
    for name, af in AIRFRAMES.items():
        base = estimate(**af)
        print(f"\n{name}: v_e={base['e']['v']:.1f} m/s  v_r={base['r']['v']:.1f} m/s  P_mot,e={base['e']['p_mot']:.0f} W")
        for cname, p_c, m_c in COMPUTE:
            o = estimate(**with_mass(af, m_c), p_compute=p_c)
            print(f"  {cname:27s} P_c/P_mot,e={p_c / o['e']['p_mot'] * 100:5.1f}%"
                  f"  endurance={o['e']['t'] / 60:5.1f} min ({(o['e']['t'] / base['e']['t'] - 1) * 100:+5.1f}%)"
                  f"  range={o['r']['x'] / 1000:5.2f} km ({(o['r']['x'] / base['r']['x'] - 1) * 100:+5.1f}%)"
                  f"  T/W x{af['m'] / (af['m'] + m_c):.2f}")


def power_vs_mass_split():
    print("\nEndurance cost split into power-only and mass-only parts")
    for name in list(AIRFRAMES)[:2]:
        af = AIRFRAMES[name]
        t0 = estimate(**af)["e"]["t"]
        for cname, p_c, m_c in COMPUTE[1:3]:
            power = estimate(**af, p_compute=p_c)["e"]["t"] / t0 - 1
            mass = estimate(**with_mass(af, m_c))["e"]["t"] / t0 - 1
            both = estimate(**with_mass(af, m_c), p_compute=p_c)["e"]["t"] / t0 - 1
            print(f"  {name.split()[0]:7s} {cname:20s} power only {power * 100:+5.1f}%"
                  f"  mass only {mass * 100:+5.1f}%  both {both * 100:+5.1f}%")


def stopping_speed_table(a=5.0):
    print(f"\nStopping-limited speed v_stop [m/s], a={a} m/s^2")
    for d in (5, 10, 20, 40):
        row = "  ".join(f"tau={tau * 1000:3.0f} ms:{v_stop(tau, d, a):5.1f}" for tau in (0.02, 0.05, 0.1, 0.2, 0.5))
        print(f"  d={d:2d} m: {row}")


if __name__ == "__main__":
    compute_cost_table()
    power_vs_mass_split()
    stopping_speed_table()
