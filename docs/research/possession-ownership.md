# Possession ownership from control events (#138)

- **Issue:** [#138](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/138), from Astra audit finding A4.
- **Evidence class:** **Original** (check design) and **Inferred** (false-positive assessment on development builds). Nothing here is fitted or compared with EPM.
- **Decision:** [ADR-0034](../DECISIONS.md#adr-0034--opt-in-control-ownership-rule-and-independent-ownership-checks)

## Problem

The pilot checks scores, counts, minutes and box plus-minus. None of them reads which team a scoreless possession belongs to. The audit's counterexample adds an away missed field goal to the scoreless Q2 possession of the synthetic game in `tests/test_pilot.py` and flips only the parser's owner. Both variants passed every existing check. Their RAPM rows were `(200, 100, 0)` and `(100, 200, 0)`, so the flip swaps all ten player roles.

## Rule

Control evidence is limited to events that only the team with the ball can make:

| Event family | Decisive? | Reason |
| --- | --- | --- |
| Field-goal attempt (made or missed, V2 types 1 and 2) | Yes | Only the offense shoots. |
| Turnover (type 5) | Yes, except at an opponent free-throw clock | The committing team had the ball. A turnover recorded at the same period and clock as the other team's free throw is part of a dead-ball cluster. In the development builds these are mostly and-one sequences in which the fouling team is also charged a turnover. |
| Free throw | No | Technical and flagrant free throws do not follow control. Scored free throws are already checked through `score_allocation`. |
| Rebound | No | A defensive rebound ends the other team's possession. Team rebounds carry no reliable side. |
| Foul, violation | No | Either team can commit them, and the possession continues. |
| Jump ball | No | It decides control but carries no owner of its own. |
| Own basket | Not separate | The feed records it as a made shot by the credited team. The score check in the normalizer already applies to it. |
| Retained possession (kicked ball, flagrant) | No | Possession continues without a decisive control event. |

The evidence source is the parser's event team (`event.team_id`). The normalizer's existing relabel step still uses independent data.nba offense evidence for unresolved possessions. With the rule on, that evidence can relabel a possession only to the team its control events support.

## Where the rule runs

- **`pilot build --control-ownership`** (opt-in, rule `control-ownership-issue-138-v1`). This option leaves an accepted possession unresolved when a decisive event by the other team contradicts it, as a contradicting score already does. The manifest records `control_ownership_rule`, and each affected game gets a `control_ownership_conflicts` warning.
- **`pilot check`** enforces `control_events_match_possession_offense` on accepted possessions for builds that declare the rule. For older builds it prints the count as an `info` line without failing. This keeps their acceptance and the ADR-0022 classification in `season_quality` as recorded.
- **`rapm_rows`** always counts `eligible_control_events_match_offense` on eligible possessions and records the count under `control_ownership` in its manifest. For a pilot built with the rule, the count must be zero or the build fails. Pilot builds made without the rule still rebuild their frozen row sets, and their conflicts are recorded rather than enforced.
- **`pilot ownership BUILD`** reports coverage and disagreement by event family and possession status.

## Development-build assessment

The coverage report ran on the canonical pilot builds that feed the multi-season row sets. 2023–24 and 2024–25 are outer-validation seasons. The ADR-0022 matrix allows data-quality diagnostics for them. No 2025–26 data was read. Counts are for accepted possessions.

| Season (build) | Accepted possessions | With decisive evidence | Decisive FGA disagreements | Decisive turnover disagreements | Ambiguous turnovers | Flagged possessions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2018–19 (`issue-25-v1`) | 256,845 | 233,797 | 13 | 2 | 381 | 13 |
| 2019–20 (`issue-25-v1`) | 225,227 | 204,993 | 9 | 3 | 353 | 12 |
| 2020–21 (`issue-25-v1`) | 229,190 | 209,428 | 9 | 8 | 325 | 16 |
| 2021–22 (`issue-25-v1`) | 256,017 | 233,862 | 16 | 8 | 372 | 23 |
| 2022–23 (`issue-19-v6`) | 256,456 | 233,182 | 4 | 1 | 403 | 4 |
| 2023–24 (`issue-52-v1`) | 255,337 | 233,588 | 0 | 0 | 322 | 0 |
| 2024–25 (`issue-52-v1`) | 254,727 | 232,860 | 2 | 1 | 311 | 3 |

About 91% of accepted possessions contain decisive evidence. The remaining 9% rely on the parser alone. They are mostly possessions that end in free throws without a field-goal attempt, and short end-of-period possessions. Flagged possessions are 0 to 0.009% of accepted possessions per season.

**Hand review.** All 6 raw disagreements in 2022–23 were examined, along with 7 dead-ball-clock cases in 2018–19 and 2019–20 and a random 8 of the 23 flagged 2021–22 possessions.

- **Dead-ball turnovers (excluded by the rule).** Every reviewed case was a turnover charged to the defense at the clock of an and-one or similar free-throw cluster. The offense was confirmed by its own made shot and free throws. Before the exemption, these were the only false positives found.
- **Remaining flags (kept).** Every reviewed case was a genuine merge. The flagged team really had the ball, for example after missed free throws and its own offensive rebound, after an offensive foul, or on an end-of-period heave. The parser joined those events to the other team's possession.

**Measured precision.** In the reviewed sample, the precision for flagged possessions is 12 of 12 (4 in 2022–23 and 8 in 2021–22). Recall is not measured. A wrong-side possession without a decisive event cannot be detected by this rule.

## 2022–23 rebuild with and without the rule

The rebuild used snapshot `data/raw/2022-23/issue-5-v2` and a single commit for both builds. Commands:

```sh
.venv/bin/python -m bil.data.pilot build SNAPSHOT OUTPUT --code-commit "$(git rev-parse HEAD)" --control-ownership
.venv/bin/python -m bil.data.pilot check OUTPUT SNAPSHOT
.venv/bin/python -m bil.data.rapm_rows OUTPUT ROWS --code-commit "$(git rev-parse HEAD)" --pilot-manifest-sha256 SHA
```

| Build | `check` | Possessions changed | Eligible conflicts in rows | Model rows |
| --- | --- | --- | --- | ---: |
| Without rule (`issue-138-base-v1`) | 26 of 26, `info` line reports 4 conflicts | — | — | — |
| With rule (`issue-138-control-v2`) | 27 of 27 | 4 accepted → unresolved, in 4 games with a `control_ownership_conflicts` warning | 0 (enforced) | 224,037 |
| Frozen `issue-19-v6` rows rebuilt | — | — | 2 (recorded, not enforced) | 224,039 |

- **Rule build.** Apart from those 4 statuses, events, stints, lineups, score allocations and game acceptance are identical.
- **Frozen rebuild.** The rebuilt row set is byte-identical to the published `issue-82-canonical-v1` row set (`model_row` SHA-256 `ebadd151…`).
- **Runtime.** Both builds ran for 62 s, with peak RSS of 0.79 GB without the rule and 0.85 GB with it.
- **Overlap with scores.** Seven more possessions had a wrong-side control event that a score also contradicted. They were already unresolved without the rule and are not counted as rule conflicts.

## Limits

- The check cannot see ownership errors in possessions without a decisive event. That is about 9% of accepted possessions.
- Event teams come from the same V2 feed as the parser's possessions. Feed-independent ownership evidence for every possession needs a separately registered source validation (#133). This check is supplied for that validation and does not replace it.
- The frozen #26/#27/#35/#36/#39/#42 results used pilot builds without the rule. Their row sets contain the flagged possessions listed above, a few per season. The effect of removing them has not been measured. Any re-estimate is a new registered comparison and does not revise those results.
