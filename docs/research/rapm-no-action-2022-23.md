# No-action possessions in the RAPM row set (2022–23)

[Issue #82](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/82) decides whether run-out possessions with no action belong in the RAPM row set. [ADR-0019](../DECISIONS.md) excludes them from model rows and keeps them in the ledgers. The [row contract](rapm-historical-rows.md) specifies the rule. This report gives the rebuilt counts and the effect on the [#23 baseline](rapm-baseline-2022-23.md) and the [#24 context ablations](rapm-context-ablations-2022-23.md). The same change ships the ledger tightening of [#74](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/74).

**Provenance.** The [addendum protocol](rapm-no-action-protocol.md) was committed with the runner pin option at `4ab4246` before either run. Both runs came from a clean tree at that commit (`working_tree_clean` true in both manifests) and wrote to new private directories `issue-82-baseline-v1` and `issue-82-context-v1`. The row set `issue-82-v1` was built at `d2f36a5` from the pinned pilot `issue-19-v6` (manifest SHA-256 `89cb2e82…1570`). Source data are attributed to NBA.com and stay private under the [pilot terms](../data-pilot.md). Only 2022–23 was read. No 2023–24 or later data and no EPM value was read or used.

| Claim | Label |
| --- | --- |
| The no-action rule and its ordering in the disposition | **Original** BIL design |
| Counts, reconciliation and every metric below | **Experimental**, one development season, retrospective capture-bound |
| Reasons offered for the residual end-of-period effect | **Inferred** |

## Result in one paragraph

Excluding the 1,003 stable-lineup no-action possessions removes about half of the end-of-period effect and about 80% of the held-out time gain, and leaves the player result nearly where it was. The time block's held-out gain over zero context falls from −25.7 to −4.8 (95% interval −7.6 to −1.9), and the home, score and time (HST) gain from −32.3 to −10.9 (−15.7 to −6.0). The end-of-period coefficient halves, from −30.5 to −15.9. Player RAPM's gain over the league mean changes only from −14.1 to −13.2. The context-only comparator no longer beats zero-context player RAPM: the HST context-only model is now +4.7 (−1.8 to +10.9) against it, where it was −16.4 before. Score terms, home and late-blowout weighting behave as before, and no #24 verdict changes.

## Rebuilt row set

`issue-82-v1` has build id `b5a0a640…9b5c`. All 17 identity checks report 0 violations, including the two new checks (no-action possessions have no action events and score 0, and stints are contiguous within each period).

| Scope | Eligible (v1 → new) | Multiple-lineup | No-action | Modeled points | Final points |
| --- | --- | --- | --- | ---: | ---: |
| Regular season | 209,942 → 209,006 | 30,338 → 30,306 | 968 | 233,592 | 277,039 |
| Playoffs | 14,097 → 14,030 | 2,079 → 2,075 | 71 | 15,499 | 18,411 |
| Total | 224,039 → 223,036 | 32,417 → 32,381 | 1,039 | 249,091 | 295,450 |

Of the 1,039, 1,003 were eligible and 36 were multiple-lineup. Pilot-excluded (2,756) and unresolved (51) possessions are unchanged, as are all 259,263 dispositions and 155,440 score classifications. Modeled points stay at 249,091 because every no-action possession scores 0, and every other point total matches `issue-59-v1`. No model row changed apart from the 1,003 removed. The 1,039 count is larger than the 996 in the #82 review because that count covered only possessions starting within 24 s of a period's end. By pilot end reason, 1,025 end at the period end, and 7 each at a jump ball or another reason. The #74 changes leave other rows alone. 36,227 non-eligible dispositions now carry NULL lineup IDs, and the explicit `exposure` column sums to 223,036.

## Effect on the #23 baseline

Pooled R1–R4 on 136,119 held-out possessions (was 136,730) from 786 games. Delta is MSE(RAPM) − MSE(league), negative is better. Intervals are 95% game-clustered bootstrap (2,000 resamples, seed 2023). The grid again selects $\lambda$ = 4,000.

| Quantity | `issue-59-v1` | `issue-82-v1` |
| --- | --- | --- |
| Player RAPM vs league mean, pooled R1–R4 | −14.09 (−18.33 to −9.85) | −13.17 (−17.36 to −9.03) |
| Offense-only / defense-only | −9.25 / +1.09 | −8.99 / +0.28 |
| P1 playoffs | −7.98 (−23.95 to +7.53) | −7.74 (−23.43 to +7.43) |
| Team-game RMSE (points), league / RAPM | 10.69 / 10.45 | 10.72 / 10.47 |
| Game-half total correlation (398 players) | 0.382 | 0.385 |
| Final-fit offense/defense correlation | 0.057 | 0.091 |

The baseline's main result stands. Its absolute MSE levels differ because the held-out set changes.

## Effect on the #24 context results

C0 is the zero-context fit. Δ is against C0 on the same possessions, pooled R1–R4 (P1 playoffs in the last column). The rows and verdicts are in the same order as #24.

| Variant | `issue-59-v1` Δ vs C0 | `issue-82-v1` Δ vs C0 | Verdict (unchanged) | P1, new |
| --- | --- | --- | --- | --- |
| `H_fit` | −0.39 (−1.94 to +1.15) | −0.33 (−1.90 to +1.27) | inconclusive | −2.8 (−6.8 to +1.1) |
| `S_fit` | −6.32 (−9.64 to −3.02) | −5.83 (−8.99 to −2.62) | supported | −0.8 (−11.3 to +12.0) |
| `T_fit` | −25.69 (−31.47 to −19.72) | −4.76 (−7.55 to −1.85) | supported | −12.4 (−21.7 to −2.6) |
| `T_off` | −25.68 (−31.59 to −19.67) | −4.77 (−7.64 to −1.77) | supported | −12.4 (−21.9 to −2.3) |
| `HST_fit` | −32.25 (−39.03 to −25.39) | −10.85 (−15.73 to −5.95) | supported | −18.3 (−31.7 to −4.8) |
| `HST_off` | −32.68 (−39.11 to −26.07) | −11.25 (−15.56 to −6.95) | supported | −19.2 (−30.6 to −7.7) |
| `W_half` | +0.00 (−0.29 to +0.30) | +0.02 (−0.27 to +0.31) | rejected | +0.2 (−0.5 to +0.8) |
| `W_drop` | +0.17 (−0.44 to +0.78) | +0.20 (−0.40 to +0.79) | rejected | +0.3 (−0.9 to +1.5) |

`Sbin_fit`, `Slate_fit` and `S_off` move like `S_fit` (new −5.2, −5.5 and −5.8). Fitted control and the eligible offset remain indistinguishable for time (paired difference +0.00, −0.37 to +0.39). The time block still helps on every fold, but the gain is now small and uneven: R1–R4 for `T_fit` are −8.2, +1.0, −6.0 and −6.3 (R2's interval, −5.4 to +7.1, includes 0). Home is still inconclusive. Final in-sample gains for the fitted variants (new, old in brackets): `T_fit` −6.0 (−26.9), `HST_fit` −17.1 (−38.5), `S_fit` −8.5 (−9.2). The fitted context coefficients in the final fit are: end of period −15.6 (−30.2), home +1.60 (+1.60), margin −0.31 (−0.32) per point, and the final two minutes −0.15 (−3.9). Player totals still move little: RMS shift against C0 is 0.24 for `HST_fit` (was 0.26) and 0.02 for `T_fit` (was 0.04).

Team-game RMSE is essentially unchanged (HST_fit 11.51 against 11.54, `T_fit` 10.46 against 10.44). Score terms still worsen team-game aggregates.

**Late blowouts and the playoffs (descriptive).** On held-out regular-season late-blowout possessions, `T_fit` goes from −116 (−143 to −91) to −4 (−14 to +5) and `HST_fit` from −153 to −38 (−74 to −4), while `S_fit` is unchanged at −33 (−66 to −1). So the old time gain on blowouts was nearly all no-action possessions. In the 641 playoff late-blowout possessions, `T_fit` is now worse than C0 by +14.1 (+4.0 to +24.8), against −93.6 (−139.3 to −49.7) before. That is a small stratum and should not be given weight.

## Context-only comparator (#77)

Context-only models, with no players, against the league mean (pooled R1–R4):

| Comparator | `issue-59-v1` Δ vs league | `issue-82-v1` Δ vs league | New Δ vs C0 |
| --- | --- | --- | --- |
| C0 (player RAPM, no context) | −14.09 (−18.33 to −9.85) | −13.17 (−17.36 to −9.03) | 0 |
| CTX home | −0.44 (−2.07 to +1.18) | −0.37 (−2.07 to +1.34) | +12.80 (+8.39 to +17.13) |
| CTX score (linear) | −3.32 (−5.92 to −0.66) | −2.97 (−5.43 to −0.43) | +10.21 (+4.81 to +15.52) |
| CTX time | −26.86 (−32.68 to −20.97) | −5.23 (−8.13 to −2.24) | +7.94 (+3.10 to +12.86) |
| CTX home + score + time | −30.50 (−37.16 to −23.78) | −8.51 (−13.02 to −3.95) | +4.66 (−1.82 to +10.88) |

Under the prior row set, a context-only model with time terms beat zero-context player RAPM on held-out possessions (HST −16.4 against C0). With no-action possessions excluded, it does not: time-only context is worse than C0, and the full context-only model is not distinguishable from it. The flagged concern in #24 is therefore confirmed. Player RAPM still adds to context: `HST_fit` is −24.0 (−30.3 to −17.5) against the league mean, and −15.5 below the context-only model's −8.5. Final context-only coefficients, in points per 100 with game-clustered 95% intervals: end of period −16.0 (−19.2 to −12.9), where it was −30.5. The final two minutes is now 0.0 (−2.6 to +2.6), where it was −3.8. Home is +1.53 (+1.03 to +2.03) per side, and the margin slope is −0.21 (−0.26 to −0.16).

## What remains of the end-of-period effect

A −16 end-of-period coefficient survives with no-action possessions removed (held-out time gain −4.8, interval excluding 0). The pilot contains no field that identifies why. One **Inferred** candidate is game-final possessions, which the #24 review found score 0.6 points per 100. This report does not test them. They are not run-outs, because they contain action. Whether they need their own treatment (for example, game-final possessions) is a separate question. It is not decided here, and no variant was chosen from these numbers.

## Limitations and deviations

- One development season, retrospective and capture-bound. The comparison is descriptive: the `issue-59-v1` values are the published #23 and #24 results, not reruns. Row sets differ by exactly the 1,003 removed rows, so MSE levels differ for that reason.
- The same variants were scored on the same folds as in #24, without multiplicity adjustment.
- The no-action rule uses the pilot's event kinds. A possession with only substitutions, timeouts, replays, jump balls or `other` events and no action kind counts as no-action. That includes 14 that did not end at a period end.
- The runners take the new pin through `--pin-manifest-sha256`, which pins the model rows and game reconciliation through the digests the manifest lists. The #59 constants stay the default.
- No deviation from the addendum protocol occurred.

## Reproduce

```sh
uv run python -m bil.data.rapm_rows data/processed/2022-23/issue-19-v6 data/processed/2022-23/issue-82-v1 \
  --pilot-manifest-sha256 89cb2e82af4d0fc4b7a95cf0f94b99b2b088361ffa893ce192de2b519d711570 \
  --code-commit d2f36a5919f1b5b714853964c61d3d8dec2bad7b
PIN=507e11c545027719f8c8580220862665bfb6803b5d6b95a6ef939d47c2556d7f
uv run python -m bil.models.rapm.baseline data/processed/2022-23/issue-82-v1 \
  data/processed/2022-23/issue-82-baseline-v1 --pin-manifest-sha256 $PIN \
  --protocol docs/research/rapm-no-action-protocol.md
uv run python -m bil.models.rapm.context_ablation data/processed/2022-23/issue-82-v1 \
  data/processed/2022-23/issue-19-v6 data/processed/2022-23/issue-82-context-v1 \
  --pin-manifest-sha256 $PIN --protocol docs/research/rapm-no-action-protocol.md
```

Run facts: baseline 53 fits in 19 s with 895 MiB peak memory, and context ablation 83 fits in 35 s with 937 MiB, all LSQR converged. Output SHA-256: baseline `results.json` `30420ec2…98b70`, context `results.json` `04b3f0ee…6cd33`.
