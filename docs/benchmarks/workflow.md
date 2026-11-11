# Benchmarking workflow

How a compute target is measured for the mission model: preparing the target, running the stand-in pipelines at mission rate, and turning the results into the [results page](results.md), the [optimal-speed plan](optimal-speed.md#phase-2-results-first-two-targets) and, once the mass is weighed, a `models/data/compute.json` entry. The harness is in [`bench/`](../../bench/). This page follows the run of November 2026 on a Jetson Orin Nano Super and an Arduino Ventuno Q, with the commands as they were run.

## The flow

```text
 development host                       target (over SSH)                       repo
 ----------------                       -----------------                       ----
 make_detector.py ──► bench/assets/ ──rsync──► ~/drone-bench/bench/
                                         one Python environment per target
                                         smoke run (10 s)
                                         run set: CPU set, then accelerated set
                                           6 runs each: 3 pipelines × {alone, loaded}
                         ◄──rsync── bench/results/<target>/*.json
 summarize.py --page ──────────────────────────────────────────────────► docs/benchmarks/results.md
 findings, pitfalls ───────────────────────────────────────────────────► plan, issue #8
 weighed mass + latency outside the harness ─► to_compute.py --write ──► models/data/compute.json
```

Each step below says what it does, the command, and what goes wrong if it's skipped.

## 1. What a run measures

The mission model needs three numbers per target and mission: the end-to-end latency (p99), the power the compute draws, and the mass it adds. The harness measures the first two on the target itself, by running a stand-in L1 pipeline for the mission at its mission rate:

| Pipeline | Rate | Stages | Accelerated by |
|---|---|---|---|
| `racing` | 60 Hz | detect (YOLOv8n-shaped, 320 px) → decode → gate PnP → state estimate (IMU propagation and an 18-state Kalman filter) → MPC (N = 20) | `--provider tensorrt` or `qnn` |
| `scout` | 30 Hz | stereo depth (640 × 480, 64 disparities) → points → occupancy mapping → motion-primitive planner | `--stereo vpi-cuda` |
| `inspection` | 30 Hz | VIO front end (KLT) → VIO back end (essential matrix and a 15-state filter) → standoff plane fit → PID control | none (CPU) |

A run offers frames at the mission rate into a one-deep queue. A frame that arrives while the queue is full is dropped. Each frame carries its capture timestamp, and the latency is measured from that timestamp to the end of the last stage, so it includes waiting in the queue.

Each run records:
- the latency distribution (p50, p90, p99, max);
- each stage's timing;
- the frames offered, processed and dropped;
- the power trace of the total input rail during the timed window, and the idle power before it;
- the thermal zones at the start and the end;
- the platform: board, power mode, library versions and the BLAS threading environment.

**What it doesn't measure.** The detector has random weights and the frames are synthetic, so the harness measures compute cost, not perception quality: it says nothing about detection range. Latency stops at the end of the last stage. It excludes exposure, readout, the ISP and the link to the flight controller, which are added later with `--latency-extra-ms`. Interception has no pipeline.

## 2. Prepare the host

The racing detector is generated once, on any machine with PyTorch:

```sh
python3 bench/make_detector.py          # writes bench/assets/det320.onnx (gitignored) and det320.json
python3 -m unittest discover -s bench   # the harness tests, before anything goes to a target
```

The ONNX file is gitignored, so it is copied to each target with the rest of `bench/`. The TensorRT engine is built on the target, the first time `--provider tensorrt` runs, and cached next to the model as `det320.fp16.trt<version>.engine`.

## 3. Prepare a target

### Access

Each target needs:
- an SSH login with a key (`ssh-copy-id stillwater@<host>`);
- the groups that its power monitor and accelerator need;
- for `jetson_clocks`, sudo.

| Board | Groups the harness needs | Why |
|---|---|---|
| Jetson Orin | `i2c` (and `video`, `render` for the GPU) | the INA3221 power monitor's hwmon files |
| Ventuno Q | `fastrpc` | the NPU: read-write access to `/dev/fastrpc-cdsp` and `/dev/dma_heap/system` |

Without `fastrpc`, the NPU session fails at device creation with `DEVICE_ERROR_INVALID_CONFIG`. Nothing in that message points at permissions. A group change takes effect at the next login.

### Copy the harness

```sh
rsync -a --exclude results --exclude __pycache__ bench/ stillwater@<host>:drone-bench/bench/
```

The results stay on the target until the set is done, and are copied back in step 6.

### One Python environment for both sets

A target is measured twice: once on the CPU only, and once with its accelerator. **Both sets run in the same Python environment**, so they differ only in where the detector and the stereo run. A first Jetson GPU set, run against the system OpenCV 4.8 built with TBB, showed KLT tracking 6× slower than the pip OpenCV 5.0 the CPU set used. That would have been read as an accelerator effect.

The harness needs numpy and OpenCV, with onnxruntime optional, and stays Python 3.6 compatible because targets lag. The environments used:

**Jetson Orin Nano Super** (JetPack 6.2.1, Python 3.10). TensorRT and VPI come from JetPack, so the venv sees the system site packages, and pins the OpenCV and onnxruntime wheels without their dependencies, so the system numpy stays:

```sh
python3 -m venv --system-site-packages ~/drone-bench-sys-venv
~/drone-bench-sys-venv/bin/pip install --no-deps opencv-python-headless==5.0.0.93 onnxruntime==1.23.2
# TensorRT 10.3 (python3-libnvinfer), VPI 3.2.4 and numpy 1.21.5 come from the system
```

**Ventuno Q** (Ubuntu 24.04, Python 3.12). The image has no `ensurepip`, so the venv is created without pip and bootstrapped:

```sh
python3 -m venv --without-pip ~/drone-bench-qnn-venv
curl -sSLo /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py && ~/drone-bench-qnn-venv/bin/python /tmp/get-pip.py
~/drone-bench-qnn-venv/bin/pip install numpy opencv-python-headless==5.0.0.93 onnxruntime==1.31.1 onnxruntime-qnn==2.5.0
```

onnxruntime-qnn 2.x is a plugin execution provider. The harness registers it and selects the HTP device itself, so there is no `providers=["QNNExecutionProvider"]` line to write. The plugin must match the QAIRT runtime that the board's image ships:
- onnxruntime-qnn 2.5.0 (QNN 2.49) matches the image's QAIRT 2.49;
- 2.7.0 (QNN 2.51) fails with `INCOMPATIBLE_BINARIES`.

The harness uses the system HTP backend, `/usr/lib/libQnnHtp.so`, when it exists. `QNN_BACKEND` overrides it.

### Power source

The model needs the power the battery supplies to the compute, so the harness reads the **total input rail**, not a CPU or GPU rail, and records idle alongside rather than subtracting it.

| Board | `--power` | What it reads |
|---|---|---|
| Jetson Orin | `jetson` | INA3221 `VDD_IN`: the module input. It excludes the carrier board. Every other rail is recorded as well. |
| Ventuno Q | `file:<hwmon>/power1_input:1e-6` | INA232 `power1_input`, in µW: the 20 V board input, including the fan, the regulators and the peripherals |
| Intel | `rapl` | the CPU package only (root-only), so it can't stand in for board power |
| any | `none`, then `to_compute.py --power-csv` | an external logger at the battery feed |

The Ventuno's monitor is found by name, since hwmon numbering isn't stable:

```sh
PWR=$(dirname $(grep -l "^ina232$" /sys/class/hwmon/*/name))/power1_input
```

The two boards' rails differ in scope: the Jetson's idles at 5.3 W, the Ventuno's at 8.5 W. Their power numbers can't be compared until both are measured at the same point, with an external logger at the battery feed.

### Smoke run

A 10 s run checks the environment, the accelerator and the power path before a 30-minute set:

```sh
~/drone-bench-qnn-venv/bin/python bench/run.py --pipeline racing --target smoke --provider qnn \
    --duration 10 --warmup 3 --idle 0 --out /tmp/smoke.json
```

What to look for:
- the detector's stage time is the accelerator's, not the CPU's (2.9 ms on the Ventuno NPU, against 36 ms on its CPU);
- nothing is dropped;
- the result's `platform.thread_env` shows BLAS at one thread.

## 4. Name the target

The target name is the key that `compute.json`, `to_compute.py` and the results page use. It names everything that changes the numbers and isn't otherwise in the result:

```text
<board>-<power mode>[-<clock policy>]-<set>
orin-nano-super-25w-cpu          default DVFS governor, CPU only
orin-nano-super-25w-gpu          default DVFS governor, TensorRT detector and VPI stereo
orin-nano-super-25w-maxclk-gpu   jetson_clocks, the same accelerators
ventuno-q-cpu, ventuno-q-npu
```

Clock policy belongs in the name. On the Orin Nano, the GPU's p99 for racing is 13.5 ms under the default governor and 7.0 ms with `jetson_clocks`, so a `compute.json` entry has to say which one the drone will fly with. Before a `maxclk` set, check that the clocks are pinned. `jetson_clocks` exits without error even when a later restore undid it:

```sh
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_{min,cur,max}_freq       # all three equal
cat /sys/class/devfreq/17000000.gpu/{min,cur,max}_freq                     # all three equal
```

## 5. Run a set

A set is six runs: each pipeline alone, then each with the other two as concurrent load. The plan asks for latency under load, and the loaded runs are the ones the mission model should use. Each run:
1. builds the pipeline;
2. measures idle power (`--idle 10`);
3. starts the background loads;
4. soaks untimed until the module is warm (`--soak 60`);
5. warms up (`--warmup 5`);
6. measures for `--duration 60`.

That comes to about 2.5 minutes per run, so the two sets of a target take about 30 minutes.

The script run on the Ventuno, both sets in one environment:

```sh
#!/bin/bash
cd ~/drone-bench
PY=~/drone-bench-qnn-venv/bin/python
export QNN_BACKEND=/usr/lib/libQnnHtp.so
PWR=$(dirname $(grep -l "^ina232$" /sys/class/hwmon/*/name))/power1_input
COMMON="--power file:$PWR:1e-6 --duration 60 --warmup 5 --soak 60 --idle 10"
BASE="Arduino Ventuno Q (Qualcomm Monaco), open air, stock fan; power = INA232 board input rail (20 V), includes fan and peripherals"
for set in cpu npu; do
  if [ $set = cpu ]; then PROV=cpu; DESC="CPU only (onnxruntime CPU provider)"
  else PROV=qnn; DESC="detector on HTP NPU (onnxruntime-qnn, FP16), stereo on CPU (SGBM)"; fi
  for p in racing scout inspection; do
    $PY bench/run.py --pipeline $p --target ventuno-q-$set --provider $PROV $COMMON --notes "$BASE; $DESC; no background load"
  done
  for p in racing scout inspection; do
    bg=""; for q in racing scout inspection; do [ $q != $p ] && bg="$bg --background $q"; done
    $PY bench/run.py --pipeline $p --target ventuno-q-$set --provider $PROV $COMMON $bg --notes "$BASE; $DESC; other two pipelines as background load"
  done
done
echo ALL-DONE
```

The Jetson's script has the same shape:
- each set gets `--power jetson` and a `--provider` and `--stereo` pair: `cpu` and `sgbm`, then `tensorrt` and `vpi-cuda`;
- the notes name the JetPack, the power mode and the environment;
- the `maxclk` variant changes only the target names and the notes.

`--notes` records what the result can't detect: the enclosure, the cooling, the clock policy and the power rail's scope. The script runs detached, and its log is followed from the host:

```sh
ssh stillwater@<host> 'nohup ~/drone-bench/run_matched.sh > ~/drone-bench/matched.log 2>&1 &'
ssh stillwater@<host> 'tail -f ~/drone-bench/matched.log' | grep -E --line-buffered "^(racing|scout|inspection) on|latency p50|power .* mean|Traceback|Error|ALL-DONE"
```

The filter includes `Traceback` and `Error`, so that a crash shows up in the log rather than looking like a long run.

## 6. Collect and publish

```sh
rsync -a stillwater@<host>:drone-bench/bench/results/<target> bench/results/
python3 bench/summarize.py bench/results/<target>      # one table, to read the set
python3 bench/summarize.py --page                      # regenerate docs/benchmarks/results.md
python3 -m unittest discover -s bench                  # fails if results.md is stale
```

Before writing anything up, read the set for confounds:
- an accelerated set slower somewhere it shouldn't be, which points to the environment, not the accelerator;
- a pipeline better under load than alone, which points to DVFS;
- a CPU stage that changed between the two sets.

Each of these showed up in the run of November 2026, and each had a cause outside the hardware (see [pitfalls](#pitfalls-found-on-the-first-targets)).

Then, in one PR:
- the results, under `bench/results/<target>/`;
- the regenerated results page;
- the findings and the summary tables in the [plan's Phase 2 section](optimal-speed.md#phase-2-results-first-two-targets);
- a new pitfall or placeholder, added to [#8](https://github.com/branes-ai/drone-capability/issues/8).

The PR references the plan's issue (`Refs #4`). On merge, this site redeploys.

## 7. Into the mission model

A target enters `models/data/compute.json` once three things exist:

1. **A weighed mass.** Copy [`bench/data/mass/TEMPLATE.json`](../../bench/data/mass/TEMPLATE.json) and weigh every item: the module, the carrier, the cooling and the cabling. `to_compute.py` refuses an item marked `"weighed": false`. Datasheet module masses leave out the carrier and the heatsink, and mass is the channel the model is most sensitive to.
2. **The latency outside the harness:** exposure, readout, the ISP and transport to the flight controller, measured per camera and link.
3. **Results that keep up.** A result that drops more than 1% of frames is rejected, because that pipeline doesn't run at mission rate on that target.

```sh
python3 bench/to_compute.py --target orin-nano-super-25w-gpu \
    --mass bench/data/mass/orin-nano-super-25w-gpu.json \
    --latency-extra-ms 15 bench/results/orin-nano-super-25w-gpu/*.json --write
```

For each pipeline, it writes:
- `latency_by_pipeline_s`: the p99 latency plus the extra;
- `p_compute_by_pipeline_w`: the mean total-rail power, or the external logger's CSV with `--power-csv`.

The option-wide `latency_s` and `p_compute` become the worst case over the pipelines. Each mission in `missions.json` names its pipeline, and the model uses that pipeline's numbers. After `--write`, run the model tests and the three model scripts, and update the plan's estimate tables (see [`CLAUDE.md`](../../CLAUDE.md)).

As of November 2026, no target has reached this step: the masses aren't weighed, and the latency outside the harness isn't measured.

## Pitfalls found on the first targets

Each of these changed a number by 2× or more before it was found. The harness now guards against the first three. The rest are checks to make on every new target.

| Pitfall | Symptom | Fix or check |
|---|---|---|
| Multithreaded BLAS | Detector at 75 ms in the pipeline against 30 ms alone (Jetson, system OpenBLAS): idle BLAS threads spin on the cores onnxruntime needs | `run.py` defaults `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and `MKL_NUM_THREADS` to 1 before numpy loads. Check `platform.thread_env`. |
| CUDA in a forked child | Background loads fail with `cudaErrorInitializationError` (VPI) or "CUDA initialization failure" (TensorRT) | Background processes use the `spawn` start method |
| ctypes without argtypes | TensorRT run segfaults: 64-bit device pointers truncated to 32 bits | `argtypes` and `restype` declared for every libcudart call |
| OpenCV build | KLT 6× slower in one set (system OpenCV 4.8 with TBB against pip OpenCV 5.0) | Run both sets in one environment, and compare `platform.opencv` |
| DVFS | GPU racing p99 13.5 ms under the governor, against 7.0 ms pinned. Scouting is better under load than alone | Name the clock policy in the target, and measure the policy that will fly |
| Power-rail scope | Ventuno idles at 8.5 W (board input), Jetson at 5.3 W (module input) | Don't compare across boards; measure at the battery feed for `compute.json` |
| NPU device access | `DEVICE_ERROR_INVALID_CONFIG` at QNN device creation | The user must be in `fastrpc` |
| QAIRT version mismatch | `INCOMPATIBLE_BINARIES` | Match onnxruntime-qnn to the image's QAIRT, and use the system `libQnnHtp.so` |
| Thermal state | Short, cold runs understate latency and power | `--soak`. These runs used 60 s in open air; a sealed airframe needs longer, in its enclosure. |
| `pkill -f bench/run.py` over SSH | Kills the SSH shell that runs it, whose own command line matches | Match with `pgrep -f "[b]ench/run.py"`, or kill by PID |

The open items are tracked in [#8](https://github.com/branes-ai/drone-capability/issues/8), under "Phase 2 harness" and "Found on the first targets".

## The run of November 2026

| Board | Sets | Runs | Environment |
|---|---|---|---|
| Jetson Orin Nano Super, 25 W | CPU and GPU, under the default DVFS governor and with `jetson_clocks` | 24 | `~/drone-bench-sys-venv` |
| Arduino Ventuno Q | CPU and NPU | 12 | `~/drone-bench-qnn-venv` |
| Desktop i7-12700K | CPU, a harness check only (not a flight target, no power reading) | 3 | development host |

The results are on the [results page](results.md), and what they say about each target is in the [plan](optimal-speed.md#phase-2-results-first-two-targets):
- CPU-only companions don't carry the racing pipeline.
- An accelerator also frees the CPU for the pipelines that don't use it.
- Scouting needs a stereo engine.
- DVFS is part of the target.
