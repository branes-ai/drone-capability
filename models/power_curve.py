"""Power-versus-speed curve P(v), calibrated to the pen-and-paper anchors.

The pen-and-paper algorithm gives three points of a multicopter's
mechanical power curve but not the curve itself:

  P(0)   = P_h            hover power (eq. 5)
  P(v_e) = 0.914 P_h      the minimum of the curve, at the endurance speed (eqs. 17, 18)
  P(v_r) = 1.092 P_h      where a tangent from the origin touches the curve,
                          at the range speed (eqs. 17, 18)

Phase 1 needs the whole curve to find how the range-optimal speed moves when
compute power is added. The paper's BEM simulator is not published, so we use
a two-parameter surrogate in the normalized speed x = v / v_ih:

  P(v) / P_h = u(k x) + D x^3

- u(x) is the momentum-theory (Glauert) induced inflow ratio in level forward
  flight, the solution of u^4 + x^2 u^2 = 1. The inflow scale k absorbs what
  momentum theory misses: dynamic lift is stronger on large, slow-turning
  propellers (k > 1) than on small ones (k < 1).
- D x^3 is parasite (body drag) power.

k and D are fitted per airframe by least squares to four conditions: the
power level and zero slope at v_e, and the power level and origin tangent at
v_r. A wider family (with profile power terms) was tried, and the fit drove
those terms to zero, so two parameters are enough.

Accuracy against the anchors: the fitted v_e and v_r land within 4% of eq. 18,
and the power levels within 3% on small airframes and within 9% on large ones
(Matrice class), where the paper's curve dips deeper than momentum theory can.
See docs/benchmarks/optimal-speed.md, Phase 1 results.
"""

import math

import numpy as np
from scipy.optimize import least_squares, minimize_scalar

import pen_and_paper as pp


def inflow(x):
    """Glauert induced-velocity ratio v_i / v_ih at normalized forward speed x."""
    x = np.asarray(x, dtype=float)
    return np.sqrt((-x * x + np.sqrt(x ** 4 + 4)) / 2)


def shape(x, k, d):
    """Normalized mechanical power P / P_h at normalized speed x."""
    x = np.asarray(x, dtype=float)
    return inflow(k * x) + d * x ** 3


def _slope(x, k, d, h=1e-6):
    return (shape(x + h, k, d) - shape(x - h, k, d)) / (2 * h)


def fit(x_e, x_r):
    """Fit (k, D) to the pen-and-paper anchors at normalized speeds x_e and x_r."""
    def residuals(p):
        k, d = p
        f_r = shape(x_r, k, d)
        return [shape(x_e, k, d) - pp.P_E_OVER_P_H,
                _slope(x_e, k, d),
                f_r - pp.P_R_OVER_P_H,
                _slope(x_r, k, d) * x_r - f_r]
    sol = least_squares(residuals, [1.0, 0.05], bounds=([0.1, 0.0], [10.0, np.inf]))
    return tuple(sol.x)


class PowerCurve:
    """Mechanical power curve of one airframe at one total mass."""

    def __init__(self, m, r, n_rotors, area_cm2, eta_p=pp.ETA_P_CALIBRATED):
        self.m = m
        self.v_ih, self.p_h = pp.hover(m, r, n_rotors, eta_p)
        # Anchor speeds from eq. 18 (they do not depend on eta_p).
        self.v_e_eq18 = self.v_ih / (pp.C_E[0] + pp.C_E[1] * self.v_ih + pp.C_E[2] * area_cm2)
        self.v_r_eq18 = self.v_ih / (pp.C_R[0] + pp.C_R[1] * self.v_ih + pp.C_R[2] * area_cm2)
        self.k, self.d = fit(self.v_e_eq18 / self.v_ih, self.v_r_eq18 / self.v_ih)

    def power(self, v):
        """Mechanical power [W] at airspeed v [m/s]."""
        return self.p_h * shape(np.asarray(v, dtype=float) / self.v_ih, self.k, self.d)

    def drag_coefficient(self):
        """Quadratic body-drag coefficient [N/(m/s)^2] implied by the parasite term.

        Parasite power D P_h (v / v_ih)^3 equals drag force times speed, so
        F = D P_h v^2 / v_ih^3.
        """
        return self.d * self.p_h / self.v_ih ** 3


def electrical_power(curve, v, p_compute=0.0):
    """Total electrical power [W]: motors through eta_M, plus compute."""
    return curve.power(v) / pp.ETA_M + p_compute


def flight_time(curve, v, n_series, capacity_ah, p_compute=0.0):
    """Flight time [s] at constant speed v, with the eq. 21 effective capacity."""
    p_tot = electrical_power(curve, v, p_compute)
    p_cell = p_tot / (n_series * capacity_ah)
    kappa = sum(c * p_cell ** i for i, c in enumerate(pp.D_BAT))
    return kappa * capacity_ah * pp.V_CELL * n_series * 3600 / p_tot


def distance(curve, v, n_series, capacity_ah, p_compute=0.0):
    """Distance [m] flown at constant speed v until the battery is empty."""
    return v * flight_time(curve, v, n_series, capacity_ah, p_compute)


def optimal_speeds(curve, n_series, capacity_ah, p_compute=0.0):
    """Endurance- and range-optimal speeds [m/s] of the full model, with compute power."""
    hi = 4 * curve.v_r_eq18
    v_e = minimize_scalar(lambda v: -flight_time(curve, v, n_series, capacity_ah, p_compute),
                          bounds=(0.05 * curve.v_ih, hi), method="bounded", options={"xatol": 1e-4}).x
    v_r = minimize_scalar(lambda v: -distance(curve, v, n_series, capacity_ah, p_compute),
                          bounds=(0.05 * curve.v_ih, hi), method="bounded", options={"xatol": 1e-4}).x
    return float(v_e), float(v_r)


def top_speed(m, max_thrust_n, drag_coefficient):
    """Level-flight top speed [m/s]: full thrust, with drag balancing the horizontal component."""
    w = m * pp.G
    if max_thrust_n <= w:
        return 0.0
    return math.sqrt(math.sqrt(max_thrust_n ** 2 - w ** 2) / drag_coefficient)


def max_horizontal_accel(m, max_thrust_n):
    """Horizontal acceleration [m/s^2] at full thrust while holding altitude."""
    tw = max_thrust_n / (m * pp.G)
    return pp.G * math.sqrt(tw * tw - 1) if tw > 1 else 0.0
