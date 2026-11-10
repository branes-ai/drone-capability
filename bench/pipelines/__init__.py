"""L1 stand-in pipelines, one per form factor. Each module exposes build(provider, threads) -> Pipeline."""

import importlib

NAMES = ("racing", "scout", "inspection")


def build(name, provider="auto", threads=0):
    if name not in NAMES:
        raise ValueError("unknown pipeline %r; choose from %s" % (name, ", ".join(NAMES)))
    return importlib.import_module("pipelines." + name).build(provider, threads)
