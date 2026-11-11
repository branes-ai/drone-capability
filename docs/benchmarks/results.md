# Phase 2 results

Every measurement the Phase 2 harness has recorded, one section per target. The [optimal-speed plan](optimal-speed.md#phase-2-results-first-two-targets) reads them, and the [benchmarking workflow](workflow.md) says how they were taken.

This page is generated from `bench/results/` by `python3 bench/summarize.py --page`; don't edit it by hand. The bench tests fail when it is out of date.

- **Rate** is the achieved rate over the mission rate. **Kept** is the share of offered frames processed; a pipeline that drops more than 1% doesn't keep up on that target, and `bench/to_compute.py` rejects it.
- **Latency** runs from the frame's capture timestamp to the end of the last stage, so it includes queueing; it excludes exposure, readout, the ISP and transport to the flight controller.
- **Power** is the mean of the target's total input rail during the timed run, and **idle** the mean over the 10 s before it. The rails differ in scope between boards: see each target's power line.
- **Load** is `alone`, or `other two pipelines`: the target's other two pipelines run in separate processes at their own mission rates.
- These are the stand-in pipelines: they measure compute cost, not perception quality.

| Target | Board | Detector | Stereo |
|---|---|---|---|
| [orin-nano-super-25w-cpu](#orin-nano-super-25w-cpu) | NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super | `onnxruntime:CPUExecutionProvider` | `sgbm` |
| [orin-nano-super-25w-gpu](#orin-nano-super-25w-gpu) | NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super | `tensorrt-10.3.0:fp16` | `vpi-cuda` |
| [orin-nano-super-25w-maxclk-cpu](#orin-nano-super-25w-maxclk-cpu) | NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super | `onnxruntime:CPUExecutionProvider` | `sgbm` |
| [orin-nano-super-25w-maxclk-gpu](#orin-nano-super-25w-maxclk-gpu) | NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super | `tensorrt-10.3.0:fp16` | `vpi-cuda` |
| [ventuno-q-cpu](#ventuno-q-cpu) | Qualcomm Technologies, Inc. Monaco Monza addons | `onnxruntime:CPUExecutionProvider` | `sgbm` |
| [ventuno-q-npu](#ventuno-q-npu) | Qualcomm Technologies, Inc. Monaco Monza addons | `onnxruntime-qnn:HTP:fp16` | `sgbm` |
| [desktop-i7-12700k](#desktop-i7-12700k) | 12th Gen Intel(R) Core(TM) i7-12700K | `onnxruntime:CPUExecutionProvider` | `sgbm` |

## orin-nano-super-25w-cpu

- **Board:** NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super, 6 CPU cores, NV Power Mode: 25W
- **System:** Linux-5.15.148-tegra-aarch64-with-glibc2.35; Python 3.10.12, numpy 1.21.5, OpenCV 5.0.0, onnxruntime 1.23.2
- **Detector:** `onnxruntime:CPUExecutionProvider`; **stereo:** `sgbm`
- **Power:** `VDD_IN` rail, jetson backend
- **Notes:** Jetson Orin Nano Super dev kit, JetPack 6.2.1, nvpmodel 25W, open air, stock fan; venv with system site packages (numpy 1.21.5, TensorRT 10.3, VPI 3.2.4) + OpenCV 5.0.0 + onnxruntime 1.23.2; BLAS single-threaded; power = INA3221 VDD_IN (module input); detector on onnxruntime CPU, stereo on OpenCV SGBM (CPU)
- **Measured:** 2026-11-10, 60 s per run

| Pipeline | Load | Rate [Hz] | Kept | p50 [ms] | p99 [ms] | max [ms] | Power [W] | Idle [W] |
|---|---|---|---|---|---|---|---|---|
| racing | alone | 27.1 / 60 | 45% | 45.4 | 54.4 | 102.3 | 8.6 | 5.4 |
| racing | other two pipelines | 7.4 / 60 | 12% | 143.3 | 245.0 | 269.9 | 8.3 | 5.3 |
| scout | alone | 7.0 / 30 | 23% | 158.9 | 175.4 | 176.1 | 5.9 | 5.3 |
| scout | other two pipelines | 4.5 / 30 | 15% | 225.6 | 356.8 | 366.0 | 8.3 | 5.3 |
| inspection | alone | 30.0 / 30 | 100% | 26.9 | 27.6 | 38.0 | 6.0 | 5.3 |
| inspection | other two pipelines | 19.8 / 30 | 66% | 65.6 | 107.7 | 128.7 | 8.3 | 5.3 |

Stage times, p50 / p99 [ms]:

| Pipeline | Load | Stages | Result |
|---|---|---|---|
| racing | alone | detect 32.6 / 36.9, decode 1.7 / 2.1, gate_pnp 0.2 / 0.3, estimate 0.3 / 0.4, mpc 1.8 / 1.9 | [racing-20261110T213852Z.json](../../bench/results/orin-nano-super-25w-cpu/racing-20261110T213852Z.json) |
| racing | other two pipelines | detect 127.7 / 227.5, decode 1.7 / 15.6, gate_pnp 0.2 / 0.7, estimate 0.3 / 3.9, mpc 1.8 / 14.0 | [racing-20261110T214539Z.json](../../bench/results/orin-nano-super-25w-cpu/racing-20261110T214539Z.json) |
| scout | alone | depth 136.0 / 138.4, points 0.8 / 1.0, mapping 4.2 / 4.5, planner 1.3 / 1.5 | [scout-20261110T214107Z.json](../../bench/results/orin-nano-super-25w-cpu/scout-20261110T214107Z.json) |
| scout | other two pipelines | depth 193.4 / 319.5, points 0.9 / 15.7, mapping 4.6 / 27.0, planner 1.5 / 18.0 | [scout-20261110T214755Z.json](../../bench/results/orin-nano-super-25w-cpu/scout-20261110T214755Z.json) |
| inspection | alone | vio_front 2.5 / 2.9, vio_back 2.1 / 2.7, standoff 22.1 / 22.6, control 0.0 / 0.1 | [inspection-20261110T214323Z.json](../../bench/results/orin-nano-super-25w-cpu/inspection-20261110T214323Z.json) |
| inspection | other two pipelines | vio_front 10.1 / 30.4, vio_back 2.4 / 13.9, standoff 38.5 / 62.7, control 0.1 / 0.1 | [inspection-20261110T215011Z.json](../../bench/results/orin-nano-super-25w-cpu/inspection-20261110T215011Z.json) |

## orin-nano-super-25w-gpu

- **Board:** NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super, 6 CPU cores, NV Power Mode: 25W
- **System:** Linux-5.15.148-tegra-aarch64-with-glibc2.35; Python 3.10.12, numpy 1.21.5, OpenCV 5.0.0, onnxruntime 1.23.2
- **Detector:** `tensorrt-10.3.0:fp16`; **stereo:** `vpi-cuda`
- **Power:** `VDD_IN` rail, jetson backend
- **Notes:** Jetson Orin Nano Super dev kit, JetPack 6.2.1, nvpmodel 25W, open air, stock fan; venv with system site packages (numpy 1.21.5, TensorRT 10.3, VPI 3.2.4) + OpenCV 5.0.0 + onnxruntime 1.23.2; BLAS single-threaded; power = INA3221 VDD_IN (module input); detector on TensorRT 10.3 FP16 (GPU), stereo on VPI CUDA (GPU)
- **Measured:** 2026-11-10, 60 s per run

| Pipeline | Load | Rate [Hz] | Kept | p50 [ms] | p99 [ms] | max [ms] | Power [W] | Idle [W] |
|---|---|---|---|---|---|---|---|---|
| racing | alone | 60.0 / 60 | 100% | 13.2 | 13.5 | 15.2 | 6.1 | 5.3 |
| racing | other two pipelines | 60.0 / 60 | 100% | 11.5 | 14.2 | 16.7 | 9.3 | 5.3 |
| scout | alone | 27.8 / 30 | 93% | 52.7 | 69.3 | 70.3 | 7.3 | 5.3 |
| scout | other two pipelines | 30.0 / 30 | 100% | 28.4 | 41.4 | 50.7 | 9.3 | 5.3 |
| inspection | alone | 30.0 / 30 | 100% | 26.2 | 27.6 | 49.9 | 6.0 | 5.3 |
| inspection | other two pipelines | 30.0 / 30 | 100% | 28.5 | 36.3 | 43.2 | 9.4 | 5.3 |

Stage times, p50 / p99 [ms]:

| Pipeline | Load | Stages | Result |
|---|---|---|---|
| racing | alone | detect 6.9 / 7.0, decode 2.5 / 2.7, gate_pnp 0.3 / 0.3, estimate 0.4 / 0.5, mpc 3.1 / 3.2 | [racing-20261110T215226Z.json](../../bench/results/orin-nano-super-25w-gpu/racing-20261110T215226Z.json) |
| racing | other two pipelines | detect 6.3 / 9.2, decode 1.5 / 2.6, gate_pnp 0.2 / 0.3, estimate 0.3 / 0.4, mpc 1.8 / 2.9 | [racing-20261110T215914Z.json](../../bench/results/orin-nano-super-25w-gpu/racing-20261110T215914Z.json) |
| scout | alone | depth 24.6 / 25.1, points 1.4 / 1.5, mapping 8.3 / 8.5, planner 2.2 / 2.4 | [scout-20261110T215442Z.json](../../bench/results/orin-nano-super-25w-gpu/scout-20261110T215442Z.json) |
| scout | other two pipelines | depth 20.5 / 24.3, points 1.1 / 1.9, mapping 4.8 / 8.7, planner 1.4 / 2.6 | [scout-20261110T220130Z.json](../../bench/results/orin-nano-super-25w-gpu/scout-20261110T220130Z.json) |
| inspection | alone | vio_front 2.2 / 2.6, vio_back 2.1 / 2.7, standoff 21.7 / 22.7, control 0.0 / 0.1 | [inspection-20261110T215658Z.json](../../bench/results/orin-nano-super-25w-gpu/inspection-20261110T215658Z.json) |
| inspection | other two pipelines | vio_front 3.4 / 8.6, vio_back 2.4 / 3.4, standoff 22.4 / 25.9, control 0.1 / 0.1 | [inspection-20261110T220346Z.json](../../bench/results/orin-nano-super-25w-gpu/inspection-20261110T220346Z.json) |

## orin-nano-super-25w-maxclk-cpu

- **Board:** NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super, 6 CPU cores, NV Power Mode: 25W
- **System:** Linux-5.15.148-tegra-aarch64-with-glibc2.35; Python 3.10.12, numpy 1.21.5, OpenCV 5.0.0, onnxruntime 1.23.2
- **Detector:** `onnxruntime:CPUExecutionProvider`; **stereo:** `sgbm`
- **Power:** `VDD_IN` rail, jetson backend
- **Notes:** Jetson Orin Nano Super dev kit, JetPack 6.2.1, nvpmodel 25W + jetson_clocks (CPU, GPU, EMC pinned at max), open air, stock fan; venv with system site packages (numpy 1.21.5, TensorRT 10.3, VPI 3.2.4) + OpenCV 5.0.0 + onnxruntime 1.23.2; BLAS single-threaded; power = INA3221 VDD_IN (module input); detector on onnxruntime CPU, stereo on OpenCV SGBM (CPU)
- **Measured:** 2026-11-10, 60 s per run

| Pipeline | Load | Rate [Hz] | Kept | p50 [ms] | p99 [ms] | max [ms] | Power [W] | Idle [W] |
|---|---|---|---|---|---|---|---|---|
| racing | alone | 28.8 / 60 | 48% | 43.2 | 51.6 | 58.7 | 10.8 | 7.1 |
| racing | other two pipelines | 8.2 / 60 | 14% | 128.7 | 227.4 | 270.0 | 10.4 | 7.1 |
| scout | alone | 7.1 / 30 | 24% | 157.3 | 173.7 | 174.3 | 7.8 | 7.2 |
| scout | other two pipelines | 4.1 / 30 | 14% | 283.6 | 350.8 | 377.4 | 10.4 | 7.2 |
| inspection | alone | 30.0 / 30 | 100% | 24.9 | 25.7 | 43.7 | 7.8 | 7.1 |
| inspection | other two pipelines | 23.0 / 30 | 77% | 58.2 | 102.3 | 123.2 | 10.4 | 7.2 |

Stage times, p50 / p99 [ms]:

| Pipeline | Load | Stages | Result |
|---|---|---|---|
| racing | alone | detect 30.8 / 34.5, decode 1.6 / 1.8, gate_pnp 0.2 / 0.2, estimate 0.3 / 0.3, mpc 1.8 / 1.8 | [racing-20261110T234138Z.json](../../bench/results/orin-nano-super-25w-maxclk-cpu/racing-20261110T234138Z.json) |
| racing | other two pipelines | detect 112.2 / 214.9, decode 1.6 / 16.0, gate_pnp 0.2 / 0.4, estimate 0.3 / 4.7, mpc 1.8 / 14.1 | [racing-20261110T234825Z.json](../../bench/results/orin-nano-super-25w-maxclk-cpu/racing-20261110T234825Z.json) |
| scout | alone | depth 134.8 / 136.7, points 0.7 / 0.8, mapping 4.1 / 4.2, planner 1.2 / 1.4 | [scout-20261110T234354Z.json](../../bench/results/orin-nano-super-25w-maxclk-cpu/scout-20261110T234354Z.json) |
| scout | other two pipelines | depth 259.7 / 320.9, points 0.8 / 17.8, mapping 4.3 / 24.2, planner 1.4 / 18.1 | [scout-20261110T235041Z.json](../../bench/results/orin-nano-super-25w-maxclk-cpu/scout-20261110T235041Z.json) |
| inspection | alone | vio_front 1.9 / 2.2, vio_back 2.1 / 2.6, standoff 20.9 / 21.3, control 0.0 / 0.1 | [inspection-20261110T234609Z.json](../../bench/results/orin-nano-super-25w-maxclk-cpu/inspection-20261110T234609Z.json) |
| inspection | other two pipelines | vio_front 10.2 / 27.4, vio_back 2.3 / 9.5, standoff 22.3 / 58.7, control 0.1 / 0.1 | [inspection-20261110T235256Z.json](../../bench/results/orin-nano-super-25w-maxclk-cpu/inspection-20261110T235256Z.json) |

## orin-nano-super-25w-maxclk-gpu

- **Board:** NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super, 6 CPU cores, NV Power Mode: 25W
- **System:** Linux-5.15.148-tegra-aarch64-with-glibc2.35; Python 3.10.12, numpy 1.21.5, OpenCV 5.0.0, onnxruntime 1.23.2
- **Detector:** `tensorrt-10.3.0:fp16`; **stereo:** `vpi-cuda`
- **Power:** `VDD_IN` rail, jetson backend
- **Notes:** Jetson Orin Nano Super dev kit, JetPack 6.2.1, nvpmodel 25W + jetson_clocks (CPU, GPU, EMC pinned at max), open air, stock fan; venv with system site packages (numpy 1.21.5, TensorRT 10.3, VPI 3.2.4) + OpenCV 5.0.0 + onnxruntime 1.23.2; BLAS single-threaded; power = INA3221 VDD_IN (module input); detector on TensorRT 10.3 FP16 (GPU), stereo on VPI CUDA (GPU)
- **Measured:** 2026-11-10, 60 s per run

| Pipeline | Load | Rate [Hz] | Kept | p50 [ms] | p99 [ms] | max [ms] | Power [W] | Idle [W] |
|---|---|---|---|---|---|---|---|---|
| racing | alone | 60.0 / 60 | 100% | 6.8 | 7.0 | 10.9 | 8.1 | 7.2 |
| racing | other two pipelines | 60.0 / 60 | 100% | 7.1 | 7.9 | 13.6 | 11.2 | 7.1 |
| scout | alone | 30.0 / 30 | 100% | 16.1 | 16.4 | 29.4 | 9.6 | 7.1 |
| scout | other two pipelines | 30.0 / 30 | 100% | 19.2 | 20.8 | 27.5 | 11.3 | 7.1 |
| inspection | alone | 30.0 / 30 | 100% | 25.2 | 26.9 | 42.4 | 7.8 | 7.2 |
| inspection | other two pipelines | 30.0 / 30 | 100% | 26.4 | 32.5 | 52.6 | 11.3 | 7.1 |

Stage times, p50 / p99 [ms]:

| Pipeline | Load | Stages | Result |
|---|---|---|---|
| racing | alone | detect 3.2 / 3.3, decode 1.4 / 1.4, gate_pnp 0.1 / 0.2, estimate 0.2 / 0.2, mpc 1.7 / 1.8 | [racing-20261110T235512Z.json](../../bench/results/orin-nano-super-25w-maxclk-gpu/racing-20261110T235512Z.json) |
| racing | other two pipelines | detect 3.5 / 4.2, decode 1.4 / 1.6, gate_pnp 0.2 / 0.2, estimate 0.2 / 0.3, mpc 1.7 / 1.8 | [racing-20261111T000159Z.json](../../bench/results/orin-nano-super-25w-maxclk-gpu/racing-20261111T000159Z.json) |
| scout | alone | depth 9.5 / 9.7, points 0.8 / 0.9, mapping 4.5 / 4.6, planner 1.2 / 1.3 | [scout-20261110T235728Z.json](../../bench/results/orin-nano-super-25w-maxclk-gpu/scout-20261110T235728Z.json) |
| scout | other two pipelines | depth 12.4 / 13.4, points 0.8 / 0.9, mapping 4.6 / 4.9, planner 1.3 / 1.4 | [scout-20261111T000415Z.json](../../bench/results/orin-nano-super-25w-maxclk-gpu/scout-20261111T000415Z.json) |
| inspection | alone | vio_front 1.9 / 2.2, vio_back 2.1 / 2.7, standoff 21.1 / 22.2, control 0.0 / 0.1 | [inspection-20261110T235943Z.json](../../bench/results/orin-nano-super-25w-maxclk-gpu/inspection-20261110T235943Z.json) |
| inspection | other two pipelines | vio_front 2.2 / 4.5, vio_back 2.2 / 2.9, standoff 21.8 / 24.7, control 0.1 / 0.1 | [inspection-20261111T000631Z.json](../../bench/results/orin-nano-super-25w-maxclk-gpu/inspection-20261111T000631Z.json) |

## ventuno-q-cpu

- **Board:** Qualcomm Technologies, Inc. Monaco Monza addons, 8 CPU cores
- **System:** Linux-6.8.0-1089-qcom-aarch64-with-glibc2.39; Python 3.12.3, numpy 2.5.4, OpenCV 5.0.0, onnxruntime 1.31.1
- **Detector:** `onnxruntime:CPUExecutionProvider`; **stereo:** `sgbm`
- **Power:** `power1_input` rail, file backend
- **Notes:** Arduino Ventuno Q (Qualcomm Monaco), open air, stock fan; power = INA232 board input rail (20 V), includes fan and peripherals; CPU only (onnxruntime CPU provider)
- **Measured:** 2026-11-10, 60 s per run

| Pipeline | Load | Rate [Hz] | Kept | p50 [ms] | p99 [ms] | max [ms] | Power [W] | Idle [W] |
|---|---|---|---|---|---|---|---|---|
| racing | alone | 25.8 / 60 | 43% | 46.9 | 55.5 | 74.8 | 14.6 | 8.7 |
| racing | other two pipelines | 10.1 / 60 | 17% | 102.3 | 152.8 | 166.7 | 14.6 | 8.5 |
| scout | alone | 12.1 / 30 | 40% | 99.5 | 115.9 | 116.9 | 11.2 | 8.5 |
| scout | other two pipelines | 6.6 / 30 | 22% | 197.2 | 272.0 | 321.1 | 14.5 | 8.7 |
| inspection | alone | 30.0 / 30 | 100% | 19.5 | 24.1 | 27.5 | 10.2 | 8.7 |
| inspection | other two pipelines | 17.9 / 30 | 60% | 72.1 | 108.5 | 116.1 | 14.7 | 8.7 |

Stage times, p50 / p99 [ms]:

| Pipeline | Load | Stages | Result |
|---|---|---|---|
| racing | alone | detect 36.4 / 39.5, decode 1.1 / 1.4, gate_pnp 0.1 / 0.2, estimate 0.2 / 0.3, mpc 0.6 / 0.8 | [racing-20261110T233252Z.json](../../bench/results/ventuno-q-cpu/racing-20261110T233252Z.json) |
| racing | other two pipelines | detect 87.9 / 138.9, decode 1.2 / 10.3, gate_pnp 0.1 / 3.2, estimate 0.2 / 3.3, mpc 0.7 / 6.4 | [racing-20261110T233939Z.json](../../bench/results/ventuno-q-cpu/racing-20261110T233939Z.json) |
| scout | alone | depth 78.5 / 79.6, points 0.6 / 0.9, mapping 2.8 / 3.6, planner 0.7 / 0.9 | [scout-20261110T233508Z.json](../../bench/results/ventuno-q-cpu/scout-20261110T233508Z.json) |
| scout | other two pipelines | depth 179.8 / 248.3, points 0.7 / 4.7, mapping 6.0 / 9.7, planner 0.9 / 4.9 | [scout-20261110T234155Z.json](../../bench/results/ventuno-q-cpu/scout-20261110T234155Z.json) |
| inspection | alone | vio_front 2.9 / 3.8, vio_back 1.7 / 2.6, standoff 14.2 / 18.4, control 0.0 / 0.1 | [inspection-20261110T233724Z.json](../../bench/results/ventuno-q-cpu/inspection-20261110T233724Z.json) |
| inspection | other two pipelines | vio_front 11.5 / 25.1, vio_back 1.9 / 8.5, standoff 38.5 / 59.1, control 0.0 / 3.1 | [inspection-20261110T234411Z.json](../../bench/results/ventuno-q-cpu/inspection-20261110T234411Z.json) |

## ventuno-q-npu

- **Board:** Qualcomm Technologies, Inc. Monaco Monza addons, 8 CPU cores
- **System:** Linux-6.8.0-1089-qcom-aarch64-with-glibc2.39; Python 3.12.3, numpy 2.5.4, OpenCV 5.0.0, onnxruntime 1.31.1
- **Detector:** `onnxruntime-qnn:HTP:fp16`; **stereo:** `sgbm`
- **Power:** `power1_input` rail, file backend
- **Notes:** Arduino Ventuno Q (Qualcomm Monaco), open air, stock fan; power = INA232 board input rail (20 V), includes fan and peripherals; detector on HTP NPU (onnxruntime-qnn, FP16), stereo on CPU (SGBM)
- **Measured:** 2026-11-10, 60 s per run

| Pipeline | Load | Rate [Hz] | Kept | p50 [ms] | p99 [ms] | max [ms] | Power [W] | Idle [W] |
|---|---|---|---|---|---|---|---|---|
| racing | alone | 60.0 / 60 | 100% | 5.8 | 7.7 | 17.3 | 10.5 | 8.5 |
| racing | other two pipelines | 60.0 / 60 | 100% | 5.3 | 14.6 | 16.9 | 13.2 | 8.5 |
| scout | alone | 12.1 / 30 | 40% | 99.3 | 115.5 | 117.9 | 11.2 | 8.9 |
| scout | other two pipelines | 11.8 / 30 | 40% | 100.8 | 117.3 | 117.9 | 13.3 | 9.1 |
| inspection | alone | 30.0 / 30 | 100% | 19.5 | 23.0 | 35.2 | 10.3 | 8.4 |
| inspection | other two pipelines | 30.0 / 30 | 100% | 20.9 | 23.3 | 28.3 | 13.3 | 8.4 |

Stage times, p50 / p99 [ms]:

| Pipeline | Load | Stages | Result |
|---|---|---|---|
| racing | alone | detect 2.8 / 3.2, decode 1.5 / 2.5, gate_pnp 0.1 / 0.4, estimate 0.2 / 0.5, mpc 0.6 / 1.4 | [racing-20261110T234627Z.json](../../bench/results/ventuno-q-npu/racing-20261110T234627Z.json) |
| racing | other two pipelines | detect 2.6 / 4.3, decode 1.3 / 5.1, gate_pnp 0.2 / 0.5, estimate 0.2 / 0.8, mpc 0.7 / 3.6 | [racing-20261110T235315Z.json](../../bench/results/ventuno-q-npu/racing-20261110T235315Z.json) |
| scout | alone | depth 78.1 / 79.3, points 0.7 / 1.2, mapping 2.8 / 3.4, planner 0.7 / 1.2 | [scout-20261110T234843Z.json](../../bench/results/ventuno-q-npu/scout-20261110T234843Z.json) |
| scout | other two pipelines | depth 80.0 / 81.3, points 0.6 / 0.9, mapping 2.7 / 3.1, planner 0.7 / 1.0 | [scout-20261110T235531Z.json](../../bench/results/ventuno-q-npu/scout-20261110T235531Z.json) |
| inspection | alone | vio_front 3.0 / 3.8, vio_back 1.7 / 2.5, standoff 13.9 / 17.9, control 0.0 / 0.1 | [inspection-20261110T235058Z.json](../../bench/results/ventuno-q-npu/inspection-20261110T235058Z.json) |
| inspection | other two pipelines | vio_front 3.0 / 4.0, vio_back 1.7 / 2.1, standoff 15.7 / 17.5, control 0.0 / 0.1 | [inspection-20261110T235747Z.json](../../bench/results/ventuno-q-npu/inspection-20261110T235747Z.json) |

## desktop-i7-12700k

- **Board:** 12th Gen Intel(R) Core(TM) i7-12700K, 20 CPU cores
- **System:** Linux-7.0.0-43-generic-x86_64-with-glibc2.43; Python 3.11.17, numpy 2.2.6, OpenCV 4.12.0, onnxruntime 1.23.2
- **Detector:** `onnxruntime:CPUExecutionProvider`; **stereo:** `sgbm`
- **Power:** not measured
- **Notes:** harness check on the development desktop, not a flight target; no power (RAPL is root-only)
- **Measured:** 2026-11-10, 30 s per run

| Pipeline | Load | Rate [Hz] | Kept | p50 [ms] | p99 [ms] | max [ms] | Power [W] | Idle [W] |
|---|---|---|---|---|---|---|---|---|
| racing | other two pipelines | 60.0 / 60 | 100% | 5.5 | 6.2 | 9.7 | - | - |
| scout | other two pipelines | 25.9 / 30 | 86% | 56.2 | 73.2 | 74.3 | - | - |
| inspection | other two pipelines | 30.0 / 30 | 100% | 6.3 | 7.7 | 11.7 | - | - |

Stage times, p50 / p99 [ms]:

| Pipeline | Load | Stages | Result |
|---|---|---|---|
| racing | other two pipelines | detect 4.6 / 5.0, decode 0.6 / 0.7, gate_pnp 0.1 / 0.1, estimate 0.1 / 0.1, mpc 0.2 / 0.3 | [racing-20261110T193849Z.json](../../bench/results/desktop-i7-12700k/racing-20261110T193849Z.json) |
| scout | other two pipelines | depth 35.5 / 39.0, points 0.2 / 0.3, mapping 1.6 / 2.3, planner 0.5 / 0.6 | [scout-20261110T193925Z.json](../../bench/results/desktop-i7-12700k/scout-20261110T193925Z.json) |
| inspection | other two pipelines | vio_front 0.5 / 0.7, vio_back 1.3 / 1.9, standoff 4.5 / 5.2, control 0.0 / 0.0 | [inspection-20261110T194000Z.json](../../bench/results/desktop-i7-12700k/inspection-20261110T194000Z.json) |
