"""Phase 2 runner: measure one L1 pipeline's latency and power on this machine.

    python3 bench/run.py --pipeline racing --target orin-nx-15w --power jetson
    python3 bench/run.py --pipeline scout --target desktop --duration 30 --background inspection
    python3 bench/run.py --pipeline inspection --target qcs6490 --power none --stress 2
    python3 bench/run.py --pipeline racing --target orin-nano --power jetson --provider tensorrt
    python3 bench/run.py --pipeline scout --target orin-nano --power jetson --stereo vpi-cuda
    python3 bench/run.py --pipeline racing --target ventuno-q --provider qnn   # Qualcomm NPU

The result is written to bench/results/<target>/<pipeline>-<UTC time>.json
(or --out). bench/to_compute.py turns results plus a weighed-mass record into
an entry for models/data/compute.json.

Concurrent load, as the plan requires:
  --background NAME   run another pipeline in a separate process at its own rate
                      (repeatable), e.g. the mission's other perception tasks
  --stress N          N processes of busy matrix multiplies (a pessimistic load)

Measure at thermal steady state, in a representative enclosure: use
--soak to run the pipeline untimed first until temperatures settle.
"""

import argparse
import json
import multiprocessing as mp
import os
import platform
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Single-threaded BLAS, set before numpy loads (spawned background processes
# inherit it). The pipelines only multiply small matrices, and a threaded
# OpenBLAS spins its idle threads, which steals the cores the detector runtime
# needs: on the Jetson with the system numpy this doubled detector latency
# (30 -> 75 ms). Override by setting the variables explicitly.
BLAS_ENV = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
for _v in BLAS_ENV:
    os.environ.setdefault(_v, "1")

import harness  # noqa: E402
import pipelines  # noqa: E402
import power  # noqa: E402


def _background(name, provider, opts, stop):
    p = pipelines.build(name, provider, **opts)
    k = 0
    period = 1.0 / p.rate_hz
    t_next = time.perf_counter()
    while not stop.is_set():
        p.process(p.source(k))
        k += 1
        t_next += period
        time.sleep(max(0.0, t_next - time.perf_counter()))


def _stress(stop):
    import numpy as np
    a = np.random.rand(256, 256)
    while not stop.is_set():
        a = np.tanh(a @ a)


def _cmd(args):
    try:
        return subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=5).decode().strip()
    except Exception:
        return None


def platform_info():
    info = {"hostname": socket.gethostname(), "machine": platform.machine(), "system": platform.platform(),
            "python": platform.python_version(), "cpus": os.cpu_count(),
            "thread_env": {v: os.environ.get(v) for v in BLAS_ENV}}
    for path in ("/proc/device-tree/model", "/etc/nv_tegra_release"):
        if os.path.exists(path):
            with open(path) as f:
                info[os.path.basename(path)] = f.read().strip("\x00\n ")
    if os.path.exists("/proc/cpuinfo"):
        with open("/proc/cpuinfo") as f:
            names = [l.split(":", 1)[1].strip() for l in f if l.lower().startswith("model name")]
        if names:
            info["cpu"] = names[0]
    nvp = _cmd(["nvpmodel", "-q"])
    if nvp:
        info["nvpmodel"] = nvp
    import cv2
    import numpy
    info["numpy"], info["opencv"] = numpy.__version__, cv2.__version__
    try:
        import onnxruntime
        info["onnxruntime"] = onnxruntime.__version__
        info["ort_providers"] = onnxruntime.get_available_providers()
    except ImportError:
        pass
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pipeline", required=True, choices=pipelines.NAMES)
    ap.add_argument("--target", required=True, help="target name, e.g. orin-nx-15w (matches compute.json keys)")
    ap.add_argument("--duration", type=float, default=60.0, help="timed run [s]")
    ap.add_argument("--warmup", type=float, default=5.0, help="untimed warm-up [s]")
    ap.add_argument("--soak", type=float, default=0.0, help="untimed thermal soak before the warm-up [s]")
    ap.add_argument("--idle", type=float, default=10.0, help="idle power window before the run [s]")
    ap.add_argument("--power", default="none", help="jetson, rapl, file:PATH[:SCALE], or none")
    ap.add_argument("--power-rate", type=float, default=50.0, help="power sampling rate [Hz]")
    ap.add_argument("--provider", default="auto", help="detector runtime: auto, opencv, or an onnxruntime provider")
    ap.add_argument("--threads", type=int, default=0, help="detector intra-op threads (0: runtime default)")
    ap.add_argument("--stereo", default="sgbm", help="scouting stereo backend: sgbm (CPU) or vpi-cuda (Jetson GPU)")
    ap.add_argument("--rate", type=float, help="override the pipeline's mission rate [Hz]")
    ap.add_argument("--background", action="append", default=[], choices=pipelines.NAMES)
    ap.add_argument("--stress", type=int, default=0)
    ap.add_argument("--notes", default="", help="free text: enclosure, cooling, clocks, anything not detected")
    ap.add_argument("--out", help="output file (default: bench/results/<target>/...)")
    args = ap.parse_args(argv)

    be = power.backend(args.power)
    opts = {"stereo": args.stereo}
    pipe = pipelines.build(args.pipeline, args.provider, args.threads, **opts)
    if args.rate:
        pipe.rate_hz = args.rate

    idle = power.measure_idle(be, args.idle, args.power_rate)

    # spawn, not fork: a forked child cannot initialise CUDA once the parent has
    # (TensorRT, VPI), and spawn behaves the same on every platform.
    ctx = mp.get_context("spawn")
    stop = ctx.Event()
    procs = [ctx.Process(target=_background, args=(n, args.provider, opts, stop)) for n in args.background]
    procs += [ctx.Process(target=_stress, args=(stop,)) for _ in range(args.stress)]
    for p in procs:
        p.daemon = True
        p.start()
    try:
        if args.soak > 0:
            harness.run(pipe, 0.0, warmup_s=args.soak)
        temps_start = power.temperatures()
        sampler = power.Sampler(be, args.power_rate)
        if be.name != "none":
            # Sample the timed window only: start after the warm-up.
            t_on = time.perf_counter() + args.warmup
            import threading
            threading.Timer(max(0.0, t_on - time.perf_counter()), sampler.start).start()
        stats = harness.run(pipe, args.duration, warmup_s=args.warmup)
        sampler.stop()
        temps_end = power.temperatures()
    finally:
        stop.set()
        for p in procs:
            p.join(timeout=5)

    result = {
        "schema": "drone-capability/bench-result/1",
        "target": args.target, "pipeline": args.pipeline, "description": pipe.description,
        "pipeline_meta": pipe.meta,
        "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": platform_info(),
        "load": {"background": args.background, "stress": args.stress},
        "accelerators": {"detector": args.provider, "stereo": args.stereo},
        "notes": args.notes,
        "latency_scope": "frame capture timestamp to end of the last stage; excludes exposure, readout, ISP, "
                         "and transport to the flight controller",
        **stats,
        "power": {"idle": idle, "run": sampler.summary()},
        "temperature_c": {"start": temps_start, "end": temps_end},
    }
    out = args.out or os.path.join(HERE, "results", args.target,
                                   "%s-%s.json" % (args.pipeline, time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")

    lat = stats["latency_s"]
    run_p = result["power"]["run"]
    print("%s on %s: %d frames at %.1f/%.1f Hz, %.1f%% dropped" % (
        args.pipeline, args.target, stats["frames_processed"], stats["achieved_rate_hz"], pipe.rate_hz,
        100 * (stats["drop_fraction"] or 0)))
    if lat["n"]:
        print("  latency p50 %.1f ms  p99 %.1f ms  max %.1f ms" % (1e3 * lat["p50"], 1e3 * lat["p99"], 1e3 * lat["max"]))
        for st in stats["stages"]:
            print("    %-10s p50 %7.2f ms  p99 %7.2f ms" % (st["name"], 1e3 * st["p50"], 1e3 * st["p99"]))
    if run_p:
        print("  power %.2f W mean (%s), idle %s" % (run_p["mean_w"], run_p["total_rail"],
                                                    "%.2f W" % idle["mean_w"] if idle else "-"))
    print("  wrote", os.path.relpath(out))


if __name__ == "__main__":
    main()
