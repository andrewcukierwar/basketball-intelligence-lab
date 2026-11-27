# V2-free event path: validation result

**Protocol:** [v3-event-path-protocol.md](v3-event-path-protocol.md), registered at commit `8da7a7e` (file SHA-256 `d4cb2d63…c453`). This run used that commit with a clean tracked tree and no deviations.
**Issue:** [#133](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/133).
**Classification:** Development validation of a data-pipeline component (Inferred). The 2025–26 holdout was not read.

## Verdict: fail

`scripts/v3_event_verdict.py`:

| Season | L1 | L2 | L3 | L4 | L5 | L6 | L7 (both seasons) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2023–24 | pass | **fail** | **fail** | pass | pass | pass | pass |
| 2024–25 | pass | **fail** | **fail** | pass | pass | pass | pass |

Under §5 the path is **not adopted**. The adapter is not changed on 2023–24 or 2024–25, and #42 stays blocked.

## What failed

- **Game coverage.**
  - 2023–24: the V3 build accepts 1,146 of 1,230 regular-season games (93.2%, floor 97%). V2 accepts 1,218, and 77 games are accepted by V2 only.
  - 2024–25: the V3 build accepts 1,181 regular-season games (96.0%). V2 accepts 1,205, and 24 games are accepted by V2 only.
  - Playoffs: V3 matches V2 in both seasons (81 / 81 and 84 / 84).
- **Cause.** Nearly all the lost games are quarantined as `v3_unmapped_action`: a V3 `(actionType, subType)` pair missing from the type table learned on 2020–23.

| Unmapped pair | 2023–24 games | 2024–25 games |
| --- | ---: | ---: |
| `('Foul', 'Flopping')` | 74 | 17 |
| `('Foul', 'Bench')` | 1 | 3 |
| `('Turnover', '10 Second Violaton')` | 1 | 1 |
| `('Foul', '')` | 0 | 1 |

- **Flopping** is a technical-foul category the NBA introduced in 2023–24 (Documented league rule change). It never occurs in the development seasons. This is the residual risk the protocol named: a new action type that the frozen table cannot map.
- **One game per season** is lost to `v3_substitution_unpaired`.

## What held

In games both builds accept:
- **Checks.** All 26 `check` invariants pass in both seasons.
- **Rows.** Row mismatch is 0.225% and 0.239% (limit 0.5%). The per-game points gap is 0.230% and 0.237% (limit 0.5%).
- **Fields.**
  - Event type, action, period, clock and player 1's team agree on at least 99.999% of events.
  - The lowest player slot is foul player 2: 99.762% and 99.750% (limit 99.0%).
  - Unmatched events are at most 0.0025%.
- **#36 rerun.** The `rapm_context` delta moves by −0.079, from −4.594 to −4.674. Both intervals still exclude 0: game [−5.912, −3.442] and week [−5.780, −3.498]. Every verdict is unchanged.

These figures describe the accepted games only. They do not rescue the result, because the registered verdict requires every limit.

## Exposure created by this run

- **Vocabulary.** The 2023–25 unmapped pairs above are now known. Any later adapter change that maps them would be developed on 2023–25, so those seasons can no longer validate it.
- **Paired seasons.** No V2-paired season with liveData remains unexposed: liveData starts in 2020–21 and V2 ends in 2024–25.

Outputs (private): `data/processed/<season>/issue-133-v1{,-rows,-compare.json,-fields.json}`, `data/processed/quality/issue-133-v1/`, and `data/processed/expected_impact/issue-133-v1-{model-check,verdict}.json`.

## Revision 2: verdict fail (L8)

**Protocol:** [v3-event-path-protocol-r2.md](v3-event-path-protocol-r2.md), registered at commit `807463c` (file SHA-256 `67aa7ab1…7ae9`). This run used that commit with a clean tracked tree and no deviations. Classification: Experimental, because 2023–25 were exposed by the first run.

| Season | L1 | L2 | L3 | L4 | L5 | L6 | L8 | L7 (both seasons) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023–24 | pass | pass | pass | pass | pass | pass | **fail** | pass |
| 2024–25 | pass | pass | pass | pass | pass | pass | **fail** | pass |

Under revision 2's §4 the path is **not adopted**. There is no further revision on 2023–25, and #42 stays blocked.

- **Coverage restored.**
  - 2023–24 regular season: 1,220 of 1,230 games (99.2%) against V2's 1,218, with 3 accepted by V2 only.
  - 2024–25: 1,199 (97.5%) against 1,205, with 6 accepted by V2 only.
  - Remaining rebuild quarantines: `v3_unmapped_action` 1 and 4, which are the unmarked `Bench` and empty-subtype fouls the narrowed fallback refuses. `v3_substitution_unpaired` 1 and 1.
- **Fidelity.**
  - Row mismatch: 0.22% and 0.24%.
  - Per-game points gap: 0.23% and 0.24%.
  - Lowest player slot: 99.76% and 99.75%.
- **#36 rerun.** The `rapm_context` delta moves by +0.060, from −4.594 to −4.534. Both intervals exclude 0, and every verdict is unchanged.
- **Why L8 fails.**
  - **Agreement.** 1 of 80 (2023–24) and 1 of 18 (2024–25) revision-2 events agree with V2 on parser class.
  - **The mismatch.** Every disagreement is a flopping foul. V2 codes it as foul action **32**, a code pbpstats 1.3.11 does not classify, so to the parser it is neither technical nor personal. Revision 2 coded it as a non-unsportsmanlike technical (6, 12).
  - **The rest agree.** The one `10 Second Violaton` turnover agrees in each season.
- **Reading (Inferred).**
  - **What failed.** The documented-rule mapping does not match V2's own coding.
  - **What the other limits show.** The rows are nearly unaffected, by L4, L5 and L7, which suggests that in these games the parser's handling of the two classes rarely differs.
  - **Why the verdict stands.** L8 was registered to test class agreement, not row effects. The verdict is not overridden here.

Outputs (private): `data/processed/<season>/issue-133-v2{,-rows,-compare.json,-fields.json}`, `data/processed/quality/issue-133-v2/` and `data/processed/expected_impact/issue-133-v2-{model-check,verdict}.json`.
