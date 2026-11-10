"""Turn Phase 2 results and a weighed-mass record into a models/data/compute.json entry.

    python3 bench/to_compute.py --target orin-nx-15w \\
        --mass bench/data/mass/orin-nx-15w.json bench/results/orin-nx-15w/*.json
    python3 bench/to_compute.py ... --power-csv logger.csv      # external logger instead of on-board rails
    python3 bench/to_compute.py ... --write                     # update models/data/compute.json in place

For each pipeline, the newest result is used:
- latency_by_pipeline_s[p]   = p99 end-to-end latency, plus --latency-extra-ms
                               (exposure, readout, transport to the FC), which
                               the harness does not see
- p_compute_by_pipeline_w[p] = mean total-rail power during the timed run
- latency_s, p_compute       = the worst over the pipelines, as the default for
                               missions that name no pipeline
- m_compute                  = sum of the mass record's items [kg]

The mission model picks the per-pipeline value through each mission's
'pipeline' field. Results whose frames were dropped above --max-drop are
rejected: the pipeline does not keep up at mission rate on that target.
"""

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMPUTE_JSON = os.path.join(os.path.dirname(HERE), "models", "data", "compute.json")


def load_results(paths, target):
    newest = {}
    for p in paths:
        with open(p) as f:
            r = json.load(f)
        if r.get("schema") != "drone-capability/bench-result/1":
            raise ValueError("%s: not a bench result" % p)
        if r["target"] != target:
            raise ValueError("%s: target %r, expected %r" % (p, r["target"], target))
        if r["pipeline"] not in newest or r["time_utc"] > newest[r["pipeline"]]["time_utc"]:
            newest[r["pipeline"]] = dict(r, _path=p)
    return newest


def mass_kg(record):
    """Sum of the weighed items [g] -> kg. Every item must be weighed, not taken from a datasheet."""
    items = record["items"]
    unweighed = [i["item"] for i in items if not i.get("weighed")]
    if unweighed:
        raise ValueError("mass items not weighed: %s" % ", ".join(unweighed))
    return sum(i["grams"] for i in items) / 1000.0


def csv_mean_w(path):
    """Mean of the 'watts' column of an external logger CSV (trim it to the timed run first)."""
    with open(path) as f:
        ws = [float(row["watts"]) for row in csv.DictReader(f)]
    if not ws:
        raise ValueError("%s: no rows" % path)
    return sum(ws) / len(ws)


def entry(target, results, mass_record, latency_extra_s=0.0, power_csv=None, max_drop=0.01, description=""):
    lat, pwr, sources = {}, {}, []
    for name, r in sorted(results.items()):
        if (r["drop_fraction"] or 0) > max_drop:
            raise ValueError("%s: %.1f%% of frames dropped at %.0f Hz; the pipeline does not keep up"
                             % (r["_path"], 100 * r["drop_fraction"], r["rate_hz"]))
        lat[name] = r["latency_s"]["p99"] + latency_extra_s
        run = (r.get("power") or {}).get("run")
        if power_csv:
            pwr[name] = csv_mean_w(power_csv[name]) if isinstance(power_csv, dict) else csv_mean_w(power_csv)
        elif run:
            pwr[name] = run["mean_w"]
        sources.append(os.path.relpath(r["_path"], os.path.dirname(HERE)))
    if len(pwr) != len(lat):
        raise ValueError("no power measurement for %s: use an on-board backend or --power-csv"
                         % ", ".join(sorted(set(lat) - set(pwr))))
    return {
        "description": description or mass_record.get("description", target),
        "p_compute": max(pwr.values()), "m_compute": mass_kg(mass_record), "latency_s": max(lat.values()),
        "p_compute_by_pipeline_w": pwr, "latency_by_pipeline_s": lat,
        "measured": {"sources": sources, "latency_extra_s": latency_extra_s,
                     "power_source": "external CSV" if power_csv else "on-board rail"},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="+")
    ap.add_argument("--target", required=True)
    ap.add_argument("--mass", required=True, help="weighed-mass record (bench/data/mass/TEMPLATE.json)")
    ap.add_argument("--latency-extra-ms", type=float, default=0.0)
    ap.add_argument("--power-csv", help="external logger CSV with a 'watts' column, trimmed to the run")
    ap.add_argument("--max-drop", type=float, default=0.01)
    ap.add_argument("--write", action="store_true", help="update models/data/compute.json")
    args = ap.parse_args(argv)

    with open(args.mass) as f:
        mass_record = json.load(f)
    e = entry(args.target, load_results(args.results, args.target), mass_record,
              args.latency_extra_ms / 1000.0, args.power_csv, args.max_drop)
    if args.write:
        with open(COMPUTE_JSON) as f:
            data = json.load(f)
        data[args.target] = e
        with open(COMPUTE_JSON, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        print("updated", os.path.relpath(COMPUTE_JSON), "entry", args.target, file=sys.stderr)
    json.dump({args.target: e}, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
