"""Pen-and-paper range, endurance, and optimal-speed estimates for multicopters.

Implements the algorithm in Sec. VII of L. Bauersfeld and D. Scaramuzza,
"Range, Endurance, and Optimal Speed Estimates for Multicopters",
IEEE RA-L 2022 (arXiv:2109.04741), extended with a constant compute power
draw P_c. Compute mass is modeled by adding it to the vehicle mass m.

Propeller figure of merit (Phase 0 finding)
-------------------------------------------
The paper states eta_P = 0.6 (Sec. III-B), but its own results are not
consistent with that value:
- its Mavic 3 example uses P_h = 73.5 W, which eq. 5 only gives with
  eta_P = 0.540;
- a single eta_P fitted to all of Table III is 0.538.
With 0.6, endurance and range come out 4-17% higher than Table III. The
default here is ETA_P_CALIBRATED = 0.54. Pass eta_p=ETA_P_STATED to get the
paper's stated value. See docs/benchmarks/optimal-speed.md, Phase 0 results.

Run this file to print the reproduction of the Mavic 3 example and Table III.
"""

import math

RHO = 1.225              # air density [kg/m^3]
G = 9.81                 # gravity [m/s^2]
ETA_P_STATED = 0.6       # propeller figure of merit as stated in the paper (Sec. III-B)
ETA_P_CALIBRATED = 0.54  # figure of merit that reproduces the paper's results (Phase 0)
ETA_M = 0.75             # constant motor efficiency (Sec. IV-B)
V_CELL = 3.7             # nominal LiPo cell voltage [V]

# Table II coefficients
C_E = (0.10188, 0.071358, 0.0007381)       # endurance speed, eq. 18
C_R = (0.041546, 0.041122, 0.00053292)     # range speed, eq. 18
D_BAT = (0.9876, -0.0020, -5.2484e-05, 1.2230e-07)  # effective capacity, eq. 21

P_E_OVER_P_H = 0.914  # eq. 17
P_R_OVER_P_H = 1.092  # eq. 17


def hover(m, r, n_rotors, eta_p=ETA_P_CALIBRATED):
    """Hover induced velocity [m/s] and mechanical hover power [W] (eqs. 4, 5)."""
    v_ih = math.sqrt(m * G / (2 * RHO * math.pi * r * r * n_rotors))
    p_h = (m * G) ** 1.5 / (eta_p * math.sqrt(2 * RHO * math.pi * n_rotors) * r)
    return v_ih, p_h


def estimate(m, r, n_rotors, n_series, capacity_ah, area_cm2,
             p_compute=0.0, p_hover=None, eta_p=ETA_P_CALIBRATED):
    """Endurance- and range-optimal operating points.

    m            vehicle mass [kg], including compute
    r            propeller radius [m]
    n_rotors     number of rotors
    n_series     cells in series (S)
    capacity_ah  total pack capacity [Ah]; parallel strings are folded in
    area_cm2     average surface area [cm^2], as used by eq. 18
    p_compute    constant electrical compute power [W] (not in the paper)
    p_hover      override for mechanical hover power [W]
    eta_p        propeller figure of merit used by eq. 5

    Returns {"v_ih", "p_h", "e": {...}, "r": {...}}. The "e" (endurance) and
    "r" (range) entries hold the mechanical power p [W], electrical power
    p_mot [W], per-cell power p_cell [W/Ah], effective capacity c_eff [Ah],
    flight time t [s], speed v [m/s], and distance x [m].

    Eq. 18 is fitted without compute power, so v does not include the
    upward shift of the range-optimal speed caused by p_compute.
    """
    v_ih, p_h = hover(m, r, n_rotors, eta_p)
    if p_hover is not None:
        p_h = p_hover
    out = {"v_ih": v_ih, "p_h": p_h}
    for key, ratio, c in (("e", P_E_OVER_P_H, C_E), ("r", P_R_OVER_P_H, C_R)):
        p = ratio * p_h                                            # eq. 17
        p_mot = p / ETA_M + p_compute                              # eq. 6, eta_M constant
        p_cell = p_mot / (n_series * capacity_ah)                  # eq. 14
        kappa = sum(d * p_cell ** i for i, d in enumerate(D_BAT))  # eq. 21
        c_eff = kappa * capacity_ah
        t = c_eff * V_CELL * n_series * 3600 / p_mot
        v = v_ih / (c[0] + c[1] * v_ih + c[2] * area_cm2)          # eq. 18
        out[key] = {"p": p, "p_mot": p_mot, "p_cell": p_cell, "c_eff": c_eff,
                    "t": t, "v": v, "x": v * t}
    return out


def v_stop(tau, d, a):
    """Highest speed that can stop within sensing range d [m], given latency tau [s] and deceleration a [m/s^2]."""
    return a * (math.sqrt(tau * tau + 2 * d / a) - tau)


def v_track(tau, e):
    """Highest speed whose error over one latency interval tau [s] stays inside corridor e [m]."""
    return e / tau


if __name__ == "__main__":
    from paper_data import MAVIC3_EXAMPLE, TABLE_III, inputs

    ex = MAVIC3_EXAMPLE
    print("Mavic 3 worked example (Sec. VII-E)")
    for label, kw in (("paper's P_h = 73.5 W", {"p_hover": ex["p_h"]}),
                      ("eq. 5, eta_P = 0.54", {}),
                      ("eq. 5, eta_P = 0.6", {"eta_p": ETA_P_STATED})):
        o = estimate(**ex["inputs"], **kw)
        print(f"  {label:21s} P_h={o['p_h']:5.1f} W  t_e={o['e']['t']:4.0f} s ({ex['t_e']})"
              f"  t_r={o['r']['t']:4.0f} s ({ex['t_r']})  v_e={o['e']['v']:.2f} ({ex['v_e']})"
              f"  v_r={o['r']['v']:.2f} ({ex['v_r']})  x_r={o['r']['x'] / 1000:.1f} km ({ex['x_r'] / 1000})")

    for eta in (ETA_P_CALIBRATED, ETA_P_STATED):
        print(f"\nTable III, eta_P = {eta}   (model vs. paper, percent difference)")
        for row in TABLE_III:
            o = estimate(**inputs(row), eta_p=eta)
            t, x, v = o["e"]["t"] / 60, o["r"]["x"] / 1000, o["r"]["v"] * 3.6
            p = row["paper"]
            print(f"  {row['name']:20s} endurance {t:5.1f} vs {p['t_e_min']:4} min ({(t / p['t_e_min'] - 1) * 100:+5.1f}%)"
                  f"  range {x:5.1f} vs {p['x_r_km']:4} km ({(x / p['x_r_km'] - 1) * 100:+5.1f}%)"
                  f"  v_r {v:4.1f} vs {p['v_r_kmh']} km/h")
