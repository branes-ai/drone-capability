"""Summarize Phase 2 results as markdown: one table, or the published results page.

    python3 bench/summarize.py bench/results/*/            # every target, one table
    python3 bench/summarize.py bench/results/ventuno-q-npu bench/results/orin-nano-super-25w-gpu
    python3 bench/summarize.py --page                      # rewrite docs/benchmarks/results.md

The results page is generated from bench/results/ and checked by the bench
tests, so commit it with the results it shows.

For each (target, pipeline, load), the newest result is shown. 'Keeps up' is
the share of frames processed at mission rate; a pipeline that drops frames
is slower than the rate even where its p99 looks acceptable.
"""

import argparse
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
PAGE = os.path.join(os.path.dirname(HERE), "docs", "benchmarks", "results.md")


def load(paths):
    rows = {}
    for p in paths:
        files = sorted(glob.glob(os.path.join(p, "*.json"))) if os.path.isdir(p) else [p]
        for f in files:
            with open(f) as fh:
                r = json.load(fh)
            if r.get("schema") != "drone-capability/bench-result/1":
                continue
            load_name = "+bg" if r["load"]["background"] else ("+stress" if r["load"]["stress"] else "alone")
            key = (r["target"], r["pipeline"], load_name)
            if key not in rows or r["time_utc"] > rows[key]["time_utc"]:
                rows[key] = dict(r, _path=f)
    return rows


ORDER = {"racing": 0, "scout": 1, "inspection": 2}


def table(rows):
    out = ["| Target | Pipeline | Load | Rate [Hz] | Kept | p50 [ms] | p99 [ms] | Power [W] | Idle [W] | Slowest stage (p50) |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(rows, key=lambda k: (k[0], ORDER.get(k[1], 9), k[2] != "alone")):
        r = rows[key]
        lat = r["latency_s"]
        run = (r.get("power") or {}).get("run")
        idle = (r.get("power") or {}).get("idle")
        slow = max(r["stages"], key=lambda s: s.get("p50") or 0)
        kept = 1 - (r["drop_fraction"] or 0)
        out.append("| %s | %s | %s | %.1f / %.0f | %.0f%% | %.1f | %.1f | %s | %s | %s %.1f ms |" % (
            r["target"], r["pipeline"], "other two pipelines" if key[2] == "+bg" else key[2],
            r["achieved_rate_hz"], r["rate_hz"], 100 * kept, 1e3 * lat["p50"], 1e3 * lat["p99"],
            "%.1f" % run["mean_w"] if run else "-", "%.1f" % idle["mean_w"] if idle else "-",
            slow["name"], 1e3 * slow["p50"]))
    return "\n".join(out)


def _ms(x):
    return "-" if x is None else "%.1f" % (1e3 * x)


def _w(r, which):
    p = (r.get("power") or {}).get(which)
    return "%.1f" % p["mean_w"] if p else "-"


def _sorted(rows):
    return sorted(rows, key=lambda k: (ORDER.get(k[1], 9), k[2] != "alone"))


def target_info(runs):
    """What a target's results say about it: board, software, runtimes, power rail, notes."""
    first = runs[_sorted(runs)[0]]
    plat = first["platform"]
    meta = {}
    for r in runs.values():
        meta.update(r.get("pipeline_meta") or {})
    run_p = next(((r.get("power") or {}).get("run") for r in runs.values() if (r.get("power") or {}).get("run")), None)
    sw = ["Python %s" % plat["python"], "numpy %s" % plat["numpy"], "OpenCV %s" % plat["opencv"]]
    if plat.get("onnxruntime"):
        sw.append("onnxruntime %s" % plat["onnxruntime"])
    notes = first.get("notes", "")
    for suffix in ("; no background load", "; other two pipelines as background load"):
        notes = notes.replace(suffix, "")
    return {
        "board": plat.get("model") or plat.get("cpu") or plat.get("machine"),
        "cpus": plat["cpus"], "power_mode": (plat.get("nvpmodel") or "").splitlines()[:1],
        "system": plat["system"], "software": ", ".join(sw),
        "detector": meta.get("detector_runtime", "-"), "stereo": meta.get("stereo_backend", "sgbm"),
        "rail": "`%s` rail, %s backend" % (run_p["total_rail"], run_p["backend"]) if run_p else "not measured",
        "notes": notes or "-", "date": first["time_utc"][:10], "duration_s": first["duration_s"],
    }


def _load_label(key):
    return "other two pipelines" if key[2] == "+bg" else key[2]


def target_section(target, rows):
    """One target's section of the results page: the board, the runs, and the stages."""
    runs = {k: r for k, r in rows.items() if k[0] == target}
    i = target_info(runs)
    out = ["## %s" % target, "",
           "- **Board:** %s, %s CPU cores%s" % (i["board"], i["cpus"], "".join(", " + m for m in i["power_mode"])),
           "- **System:** %s; %s" % (i["system"], i["software"]),
           "- **Detector:** `%s`; **stereo:** `%s`" % (i["detector"], i["stereo"]),
           "- **Power:** %s" % i["rail"],
           "- **Notes:** %s" % i["notes"],
           "- **Measured:** %s, %.0f s per run" % (i["date"], i["duration_s"]),
           "",
           "| Pipeline | Load | Rate [Hz] | Kept | p50 [ms] | p99 [ms] | max [ms] | Power [W] | Idle [W] |",
           "|---|---|---|---|---|---|---|---|---|"]
    for key in _sorted(runs):
        r = runs[key]
        lat = r["latency_s"]
        out.append("| %s | %s | %.1f / %.0f | %.0f%% | %s | %s | %s | %s | %s |" % (
            key[1], _load_label(key), r["achieved_rate_hz"], r["rate_hz"],
            100 * (1 - (r["drop_fraction"] or 0)), _ms(lat["p50"]), _ms(lat["p99"]), _ms(lat.get("max")),
            _w(r, "run"), _w(r, "idle")))
    out += ["", "Stage times, p50 / p99 [ms]:", "",
            "| Pipeline | Load | Stages | Result |", "|---|---|---|---|"]
    for key in _sorted(runs):
        r = runs[key]
        stages = ", ".join("%s %s / %s" % (st["name"], _ms(st["p50"]), _ms(st["p99"])) for st in r["stages"])
        link = os.path.relpath(r["_path"], os.path.dirname(PAGE)).replace(os.sep, "/")
        out.append("| %s | %s | %s | [%s](%s) |" % (key[1], _load_label(key), stages, os.path.basename(link), link))
    return "\n".join(out)


PAGE_HEAD = """# Phase 2 results

Every measurement the Phase 2 harness has recorded, one section per target. The [optimal-speed plan](optimal-speed.md#phase-2-results-first-two-targets) reads them, and the [benchmarking workflow](workflow.md) says how they were taken.

This page is generated from `bench/results/` by `python3 bench/summarize.py --page`; don't edit it by hand. The bench tests fail when it is out of date.

- **Rate** is the achieved rate over the mission rate. **Kept** is the share of offered frames processed; a pipeline that drops more than 1% doesn't keep up on that target, and `bench/to_compute.py` rejects it.
- **Latency** runs from the frame's capture timestamp to the end of the last stage, so it includes queueing; it excludes exposure, readout, the ISP and transport to the flight controller.
- **Power** is the mean of the target's total input rail during the timed run, and **idle** the mean over the 10 s before it. The rails differ in scope between boards: see each target's power line.
- **Load** is `alone`, or `other two pipelines`: the target's other two pipelines run in separate processes at their own mission rates.
- These are the stand-in pipelines: they measure compute cost, not perception quality.
"""


def page(rows):
    targets = sorted(set(k[0] for k in rows), key=lambda t: (t.startswith("desktop"), t))
    out = [PAGE_HEAD, "| Target | Board | Detector | Stereo |", "|---|---|---|---|"]
    for t in targets:
        i = target_info({k: r for k, r in rows.items() if k[0] == t})
        out.append("| [%s](#%s) | %s | `%s` | `%s` |" % (t, t, i["board"], i["detector"], i["stereo"]))
    return "\n".join(out) + "\n\n" + "\n\n".join(target_section(t, rows) for t in targets) + "\n"


def all_results():
    return load(sorted(glob.glob(os.path.join(RESULTS, "*", ""))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="result files or directories (default: every target)")
    ap.add_argument("--page", action="store_true", help="write the results page, %s" % os.path.relpath(PAGE))
    args = ap.parse_args()
    rows = load(args.paths) if args.paths else all_results()
    if args.page:
        with open(PAGE, "w") as f:
            f.write(page(rows))
        print("wrote", os.path.relpath(PAGE))
    else:
        print(table(rows))


if __name__ == "__main__":
    main()
