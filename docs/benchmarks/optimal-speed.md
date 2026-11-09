# Benchmark plan: optimal flight speed and the cost of compute

**Status:** proposed
**Source paper:** L. Bauersfeld and D. Scaramuzza, *Range, Endurance, and Optimal Speed Estimates for Multicopters*, IEEE Robotics and Automation Letters, 2022 ([arXiv:2109.04741](https://arxiv.org/abs/2109.04741)). A local copy is in `research/`.

## The question

Does a more compute-efficient flight computer and flight controller improve the mission capability of a drone? If so, by how much, for which form factor, and through which mechanism?

"Compute efficiency" here means the same perception and estimation work done with less power, less mass, and less latency. "Mission capability" means the speed, range, and endurance a drone can actually use in its mission. This plan covers four form factors: **racing**, **scouting**, **inspection**, and **interception**.

## What the paper gives us

The paper is the best available first-principles method for estimating a multicopter's energy-optimal flight speeds, and it is validated against real flights.

### The model chain

```text
 airframe + propellers ──> BEM aerodynamics ──> shaft power ──> motor model ──> electrical power ──> battery model ──> voltage, energy, time
 (mass, prop radius,       (blade-element      Q·Ω            η_M(Ω), fitted    P_mot(t)            OTC Thevenin circuit,
  rotor count, area)        momentum theory)                   on 44 motor-prop                     fitted on 10 LiPo packs
                                                               pairs
```

| Component | Accuracy reported in the paper |
|---|---|
| BEM aerodynamics | thrust RMSE 0.91 N, on flights up to 65 km/h (18 m/s) |
| Power, simulated vs. measured | 2.5% RMSE on circle flights from 4 to 10 m/s |
| Battery voltage (OTC model) | 43.1 mV per cell (1.3%) on discharge tests, 60.8 mV in flight |

### Two energy-optimal speeds

- **$v_e$, the endurance-optimal speed,** minimizes power: $v_e = \arg\min_v P(v)$. Flying slowly forward uses *less* power than hovering, because of dynamic lift: $P_e / P_h = 0.914$.
- **$v_r$, the range-optimal speed,** minimizes energy per distance: $v_r = \arg\max_v v / P(v)$. On the power curve, this is where a tangent line drawn from the origin touches it: $P_r / P_h = 1.092$.

### The pen-and-paper algorithm (Sec. VII)

From mass $m$, propeller radius $r$, rotor count $N_r$, cell count and capacity, and frontal area $A$:

1. hover induced velocity $v_{i,h} = \sqrt{mg / (2\rho\pi r^2 N_r)}$ and hover power $P_h = (mg)^{3/2} / (\eta_P \sqrt{2\rho\pi N_r}\, r)$, with $\eta_P = 0.6$ (eqs. 4 and 5)
2. $P_e = 0.914\,P_h$ and $P_r = 1.092\,P_h$ (eq. 17)
3. electrical power $P_{mot} = P / \eta_M$, with $\eta_M = 0.75$
4. per-cell power, then effective capacity from a cubic Peukert-like fit (eq. 21)
5. $t = C_{eff} \cdot 3.7\,\mathrm{V} \cdot N_S \cdot 3600 / P_{mot}$
6. $1/\hat v = c_0 + c_1 v_{i,h} + c_2 A$, with $A$ in cm², and $v = \hat v \cdot v_{i,h}$ (eq. 18, $R^2 \approx 0.97$)
7. range $x_r = v_r t_r$

The paper's six commercial drones (Table III) come out within about 10% of the manufacturers' figures.

**Reproduction check.** We implemented the algorithm and reran the paper's DJI Mavic 3 example. Using the paper's stated $P_h = 73.5$ W, we get $t_e$ = 2908 s (paper: 2909 s), $v_e$ = 7.74 m/s (7.75), $v_r$ = 13.19 m/s (13.12), and $x_r$ = 32.0 km (32.1). Eq. 5 with $\eta_P = 0.6$ gives only $P_h$ = 66.2 W for the stated mass and propeller, so the worked example effectively uses $\eta_P \approx 0.54$. Phase 0 must resolve this, and the calibration of $\eta_P$ becomes a reported parameter.

### What the paper leaves out, and why it matters here

> "The power consumption of the flight controller and potentially the onboard computer is neglected as it is typically negligible compared to the power consumption of the motors. For example, an NVIDIA Jetson TX2 consumes <10 W while the research platform needs 130 W to hover." (Sec. VII-A)

That assumption is exactly what this benchmark tests. It holds for the paper's 752 g research quad running *motion-capture* state estimation. It stops holding once the drone carries its own perception. The paper also assumes:
- the drone flies at its energy-optimal speed;
- the only limits are aerodynamic and electrochemical;
- straight, steady flight, with no takeoff, landing, or maneuvering.

None of the four target missions fly that way all the time.

## How compute enters mission capability

Compute affects a mission through four channels. The paper's model can carry the first two. The other two set a separate *speed limit*.

| Channel | Mechanism | What it changes |
|---|---|---|
| **1. Power** $P_c$ | adds a constant offset to the power curve | endurance and range, and it shifts $v_r$ |
| **2. Mass** $m_c$ | raises hover power ($P_h \propto m^{3/2}$) and lowers thrust-to-weight | endurance, range, $v_e$ and $v_r$ (through $v_{i,h}$), acceleration and agility |
| **3. Latency** $\tau$ (p99, not the mean) | the drone travels "blind" during $\tau$ | the maximum safe speed and the trajectory-tracking error |
| **4. Perception quality** | sensing range $d$, estimation accuracy, detection rate, all bought with compute | the maximum safe speed, and how tight a corridor the drone can hold |

The speed a mission can actually use is the smallest of these limits:

$$v_{mission} = \min\big(\; v_{energy}(P_c, m_c),\;\; v_{stop}(\tau, d, a),\;\; v_{track}(\tau, e),\;\; v_{max}(T/W) \;\big)$$

where $v_{energy}$ is $v_r$ or $v_e$ depending on what the mission is trying to maximize, and:

- $v_{stop} = a\left(\sqrt{\tau^2 + 2d/a} - \tau\right)$ stops within the sensing range $d$ at deceleration $a$.
- $v_{track} \approx e / \tau$ keeps the error that builds up during one latency interval inside the corridor $e$.
- $v_{max}$ is the top speed that thrust-to-weight allows.

**The central claim to test:** whenever $v_{stop}$ or $v_{track}$ is below $v_r$, the drone is speed-limited by its compute, not its energy. In that case, lower latency and longer perception range convert directly into mission speed, and indirectly into range, because flying below $v_r$ costs energy per meter.

### Two analytic results the benchmark should confirm

1. **Compute power does not move the endurance-optimal speed.** A constant offset does not move the curve's minimum, so $v_e$ stays put.
2. **Compute power *raises* the range-optimal speed while reducing range.** Adding $P_c$ lifts the curve, so the tangent from the origin touches it at a higher speed, satisfying $P'(v_r) = (P(v_r) + P_c)/v_r$. A power-hungry flight computer should therefore cruise *faster* to maximize range. If perception can't keep up at that speed, the penalty compounds. The pen-and-paper algorithm can't show this shift, because eq. 18 is fitted without $P_c$. Phase 1 adds it.

### First-order estimates

These come from our implementation of the pen-and-paper algorithm ([`models/pen_and_paper.py`](../../models/pen_and_paper.py)); [`models/compute_scenarios.py`](../../models/compute_scenarios.py) reproduces every table in this section. We used eq. 5 hover power with $\eta_P = 0.6$, airframes taken from the paper, and $P_c$ and $m_c$ added. The compute options are **illustrative**, not measured: module plus carrier plus cooling, over a flight-controller-only baseline. Replacing them with measured values is the point of Phase 2. $v_r$ is not corrected for the shift described in result 2.

| Airframe | Compute option | $P_c / P_{mot,e}$ | Endurance | Range | Thrust-to-weight |
|---|---|---|---|---|---|
| **Racing / interceptor class**: 0.75 kg, 4S 1.8 Ah, 5.1" props ($v_e$ 9.6 m/s, $v_r$ 16.5 m/s) | flight-controller MCU only (0.5 W) | 0.4% | 13.3 min | 10.9 km | ×1.00 |
| | efficient companion (7 W, +40 g) | 5.4% | −13% | −12% | ×0.95 |
| | Orin NX class (15 W, +120 g) | 9.6% | −29% | −27% | ×0.86 |
| | AGX Orin class (40 W, +350 g) | 16.6% | −57% | −54% | ×0.68 |
| **Scout class**: 0.90 kg, 4S 5.0 Ah, Mavic 3 ($v_e$ 7.7 m/s, $v_r$ 13.2 m/s) | flight-controller MCU only | 0.6% | 53.5 min | 35.4 km | ×1.00 |
| | efficient companion | 7.5% | −14% | −12% | ×0.96 |
| | Orin NX class | 13.3% | −29% | −25% | ×0.88 |
| | AGX Orin class | 23.2% | −54% | −48% | ×0.72 |
| **Heavy inspection class**: 6.14 kg, 6S2P 15.3 Ah, Matrice 200 ($v_e$ 3.6 m/s, $v_r$ 5.3 m/s) | flight-controller MCU only | 0.1% | 24.8 min | 6.6 km | ×1.00 |
| | efficient companion | 0.9% | −2% | −2% | ×0.99 |
| | Orin NX class | 1.8% | −5% | −4% | ×0.98 |
| | AGX Orin class | 4.4% | −12% | −10% | ×0.95 |

**Mass costs as much as power.** We split the Orin NX case into its two effects. On the scout airframe, power alone costs 16% of endurance and mass alone costs 17%. On the racing airframe, the split is 12% for power and 21% for mass. The power-only loss is larger than the power fraction (13.3%) because higher current draw also lowers the battery's effective capacity. A benchmark that reports only watts misses half the cost.

**Latency matters less than sensing range for stopping.** Here is $v_{stop}$ in m/s, at $a = 5$ m/s²:

| Sensing range $d$ | $\tau$ = 20 ms | 50 ms | 100 ms | 200 ms | 500 ms |
|---|---|---|---|---|---|
| 5 m | 7.0 | 6.8 | 6.6 | 6.1 | 5.0 |
| 10 m | 9.9 | 9.8 | 9.5 | 9.0 | 7.8 |
| 20 m | 14.0 | 13.9 | 13.7 | 13.2 | 11.9 |
| 40 m | 19.9 | 19.8 | 19.5 | 19.0 | 17.7 |

Below about 100 ms, latency costs a few percent of stopping-limited speed. Doubling the reliable sensing range is worth 40% or more. Latency matters most for *tracking*. With $v_{track} \approx e/\tau$, the speed limit is directly proportional to $1/\tau$, which is why racing and close-quarters inspection are latency-bound. For a scout, compute buys speed mainly by making longer-range perception affordable within its power, mass, and latency budget.

## Hypotheses by form factor

| Form factor | Capability metric | Expected binding constraint | Hypothesis |
|---|---|---|---|
| **Racing** | lap time, maximum speed through gates | $v_{track}$ (latency, estimation accuracy) and thrust-to-weight | Lower latency and lower compute mass raise speed directly. Compute power matters only through mass and cooling, since races last 2 to 3 minutes. |
| **Scouting** | time to goal and range through unknown clutter | $v_{stop}$ (sensing range, latency) in clutter, $v_r$ in the open | In clutter, $v_{stop} < v_r$, so the scout is compute-limited. An efficient computer that affords longer-range perception raises both speed and range. In the open, compute power and mass cost 12 to 25% of range. |
| **Inspection** | time on station, standoff accuracy, area covered per sortie | endurance near $v_e$ and hover; $v_{track}$ for close standoff | Compute efficiency matters a lot on small inspection drones (Skydio class) and little on heavy ones (Matrice class: −5% for an Orin NX). Latency sets how close and how fast the drone can work near structures. |
| **Interception** | closing speed, miss distance, engagement envelope | guidance-loop latency, thrust-to-weight, top speed | Dash speeds are well beyond the paper's validated envelope. Capability is set by $\tau$ in the tracking loop and by thrust-to-weight. Energy only has to last the engagement window. |

## Benchmark plan

### Phase 0: reproduce the paper

- Implement the pen-and-paper algorithm in `models/` with the coefficients from Tables I and II. A prototype is in [`models/pen_and_paper.py`](../../models/pen_and_paper.py); it reproduces the Mavic 3 example but not yet the rest of Table III.
- Reproduce all six drones in Table III, and match the paper's own numbers to within 1%.
- Resolve the $\eta_P$ discrepancy in the hover power.
- **Deliverable:** a reference model with a regression test against Table III.
- **Exit criterion:** every Table III number is reproduced, and every deviation is explained.

### Phase 1: add compute to the model

- Add $P_c$ and $m_c$ to the power model and propagate them through the battery model.
- Build a full power-versus-speed curve $P(v)$, so we can compute the $v_r$ shift from $P_c$. Two candidate sources:
  - the paper's BEM simulator / NeuroBEM, if available;
  - a momentum-theory-plus-drag curve calibrated to the paper's anchor points ($P_h$, $P_e$ at $v_e$, $P_r$ at $v_r$).
- Add $v_{stop}$, $v_{track}$, and $v_{max}$, and output $v_{mission}$ together with the constraint that binds it.
- **Deliverable:** `drone-capability estimate` produces, for each airframe and compute option: $v_e$, $v_r$, $v_{mission}$, endurance, range, thrust-to-weight, and the binding constraint.

### Phase 2: measure the compute

For each target (STM32 F4/F7/H7 flight controllers, efficient companions such as Dragonwing / Ventuno Q, Jetson Orin NX and AGX, Intel embedded), run the L1 pipeline for each form factor:

| Form factor | L1 pipeline |
|---|---|
| Racing | gate detection, then state estimation, then MPC |
| Scouting | stereo or monocular depth, then mapping, then local planner |
| Inspection | VIO, then standoff estimation, then position control |
| Interception | detector and tracker, then guidance law |

For each, record:
- **Latency:** the end-to-end distribution (p50/p99/max), under concurrent load.
- **Power:** the average power and the power trace at mission rate.
- **Mass:** weigh the module, carrier, cooling, and cabling. Don't take the datasheet's module mass.
- **Perception quality:** sensing range or detection range at the operating point.

**Deliverable:** measured ($\tau$, $P_c$, $m_c$, $d$) for each target, which replace the illustrative values above.

### Phase 3: capability cards

Combine Phase 1 and Phase 2 into a capability card for each (form factor, compute option). Each card shows the binding constraint and how much mission capability moves per watt, per gram, and per millisecond.

This phase answers the core question quantitatively. For each form factor:
- How much does moving from compute option X to Y change $v_{mission}$, range, and endurance?
- Which channel (power, mass, latency, or perception quality) is responsible?

### Phase 4: closed-loop simulation (L2)

- Fly mission scenarios in the `anatomy` simulator, injecting the measured latency distributions and power traces. Scenarios:
  - a racing gate course
  - a scout clutter field at several obstacle densities
  - an inspection orbit around a structure
  - an intercept engagement
- Compare the speed actually flown, the collisions, the time to goal, and the energy used against the Phase 3 predictions.
- **Exit criterion:** the predicted $v_{mission}$ is within 10% of the simulated value, and the binding constraint is identified correctly.

### Phase 5: flight validation (proving the optimal speed)

Repeat the paper's validation experiment (Sec. VI-A, Fig. 5): fly constant-speed circles or straight legs at stepped speeds, for example 2 to 16 m/s in 2 m/s steps, while logging pack voltage and current. Plot range per Wh against speed and find where it peaks. That speed is the measured $v_r$.

Run the experiment in four configurations, so each channel is isolated:

| Configuration | Emulates | Purpose |
|---|---|---|
| A: baseline | flight controller only | reproduce the paper's curve on our airframe |
| B: + resistive load at $P_c$ | power only | confirm the predicted upward shift of $v_r$ and the range loss |
| C: + ballast at $m_c$ | mass only | confirm the hover-power and $v_{i,h}$ scaling |
| D: + real flight computer running the L1 pipeline | everything | confirm that B and C add up to D |

- **Airframes:** at least the racing / interceptor class (5-inch) and the scout class.
- **Exit criteria:** the measured $v_r$ is within 10% of prediction, and the measured endurance and range deltas are within 10% of the Phase 3 numbers.

## Instrumentation

- **Pack power:** voltage and current at 100 Hz or more, from the flight controller's power module, checked against an external logger.
- **Compute power:** a separate rail measurement, so $P_c$ is never inferred from the difference between two flights.
- **State:** ground truth from motion capture where available, otherwise RTK GNSS, for speed and tracking error.
- **Wind:** wind speed and direction at the flying site. The paper's correction (eqs. 19 and 20) applies outdoors. Fly indoors or in calm air for Phase 5 B to D.
- **Battery:** pack temperature, and the cycle count per pack. Rotate packs between configurations to control for battery aging.

## Limits and open questions

- **Validity envelope.** The BEM model is validated only up to 18 m/s, and eq. 18 is a regression over the paper's simulated airframes. Racing (more than 30 m/s) and interception dash speeds need the full BEM simulator or new measurements, not the pen-and-paper algorithm. Nano drones (under 50 g) are probably outside the fitted range, and the low Reynolds numbers at that size change propeller efficiency.
- **Steady flight versus missions.** Racing and interception are dominated by transients. Phase 4 has to carry those missions, because their power traces are nothing like steady cruise.
- **Thermal.** A sealed racing or interceptor airframe may throttle a 15 to 40 W module. Latency should be measured at thermal steady state, in a representative enclosure.
- **The paper's model availability.** Is the BEM simulator / NeuroBEM model available to use for Phase 1? If not, which calibrated surrogate do we adopt?
- **Reference airframes.** The airframes here are borrowed from the paper. Each sister mission repo should provide its own reference airframe and compute candidates for Phase 3.
