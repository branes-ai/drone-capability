"""Power and temperature sampling for the Phase 2 harness.

Backends, chosen with --power:

- jetson   on-module INA3221 monitors. Orin (JetPack 5/6) exposes hwmon files
           in*_label / in*_input [mV] / curr*_input [mA]; the original Nano
           (JetPack 4) exposes iio files rail_name_N / in_power N_input [mW].
           The 'total' is the module input rail (VDD_IN, POM_5V_IN, or
           VIN_SYS_5V0 on AGX Orin); every rail is recorded.
- rapl     Intel RAPL package energy counter. CPU package only, not the board;
           the counter is usually root-readable only.
- file:PATH[:SCALE]
           any sysfs file that reports power; SCALE converts to W (default
           1e-6, for microwatts). For boards with no on-board monitor, such as
           most Qualcomm Dragonwing kits, use an external USB or shunt logger
           and merge its CSV with bench/to_compute.py --power-csv instead.
- none     no power sampling.

The compute power the model needs is the power the battery supplies to the
compute module, so it is the total input rail, not a CPU or GPU rail, and
not the increase over idle (idle is recorded alongside, for reference).
"""

import glob
import os
import threading
import time


def _read(path):
    with open(path) as f:
        return f.read().strip()


class Backend(object):
    name = "none"
    total_rail = None

    def read(self):
        """Return (total power [W] or None, {rail: W})."""
        return None, {}


class FileBackend(Backend):
    def __init__(self, path, scale=1e-6):
        self.name, self.path, self.scale = "file", path, scale
        self.total_rail = os.path.basename(path)

    def read(self):
        w = float(_read(self.path)) * self.scale
        return w, {self.total_rail: w}


class RaplBackend(Backend):
    """Differentiates the package energy counter between reads."""

    name, total_rail = "rapl", "package-0"

    def __init__(self, root="/sys/class/powercap/intel-rapl:0"):
        self.energy = os.path.join(root, "energy_uj")
        self.wrap = float(_read(os.path.join(root, "max_energy_range_uj")))
        self.last = None
        _read(self.energy)  # fail now, not in the sampling thread, if unreadable

    def read(self):
        e, t = float(_read(self.energy)), time.perf_counter()
        last, self.last = self.last, (e, t)
        if last is None or t <= last[1]:
            return None, {}
        de = e - last[0]
        if de < 0:
            de += self.wrap
        w = de * 1e-6 / (t - last[1])
        return w, {self.total_rail: w}


TOTAL_RAILS = ("VDD_IN", "POM_5V_IN", "VIN_SYS_5V0", "VIN")


class JetsonBackend(Backend):
    name = "jetson"

    def __init__(self, root="/sys/bus/i2c/drivers"):
        self.rails = []  # (label, reader)
        for hw in sorted(glob.glob(os.path.join(root, "ina3221", "*", "hwmon", "hwmon*"))):
            for lab in sorted(glob.glob(os.path.join(hw, "in*_label"))):
                ch = os.path.basename(lab)[2:-6]
                label = _read(lab)
                v, i = os.path.join(hw, "in%s_input" % ch), os.path.join(hw, "curr%s_input" % ch)
                if label.lower().startswith("sum of") or not os.path.exists(i):
                    continue
                self.rails.append((label, (lambda v=v, i=i: float(_read(v)) * float(_read(i)) * 1e-6)))
        for dev in sorted(glob.glob(os.path.join(root, "ina3221x", "*", "iio:device*"))):
            for name in sorted(glob.glob(os.path.join(dev, "rail_name_*"))):
                ch = name.rsplit("_", 1)[1]
                p = os.path.join(dev, "in_power%s_input" % ch)
                self.rails.append((_read(name), (lambda p=p: float(_read(p)) * 1e-3)))
        if not self.rails:
            raise RuntimeError("no INA3221 rails found under %s" % root)
        labels = [l for l, _ in self.rails]
        self.total_rail = next((r for r in TOTAL_RAILS if r in labels), None)

    def read(self):
        rails = {label: f() for label, f in self.rails}
        total = rails[self.total_rail] if self.total_rail else sum(rails.values())
        return total, rails


def backend(spec):
    if spec in (None, "none"):
        return Backend()
    if spec == "jetson":
        return JetsonBackend()
    if spec == "rapl":
        return RaplBackend()
    if spec.startswith("file:"):
        parts = spec[5:].split(":")
        return FileBackend(parts[0], float(parts[1]) if len(parts) > 1 else 1e-6)
    raise ValueError("unknown power backend %r (jetson, rapl, file:PATH[:SCALE], none)" % spec)


def temperatures():
    """{thermal zone type: degC} for every readable thermal zone."""
    out = {}
    for z in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
        try:
            name = _read(os.path.join(z, "type"))
            out[name if name not in out else "%s.%s" % (name, os.path.basename(z))] = \
                float(_read(os.path.join(z, "temp"))) / 1000.0
        except Exception:
            # Best effort: some zones (e.g. on Jetson) fail to read mid-call with
            # driver-specific errors; a missing temperature must not end a run.
            pass
    return out


class Sampler(object):
    """Samples a backend at a fixed rate in a background thread."""

    def __init__(self, be, rate_hz=50.0):
        self.be, self.period = be, 1.0 / rate_hz
        self.samples = []  # (t [s], total W, {rail: W})
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self.samples, self._stop = [], threading.Event()
        self._thread = threading.Thread(target=self._loop)
        self._thread.daemon = True
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join()
        return self

    def _loop(self):
        t_next = time.perf_counter()
        while not self._stop.is_set():
            total, rails = self.be.read()
            if total is not None:
                self.samples.append((time.perf_counter(), total, rails))
            t_next += self.period
            self._stop.wait(max(0.0, t_next - time.perf_counter()))

    def summary(self, trace_points=200):
        if not self.samples:
            return None
        ws = [s[1] for s in self.samples]
        rails = {}
        for _, _, r in self.samples:
            for k, v in r.items():
                rails.setdefault(k, []).append(v)
        step = max(1, len(self.samples) // trace_points)
        t0 = self.samples[0][0]
        return {
            "backend": self.be.name, "total_rail": self.be.total_rail,
            "n": len(ws), "mean_w": sum(ws) / len(ws), "max_w": max(ws), "min_w": min(ws),
            "rails_mean_w": {k: sum(v) / len(v) for k, v in rails.items()},
            "trace": [[round(t - t0, 3), round(w, 3)] for t, w, _ in self.samples[::step]],
        }


def measure_idle(be, seconds, rate_hz=50.0):
    """Mean power over an idle window, or None without a backend."""
    if be.name == "none" or seconds <= 0:
        return None
    s = Sampler(be, rate_hz).start()
    time.sleep(seconds)
    return s.stop().summary(trace_points=20)
