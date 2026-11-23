# Historical RAPM rows for the 2022–23 pilot

[Issue #20](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/20) defines the first historical input to the [synthetic RAPM estimator](rapm-synthetic.md). This contract fixes the unweighted zero-prior baseline input. The 2022–23 data, row set and full-season reports stay private under the [pilot source terms](../data-pilot.md). NBA source data are attributed to NBA.com.

## Select the cohort

Pin the pilot manifest, its source snapshot and its manifest-listed table digests. Use its accepted, complete final streams for the 2022–23 regular season and playoffs. Within that snapshot, resolve the game revision through each stream's official game revision. Join possession, stint, lineup and score allocation on both game ID and stream revision. Quarantined games contribute one game disposition and zero modeling rows. Report regular-season and playoff coverage separately, including the overlapping adjudication strata in the pilot's game review.

The pilot has played dates but lacks verified historical publication times and earlier revisions. Carry the game date, stream availability time and basis from the pinned inputs. Use those rows for retrospective chronological analysis. Strict rolling-origin availability at historical game dates is unavailable for this snapshot. Apply the separate [evaluation contract](../validation-strategy.md) before any dated fit.

## Assign one disposition per possession

Use the canonical half-open sequence intervals. Find every same-period stint whose start is before the possession's end and whose end is after its start. Use the sides' actual lineup IDs and verify that their sequence intersections cover the possession once. A change exactly at the end belongs to the following interval. An interior same-clock stint with a nonempty sequence interval is part of the possession even if its elapsed duration is zero. The canonical lineup state at a substitution applies to following events.

| Reason | Rule | Modeling exposure |
| --- | --- | --- |
| `pilot_excluded` | Pilot status is excluded, including parser-excluded period-ending intervals. | 0 |
| `unresolved_control` | Pilot status is unresolved. | 0 |
| `multiple_lineups` | Pilot status is accepted and more than one distinct actual offense/defense lineup pair appears inside the possession. | 0 |
| `eligible` | Pilot status is accepted and one actual lineup pair covers the entire possession. | 1 |

Check the source status first, then the lineup rule. Match the offense and defense IDs to the home and away sides for each eligible row. Each role has five distinct NBA player IDs, and the roles are disjoint. Invalid status, identities, coverage or score links in the accepted input invalidate the build. Retain valid pilot offense relabels under their documented adjudication stratum. A repeated offense already covered by the pilot's retention or flagrant exception follows the same rules.

Use one full opportunity per eligible row and unit base weight. The baseline contains all eligible score states, including late and lopsided games. Leave context weighting, garbage-time filtering and sensitivity analysis to registered modeling comparisons. Report the exposure lost to multiple lineups. This conservative restriction can change the sample mix across teams and game states. It avoids assigning all points to one of several lineups or treating within-possession fragments as independent opportunities.

## Assign points from the score ledger

For a possession, sum its signed `control_possession` allocations. Match the scoring side to the offense before adding points. An eligible possession with no such allocations has zero points. The total must be finite and nonnegative. The solver applies the existing 100× response scale and positive-defense convention.

An official `credited_stint_seq` may differ from the actual lineup for a shot at the same clock. Preserve that link in the source scoring ledger. Use the actual full-possession lineup on the modeling row and the canonical possession assignment for its points. The modeling exposure cannot be inferred from official player plus-minus.

Route every score allocation to exactly one destination.

| Allocation | Destination |
| --- | --- |
| `control_possession` | Linked possession's disposition, including control points on possessions excluded from the model. |
| `unassigned_dead_ball` | Unassigned dead-ball points. This includes technical and flagrant free throws the pilot excludes from control scoring. |
| `unresolved` | Unresolved scoring. This allocation has no verified possession link. |

A live retained-ball sequence can continue within its original possession. Preserve the pilot's possession boundaries and score assignments. A dead-ball or unresolved allocation contributes to score reconciliation with zero modeling points and zero additional exposure.

## Row identity and reconciliation

| Artifact | Grain and required evidence |
| --- | --- |
| Model rows | One per eligible `(game_id, stream_revision, possession_seq)`. Record game revision, played date, season and season type, period and sequence boundaries, offense and defense IDs, sorted player IDs for each role, model points, unit exposure and weight, and stream availability and basis. |
| Possession dispositions | One per canonical possession with the same key, pilot status, final reason, assigned control points and modeling exposure. This covers eligible rows as well as exclusions. |
| Scoring reconciliation | Classify each source `(game_id, stream_revision, seq, scoring_team_id)` once. Retain the linked possession key when present, disposition and signed points. |
| Game reconciliation | One row per expected game, with stream and disposition, season type, adjudication strata and aggregate counts. Preserve the quarantine reason where present. |
| Manifest | Contract revision and code commit; pilot manifest and source snapshot digests; row counts and SHA-256 for each output; unit exposure and retrospective evidence tier; game and season-type coverage plus counts by adjudication stratum. |

Verify these identities for every game before summing across games.

1. Canonical possession count equals eligible plus multiple-lineup plus pilot-excluded plus unresolved-control counts. Pilot-accepted count equals eligible plus multiple-lineup counts. Every eligible key has one model row with exposure and base weight both equal to 1.
2. Sum of modeled points equals the eligible disposition's assigned control points, by scoring team. That category plus all other assigned control points, unassigned dead-ball points and unresolved points equals the signed score-allocation total. It reconciles to the final score independently on each side.
3. Modeled team offensive exposure sums to the eligible possession count. Player-role exposure sums to five times that count in each role. Quarantined games enter only the expected-game and quarantine denominators.

The first extractor emits per-possession rows. If a later fit groups rows, only identical complete design vectors may share a group. Let their observation weights sum to $W$ and their weighted response mean be $\\bar y$. The group's loss at prediction $f$ is $W(\\bar y-f)^2$ plus $\\sum_i w_i(y_i-\\bar y)^2$. The latter is independent of coefficients. Keep raw total weights and the same penalty to preserve the minimizer. Include that constant if comparing objective values. Context columns and cutoff assignment must also match. Forecast evaluation retains the original row grain.

## Initial pilot exposure profile

An exploratory join against the pinned #19 pilot measured the maximum cohort under this rule. The row builder and manifest in #59 complete the full ledger reconciliation.

| Season type | Pilot-accepted possessions | Multiple-lineup exclusions | Eligible possessions |
| --- | ---: | ---: | ---: |
| Regular season | 240,280 | 30,338 | 209,942 |
| Playoffs | 16,176 | 2,079 | 14,097 |
| Total | 256,456 | 32,417 | 224,039 |

The excluded group accounts for 12.64% of pilot-accepted possessions and scores 138.20 assigned control points per 100 opportunities. The retained group scores 111.18. Interpret the first historical fit as evidence about stable-lineup possessions. Whole-game or all-possession transport requires separate validation.

## Synthetic example

The [hand-adjudicated sequence fixture](../../tests/fixtures/rapm/historical_rows.json) includes a same-clock lineup credit, an interior zero-duration lineup, retained-ball scoring, parser exclusions, unresolved offense and a zero-point possession. It uses fictitious game and player IDs.
