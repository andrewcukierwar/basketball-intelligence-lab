# Issue 22 executable historical evaluation checks

- **Date** 2026-11-23
- **Branch** `codex/issue-22-evaluation-checks` from `d3d01f3`
- **Issue** [#22](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/22)

The local validator implements the row-level checks needed to replay historical forecast manifests and verify a linked score. It resolves revisions before checking observed times and maturity, keeps late or unknown archive revisions visible as limitations in retrospective evidence, and checks learned parent cutoffs and per-example forward features and parent predictions. A pinned scoring view can revise a mature label and recompute scalar metrics under a new score run using the same forecast and prediction bytes.

The existing synthetic manifest pair now references executable evidence artifacts. Tests cover Eastern midnight and DST, exact cutoff and retraction behavior, unavailable revisions, transitive fit times and cycles, future-row perturbation before a cached transform, per-example calibration and feature cutoffs, mature scoring outcomes and exact-byte tampering. Independent review identified unvalidated prediction values for targets without outcomes and stale daily matches for moved games. Regression tests cover both paths. The data and forecasts are synthetic. Local validation checks cited evidence and score arithmetic. Independent verification of publication provenance and prospective receipts belongs to later workflows.

| Check | Result |
| --- | --- |
| `PYTHONPATH=src python -m bil.evaluation tests/fixtures/evaluation/synthetic_forecast.json --score tests/fixtures/evaluation/synthetic_score.json` | Verified the frozen forecast and recomputed one result. Candidate margin MAE was 4 points and paired delta was −1 point, with one of two expected targets scored. |
| `PYTHONPATH=src python -m pytest -q` | 63 passed. |
| `ruff check .`, `ruff format --check .`, `python -m mypy src`, `git diff --check` | Passed. |

The first run uses unweighted scalar scoring and one scored origin per target key. The first real historical model can use the same checks after it emits vetted row-level proofs and immutable output artifacts. The fixtures supply cohort membership, label closure and declared fit references. Production evidence needs dated schedule inputs, horizon starts where applicable, and separately verified fit artifact contents. Focused independent re-review of `34b953e` reproduced both original failures against the fixes, recomputed the unchanged baseline score, and passed all 20 evaluation tests. No blockers remain.
