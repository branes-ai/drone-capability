"""Phase 1 tests: the power curve, compute-power effects, and the mission speed limits.

Run from the repo root:  python3 -m unittest discover -s models
"""

import unittest

import mission as ms
import pen_and_paper as pp
import power_curve as pc
from paper_data import TABLE_III, inputs

SMALL = [r for r in TABLE_III if r["m"] < 2]
LARGE = [r for r in TABLE_III if r["m"] >= 2]


def curve(row):
    return pc.PowerCurve(row["m"], row["r"], row["n_rotors"], row["area_cm2"])


def rel(a, b):
    return abs(a / b - 1)


class PowerCurveFit(unittest.TestCase):
    """The surrogate must reproduce the pen-and-paper anchors it is fitted to."""

    def test_hover_power_is_exact(self):
        for row in TABLE_III:
            c = curve(row)
            self.assertAlmostEqual(float(c.power(0.0)), c.p_h, places=6)

    def test_optimal_speeds_match_eq18_within_4_percent(self):
        for row in TABLE_III:
            with self.subTest(row["name"]):
                c = curve(row)
                v_e, v_r = pc.optimal_speeds(c, row["n_series"], row["capacity_ah"])
                self.assertLess(rel(v_e, c.v_e_eq18), 0.04)
                self.assertLess(rel(v_r, c.v_r_eq18), 0.04)

    def test_endurance_and_range_match_pen_and_paper(self):
        # Within 1.5% on small airframes; within 6% on large ones, where the
        # paper's curve dips deeper than momentum theory allows.
        for rows, tol in ((SMALL, 0.015), (LARGE, 0.06)):
            for row in rows:
                with self.subTest(row["name"]):
                    c, ref = curve(row), pp.estimate(**inputs(row))
                    v_e, v_r = pc.optimal_speeds(c, row["n_series"], row["capacity_ah"])
                    self.assertLess(rel(pc.flight_time(c, v_e, row["n_series"], row["capacity_ah"]), ref["e"]["t"]), tol)
                    self.assertLess(rel(pc.distance(c, v_r, row["n_series"], row["capacity_ah"]), ref["r"]["x"]), tol)

    def test_fit_is_physical(self):
        for row in TABLE_III:
            c = curve(row)
            self.assertGreater(c.k, 0)
            self.assertGreaterEqual(c.d, 0)


class ComputePowerShifts(unittest.TestCase):
    """The plan's two analytic results, on the full curve."""

    ROW = TABLE_III[1]  # DJI Mavic 3

    def setUp(self):
        self.c = curve(self.ROW)
        self.args = (self.ROW["n_series"], self.ROW["capacity_ah"])

    def test_endurance_speed_does_not_move(self):
        v_e0, _ = pc.optimal_speeds(self.c, *self.args)
        for p_c in (7, 15, 40):
            v_e, _ = pc.optimal_speeds(self.c, *self.args, p_compute=p_c)
            self.assertAlmostEqual(v_e, v_e0, delta=0.01)

    def test_range_speed_rises_with_compute_power(self):
        prev = pc.optimal_speeds(self.c, *self.args)[1]
        for p_c in (7, 15, 40):
            v_r = pc.optimal_speeds(self.c, *self.args, p_compute=p_c)[1]
            self.assertGreater(v_r, prev)
            prev = v_r

    def test_reoptimizing_speed_recovers_range(self):
        v_r0 = pc.optimal_speeds(self.c, *self.args)[1]
        v_r40 = pc.optimal_speeds(self.c, *self.args, p_compute=40)[1]
        self.assertGreater(pc.distance(self.c, v_r40, *self.args, p_compute=40),
                           pc.distance(self.c, v_r0, *self.args, p_compute=40))


class SpeedLimits(unittest.TestCase):

    def test_top_speed_balances_drag(self):
        v = pc.top_speed(1.0, 40.0, 0.03)
        self.assertAlmostEqual(0.03 * v * v, (40.0 ** 2 - pp.G ** 2) ** 0.5)

    def test_no_top_speed_without_excess_thrust(self):
        self.assertEqual(pc.top_speed(1.0, 9.0, 0.03), 0.0)

    def test_turn_and_agility(self):
        self.assertAlmostEqual(ms.v_turn(20.0, 5.0), 10.0)
        self.assertAlmostEqual(ms.v_agility(0.05, 10.0), ms.PHASE_BUDGET_RAD * 200)


class Missions(unittest.TestCase):

    def test_fc_only_cannot_fly_autonomous_missions(self):
        for mission in ms.load("missions"):
            self.assertFalse(ms.capability_by_name(mission, "fc-only")["feasible"])

    def test_binding_limit_is_the_minimum(self):
        for mission in ms.load("missions"):
            for compute in ("efficient-companion", "orin-nx-15w", "agx-orin-40w"):
                cap = ms.capability_by_name(mission, compute)
                self.assertEqual(cap["v_mission"], min(cap["limits"].values()))
                self.assertEqual(cap["limits"][cap["binding"]], cap["v_mission"])

    def test_heavier_compute_lowers_thrust_to_weight(self):
        for mission in ms.load("missions"):
            tws = [ms.capability_by_name(mission, c)["thrust_to_weight"]
                   for c in ("efficient-companion", "orin-nx-15w", "agx-orin-40w")]
            self.assertEqual(tws, sorted(tws, reverse=True))

    def test_latency_budget_is_where_latency_starts_to_bind(self):
        missions, computes, airframes = ms.load("missions"), ms.load("compute"), ms.load("airframes")
        for name, mission in missions.items():
            with self.subTest(name):
                airframe, compute = airframes[mission["airframe"]], computes["orin-nx-15w"]
                budget = ms.latency_budget(ms.capability(airframe, compute, mission), mission)
                below = ms.capability(airframe, {**compute, "latency_s": 0.95 * budget}, mission)
                above = ms.capability(airframe, {**compute, "latency_s": 1.05 * budget}, mission)
                self.assertNotIn(below["binding"], ("v_stop", "v_agility", "v_track"))
                self.assertIn(above["binding"], ("v_stop", "v_agility", "v_track"))


if __name__ == "__main__":
    unittest.main()
