# Agent run: control-event ownership check for scoreless possessions

- **Date:** 2026-11-27
- **Status:** Awaiting review
- **Related issues:** #138 (audit A4), #133
- **Branch / commit / PR:** `claude/issue-138-scoreless-ownership`

## Objective and authorized scope

Detect possessions whose offense the parser assigned to the wrong team before they enter RAPM, including scoreless possessions that every existing check passed. Define control evidence and ambiguity handling, measure coverage and false positives on development builds, and supply the check for a future registered source validation. Frozen results and the #133 verdicts stay as recorded.

## Work completed

- **Normalizer.** `pilot_normalize`: the opt-in rule `control_ownership` treats a field-goal attempt, or a turnover outside an opponent free-throw clock, by the non-offense team as a conflict. It leaves the accepted possession unresolved, through the same loop that handles score conflicts. The data.nba relabel step can still resolve the possession, but only to the supported team. `report["control_conflicts"]` counts possessions left unresolved by this rule alone.
- **Pilot build.** `pilot build --control-ownership` records `control_ownership_rule` in the manifest and adds a per-game `control_ownership_conflicts` warning. `pilot ownership BUILD` prints coverage.
- **`pilot_check`.** The new check `control_events_match_possession_offense` always runs. `ownership_coverage()` reports results by event family, status and evidence source.
- **`rapm_rows`.** `eligible_control_events_match_offense` and `control_ownership` are recorded in the manifest. The check fails the build only when the pilot declares the rule, so frozen pilots still rebuild their published row sets.
- **Tests.** The audit's correct and flipped Q2 variants are covered, along with feed relabeling, the and-one turnover exemption and the no-double-count case. The tests also cover check-path and coverage counts, plus enforced and recorded row-builder behavior.
- **Docs.** The rules, assessment and rebuild are in the [report](../research/possession-ownership.md). Also updated: the [ADR-0034](../DECISIONS.md#adr-0034--opt-in-control-ownership-rule-and-independent-ownership-checks) entry and the pilot guide section.

## Key decisions and discoveries

- **Opt-in rule.** The rule is opt-in, like the same-clock and free-throw-miss rules, so frozen pilots reproduce. The checks always run.
- **Dead-ball exemption.** The first version flagged turnovers charged to the defense in and-one clusters. The exemption removes them. All 12 hand-reviewed remaining flags were genuine merges.
- **Frozen 2018–25 builds.** They contain 0 to 23 flagged accepted possessions per season (0 to 0.009%), so `pilot check` now reports this one failure on them. The 2022–23 frozen row set has 2 affected eligible rows. The effect on published results has not been measured.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run pytest -q` | 465 passed, 3 skipped (private fixtures) |
| `ruff check`, `ruff format --check`, `mypy src` | Pass |
| `pilot ownership` on 7 canonical builds | Table in report |
| 2022–23 rebuild without / with rule (`issue-138-base-v1`, `issue-138-control-v2`) | 26/27 vs 27/27 checks. Only 4 possession statuses differ |
| `rapm_rows` from frozen `issue-19-v6` | Byte-identical to `issue-82-canonical-v1` (`model_row` `ebadd151…`), 2 conflicts recorded |
| `rapm_rows` from rule pilot | Enforced, 0 conflicts, 224,037 rows |

`issue-138-control-v1` is superseded: its warnings used the earlier count that included score-overlapping possessions.

## Blockers and remaining risks

- Possessions without a decisive event, about 9% of accepted possessions, are not covered.
- Event teams come from the same V2 feed as the possessions. Feed-independent ownership remains the job of a separately registered #133 validation.

## Next actions

Use `--control-ownership` for any new possession-source build. Any re-estimate of frozen results without the flagged possessions needs its own registration.
