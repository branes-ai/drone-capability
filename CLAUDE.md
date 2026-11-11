# drone-capability

Benchmarks that map drone algorithms and flight-computer hardware to mission capability. See [README.md](README.md) for the design, and [docs/benchmarks/](docs/benchmarks/) for the benchmark plans.

## Layout

- `docs/benchmarks/`: benchmark plans. Figures go in `docs/benchmarks/img/`, as a light and a dark PNG embedded with a `<picture>` element.
- `docs-site/`: the docs site, generated from `docs/` by [docs-kit](https://github.com/branes-ai/docs-kit) and published at <https://branes-ai.github.io/drone-capability/> on every merge to main. Edit `docs/`, never the generated content. A new document goes in the map, `docs/README.md`. The PR check (`.github/workflows/docs-site.yml`) fails on a broken relative link or anchor; check locally with `npm run build && npm run check` in `docs-site/` (Node 22). `scripts/html-figures.mjs` copies the `<picture>` images, which docs-kit doesn't handle.
- `models/`: Python capability models. Run them from the repo root:
  - `python3 models/pen_and_paper.py`: reproduces the Bauersfeld & Scaramuzza Mavic 3 example
  - `python3 models/compute_scenarios.py`: prints the estimate tables in `docs/benchmarks/optimal-speed.md`
  - `python3 models/plot_figures.py`: regenerates the figures in `docs/benchmarks/img/` (needs matplotlib)

  - `python3 models/estimate.py`: Phase 1 mission-capability estimator; inputs are in `models/data/` (airframes, compute options, missions)
  - `python3 -m unittest discover -s models`: regression tests (Phase 0 paper reproduction, Phase 1 model)

  The models need numpy and scipy; the figures also need matplotlib.

  When a model changes, run the tests, rerun the three scripts, and update the plan's tables and figures to match.

  Placeholder inputs and modelling pitfalls are tracked in [#8](https://github.com/branes-ai/drone-capability/issues/8). Check it before trusting a new estimator result. When a change replaces a placeholder or adds one, update #8 in the same PR.
- `bench/`: Phase 2 measurement harness (stand-in L1 pipelines, power sampling, results to `compute.json`). Results go in `bench/results/<target>/`, weighed masses in `bench/data/mass/`.
  - `python3 bench/make_detector.py`: generates the stand-in detector in `bench/assets/` (needs torch; the ONNX files are gitignored, copy them to targets)
  - `python3 bench/run.py --pipeline racing --target <name> --power jetson`: one measurement run
  - `python3 bench/to_compute.py --target <name> --mass ... results...`: a `compute.json` entry from results and weighed mass
  - `python3 bench/summarize.py bench/results/<target>...`: the markdown results table for the plan
  - `python3 bench/summarize.py --page`: regenerates `docs/benchmarks/results.md` from `bench/results/`; commit it with new results (a bench test fails when it is stale)
  - `python3 -m unittest discover -s bench`: harness tests

  How a target is measured, end to end, is in [docs/benchmarks/workflow.md](docs/benchmarks/workflow.md).

  Bench code runs on the targets, so keep it Python 3.6 compatible (no dataclasses, walrus, or `perf_counter_ns`) and limited to numpy and OpenCV, with onnxruntime optional.
- Papers are kept outside the repo, in `../research/`. Cite them by arXiv link; don't commit PDFs.

## Git workflow

- Work on a branch, open a PR, and merge with `gh pr merge --squash --delete-branch`.
- **Never rebase-merge** (`--rebase`). GitHub stamps the merging account's primary email (`theo@stillwater-sc.com`) as the committer on rebased commits. Squash merges keep the `theodore.omtzigt@branes.ai` author, with GitHub as the committer.
- Before pushing, check the author emails: `git log --format='%h %ae | %ce' origin/main..HEAD` should show `theodore.omtzigt@branes.ai` as the author.
- Reference the tracking issue in commits and PRs: `Refs #N` for partial work, `Closes #N` only when the issue is done.
