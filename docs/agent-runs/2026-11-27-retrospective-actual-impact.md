# Retrospective Actual impact

[Issue #41](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/41) · [PR #155](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/155) · `codex/41-actual-impact`

Scoped the optional Actual-impact issue to the existing #36 cohort. Registered two phases, freezing the October 1 anchors before whole-game retrospective fitting and scoring regular season and playoffs separately. Independent review confirmed the cutoff, cold priors, fit/outcome separation, weights and verdict before the data run. The chosen cohort is already examined and the outcome is a game-held-out retrospective diagnostic.

Clean local `7689af7`, with the same tree as the remote preregistration `c43f53b`, completed the pinned run in 9.27 s. The archived preseason values reproduced within `5e-7`. All six private artifact digests matched the manifest after copying to `data/processed/expected_impact/issue-41-v1`. The primary playoff delta was +4.686 [−1.466, +10.579], inconclusive. [Results](../research/actual-impact.md)

The held-out game regression changed every response in one assigned fold and reproduced that fold's predictions exactly. Ruff, strict mypy, `git diff --check` and 19 focused tests passed. No rating candidate was promoted to the pregame pipeline.
