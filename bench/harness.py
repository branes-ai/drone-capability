"""Phase 2 harness core: pipelines of timed stages, run at mission rate.

A pipeline is a list of stages. Each stage is a callable that takes the
previous stage's output; the first stage takes a frame from the source. The
runner paces frames at the mission rate like a camera with a one-deep queue:
when the pipeline falls behind, older frames are dropped and the newest one
is processed. End-to-end latency is measured from the frame's capture
timestamp to the end of the last stage, so it includes queueing delay.

It does NOT include camera exposure and readout, ISP, or the transport from
the companion computer to the flight controller and the motors. Add those
separately (see docs/benchmarks/optimal-speed.md, Phase 2).

Python 3.6 compatible (JetPack 4 on the original Jetson Nano ships 3.6): no
dataclasses, no walrus, no perf_counter_ns.
"""

import math
import time


class Stage(object):
    def __init__(self, name, fn):
        self.name, self.fn = name, fn


class Pipeline(object):
    """name, the mission rate [Hz], a frame source, and the stages."""

    def __init__(self, name, rate_hz, source, stages, description="", meta=None):
        self.name, self.rate_hz, self.source, self.stages = name, rate_hz, source, stages
        self.description = description
        self.meta = meta or {}

    def process(self, frame):
        """Run every stage once; return (output, per-stage durations [s])."""
        x, durations = frame, []
        for st in self.stages:
            t0 = time.perf_counter()
            x = st.fn(x)
            durations.append(time.perf_counter() - t0)
        return x, durations


def percentile(xs, q):
    """Linear-interpolated percentile, q in [0, 100]."""
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * q / 100.0
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summarize(xs):
    """Distribution summary [s] of a list of durations [s]."""
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": sum(xs) / len(xs), "p50": percentile(xs, 50),
            "p90": percentile(xs, 90), "p99": percentile(xs, 99), "max": max(xs), "min": min(xs)}


def run(pipeline, duration_s, warmup_s=2.0, clock=time.perf_counter, sleep=time.sleep):
    """Run the pipeline at its mission rate; return latency, per-stage, and rate statistics.

    Frames arrive at t_k = t0 + k / rate. At each iteration the runner takes
    the newest frame that has arrived, drops older ones, and processes it.
    """
    period = 1.0 / pipeline.rate_hz
    t_start = clock()
    t0 = t_start + warmup_s
    e2e, stages = [], [[] for _ in pipeline.stages]
    k_next, processed, dropped = 0, 0, 0
    while True:
        now = clock()
        if now >= t0 + duration_s:
            break
        if now < t0:
            # Warm-up: run back to back and discard the timings.
            pipeline.process(pipeline.source(0))
            continue
        k_newest = int((now - t0) / period)
        if k_newest < k_next:
            sleep(max(0.0, t0 + k_next * period - now))
            continue
        dropped += k_newest - k_next
        t_capture = t0 + k_newest * period
        _, durs = pipeline.process(pipeline.source(k_newest))
        t_done = clock()
        e2e.append(t_done - t_capture)
        for i, d in enumerate(durs):
            stages[i].append(d)
        processed += 1
        k_next = k_newest + 1
    frames = processed + dropped
    return {
        "rate_hz": pipeline.rate_hz,
        "duration_s": duration_s,
        "frames_offered": frames,
        "frames_processed": processed,
        "frames_dropped": dropped,
        "drop_fraction": dropped / frames if frames else None,
        "achieved_rate_hz": processed / duration_s,
        "latency_s": summarize(e2e),
        "compute_s": summarize([sum(ds) for ds in zip(*stages)]) if processed else {"n": 0},
        "stages": [dict(name=st.name, **summarize(ds)) for st, ds in zip(pipeline.stages, stages)],
    }
