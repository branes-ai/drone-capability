"""Render the figures in docs/benchmarks/optimal-speed.md.

Writes a light and a dark PNG for each figure to docs/benchmarks/img/.
The markdown embeds both with a <picture> element, so GitHub shows the one
that matches the reader's theme.

    python3 models/plot_figures.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import mission as ms
import power_curve as pc
from compute_scenarios import AIRFRAMES, with_mass
from pen_and_paper import estimate, v_stop, v_track

OUT = Path(__file__).resolve().parent.parent / "docs" / "benchmarks" / "img"

# Reference data-viz palette: chart chrome, categorical slots 1-4 (adjacent
# pairs validated; lines only), and the blue ordinal ramp (steps 250-650).
THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781",
                  grid="#e1e0d9", axis="#c3c2b7",
                  series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100"],
                  ramp=["#86b6ef", "#5598e7", "#256abf", "#104281"]),
    "dark": dict(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", muted="#898781",
                 grid="#2c2c2a", axis="#383835",
                 series=["#3987e5", "#d95926", "#199e70", "#c98500"],
                 ramp=["#184f95", "#256abf", "#3987e5", "#86b6ef"]),
}

SHORT = {name: name.split("(")[0].strip() for name in AIRFRAMES}
LABEL = {"racing": "Racing / interceptor, 0.75 kg",
         "scout": "Scout, 0.90 kg",
         "inspect": "Heavy inspection, 6.14 kg"}


def style(fig, axes, t):
    fig.patch.set_facecolor(t["surface"])
    for ax in axes:
        ax.set_facecolor(t["surface"])
        ax.grid(True, color=t["grid"], linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(t["axis"])
        ax.tick_params(colors=t["muted"], labelcolor=t["ink2"], length=0, pad=6)
        ax.xaxis.label.set_color(t["ink2"])
        ax.yaxis.label.set_color(t["ink2"])


def end_label(ax, x, y, text, t, dy=0.0):
    ax.annotate(text, (x, y), xytext=(6, dy), textcoords="offset points",
                va="center", ha="left", fontsize=9, color=t["ink2"])


def legend(ax, t, **kw):
    leg = ax.legend(frameon=False, fontsize=9, labelcolor=t["ink2"], handlelength=1.6, **kw)
    return leg


def endurance_figure(t):
    """Endurance change vs. compute power (power only) and compute mass (mass only)."""
    p_c = np.linspace(0, 40, 81)
    m_c = np.linspace(0, 0.4, 81)
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for (name, af), color in zip(AIRFRAMES.items(), t["series"]):
        key = SHORT[name]
        t0 = estimate(**af)["e"]["t"]
        dp = [(estimate(**af, p_compute=p)["e"]["t"] / t0 - 1) * 100 for p in p_c]
        dm = [(estimate(**with_mass(af, m))["e"]["t"] / t0 - 1) * 100 for m in m_c]
        a.plot(p_c, dp, color=color, linewidth=2, label=LABEL[key], solid_capstyle="round")
        b.plot(m_c * 1000, dm, color=color, linewidth=2, label=LABEL[key], solid_capstyle="round")
        end_label(a, p_c[-1], dp[-1], f"{dp[-1]:.0f}%", t)
        end_label(b, m_c[-1] * 1000, dm[-1], f"{dm[-1]:.0f}%", t)
    a.set_title("Compute power only", loc="left", fontsize=11, color=t["ink"])
    b.set_title("Compute mass only", loc="left", fontsize=11, color=t["ink"])
    a.set_xlabel("Compute power  P_c  [W]")
    b.set_xlabel("Compute mass  m_c  [g]")
    a.set_ylabel("Endurance change vs. flight controller only [%]")
    a.set_xlim(0, 46)
    b.set_xlim(0, 460)
    a.set_ylim(-70, 2)
    legend(a, t, loc="lower left")
    style(fig, (a, b), t)
    fig.tight_layout(w_pad=3)
    return fig


def speed_figure(t):
    """Stopping-limited vs. tracking-limited speed as a function of latency."""
    tau = np.logspace(np.log10(0.01), np.log10(1.0), 200)
    scout_vr = estimate(**AIRFRAMES[next(n for n in AIRFRAMES if n.startswith("scout"))])["r"]["v"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)

    for d, color in zip((5, 10, 20, 40), t["ramp"]):
        v = [v_stop(x, d, 5.0) for x in tau]
        a.plot(tau * 1000, v, color=color, linewidth=2, label=f"sensing range d = {d} m")
        end_label(a, tau[-1] * 1000, v[-1], f"{d} m", t)
    a.axhline(scout_vr, color=t["muted"], linewidth=1.2, linestyle=(0, (4, 3)))
    a.annotate(f"scout range-optimal speed  v_r = {scout_vr:.1f} m/s", (12, scout_vr),
               xytext=(0, -13), textcoords="offset points", fontsize=9, color=t["ink2"])
    a.set_title("Stopping limit:  v_stop(τ, d),  a = 5 m/s²", loc="left", fontsize=11, color=t["ink"])

    for e, color in zip((0.1, 0.2, 0.5), t["ramp"][1:]):
        v = np.minimum([v_track(x, e) for x in tau], 1e3)
        b.plot(tau * 1000, v, color=color, linewidth=2, label=f"corridor e = {e} m")
        i = np.searchsorted(-v, -28)  # label where the curve enters the plot
        b.annotate(f"{e} m", (tau[i] * 1000, v[i]), xytext=(6, -2), textcoords="offset points",
                   fontsize=9, color=t["ink2"])
    b.set_title("Tracking limit:  v_track = e / τ", loc="left", fontsize=11, color=t["ink"])

    for ax in (a, b):
        ax.set_xscale("log")
        ax.set_xlim(10, 1000)
        ax.set_xticks([10, 20, 50, 100, 200, 500, 1000])
        ax.set_xticklabels(["10", "20", "50", "100", "200", "500", "1000"])
        ax.set_xlabel("End-to-end latency  τ (p99)  [ms]")
        ax.minorticks_off()
    a.set_xlim(10, 1500)
    a.set_ylim(0, 30)
    a.set_ylabel("Maximum speed [m/s]")
    legend(a, t, loc="upper right")
    legend(b, t, loc="upper right")
    style(fig, (a, b), t)
    fig.tight_layout(w_pad=3)
    return fig


def range_shift_figure(t):
    """Range per Wh vs. speed at several compute powers: the range-optimal speed moves up."""
    af = ms.load("airframes")["scout-0.9kg"]
    s, cap = af["n_series"], af["capacity_ah"]
    curve = pc.PowerCurve(af["m"], af["r"], af["n_rotors"], af["area_cm2"])
    e_nom = cap * s * 3.7
    v = np.linspace(1.0, 24.0, 300)
    fig, ax = plt.subplots(figsize=(10, 4.4))
    for p_c, color in zip((0, 7, 15, 40), t["ramp"]):
        y = pc.distance(curve, v, s, cap, p_c) / e_nom
        _, v_r = pc.optimal_speeds(curve, s, cap, p_c)
        y_r = pc.distance(curve, v_r, s, cap, p_c) / e_nom
        ax.plot(v, y, color=color, linewidth=2, label=f"compute {p_c:2d} W:  v_r = {v_r:.1f} m/s")
        ax.plot([v_r], [y_r], "o", color=color, markersize=8, markeredgecolor=t["surface"], markeredgewidth=2)
    ax.set_title("Scout airframe (0.90 kg): compute power lowers range and raises the range-optimal speed",
                 loc="left", fontsize=11, color=t["ink"])
    ax.set_xlabel("Cruise speed  v  [m/s]")
    ax.set_ylabel("Range per Wh of battery [m/Wh]")
    ax.set_xlim(0, 24)
    ax.set_ylim(0, None)
    legend(ax, t, loc="lower center", prop={"family": "DejaVu Sans Mono", "size": 9})
    style(fig, (ax,), t)
    fig.tight_layout()
    return fig


def latency_budget_figure(t):
    """Mission speed vs. perception latency, Orin NX class compute: flat until the latency budget."""
    missions, computes, airframes = ms.load("missions"), ms.load("compute"), ms.load("airframes")
    compute = computes["orin-nx-15w"]
    tau = np.logspace(np.log10(0.01), np.log10(2.0), 120)
    fig, ax = plt.subplots(figsize=(10, 4.4))
    for (name, mission), color in zip(missions.items(), t["series"]):
        af = airframes[mission["airframe"]]
        v = [ms.capability(af, {**compute, "latency_s": x}, mission)["v_mission"] for x in tau]
        budget = ms.latency_budget(ms.capability(af, compute, mission), mission)
        # Scout and inspection nearly coincide; dash scout so both stay visible.
        dash = (0, (5, 3)) if name == "scout" else "solid"
        ax.plot(tau * 1000, v, color=color, linewidth=2, linestyle=dash, label=name)
        v_b = ms.capability(af, {**compute, "latency_s": budget}, mission)["v_mission"]
        ax.plot([budget * 1000], [v_b], "o", color=color, markersize=8, markeredgecolor=t["surface"], markeredgewidth=2)
        dy = -14 if name == "scout" else 5
        ax.annotate(f"{name}: {budget * 1000:.0f} ms", (budget * 1000, v_b), xytext=(-8 if name == "scout" else 8, dy),
                    ha="right" if name == "scout" else "left", textcoords="offset points", fontsize=9, color=t["ink2"])
    ax.set_xscale("log")
    ax.minorticks_off()
    ax.set_xticks([10, 20, 50, 100, 200, 500, 1000, 2000])
    ax.set_xticklabels(["10", "20", "50", "100", "200", "500", "1000", "2000"])
    ax.set_xlim(10, 2000)
    ax.set_ylim(0, None)
    ax.set_title("Mission speed vs. perception latency (Orin NX class mass and power); dots mark the latency budget",
                 loc="left", fontsize=11, color=t["ink"])
    ax.set_xlabel("End-to-end latency  τ (p99)  [ms]")
    ax.set_ylabel("Mission speed  v_mission  [m/s]")
    legend(ax, t, loc="lower left")
    style(fig, (ax,), t)
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = "DejaVu Sans"
    for mode, t in THEMES.items():
        for name, make in (("endurance-cost", endurance_figure), ("speed-limits", speed_figure),
                           ("range-shift", range_shift_figure), ("latency-budget", latency_budget_figure)):
            fig = make(t)
            path = OUT / f"{name}-{mode}.png"
            fig.savefig(path, dpi=160, facecolor=t["surface"])
            plt.close(fig)
            print(path)
