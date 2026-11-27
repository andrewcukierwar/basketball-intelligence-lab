# Disjoint K0 agreement and lineup support

[Issue #137](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/137) · [PR #154](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/154) · `codex/137-k0-support`

The registered experiment separated candidate fitting, K0 analogue fitting, repeat estimates and held-out outcome scoring by game. Independent review confirmed the schedule, sign and support logic. Before the run, it prompted immediate prediction hashing and identical per-season and pooled coverage slices. The focused re-review checked `52bf617`, which has the same tree as the remote preregistered `cdac679`.

`bil.models.k0_support` completed the clean pinned run in 6.18 s. All prediction digests matched the final manifest and all 199,434 held-out possession keys were unique within season. The 64,000 ridge had the lowest proxy and repeat rating RMSE, while the 4,000 ridge had the lowest lineup outcome loss. There were zero supported individual contrasts. Reported coverage and limits without expanding the cohort after scoring. [Results](../research/k0-player-support.md)

Ruff lint and formatting, strict mypy, `git diff --check` and 35 focused synthetic tests passed. Private output files were copied to `data/processed/rapm_targets/issue-137-v1` and verified against their manifest. The historical K0, SPM and EI artifacts retain their existing decisions.
