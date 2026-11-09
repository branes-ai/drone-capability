"""Pen-and-paper range, endurance, and optimal-speed estimates for multicopters.

Implements the algorithm in Sec. VII of L. Bauersfeld and D. Scaramuzza,
"Range, Endurance, and Optimal Speed Estimates for Multicopters",
IEEE RA-L 2022 (arXiv:2109.04741), extended with a constant compute power
draw P_c. Compute mass is modeled by adding it to the vehicle mass m.

This is a Phase 0/1 prototype for docs/benchmarks/optimal-speed.md.
Running this file reproduces the paper's DJI Mavic 3 worked example.
"""

import math

RHO = 1.225    # air density [kg/m^3]
G = 9.81       # gravity [m/s^2]
ETA_P = 0.6    # propeller figure of merit (paper Sec. III-B)
ETA_M = 0.75   # constant motor efficiency (paper Sec. IV-B)
V_CELL = 3.7   # nominal LiPo cell voltage [V]

# Table II coefficients
C_E = (0.10188, 0.071358, 0.0007381)       # endurance speed, eq. 18
C_R = (0.041546, 0.041122, 0.00053292)     # range speed, eq. 18
D_BAT = (0.9876, -0.0020, -5.2484e-05, 1.2230e-07)  # effective capacity, eq. 21

P_E_OVER_P_H = 0.914  # eq. 17
P_R_OVER_P_H = 1.092  # eq. 17


def hover(m, r, n_rotors):
    """Hover induced velocity [m/s] and mechanical hover power [W] (eqs. 4, 5)."""
    v_ih = math.sqrt(m * G / (2 * RHO * math.pi * r * r * n_rotors))
    p_h = (m * G) ** 1.5 / (ETA_P * math.sqrt(2 * RHO * math.pi * n_rotors) * r)
    return v_ih, p_h


def estimate(m, r, n_rotors, n_series, capacity_ah, area_cm2, p_compute=0.0, p_hover=None):
    """Endurance- and range-optimal operating points.

    m            vehicle mass [kg], including compute
    r            propeller radius [m]
    n_rotors     number of rotors
    n_series     cells in series (S)
    capacity_ah  total pack capacity [Ah]; parallel strings are folded in
    area_cm2     average surface area [cm^2], as used by eq. 18
    p_compute    constant electrical compute power [W] (not in the paper)
    p_hover      override for mechanical hover power [W]

    Returns {"e": {...}, "r": {...}} with electrical power p_mot [W],
    flight time t [s], speed v [m/s], and distance x [m].

    Eq. 18 is fitted without compute power, so v does not include the
    upward shift of the range-optimal speed caused by p_compute.
    """
    v_ih, p_h = hover(m, r, n_rotors)
    if p_hover is not None:
        p_h = p_hover
    out = {"v_ih": v_ih, "p_h": p_h}
    for key, ratio, c in (("e", P_E_OVER_P_H, C_E), ("r", P_R_OVER_P_H, C_R)):
        p_mot = ratio * p_h / ETA_M + p_compute
        p_cell = p_mot / (n_series * capacity_ah)                  # eq. 14
        kappa = sum(d * p_cell ** i for i, d in enumerate(D_BAT))  # eq. 21
        t = kappa * capacity_ah * V_CELL * n_series * 3600 / p_mot
        v = v_ih / (c[0] + c[1] * v_ih + c[2] * area_cm2)          # eq. 18
        out[key] = {"p_mot": p_mot, "t": t, "v": v, "x": v * t}
    return out


def v_stop(tau, d, a):
    """Highest speed that can stop within sensing range d [m], given latency tau [s] and deceleration a [m/s^2]."""
    return a * (math.sqrt(tau * tau + 2 * d / a) - tau)


def v_track(tau, e):
    """Highest speed whose error over one latency interval tau [s] stays inside corridor e [m]."""
    return e / tau


if __name__ == "__main__":
    # Paper Sec. VII-E: DJI Mavic 3, 0.90 kg, 11.9 cm prop radius, 4S1P 5.0 Ah, 215 cm^2.
    # Paper: v_ih 4.51 m/s, P_h 73.5 W, t_e 2909 s, t_r 2429 s, v_e 7.75, v_r 13.12 m/s, x_r 32.1 km.
    mavic3 = dict(m=0.90, r=0.119, n_rotors=4, n_series=4, capacity_ah=5.0, area_cm2=215)
    for label, kw in (("eq. 5 hover power", {}), ("paper's P_h = 73.5 W", {"p_hover": 73.5})):
        o = estimate(**mavic3, **kw)
        print(f"{label:22s} v_ih={o['v_ih']:.2f} P_h={o['p_h']:.1f} W | "
              f"t_e={o['e']['t']:.0f} s v_e={o['e']['v']:.2f} | "
              f"t_r={o['r']['t']:.0f} s v_r={o['r']['v']:.2f} x_r={o['r']['x'] / 1000:.1f} km")
