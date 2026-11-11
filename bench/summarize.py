"""Summarize Phase 2 results as a markdown table (the tables in docs/benchmarks/optimal-speed.md).

    python3 bench/summarize.py bench/results/*/            # every target
    python3 bench/summarize.py bench/results/ventuno-q-npu bench/results/orin-nano-super-25w-gpu

For each (target, pipeline, load), the newest result is shown. 'Keeps up' is
the share of frames processed at mission rate; a pipeline that drops frames
is slower than the rate even where its p99 looks acceptable.
"""

import argparse
import glob
import json
import os


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
                rows[key] = r
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="result files or directories")
    print(table(load(ap.parse_args().paths)))


if __name__ == "__main__":
    main()
