# Event-aware exposure for multi-lineup possessions

Design checkpoint for [#164](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/164). Use one event-aware candidate built on the already tested [#110 runner and archives](rapm-lineup-exposure.md). #110 compared entry and clock-fractional training on stable-lineup test possessions, and both failed advancement. Here, the question is whether a defined representation can include substitution-spanning opportunities and predict on the same mixed scoring cohort. Keep the stable-lineup reference and both #110 verdicts.

## One row per opportunity

- Use the existing accepted possession, stint, lineup, event and score-allocation ledgers and the canonical disposition. A stable possession retains its one pair and full exposure. Restrict the experimental mixed set to accepted multiple-lineup possessions with verified sides under #138, a contiguous stint overlap and defensible exposure. Keep every ineligible game or possession in the coverage denominator and its existing disposition.
- For a mixed possession, assign one exposure token to each distinct decisive shot attempt or turnover, including misses. Use the shared #138 decisive control definition, which excludes a turnover at an opponent free-throw clock. Assign each token to the intersection stint whose sequence interval actually contains that event. This preserves zero-clock live events without using scored points as weights. Divide the tokens by their count to distribute one unit of exposure. If a resolved possession contains no decisive event, use its positive reconciled clock shares. Leave a zero-clock mixed interval without decisive evidence outside the fit and report its missingness separately.
- Use one signed player row, with each active player contributing his team's share in that lineup interval. Sum repeated lineup or player coefficients and keep exactly +5 offense and −5 defense across each row. The response remains 100 × total control points from the same possession in the audited ledger. Outcome and exposure are separately reconciled. Free-throw credit remains with the official scoring-allocation stint, including a foul credited to a lineup before the shooting substitution. Neither administrative free throws nor their scores create an exposure token. The aggregate fitted value describes a possession as played and does not allocate its realized points to players or lineups.
- Use the same single intercept, unit opportunity weights and W2 training windows as #110. Use baseline penalties 4,000 offense and 8,000 defense, and multiply both by the registered fit's accepted opportunity count divided by the stable fit's count to keep penalty per opportunity comparable. The fixed-penalty case is a disclosed sensitivity. Both arms predict scores on the same held-out rows using the candidate's appraised representation, so the comparison isolates the change in training. Retain the #110 clock-fractional mix and prior stable-only results as documented references.

## Reconciliation first, then fit

1. Reuse the #110 overlap extraction and DuckDB checks. Pin its four historical source builds as development evidence. Verify each canonical possession's original point/exposure accounting before and after the new mix. Require positive unit exposure, same stream/game, legal game and lineup keys, finite coefficients, no overlap ambiguity and no decisive ownership contradictions. Excluded opportunities add zero model exposure. Report the share of the #110 mixed set that enters the new fit and do not vary rules to reach 80%.
2. Add synthetic fixtures for a shooting substitution with free-throw credit attached to the earlier lineup, a zero-clock turnover following a substitution, a retained-possession administrative free throw, and a scoreless interval with insufficient evidence. Verify output sign and mass, unchanged stable model rows, and exact allocation to the actual scoring stint. Check the sparse coefficient result against a dense oracle on a nontrivial fixture. These are the implementation acceptance gates before registration for fitting.
3. Reuse #110's chronological held-out game blocks on 2021–22 and 2022–23. Freeze the exact source and converter bytes, forecasts and denominators before scoring. Report paired possession MSE, team-game summed-control-points RMSE and 2,000 full-game cluster intervals, for the combined cohort and separately for stable, multiple-lineup, playoffs and scoreless cases. Report exposure and selection by player side, game state, clock band, substitution pattern and source stratum, along with runtime and peak RSS. Prediction on a realized event path is a conditional diagnostic.
4. Advance only if the candidate improves the mixed scoring cohort with a paired interval below zero and its upper bounds on stable and playoff MSE differences are no greater than zero. A coverage shortfall or a mixed benefit accompanied by stable/playoff harm retains the existing stable-lineup reference. Canonical adoption requires its own decision.

The exposure converter and ledger fixtures have run. The paired outcome replay remains a separate stage.


## Exposure-only archive audit

The draft converter reused #110's pinned event, disposition, score-allocation and stint checks. Its signed sparse matrix has five offense and five defense opportunities per admitted possession. For this comparison, decisive actions lacking a team stay outside the fit along with positive ownership contradictions. Administrative free throws do not create exposure tokens.

| Season | Archived mixed possessions | Mixed with action shares | Mixed with clock shares | Supported mixed |
| --- | ---: | ---: | ---: | ---: |
| 2019–20 | 30,099 | 21,434 | 8,308 | 29,742 |
| 2020–21 | 28,934 | 20,631 | 7,993 | 28,624 |
| 2021–22 | 32,974 | 23,577 | 9,025 | 32,602 |
| 2022–23 | 32,417 | 22,722 | 9,385 | 32,107 |

Overall, 123,075 of 124,424 archived mixed opportunities are supported (98.92%). No decisive action or positive clock supports 1,317 mixed intervals. Another 32 mixed and 28 stable opportunities have a decisive event with a conflicting or missing team. Together, 965,513 of 966,890 archived stable and mixed opportunities can enter a future registered fit. The original archived disposition and point ledgers remain the references.

Run the exposure-only audit with:

```sh
uv run python scripts/rapm_action_exposure.py data/processed
```

Five focused tests passed, covering zero-clock live action, an opponent technical/free-throw cluster, unresolved and wrong-side events, role mass, and sparse agreement with a dense ridge oracle. No paired model comparison has run.
