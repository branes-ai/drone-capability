# Documentation map

These documents are published at <https://branes-ai.github.io/drone-capability/>. The site is generated from this folder on every merge to main: edit the documents here, never the site. [`index.mdx`](index.mdx) is the site's landing page, and this file is its documentation map.

| Folder | Contents |
|---|---|
| [getting-started/](getting-started/introduction.md) | [Introduction](getting-started/introduction.md): what the repo measures, its layout, and how to run the models and the harness |
| [benchmarks/](benchmarks/optimal-speed.md) | [Optimal speed](benchmarks/optimal-speed.md), the benchmark plan and its results by phase; the [benchmarking workflow](benchmarks/workflow.md), how a target is measured; the [Phase 2 results](benchmarks/results.md), every measurement (generated from `bench/results/`); [Arduino board characterization](benchmarks/arduino-board-characterization.md), a proposed task |
| sessions/ | Dated session records (`YYYY-MM-DD-short-topic.md`), not published |

A plan (`plan/`) or an architecture decision (`adr/`) is published on the [architecture site](https://branes-ai.github.io/architecture/), alongside every other repo's plans and decisions and their status, rather than here. The benchmark plans in `benchmarks/` are this repo's own documents, and are published here.

Placeholder inputs and modelling pitfalls are tracked in [#8](https://github.com/branes-ai/drone-capability/issues/8), and the optimal-speed plan in [#4](https://github.com/branes-ai/drone-capability/issues/4).
