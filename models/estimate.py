"""Phase 1 estimator: mission capability for each mission and compute option.

    python3 models/estimate.py                         # every mission x every compute option
    python3 models/estimate.py --mission scout --compute orin-nx-15w
    python3 models/estimate.py --mission racing --latency-ms 200
    python3 models/estimate.py --json

The airframes, compute options, and missions are in models/data/. Compute
values are illustrative until Phase 2 measures them.
"""

import argparse
import json
import sys

import mission as ms

UNITS = {"range": ("range", 1e-3, "km"), "endurance": ("time", 1 / 60, "min"), "speed": ("speed", 1.0, "m/s")}


def card(mission_name, compute_name, mission, airframe, compute):
    cap = ms.capability(airframe, compute, mission)
    budget = ms.latency_budget(cap, mission) if cap["feasible"] else None
    sens = ms.sensitivities(airframe, compute, mission) if cap["feasible"] else {}
    return {"mission": mission_name, "compute": compute_name, "airframe": mission["airframe"],
            "objective": mission["objective"], **cap, "mission_value": ms.mission_value(cap, mission),
            "latency_budget_s": budget, "sensitivity": sens}


def print_cards(cards):
    by_mission = {}
    for c in cards:
        by_mission.setdefault(c["mission"], []).append(c)
    for name, rows in by_mission.items():
        label, scale, unit = UNITS[rows[0]["objective"]]
        print(f"\n{name}  (airframe {rows[0]['airframe']}, objective: {rows[0]['objective']})")
        print(f"  {'compute':20s} {'T/W':>5s} {'v_mission':>9s}  {'binding':10s} {label + ' [' + unit + ']':>13s}"
              f" {'latency budget':>15s} {'per +1 W':>9s} {'per +100 g':>10s} {'per +10 ms':>10s}")
        for c in rows:
            if not c["feasible"]:
                print(f"  {c['compute']:20s} {c['thrust_to_weight']:5.2f} {'-':>9s}  {c['binding']}")
                continue
            s = c["sensitivity"]
            fmt = lambda k: f"{s[k] * scale:+.2f}" if k in s else "-"
            budget = f"{c['latency_budget_s'] * 1000:.0f} ms" if c["latency_budget_s"] is not None else "-"
            print(f"  {c['compute']:20s} {c['thrust_to_weight']:5.2f} {c['v_mission']:7.1f}  "
                  f"  {c['binding']:10s} {c['mission_value'] * scale:13.1f} {budget:>15s}"
                  f" {fmt('per_watt'):>9s} {fmt('per_100g'):>10s} {fmt('per_10ms'):>10s}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mission", action="append", help="mission profile (repeatable; default: all)")
    ap.add_argument("--compute", action="append", help="compute option (repeatable; default: all)")
    ap.add_argument("--airframe", help="override the mission's airframe")
    ap.add_argument("--latency-ms", type=float, help="override every compute option's latency")
    ap.add_argument("--json", action="store_true", help="print JSON instead of tables")
    args = ap.parse_args(argv)

    missions, computes, airframes = ms.load("missions"), ms.load("compute"), ms.load("airframes")
    for kind, names, table in (("mission", args.mission, missions), ("compute", args.compute, computes)):
        unknown = set(names or []) - set(table)
        if unknown:
            ap.error(f"unknown {kind} {sorted(unknown)}; choose from {sorted(table)}")
    if args.airframe and args.airframe not in airframes:
        ap.error(f"unknown airframe {args.airframe!r}; choose from {sorted(airframes)}")

    cards = []
    for mname in args.mission or missions:
        mission = dict(missions[mname])
        if args.airframe:
            mission["airframe"] = args.airframe
        for cname in args.compute or computes:
            compute = dict(computes[cname])
            if args.latency_ms is not None and compute["latency_s"] is not None:
                compute["latency_s"] = args.latency_ms / 1000
            cards.append(card(mname, cname, mission, airframes[mission["airframe"]], compute))

    if args.json:
        json.dump(cards, sys.stdout, indent=2)
        print()
    else:
        print_cards(cards)


if __name__ == "__main__":
    main()
