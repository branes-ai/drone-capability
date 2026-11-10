"""Phase 2 harness tests.

Run from the repo root:  python3 -m unittest discover -s bench
The pipeline smoke tests need the detector assets (python3 bench/make_detector.py).
"""

import json
import os
import sys
import tempfile
import time
import unittest

import harness
import pipelines
import power
import to_compute
from pipelines.common import ASSETS

MODELS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class Stats(unittest.TestCase):

    def test_percentile_interpolates(self):
        xs = list(range(101))
        self.assertEqual(harness.percentile(xs, 50), 50)
        self.assertEqual(harness.percentile(xs, 99), 99)
        self.assertAlmostEqual(harness.percentile([0, 10], 25), 2.5)
        self.assertIsNone(harness.percentile([], 50))


class Runner(unittest.TestCase):

    def pipe(self, work_s, rate_hz):
        return harness.Pipeline("t", rate_hz, lambda k: k, [harness.Stage("w", lambda x: time.sleep(work_s) or x)])

    def test_keeps_up_when_fast(self):
        r = harness.run(self.pipe(0.001, 100.0), 0.5, warmup_s=0.05)
        self.assertEqual(r["frames_dropped"], 0)
        self.assertGreater(r["frames_processed"], 40)
        self.assertLess(r["latency_s"]["p50"], 0.01)

    def test_drops_frames_and_counts_queueing_when_slow(self):
        # 25 ms of work at 100 Hz: about 3 of every 4 frames are dropped, and the
        # latency includes the wait for the newest frame to be picked up.
        r = harness.run(self.pipe(0.025, 100.0), 0.6, warmup_s=0.05)
        self.assertGreater(r["drop_fraction"], 0.5)
        self.assertGreaterEqual(r["latency_s"]["p50"], 0.025)


class PowerBackends(unittest.TestCase):

    def test_jetson_orin_hwmon(self):
        with tempfile.TemporaryDirectory() as d:
            hw = os.path.join(d, "ina3221", "1-0040", "hwmon", "hwmon3")
            for ch, label, mv, ma in ((1, "VDD_IN", 5000, 2000), (2, "VDD_CPU_GPU_CV", 5000, 800)):
                write(os.path.join(hw, "in%d_label" % ch), label)
                write(os.path.join(hw, "in%d_input" % ch), str(mv))
                write(os.path.join(hw, "curr%d_input" % ch), str(ma))
            write(os.path.join(hw, "in7_label"), "sum of shunt voltages")
            total, rails = power.JetsonBackend(d).read()
            self.assertAlmostEqual(total, 10.0)
            self.assertEqual(set(rails), {"VDD_IN", "VDD_CPU_GPU_CV"})

    def test_jetson_nano_iio(self):
        with tempfile.TemporaryDirectory() as d:
            dev = os.path.join(d, "ina3221x", "6-0040", "iio:device0")
            for ch, name, mw in ((0, "POM_5V_IN", 4200), (1, "POM_5V_GPU", 600), (2, "POM_5V_CPU", 1100)):
                write(os.path.join(dev, "rail_name_%d" % ch), name)
                write(os.path.join(dev, "in_power%d_input" % ch), str(mw))
            be = power.JetsonBackend(d)
            self.assertEqual(be.total_rail, "POM_5V_IN")
            self.assertAlmostEqual(be.read()[0], 4.2)

    def test_rapl_handles_counter_wrap(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "max_energy_range_uj"), "1000000")
            write(os.path.join(d, "energy_uj"), "999000")
            be = power.RaplBackend(d)
            self.assertIsNone(be.read()[0])
            time.sleep(0.05)
            write(os.path.join(d, "energy_uj"), "500")  # wrapped: 1500 uJ consumed
            w, _ = be.read()
            self.assertGreater(w, 0)
            self.assertLess(w, 1.0)

    def test_file_backend_scale(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "power_now"), "7500000")
            self.assertAlmostEqual(power.backend("file:%s/power_now" % d).read()[0], 7.5)


def result(pipeline, p99, mean_w, drop=0.0, t="2026-11-10T00:00:00Z"):
    return {"schema": "drone-capability/bench-result/1", "target": "x", "pipeline": pipeline, "time_utc": t,
            "rate_hz": 30.0, "drop_fraction": drop, "latency_s": {"p99": p99},
            "power": {"run": {"mean_w": mean_w}}}


MASS = {"items": [{"item": "module", "grams": 30.0, "weighed": True},
                  {"item": "carrier", "grams": 50.0, "weighed": True}]}


class ToCompute(unittest.TestCase):

    def results(self, *rs):
        return {r["pipeline"]: dict(r, _path=os.path.join(os.path.dirname(__file__), "r.json")) for r in rs}

    def test_entry_takes_p99_power_and_worst_case_defaults(self):
        e = to_compute.entry("x", self.results(result("racing", 0.010, 9.0), result("scout", 0.050, 12.0)),
                             MASS, latency_extra_s=0.015)
        self.assertAlmostEqual(e["m_compute"], 0.08)
        self.assertAlmostEqual(e["latency_by_pipeline_s"]["racing"], 0.025)
        self.assertAlmostEqual(e["latency_s"], 0.065)
        self.assertEqual(e["p_compute"], 12.0)

    def test_rejects_unweighed_mass(self):
        mass = {"items": [{"item": "module", "grams": 30.0, "weighed": False}]}
        with self.assertRaises(ValueError):
            to_compute.entry("x", self.results(result("racing", 0.01, 9.0)), mass)

    def test_rejects_pipeline_that_does_not_keep_up(self):
        with self.assertRaises(ValueError):
            to_compute.entry("x", self.results(result("scout", 0.05, 12.0, drop=0.2)), MASS)

    def test_newest_result_wins(self):
        with tempfile.TemporaryDirectory() as d:
            for i, t in enumerate(("2026-11-10T00:00:00Z", "2026-11-11T00:00:00Z")):
                r = dict(result("racing", 0.01 * (i + 1), 9.0, t=t), target="x")
                write(os.path.join(d, "%d.json" % i), json.dumps(r))
            got = to_compute.load_results([os.path.join(d, f) for f in ("0.json", "1.json")], "x")
            self.assertAlmostEqual(got["racing"]["latency_s"]["p99"], 0.02)


class ModelUsesPerPipelineValues(unittest.TestCase):

    def test_mission_picks_its_pipeline_latency(self):
        sys.path.insert(0, MODELS)
        import mission as ms
        missions, computes, airframes = ms.load("missions"), ms.load("compute"), ms.load("airframes")
        m = missions["scout"]
        base = dict(computes["orin-nx-15w"])
        slow = dict(base, latency_by_pipeline_s={"scout": 2.0}, p_compute_by_pipeline_w={"scout": 30.0})
        a, b = ms.capability(airframes[m["airframe"]], base, m), ms.capability(airframes[m["airframe"]], slow, m)
        self.assertIn(b["binding"], ("v_stop", "v_agility"))
        self.assertLess(b["range_m"], a["range_m"])
        s = ms.sensitivities(airframes[m["airframe"]], slow, m)
        self.assertLess(s["per_10ms"], 0)


@unittest.skipUnless(os.path.exists(os.path.join(ASSETS, "det320.onnx")), "run bench/make_detector.py first")
class PipelineSmoke(unittest.TestCase):

    def test_every_pipeline_runs(self):
        for name in pipelines.NAMES:
            with self.subTest(name):
                p = pipelines.build(name)
                for k in range(3):
                    out, durs = p.process(p.source(k))
                self.assertEqual(len(durs), len(p.stages))
                self.assertIsNotNone(out)


if __name__ == "__main__":
    unittest.main()
