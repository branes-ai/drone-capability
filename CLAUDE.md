# drone-capability

Benchmarks that map drone algorithms and flight-computer hardware to mission capability. See [README.md](README.md) for the design, and [docs/benchmarks/](docs/benchmarks/) for the benchmark plans.

## Layout

- `docs/benchmarks/`: benchmark plans. Figures go in `docs/benchmarks/img/`, as a light and a dark PNG embedded with a `<picture>` element.
- `models/`: Python capability models. Run them from the repo root:
  - `python3 models/pen_and_paper.py`: reproduces the Bauersfeld & Scaramuzza Mavic 3 example
  - `python3 models/compute_scenarios.py`: prints the estimate tables in `docs/benchmarks/optimal-speed.md`
  - `python3 models/plot_figures.py`: regenerates the figures in `docs/benchmarks/img/` (needs matplotlib)

  - `python3 models/estimate.py`: Phase 1 mission-capability estimator; inputs are in `models/data/` (airframes, compute options, missions)
  - `python3 -m unittest discover -s models`: regression tests (Phase 0 paper reproduction, Phase 1 model)

  The models need numpy and scipy; the figures also need matplotlib.

  When a model changes, run the tests, rerun the three scripts, and update the plan's tables and figures to match.

  Placeholder inputs and modelling pitfalls are tracked in [#8](https://github.com/branes-ai/drone-capability/issues/8). Check it before trusting a new estimator result. When a change replaces a placeholder or adds one, update #8 in the same PR.
- Papers are kept outside the repo, in `../research/`. Cite them by arXiv link; don't commit PDFs.

## Git workflow

- Work on a branch, open a PR, and merge with `gh pr merge --squash --delete-branch`.
- **Never rebase-merge** (`--rebase`). GitHub stamps the merging account's primary email (`theo@stillwater-sc.com`) as the committer on rebased commits. Squash merges keep the `theodore.omtzigt@branes.ai` author, with GitHub as the committer.
- Before pushing, check the author emails: `git log --format='%h %ae | %ce' origin/main..HEAD` should show `theodore.omtzigt@branes.ai` as the author.
- Reference the tracking issue in commits and PRs: `Refs #N` for partial work, `Closes #N` only when the issue is done.
