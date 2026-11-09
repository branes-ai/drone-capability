"""Phase 0 regression tests: reproduce Bauersfeld & Scaramuzza, RA-L 2022.

Run from the repo root:  python3 -m unittest discover -s models
"""

import unittest

import pen_and_paper as pp
from paper_data import MAVIC3_EXAMPLE, TABLE_III, inputs


def rel(a, b):
    return abs(a / b - 1)


class Mavic3WorkedExample(unittest.TestCase):
    """Sec. VII-E is the only full-precision result in the paper: match it to 1%."""

    def setUp(self):
        self.ex = MAVIC3_EXAMPLE
        # The paper's P_h, so this test checks steps 2-8 independently of eta_P.
        self.o = pp.estimate(**self.ex["inputs"], p_hover=self.ex["p_h"])

    def test_hover_induced_velocity(self):
        self.assertLess(rel(self.o["v_ih"], self.ex["v_ih"]), 0.01)

    def test_intermediate_steps(self):
        e, r = self.o["e"], self.o["r"]
        for got, want in ((e["p"], "p_e"), (r["p"], "p_r"), (e["p_mot"], "p_mot_e"), (r["p_mot"], "p_mot_r"),
                          (e["p_cell"], "p_cell_e"), (r["p_cell"], "p_cell_r"),
                          (e["c_eff"], "c_eff_e"), (r["c_eff"], "c_eff_r")):
            with self.subTest(want):
                self.assertLess(rel(got, self.ex[want]), 0.01)

    def test_results(self):
        e, r = self.o["e"], self.o["r"]
        for got, want in ((e["t"], "t_e"), (r["t"], "t_r"), (e["v"], "v_e"), (r["v"], "v_r"), (r["x"], "x_r")):
            with self.subTest(want):
                self.assertLess(rel(got, self.ex[want]), 0.01)

    def test_calibrated_eta_reproduces_paper_hover_power(self):
        _, p_h = pp.hover(0.90, 0.119, 4)
        self.assertLess(rel(p_h, self.ex["p_h"]), 0.01)

    def test_stated_eta_does_not(self):
        """Documents the Phase 0 finding: eq. 5 with eta_P = 0.6 gives 66 W, not 73.5 W."""
        _, p_h = pp.hover(0.90, 0.119, 4, eta_p=pp.ETA_P_STATED)
        self.assertGreater(rel(p_h, self.ex["p_h"]), 0.09)


class TableIII(unittest.TestCase):
    """Table III is rounded to 2 significant figures, and no single eta_P reproduces every row."""

    def test_range_speed_within_rounding(self):
        # Eq. 18 does not depend on eta_P; allow the 0.5 km/h print rounding plus 1%.
        for row in TABLE_III:
            with self.subTest(row["name"]):
                v = pp.estimate(**inputs(row))["r"]["v"] * 3.6
                want = row["paper"]["v_r_kmh"]
                self.assertLessEqual(abs(v - want), 0.5 + 0.01 * want)

    def test_endurance_and_range_within_8_percent(self):
        for row in TABLE_III:
            with self.subTest(row["name"]):
                o = pp.estimate(**inputs(row))
                self.assertLess(rel(o["e"]["t"] / 60, row["paper"]["t_e_min"]), 0.08)
                self.assertLess(rel(o["r"]["x"] / 1000, row["paper"]["x_r_km"]), 0.08)


class ComputeExtension(unittest.TestCase):
    """Properties of the compute-power term the paper does not have."""

    AF = MAVIC3_EXAMPLE["inputs"]

    def test_zero_compute_is_the_paper_model(self):
        self.assertEqual(pp.estimate(**self.AF), pp.estimate(**self.AF, p_compute=0.0))

    def test_compute_power_reduces_endurance_and_range(self):
        prev = pp.estimate(**self.AF)
        for p_c in (1, 5, 15, 40):
            o = pp.estimate(**self.AF, p_compute=p_c)
            self.assertLess(o["e"]["t"], prev["e"]["t"])
            self.assertLess(o["r"]["x"], prev["r"]["x"])
            prev = o

    def test_compute_power_costs_more_than_its_share(self):
        """Higher current draw also lowers effective capacity, so the loss exceeds P_c / P_total."""
        base = pp.estimate(**self.AF)["e"]
        o = pp.estimate(**self.AF, p_compute=15)["e"]
        self.assertGreater(1 - o["t"] / base["t"], 15 / o["p_mot"])

    def test_compute_power_does_not_move_speeds(self):
        """The pen-and-paper eq. 18 has no P_c term; Phase 1 adds the v_r shift."""
        base, o = pp.estimate(**self.AF), pp.estimate(**self.AF, p_compute=15)
        self.assertEqual(base["e"]["v"], o["e"]["v"])
        self.assertEqual(base["r"]["v"], o["r"]["v"])


class SpeedLimits(unittest.TestCase):

    def test_v_stop_zero_latency_is_braking_limit(self):
        self.assertAlmostEqual(pp.v_stop(0.0, 10, 5), (2 * 10 * 5) ** 0.5)

    def test_v_stop_fits_in_sensing_range(self):
        for tau in (0.02, 0.1, 0.5):
            v = pp.v_stop(tau, 20, 5)
            self.assertAlmostEqual(v * tau + v * v / (2 * 5), 20)

    def test_v_track(self):
        self.assertAlmostEqual(pp.v_track(0.02, 0.2), 10)


if __name__ == "__main__":
    unittest.main()
