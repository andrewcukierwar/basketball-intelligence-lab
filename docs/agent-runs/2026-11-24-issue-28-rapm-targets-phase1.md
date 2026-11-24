# Agent run: #28 RAPM training targets, phase 1 (protocol and runner)

- **Date:** 2026-11-24
- **Status:** Awaiting independent protocol review. No real-data target was fitted.
- **Related issues:** #28 (this), #30 (consumer), #53, #99 (later seasons enter as new versions)
- **Branch / commit / PR:** `claude/issue-28-rapm-targets`. No PR yet.

## Objective and authorized scope

Freeze a protocol for provisional, independent long-window RAPM training targets for box-score SPM before any real-data fit (ADR-0026). Scope: the ten eligible seasons, a contiguous and an extended reference, rolling origins, separate offense and defense, reliability, cohorts for #30. The label is "partial-history methodology replication" everywhere. Phase 2 (a single run, results, report, PR) waits for the review.

## Work completed

- `docs/research/rapm-targets-protocol.md`: estimand, kernel, objective, in-window CV penalty rule, centring, origins, freezing and versioning, leakage tests, reliability, sensitivities, #30 registration, stopping rule. It reserves ADR-0027 and EXP-0017.
- `src/bil/models/rapm/targets.py`: runner (`python -m bil.models.rapm.targets <processed> <output_dir> --protocol-sha256 <sha>`) and pure functions.
- `src/bil/models/rapm/multiseason.py`: `SeasonPin` gains a `row_set` field (default `issue-93-v1`), and `check_season` and `load_season` take an optional pin mapping. #26 behaviour is unchanged.
- `tests/test_rapm_targets.py`: 27 synthetic tests, including that later rows cannot change a frozen target and that a revised earlier row is detected.

## Key decisions and discoveries

- **Primary label `K365` (Original).** It is a season-centred, two-sided kernel: weight 1 in the target season and `0.5 ** (gap_days / 365)` up to 730 days, where the gap is measured in real days. A missing season is real elapsed time. The window-constant label is only a sensitivity.
- **Joint fit (revision 2).** Context and season-by-season-type levels are unpenalized and fitted jointly with the two-penalty player ridge (`fit_joint`, FWL projection plus LSQR). It agrees with a dense oracle to 5e-10 or better. Revision 1's two-stage offset is kept as a sensitivity.
- **Evaluation label (revision 2).** For #30, the season-only `K0` label at the final origin with its own CV penalties, which replaces revision 1's forward-borrowing label.
- **Penalty choice.** One pair per reference, origin and scenario, by five-fold game-grouped CV inside the origin's eligible rows, using the #26 search.
- **Centring.** Labels are possession-weighted to zero within each target season. The ADR-0012 values are kept as `*_raw`.
- **Origins.** Each origin is the day after the season's last scheduled game, because a 1 July boundary would cut the 2019–20 and 2020–21 playoffs. Origins for gap seasons are unavailable.
- **Data prep.** None was needed. Canonical row sets for 2005–06 to 2007–08 (`issue-97-rows-v1`), 2015–16 (`issue-98-rows-v1`) and 2016–17 (`issue-96-rows-v1`) already existed.
- **Loader smoke check.** All ten seasons verified (2,117,689 rows, 12,640 games, 30 teams). Timing audits are zero and no season contains the repair stratum. The check printed no outcome aggregate.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run pytest -q` (revision 2) | 333 passed, 2 skipped, exit 0 (revision 1: 331 passed) |
| `uv run ruff check .` | Pass |
| `uv run ruff format --check .` | Pass |
| `uv run mypy src` | Pass (strict) |
| Independent review | Not run (arranged by the lead) |

## Blockers and remaining risks

- The runtime of about two to three hours is an estimate. No real fit was timed.
- Open questions are listed in the protocol's §12.
- ADR-0027 and EXP-0017 are reserved but not written. They are written with the phase-2 results.

## Revision 2 (after the independent protocol review)

The independent review of `0195f99` found two blockers. The evaluation label's estimand varied by fold, and the two-stage offset let context terms absorb player composition. Both were fixed before any real-data fit, together with the recommended changes. The protocol's §13 lists them. The checks were rerun after the fix.

## Next actions

1. Independent review of the protocol and runner at the pushed commit.
2. After approval, run phase 2 once from a clean tree into `data/processed/targets/issue-28-v1/`.
3. Write the report, ADR-0027 and EXP-0017, then open the PR.
