# drone-capability

A benchmark for drone mission capabilities. It measures how an algorithm and a flight computer turn into what a drone can actually do in a mission: how fast it can safely fly, how far it can go, and how many sensors it can fuse in real time.

The benchmark answers questions like this one: *if I run this Kalman filter for pose estimation on an Intel embedded processor, an NVIDIA Jetson Orin, or a Qualcomm Snapdragon or Dragonwing part, what top speed can my drone safely fly?* A drone designer can then pick the algorithm and the part from the mission requirement, not from a datasheet.

> **Status:** early design. This README describes the intent and the planned structure. The directories, commands, and report formats below are the target, not yet the implementation.

---

## Why

### Datasheets don't describe missions

Hardware vendors report TOPS, GFLOPS, memory bandwidth, and TDP. Algorithm papers report accuracy and maybe runtime on a desktop GPU. A drone designer needs something else:

- *Can this drone fly 15 m/s through a forest without hitting anything?*
- *Will adding a second camera to the VIO cut endurance by 2 minutes or by 10?*
- *Is a 40 W Jetson worth its weight on a 250 g airframe, or will a 5 W part with a lighter algorithm fly further and almost as fast?*

Getting from a TOPS number to an answer like that takes several steps: workload characterization, mapping the workload to the hardware, latency and power analysis, and a vehicle-dynamics model. Most teams make that jump by intuition or by expensive trial and error on real airframes. This repo makes it systematic, repeatable, and comparable.

### Capability is a property of the whole chain

The same extended Kalman filter can run with sub-millisecond latency on one part and miss its deadline on another. It can also run fast enough on average while its 99th-percentile latency, under contention from the perception pipeline, is too high to keep the drone safe. A useful benchmark has to keep the algorithm, the hardware, and the mission linked:

```text
   Algorithm                 Hardware                   Mission capability
 ----------------         -----------------          -------------------------
 operation count    -->   latency (p50/p99/max) -->  max safe flight speed
 arithmetic intensity     throughput                 range / endurance
 parallelism / depth      concurrency / contention   sensor-fusion capacity
 memory footprint         energy per inference       autonomy level
 numeric precision        power, mass                payload margin
```

### One shared yardstick for the Branes.AI drone family

The sister mission repos each push on a different capability:

| Mission repo | Dominant capability pressure |
|---|---|
| [`nano-drone`](../nano-drone) | energy and mass: compute power is a large fraction of the total power budget |
| [`racing-drone`](../racing-drone) | perception-to-actuation latency at the edge of the flight envelope |
| [`scout-drone`](../scout-drone) | perception latency and range for fast flight through unknown clutter |
| [`isr-drone`](../isr-drone) | endurance with sustained perception and sensor-fusion throughput |
| [`interceptor-drone`](../interceptor-drone) | tracking latency, closing speed, and guidance-loop rate |
| [`inspection-drone`](../inspection-drone) | precise station-keeping, multi-sensor fusion, and endurance near structures |

`drone-capability` gives these missions a common, mission-neutral way to measure and classify the algorithms and hardware they share. Each mission can then state its requirements in the same units.

---

## What

### Two things under test

The benchmark separates the **algorithm** from the **hardware** so that each can be classified on its own and then combined.

**Algorithm characteristics** (hardware-independent):

| Metric | Meaning | Why it matters |
|---|---|---|
| Work | operations per update (FLOPs, MACs, integer ops) | sets the lower bound on latency and energy |
| Arithmetic intensity | operations per byte moved | tells you whether the algorithm is compute- or memory-bound on a given part |
| Parallelism | available parallel work vs. critical-path depth | tells you whether the algorithm can use a GPU, DSP, or NPU, or stays serial on a CPU core |
| Footprint | working-set and parameter memory | tells you whether it fits in cache, SRAM, or only in DRAM |
| Precision | number format required for acceptable accuracy (fp64, fp32, fp16, bf16, int8, posits, fixed-point) | sets the hardware datapaths you can use and the energy per operation |
| Rate | update rate needed by the mission (IMU, camera, control loop) | sets the deadline |

**Hardware characteristics** (measured or estimated per algorithm):

| Metric | Meaning | Why it matters |
|---|---|---|
| Latency | time from input available to output ready, reported as p50, p99, and max | tail latency, not the mean, decides whether a control loop stays stable |
| Throughput | sustained updates per second | sets the sensor rate and sensor count you can support |
| Concurrency | latency and throughput when other workloads run alongside | a flight computer never runs one kernel alone |
| Jitter | variation in latency | eats into stability margin and complicates estimation |
| Energy | joules per update, and average power at the mission rate | sets the endurance and range cost |
| Mass and power envelope | module mass and power mode (for example a Jetson nvpmodel setting) | feeds back into flight power |

### Three benchmark levels

```text
 L2  Mission       closed-loop flight in simulation, scored on mission outcome
      ^            (time to goal, collisions, energy used)
      |
 L1  Capability    a complete capability pipeline at mission rates
      ^            (state estimation, VIO, obstacle perception, tracking, control)
      |
 L0  Kernel        an isolated algorithm or kernel
                   (Kalman predict/update, feature extraction, stereo, conv, GEMM, MPC solve)
```

- **L0** isolates one algorithm, so you can compare implementations and parts directly.
- **L1** runs a capability pipeline with realistic sensor rates and concurrent load, so you see contention and tail latency.
- **L2** closes the loop in the [`anatomy`](../anatomy) simulator, so you can check the capability predicted from L0 and L1 against simulated flight.

### Two ways to get a number: estimate or measure

| Mode | How | When to use it |
|---|---|---|
| **Estimate** | analytic models: operation counts, roofline mapping onto hardware descriptions from [`embodied-schemas`](../embodied-schemas), and the [`characterize`](../characterize) mappers | early design, parts you don't own yet, design-space sweeps |
| **Measure** | run the benchmark on the target, using on-board power rails or an external power meter | validation, final part selection, publishable results |

Every result records which mode produced it. When a part has both, the report shows the estimate next to the measurement, so we can see how accurate the models are and improve them.

### From compute metrics to mission capability

The core of the benchmark is a set of explicit, documented **capability models** that turn hardware metrics into flight-relevant limits. The models are deliberately simple so that a designer can check them by hand. Mission repos can swap in higher-fidelity versions.

**Latency → maximum safe speed.** A drone that sees an obstacle at sensing range $d$ must react and then brake. With end-to-end perception-to-actuation latency $\tau$ and maximum deceleration $a$:

$$v\,\tau + \frac{v^2}{2a} \le d \quad\Rightarrow\quad v_{max} = a\left(\sqrt{\tau^2 + \frac{2d}{a}} - \tau\right)$$

For tracking a trajectory (racing gates, inspection standoff), the error that builds up during one latency interval must stay inside the allowed corridor $e$: $v_{max} \approx e / \tau$. With a 0.2 m corridor, 20 ms of latency allows about 10 m/s, and 50 ms allows about 4 m/s.

**Energy → endurance and range.** Compute power $P_c$ adds directly to flight power $P_f$, and compute mass increases $P_f$ (hover power grows roughly as $m^{3/2}$). With usable battery energy $E$:

$$t_{endurance} = \frac{E}{P_f(m) + P_c}, \qquad R = v_{cruise}\, t_{endurance}$$

This is why the same algorithm choice matters so much more on a nano drone. On a roughly 30 g airframe with about 7 W of flight power, going from 0.1 W to 1 W of compute costs more than 10% of flight time. On a 2 kg ISR airframe at about 300 W, the same change hardly matters, but going from 10 W to 40 W of compute does.

**Throughput → sensor-fusion capacity.** A filter with $n$ states and $m$ measurements per update costs roughly $O(n^3)$ for the predict step and $O(n^2 m + m^3)$ for the update step. With the measured per-update latency and a CPU-utilization budget $U$, the benchmark reports the highest sensor rate, the number of sensors, or the number of tracked features or targets the part can sustain:

$$\sum_i r_i \cdot t_{update,i} \le U$$

**Tail latency → stability margin.** Reports use p99 and max latency, not the mean, when they compute speed and control-bandwidth limits. A pipeline that averages 5 ms but sometimes takes 40 ms is rated at 40 ms.

### Capability classes

Results are summarized as a **capability card** per (algorithm, implementation, hardware, power mode) combination. For example:

```text
Capability card: EKF-15 pose estimator  |  Jetson Orin NX 16GB, 15W mode  |  measured
-------------------------------------------------------------------------------------
Algorithm      15-state EKF, IMU 1 kHz + VIO 30 Hz, fp32, 1 CPU core
Latency        predict  p50 18 us   p99 31 us   max 64 us
               update   p50 92 us   p99 140 us  max 310 us
Concurrency    p99 under VIO + depth load: 210 us
Energy         ~0.9 mW incremental at mission rate

Capability     tracking-limited speed (0.2 m corridor)      > 50 m/s   class S5
               max IMU rate at 10% core budget               3.2 kHz    class F4
               endurance cost on 250 g reference airframe   -0.4 %     class E5
```

*(The numbers above are illustrative and show only the format.)*

The classes (speed **S**, endurance **E**, fusion **F**, and others as we add them) are defined against reference airframes and mission profiles in [`docs/`](docs). That way a designer can say "my mission needs S3/E4/F3" and filter the results database for algorithm-and-hardware pairs that meet it.

### Hardware targets

Most drones split their compute in two. A **flight-controller MCU** runs the hard real-time inner loops: gyro filtering, rate and attitude control, motor output, and often the navigation EKF itself. ArduPilot's EKF3 and PX4's EKF2 both run on the flight controller. A **companion computer** runs perception, mapping, planning, and learned policies. The benchmark covers both tiers, and the link between them, because a drone's capability is set by whichever tier hits its limit first.

The initial target set covers the main classes of drone flight computers:

| Tier | Class | Examples |
|---|---|---|
| Flight controller | STM32 flight-controller MCUs | STM32F4 (F405, Cortex-M4F, 168 MHz), STM32F7 (F722/F745, Cortex-M7, 216 MHz), STM32H7 (H743/H753, Cortex-M7, 480 MHz, double-precision FPU), STM32H5 (Cortex-M33, 250 MHz) |
| Flight controller | Nano and ultra-low-power MCUs | Cortex-M0+/M33 parts, RISC-V MCUs, ultra-low-power AI MCUs |
| Maker / prototyping | Arduino boards | from AVR boards (UNO, Micro) through the Portenta H7 (STM32H747) to the UNO Q and Ventuno Q (Qualcomm Dragonwing + STM32 MCU). See [Arduino board characterization](docs/benchmarks/arduino-board-characterization.md) |
| Companion | Embedded x86 | Intel Atom x7000 series, Intel Core Ultra embedded |
| Companion | Embedded GPU SoC | NVIDIA Jetson Orin Nano, Orin NX, AGX Orin |
| Companion | Mobile / robotics SoC | Qualcomm Snapdragon (QRB/Flight platforms), Qualcomm Dragonwing (QCS6490, IQ-8275, ...) |
| Companion | Accelerators | NPUs, DSPs, and dataflow accelerators, as estimated or measured targets |

The STM32 F4, F7, and H7 parts power most of today's flight controllers in Betaflight, INAV, ArduPilot, and PX4, so they are the baseline every flight-controller result is compared against. On these parts, the questions the benchmark answers are concrete:

- How high can the gyro and rate loop run?
- How many EKF states can the part update at IMU rate?
- Does the algorithm need the H7's double-precision FPU, or does single precision on an F4 do the job?
- How much headroom is left for extra sensors or onboard estimation?

Adding a target means adding a hardware description (for estimates) and a measurement harness (for measurements). See [Contributing](#contributing).

### Representative workloads

Workloads are grouped by the capability they drive. They are reference implementations of the algorithm classes used in the mission repos, so results stay comparable over time. Production implementations from `cortex`, `reflex`, and `synapse` can be benchmarked against them.

| Capability | Representative workloads |
|---|---|
| State estimation | EKF / ESKF / UKF pose filters at several state sizes, Mahony and Madgwick attitude filters, complementary filters |
| Visual odometry and SLAM | feature detection and tracking, VIO front end and back end, bundle adjustment |
| Obstacle perception | stereo depth, monocular depth networks, occupancy mapping |
| Detection and tracking | DNN detectors, multi-target trackers (for ISR and interceptor missions) |
| Planning and control | gyro filtering (biquad, notch, RPM filters), PID rate and attitude loops, MPC solves, trajectory optimization, geometric controllers |
| Learned policies | policy and VLA network inference |
| Math kernels | GEMM, Cholesky, small dense solves, at several precisions |

---

## How

### Planned repository layout

```text
drone-capability/
  workloads/        reference algorithm implementations, grouped by capability (L0)
  pipelines/        capability pipelines with sensor-rate drivers and load generators (L1)
  missions/         closed-loop mission scenarios, built on anatomy (L2)
  targets/          per-hardware build configs, measurement harnesses, power-meter adapters
  models/           capability models (latency->speed, energy->range, throughput->fusion)
  estimate/         analytic estimators: op counts, roofline, hardware mapping
  reports/          capability-card generation and result comparison
  results/          a versioned database of published results
  docs/             methodology, class definitions, reference airframes, ADRs
```

### Building

Like the sister repos, the benchmark core is C++20 and builds with CMake and Ninja using shared presets:

```bash
cmake --preset gcc-release
cmake --build --preset gcc-release
ctest --preset gcc-release
```

Cross-compilation presets for each target (for example `jetson-orin`, `qcom-aarch64`, `intel-embedded`) will be added in `targets/`.

### Workflow for a drone designer

1. **Pick a capability and a mission profile.** For example: pose estimation for a 250 g scout drone with a 10 m sensing range.
2. **Estimate first.** Run the analytic estimator across candidate algorithms and parts to narrow the design space without touching hardware:
   ```bash
   drone-capability estimate --workload ekf-15 --targets orin-nx,qcs6490,atom-x7425e --profile scout-250g
   ```
3. **Measure the shortlist.** Run L0 and L1 on the real hardware, with power measurement:
   ```bash
   drone-capability measure --workload ekf-15 --level L1 --target orin-nx --power-mode 15W
   ```
4. **Read the capability card.** Compare speed, endurance, and fusion classes against your mission requirement.
5. **Close the loop (optional).** Run the L2 mission scenario in simulation with the measured latency and power injected, and check that the predicted capability holds.

*(Command names and flags are illustrative. The CLI is not implemented yet.)*

### Methodology principles

- **Report distributions, not averages.** Latency is always reported as p50, p99, and max over a fixed and documented number of iterations, after warm-up.
- **Measure under realistic load.** L1 runs include concurrent workloads that match the mission. Results report both isolated and contended numbers.
- **Pin everything that changes the result.** Every result records the power mode, clocks, governor, thermal state, compiler and flags, library versions, and number formats.
- **Keep the models auditable.** Every capability number traces back to a measured or estimated metric and a documented model with its parameters.
- **Estimates and measurements live side by side**, so we can see how accurate the models are.
- **Results are reproducible.** A published result includes the commit, the target config, and the exact command used to produce it.

---

## How this fits the Branes.AI platform

```text
 nano / racing / scout / isr / interceptor / inspection -drone     mission requirements
                         |
                         v
                  drone-capability   <-- workloads, pipelines, capability models, reports
                   |      |      |
       anatomy (L2 sim)   |   embodied-schemas, characterize (hardware data and mapping)
                          |
        cortex / reflex / synapse  (production algorithms under test)
                          |
                 MTL5 / Universal  (linear algebra and number systems under test)
```

---

## Contributing

Contributions are welcome in three forms:

- **New workloads.** A reference implementation, its operation-count model, and its correctness test.
- **New targets.** A hardware description for estimates, plus a measurement harness and power-measurement method.
- **New capability models.** A documented model that maps hardware metrics to a mission capability, with its assumptions and validity range.

Each contribution should include enough metadata to reproduce its results. The methodology and class definitions live in [`docs/`](docs) and change through ADRs.

## License

MIT; see [LICENSE](LICENSE).
