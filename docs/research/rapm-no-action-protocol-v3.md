# Row-set variants: frozen addendum protocol v3 (2022–23)

**Status:** Frozen before the cohort comparison below ([issue #82](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/82)). **Classification:** Original BIL design. It supersedes the [v2 addendum](rapm-no-action-protocol-v2.md), which registered period-end exclusion as canonical, and keeps the [v1 addendum](rapm-no-action-protocol.md) for variant `no_action`. Results go in [the report](rapm-no-action-2022-23.md). A change here after the run starts is a deviation and is listed there.

## Decision and why v2 was withdrawn

The maintainer's principle ([ADR-0019](../DECISIONS.md)) is to exclude only verified pseudo-possessions with no live-ball opportunity, to keep run-outs, and never to condition eligibility on later actions or outcomes. The v2 audit checked that a `period_end` first event had no later action and zero duration across the possession's own events. Independent review showed that this does not establish the condition, because the possession's own events span no time by construction. The corrected audit (`scripts/audit_period_end_possessions.py`) measures the clock when each possession begins:

- All 962 accepted possessions that start with `period_end` begin after a change of control (312 defensive rebounds, 297 made shots, 260 turnovers and 93 final free throws) with 3 to 24 s on the clock. 729 are in the final period. These are run-outs.
- The pilot already marks the genuine pseudo-possessions `excluded`: 1,567 `period_end` starts, every one with under 3 s left, plus 1 unresolved.

So **canonical = the pilot-eligible set**: every accepted stable-lineup possession, with no further exclusion. The canonical model rows are byte-identical to `issue-59-v1`, and the registered #23 baseline and #24 context results stand unchanged. They are not rerun.

| Variant | Rule | Role |
| --- | --- | --- |
| `canonical` | Keep all accepted stable-lineup possessions (`issue-59-v1` rows) | Canonical |
| `period_end_start` | Also drop accepted possessions whose first event is `period_end` (962; the former variant B) | Sensitivity |
| `no_action` | Also drop accepted possessions with no shot, free throw, turnover, foul or violation event (1,039; the former variant A) | Sensitivity |

Eligible sets are nested: `no_action` within `period_end_start` within `canonical`. The runner checks this.

## Frozen inputs

| Variant | Row set | Rows | Manifest SHA-256 | `model_row.parquet` SHA-256 |
| --- | --- | ---: | --- | --- |
| `canonical` | `issue-82-canonical-v1` | 224,039 | `bd25cd0a8fe3702f5ae9021a435571224a3022c036d529f80b6e8ce108b56488` | `ebadd15122df870cdfd40e43b04d381bbb6f7058e014c4c26802d8c93b58ad90` (same as `issue-59-v1`) |
| `period_end_start` | `issue-82-period-end-start-v1` | 223,077 | `fec1d8401f9864b824f37e79c08a3906e6f56e50c5b2371da74db35af461f1f4` | `cf1236b71aedf51513414bf3d7c57ac8a3b69978f0c989276ad1f9a312702a86` (same as `issue-82-B-v1`) |
| `no_action` | `issue-82-noaction-v1` | 223,036 | `3415ef5c859666fad5a05fe85ddfafd07152287885066733a9ee87b963ffdecd` | `ce19cf3d47e92d4cf68371b779876b6278d1fa56e4dc2f39e72666978d6979a3` (same as `issue-82-v1`) |

All three were built at `0c6d111a6f26843b85dba09a40041fa05978de9d` from pilot `issue-19-v6` (manifest SHA-256 `89cb2e82…1570`). Evidence tier `retrospective_capture_bound`. Scope is 2022–23 only. No 2023–24 or later data and no EPM output is read.

## Run

Only the cohort comparison is run: `bil.models.rapm.cohort_comparison` to `issue-82-cohort-v2`. Each variant's zero-context RAPM (the #23 estimator, $\lambda$ = 4,000, folds R1 to R4, bootstrap seed 2023 with 2,000 game-clustered resamples) is fit on that variant's own rows at each fold. The league baseline is the fit-window mean of the same rows.

- **Primary:** every canonical held-out row in R1–R4, scored by all three fits. Reported: RAPM and league MSE and RAPM minus league per variant, and paired RAPM MSE differences `period_end_start − canonical`, `no_action − canonical` and `no_action − period_end_start`, with intervals.
- **Secondary:** held-out rows eligible under `no_action`.
- **Tertiary:** each variant's own held-out cohort. MSE levels are not comparable across cohorts.

The earlier variant results (`issue-82-baseline-v1`, `issue-82-context-v1`, `issue-82-B-baseline-v1`, `issue-82-B-context-v1`) are kept and labelled sensitivity evidence. The comparison does not choose a rule, and the run starts from a clean tree.
