# Run-outs and period-end possessions in the RAPM row set (2022–23)

[Issue #82](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/82) asked whether possessions that start at a period's end, or contain no action, belong in the RAPM row set. [ADR-0019](../DECISIONS.md) records the maintainer's principle: exclude only verified pseudo-possessions with no live-ball opportunity, keep run-outs, and never condition eligibility on later actions or outcomes. The verification below shows that the pilot already excludes the real pseudo-possessions, so the **canonical row set is unchanged from `issue-59-v1`** and the registered [#23](rapm-baseline-2022-23.md) and [#24](rapm-context-ablations-2022-23.md) results stand. Two alternatives are versioned as **sensitivity** variants: `period_end_start` (drop accepted possessions whose first event is `period_end`) and `no_action` (drop accepted possessions with no shot, free throw, turnover, foul or violation). The [row contract](rapm-historical-rows.md) specifies all three. The same change ships the ledger tightening of [#74](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/74).

**Provenance.** Earlier sensitivity runs: variant `no_action` under the [v1 protocol](rapm-no-action-protocol.md) (`issue-82-v1`, `issue-82-baseline-v1`, `issue-82-context-v1`) and variant `period_end_start` under the [v2 protocol](rapm-no-action-protocol-v2.md) (`issue-82-B-v1`, `issue-82-B-baseline-v1`, `issue-82-B-context-v1`). v2 was superseded because its audit was invalid. The three row sets were rebuilt at `0c6d111` and the cohort comparison registered in [protocol v3](rapm-no-action-protocol-v3.md) (`abf011b`) was run once afterwards from a clean tree to `issue-82-cohort-v2`. Source data are attributed to NBA.com and stay private under the [pilot terms](../data-pilot.md). Only 2022–23 was read. No 2023–24 or later data and no EPM value was read or used.

| Claim | Label |
| --- | --- |
| The canonical rule and the two sensitivity variants | **Original** BIL design |
| Counts, reconciliation and every metric below | **Experimental**, one development season, retrospective capture-bound |
| Reasons offered for the residual end-of-period effect | **Inferred** |

## Verification: a period-end start is not evidence of a pseudo-possession

`scripts/audit_period_end_possessions.py <pilot_dir>` on `issue-19-v6` reports, per pilot status, the clock (`remaining_ms` of the last event before the possession's first event) when the possession began.

| Pilot status | Possessions starting with `period_end` | Clock at start | Under 3 s | Preceding event |
| --- | ---: | --- | ---: | --- |
| accepted | 962 | 3 to 24 s, median 9 s | 0 | rebound 312, made shot 297, turnover 260, final free throw 93 |
| excluded | 1,567 | 0 to 2 s, median 1 s | 1,567 | rebound 666, shot 489, turnover 256, free throw 155, jump ball 1 |
| unresolved | 1 | 1 s | 1 | free throw 1 |

None of the 962 accepted possessions has an action or jump-ball event, a score allocation or a period-boundary span, and 729 of them are in the final period or overtime (233 precede `period_start`). They are run-outs after a change of control with time left, not pseudo-possessions. An earlier audit that called a period-end start sufficient measured duration over the possession's own events, which is zero for any one-event possession, and was wrong. The pilot's own under-3-s exclusion already covers the real pseudo-possessions, so no further canonical exclusion is justified.

## Rebuilt row sets

All three builds report 0 violations on every identity check (16 for canonical, 17 for the variants, which add one check each).

| Row set | Variant | Model rows | Build id | Reproduces |
| --- | --- | ---: | --- | --- |
| `issue-82-canonical-v1` | canonical | 224,039 | `9d3090ad…69b7` | `issue-59-v1` model rows: EXCEPT ALL in both directions is empty, Parquet SHA-256 `ebadd151…d90` identical |
| `issue-82-period-end-start-v1` | `period_end_start` | 223,077 | `37421b2f…5de3` | `issue-82-B-v1`: EXCEPT ALL empty, digest identical |
| `issue-82-noaction-v1` | `no_action` | 223,036 | `6fb6d752…43af` | `issue-82-v1`: EXCEPT ALL empty, digest identical |

Score classifications (155,440) are identical in all three. The game reconciliation differs only by the added exclusion columns. `period_end_start` drops 962 stable-lineup rows (896 regular season, 66 playoffs), all scoring 0. `no_action` drops 1,039 (968 and 71): 1,003 eligible plus 36 multiple-lineup, so it drops 41 more eligible rows than `period_end_start`. Modeled points stay at 249,091 and final points at 295,450 in every variant. The #74 changes (explicit `exposure`, NULL lineup IDs on non-eligible dispositions, lag-based stint contiguity) leave model rows unchanged.

## Canonical results

The canonical rows equal `issue-59-v1`, so the published #23 baseline (player RAPM vs league −14.09, 95% interval −18.33 to −9.85, $\lambda$ = 4,000) and #24 context ablations (including time −25.69 and HST −32.25 against zero context, and the context-only comparator) stand without a rerun. Their interpretation should keep the audit above in view: the large time-of-period effect includes run-outs that are legitimate possessions.

## Common-cohort comparison (run once, protocol v3)

Each variant's zero-context RAPM ($\lambda$ = 4,000) is fit on that variant's rows at each fold R1–R4 and scored on identical held-out possessions. Lower MSE is better. Intervals are 95% game-clustered bootstrap (2,000 resamples, seed 2023).

**Primary: every canonical held-out row (136,730 possessions, 786 games).**

| Fit | RAPM MSE | RAPM minus league |
| --- | ---: | --- |
| canonical | 14,095.37 | −14.09 (−18.41 to −9.84) |
| `period_end_start` | 14,093.63 | −13.93 (−18.14 to −9.82) |
| `no_action` | 14,093.51 | −13.96 (−18.15 to −9.85) |

Paired RAPM MSE differences on identical possessions: `period_end_start` − canonical −1.74 (−2.42 to −1.01), `no_action` − canonical −1.86 (−2.57 to −1.10), `no_action` − `period_end_start` −0.12 (−0.18 to −0.07).

**Secondary: held-out rows eligible under `no_action` (136,119 possessions).** The fits give MSE 14,105.27 (canonical), 14,102.81 (`period_end_start`) and 14,102.66 (`no_action`). Differences: `period_end_start` − canonical −2.46 (−3.15 to −1.74), `no_action` − canonical −2.61 (−3.33 to −1.84), `no_action` − `period_end_start` −0.15 (−0.21 to −0.09).

**Tertiary, each variant's own cohort (RAPM minus league):** canonical −14.09 (−18.41 to −9.84) on 136,730 rows, `period_end_start` −13.16 (−17.36 to −9.02) on 136,141, `no_action` −13.17 (−17.35 to −9.05) on 136,119. MSE levels are not comparable across these cohorts.

Interpretation (**Inferred**): fits on the sensitivity rows predict canonical held-out possessions slightly better, about 1.7 to 1.9 out of roughly 14,100 in MSE, so the run-outs add a little noise to player estimates. The size is small relative to the −14 player gain and to possession noise. This is a statement about the fit and does not select the eligibility rule, which follows the maintainer's principle.

## Sensitivity evidence from the earlier runs

These ran on their own cohorts under the earlier protocols. Both differ from canonical only by dropping run-outs.

| Quantity | canonical (`issue-59-v1`) | `period_end_start` | `no_action` |
| --- | --- | --- | --- |
| Player RAPM vs league | −14.09 (−18.33 to −9.85) | −13.16 (−17.36 to −8.99) | −13.17 (−17.36 to −9.03) |
| $\lambda$ selected | 4,000 | 4,000 | 4,000 |
| `T_fit` vs zero context | −25.69 (−31.47 to −19.72) | −5.20 (−8.16 to −2.06) | −4.76 (−7.55 to −1.85) |
| `HST_fit` vs zero context | −32.25 (−39.03 to −25.39) | −11.26 (−16.23 to −6.26) | −10.85 (−15.73 to −5.95) |
| `S_fit` vs zero context | −6.32 (−9.64 to −3.02) | −5.80 (−8.96 to −2.63) | −5.83 (−8.99 to −2.62) |
| `H_fit` vs zero context | −0.39 (−1.94 to +1.15) | −0.32 (−1.90 to +1.27) | −0.33 (−1.90 to +1.27) |
| Context-only HST vs zero context | −16.42 (−24.60 to −8.47) | +4.21 (−2.36 to +10.62) | +4.66 (−1.82 to +10.88) |
| Context-only end-of-period coefficient | −30.5 | −16.6 | −16.0 |

No #24 verdict changes in either variant. The late-blowout time gain collapses in both (regular-season `T_fit` −116 in canonical, about −4 in the variants). Together the sensitivity runs show that the large time-of-period effect and the context-only advantage in the canonical results depend on possessions that start at a period's end with time left. The corresponding run-outs are legitimate. This is a caveat on how to read the canonical time effect (for example, as part of end-of-period game structure), and it is not a reason to exclude them. A coefficient of about −16 remains in both variants, and the pilot has no field that explains it. One **Inferred** candidate is game-final possessions (0.6 points per 100 in the #24 review), which was not tested.

## Limitations

- One development season, retrospective and capture-bound. Nothing here is confirmatory, and nothing was tuned from these numbers.
- The cohort comparison covers zero-context RAPM only. The variants differ in the sample, and the earlier sensitivity runs used different protocols and cohorts.
- The 962 and 1,567 counts, the clock distribution and the rule apply to 2022–23. The audit script takes a pilot build path so other seasons can be checked.

## Reproduce

```sh
uv run python scripts/audit_period_end_possessions.py data/processed/2022-23/issue-19-v6
for variant in canonical period_end_start no_action; do
  uv run python -m bil.data.rapm_rows data/processed/2022-23/issue-19-v6 \
    "data/processed/2022-23/issue-82-$variant-v1" --variant "$variant" \
    --pilot-manifest-sha256 89cb2e82af4d0fc4b7a95cf0f94b99b2b088361ffa893ce192de2b519d711570 \
    --code-commit 0c6d111a6f26843b85dba09a40041fa05978de9d
done
uv run python -m bil.models.rapm.cohort_comparison data/processed/2022-23/issue-82-cohort-v2 \
  --canonical-dir data/processed/2022-23/issue-82-canonical-v1 \
  --canonical-pin bd25cd0a8fe3702f5ae9021a435571224a3022c036d529f80b6e8ce108b56488 \
  --period-end-start-dir data/processed/2022-23/issue-82-period-end-start-v1 \
  --period-end-start-pin fec1d8401f9864b824f37e79c08a3906e6f56e50c5b2371da74db35af461f1f4 \
  --no-action-dir data/processed/2022-23/issue-82-noaction-v1 \
  --no-action-pin 3415ef5c859666fad5a05fe85ddfafd07152287885066733a9ee87b963ffdecd
```

(The variant directories are named `issue-82-noaction-v1` and `issue-82-period-end-start-v1`, so substitute those names in the loop.)
