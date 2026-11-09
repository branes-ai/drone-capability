# Benchmark task: Arduino board characterization

**Status:** proposed
**Scope:** L0 and L1 benchmarks across the Arduino board family, from 8-bit AVR boards to the Qualcomm-based UNO Q and Ventuno Q, with STM32 flight controllers as the reference baseline.

## Goal

Characterize every current Arduino board class as a drone flight computer. For each board, find out which drone capabilities it can support: rate-loop frequency, attitude and pose estimation, sensor-fusion capacity, onboard perception, and the endurance cost of its power draw. Report the results as [capability cards](../../README.md#capability-classes), so a maker or drone designer can pick a board from a mission requirement.

## Why Arduino

- **The same silicon as real flight controllers.** The Portenta H7, Giga R1, Nicla Vision, and Opta all use the STM32H747, a close relative of the H743/H753 found in high-end Betaflight, ArduPilot, and PX4 flight controllers. The UNO Q and Ventuno Q pair an STM32 MCU (U5 and H5) with a Qualcomm Dragonwing application processor. That is the same flight-controller-plus-companion split real drones use, on one board.
- **The on-ramp for drone designers.** Students, makers, and startups prototype on Arduino first. A capability benchmark that speaks Arduino reaches them where they already are.
- **One toolchain across very different hardware.** The Arduino core gives a common programming model from an ATmega328P to a Cortex-A78. That makes it a fair way to compare architectures. It also adds abstraction overhead, which this task measures directly against bare-metal and RTOS builds.
- **Arduino is now part of Qualcomm.** The Q-series boards are the most accessible way into the Dragonwing parts that appear in the companion-computer tier of the main benchmark.

## Board matrix

Boards are grouped into tiers by the drone role they can plausibly fill. Part numbers come from Arduino's published specifications. Confirm each against the board's datasheet when the board is added to `targets/`.

### Tier A: 8-bit AVR (baseline and lower bound)

| Board | MCU | Core / clock | FPU |
|---|---|---|---|
| UNO R3 | ATmega328P | AVR, 16 MHz | none |
| Nano (classic) | ATmega328P | AVR, 16 MHz | none |
| Micro, Leonardo | ATmega32U4 | AVR, 16 MHz | none |
| Nano Every | ATmega4809 | AVR, 20 MHz | none |
| Mega 2560 | ATmega2560 | AVR, 16 MHz | none |

*Expected role:* a historical baseline (early MultiWii-class flight controllers ran on the ATmega328P) and a lower bound for fixed-point attitude estimation. We don't expect these boards to run an EKF at IMU rate.

### Tier B: 32-bit entry MCUs

| Board | MCU | Core / clock | FPU |
|---|---|---|---|
| Nano 33 IoT | SAMD21 | Cortex-M0+, 48 MHz | none |
| Nano RP2040 Connect | RP2040 | 2× Cortex-M0+, 133 MHz | none |
| UNO R4 Minima / WiFi, Nano R4 | Renesas RA4M1 | Cortex-M4, 48 MHz | single precision |
| Nano 33 BLE Sense Rev2 | nRF52840 | Cortex-M4F, 64 MHz | single precision |
| Nano Matter | MGM240S (EFR32MG24) | Cortex-M33, 78 MHz | single precision |
| Nano ESP32 | ESP32-S3 | 2× Xtensa LX7, 240 MHz | single precision |
| Nicla Sense ME | nRF52832 + Bosch BHI260AP | Cortex-M4F, 64 MHz + sensor-fusion hub | single precision |

*Expected role:* nano-drone flight controllers and attitude estimation. The Nano 33 BLE Sense and the Nicla Sense ME have IMUs on the board, so they can run end-to-end IMU-to-attitude benchmarks with real sensor data. The Nicla Sense ME also lets us compare host-MCU fusion against the BHI260AP's built-in fusion.

### Tier C: high-performance MCUs (flight-controller class)

| Board | MCU | Core / clock | FPU |
|---|---|---|---|
| Portenta C33 | Renesas RA6M5 | Cortex-M33, 200 MHz | single precision |
| Portenta H7 | STM32H747 | Cortex-M7 480 MHz + Cortex-M4 240 MHz | M7 double precision |
| Giga R1 WiFi | STM32H747 | Cortex-M7 480 MHz + Cortex-M4 240 MHz | M7 double precision |
| Nicla Vision | STM32H747 + camera + IMU | Cortex-M7 480 MHz + Cortex-M4 240 MHz | M7 double precision |
| Opta | STM32H747 | Cortex-M7 480 MHz + Cortex-M4 240 MHz | M7 double precision |

*Expected role:* full flight controllers with an onboard navigation EKF. These are the boards that compare directly with the H7 flight-controller baseline. The dual-core H747 lets us test one partitioning question: rate loop on the M4, estimation on the M7. The Nicla Vision adds TinyML perception on the MCU (optical flow, small detectors).

### Tier D: MCU + application processor (flight controller and companion on one board)

| Board | Application processor | Real-time MCU | Accelerator |
|---|---|---|---|
| Portenta X8 | NXP i.MX 8M Mini (4× Cortex-A53) | STM32H747 | none |
| UNO Q | Qualcomm Dragonwing QRB2210 (4× Cortex-A53) | STM32U585 (Cortex-M33, 160 MHz) | Adreno GPU |
| Ventuno Q | Qualcomm Dragonwing IQ-8275 (8× Kryo, Cortex-A78/A55 class) | STM32H5F5 (Cortex-M33) | Hexagon NPU, up to 40 TOPS |

*Expected role:* the complete two-tier drone stack. The MCU runs the inner loop and the application processor runs VIO, perception, and planning. The Ventuno Q is the first Arduino board in the same performance class as the companion computers in the main benchmark (Jetson Orin, Dragonwing). It is the bridge between the maker results and the production results.

### Reference baseline (not Arduino)

Benchmark the same kernels on production flight controllers, so every Arduino result can be read as "this board can do what a ___ flight controller does":

| Reference | MCU | Typical firmware |
|---|---|---|
| F4 flight controller | STM32F405 (Cortex-M4F, 168 MHz) | Betaflight, INAV |
| F7 flight controller | STM32F722 / F745 (Cortex-M7, 216 MHz) | Betaflight, INAV, ArduPilot |
| H7 flight controller | STM32H743 (Cortex-M7, 480 MHz) | Betaflight, ArduPilot |
| Pixhawk 6-class | STM32H753 (Cortex-M7, 480 MHz) | PX4, ArduPilot |
| Nucleo / Discovery boards | F405, F722, H743, H563 | bare metal, for clean kernel timing |

## Workloads

### L0 kernels (all MCU tiers)

| Workload | Variants | Capability it drives |
|---|---|---|
| Gyro filter chain | biquad low-pass, dynamic notch, RPM harmonic notch | maximum gyro and rate-loop frequency |
| Rate/attitude PID | single axis, three axes with feed-forward | maximum control-loop frequency |
| Attitude estimator | complementary, Mahony, Madgwick | attitude-estimation rate and accuracy |
| Pose EKF | 7-state attitude, 15-state INS, 24-state (EKF3/EKF2-like) | navigation-filter rate, sensors supported |
| Small dense linear algebra | 3×3 to 24×24 matrix multiply, Cholesky, inverse | the inner cost of the EKF and MPC |
| FFT | 128 to 1024 points | vibration analysis, dynamic notch tracking |
| Tiny MPC / LQR | condensed QP, a few states, short horizon | advanced control headroom |
| TinyML | keyword-size CNN, optical-flow net, tiny detector (int8) | onboard perception on the MCU |

Each kernel is built in several number formats where the hardware allows it: fp64, fp32, Q15/Q31 fixed point, and int8 for the networks. Formats from [Universal](https://github.com/stillwater-sc/universal) can be added as an extension. Precision is a first-class result. The question "does a 24-state EKF in fp32 drift enough to matter, compared with fp64 on the H7's double-precision FPU?" answers part selection directly.

### L0 and L1 on application processors (Tier D)

| Workload | Notes |
|---|---|
| The EKF set above, on the application cores | compare with the MCU running the same code |
| VIO front end | feature detection and tracking at 30 to 60 Hz |
| Depth / detector DNN | Ventuno Q: on the Hexagon NPU vs. the GPU vs. the CPU |
| MCU ↔ application processor bridge | round-trip latency, jitter, and throughput of the Arduino RPC/bridge path, for the IMU forwarding and setpoint return a two-tier stack needs |

### L1 pipelines

- **Flight-controller loop:** gyro read → filter chain → rate PID → motor mixer → output, at the target rate. Report the maximum sustainable rate and the CPU headroom left.
- **Flight controller with navigation:** the loop above, plus a 24-state EKF at IMU rate with simulated GPS, barometer, and magnetometer updates. Report the rate-loop jitter that the EKF causes.
- **Two-tier stack (Tier D):** the MCU flight-controller loop, with VIO on the application processor feeding position setpoints back over the bridge. Report end-to-end perception-to-actuation latency (p50/p99/max).

## Metrics and measurement method

| Metric | How it's measured |
|---|---|
| Cycles and latency | DWT `CYCCNT` on Cortex-M3/M4/M7/M33 parts that have it. A hardware timer on the M0+ and AVR. `clock_gettime(CLOCK_MONOTONIC)` and PMU counters on the application processors. Spot-check every board externally with GPIO toggling and a logic analyzer. |
| Latency distribution | p50, p99, and max over at least 10,000 iterations, after warm-up, with caches and interrupts in their normal flight state |
| Maximum loop rate | the highest rate at which the p99 period error stays below a threshold (for example 5% of the period) |
| Power and energy | a high-side current monitor on the supply rail (for example a Joulescope or Nordic PPK2-class meter), synchronized to a GPIO marker. Report idle, active, and per-update energy. |
| Memory | flash and RAM footprint from the linker map |
| Accuracy | estimator error against a ground-truth IMU dataset (for example EuRoC-style or recorded flight logs), for each number format |
| Framework overhead | the same kernel built three ways: Arduino core, bare metal (or STM32Cube HAL/LL), and RTOS (ChibiOS, NuttX, or Zephyr, matching what the flight stacks use) |

Every result records:

- the board and its revision, and the Arduino core and board-package versions
- the compiler and flags
- the clock configuration
- the cache and TCM placement (on M7 parts, whether code and data sit in ITCM/DTCM matters a lot)
- the power mode

## Mapping to drone capability

Results are turned into capability classes with the models in the main [README](../../README.md#from-compute-metrics-to-mission-capability), plus two models specific to flight controllers:

- **Control-loop class.** The highest sustainable rate-loop frequency with the full filter chain. This maps to the airframes the board can fly: a large, slow multirotor is fine at a few hundred Hz, while agile and racing quads need kHz-class loops.
- **Navigation class.** The largest EKF (by state count and sensor set) the board sustains at IMU rate with a given CPU budget. This maps to whether the board can run autonomous missions (GPS-denied VIO fusion, multi-sensor INS) or only stabilized manual flight.

The headline deliverable is a single chart: every board, placed by control-loop class and navigation class, colored by power draw, with the reference flight controllers marked.

## Phases

1. **Harness and baseline.** Build the timing and power harness and the L0 kernel set. Validate it on Nucleo F405, F722, and H743 boards against published Betaflight and ArduPilot loop-time figures.
2. **MCU sweep.** Run L0 on Tiers A, B, and C, with Arduino-core vs. bare-metal comparisons on representative boards.
3. **Flight-controller pipelines.** Run L1 flight-controller pipelines on Tier B and C boards with on-board IMUs, using recorded IMU data for repeatability.
4. **Two-tier boards.** Run L0 and L1 on the Portenta X8, UNO Q, and Ventuno Q, including the MCU ↔ application processor bridge and NPU inference.
5. **Capability cards and report.** Publish the cards to `results/` and the summary chart to `docs/`.

## Open questions

- Should Tier A be measured in full, or kept to a small fixed-point attitude baseline?
- Which Ventuno Q software path should the NPU benchmarks use (Qualcomm AI Runtime / QNN vs. TFLite delegates)? Pick the one makers will actually use.
- Which IMU dataset should be the standard for accuracy runs: public datasets, recorded logs from the sister drone repos, or both?
- Is there an Arduino-native way to run ArduPilot or PX4 builds on the Portenta H7 or Giga R1 for an apples-to-apples comparison with production flight controllers, or do we benchmark the extracted kernels only?
