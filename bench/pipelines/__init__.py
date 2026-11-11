"""L1 stand-in pipelines, one per form factor. Each module exposes build(provider, threads, **opts) -> Pipeline.

Options: stereo ('sgbm' on the CPU, or 'vpi-cuda' on a Jetson GPU) for the scouting pipeline.
"""

import importlib

NAMES = ("racing", "scout", "inspection")


def build(name, provider="auto", threads=0, **opts):
    if name not in NAMES:
        raise ValueError("unknown pipeline %r; choose from %s" % (name, ", ".join(NAMES)))
    return importlib.import_module("pipelines." + name).build(provider, threads, **opts)
