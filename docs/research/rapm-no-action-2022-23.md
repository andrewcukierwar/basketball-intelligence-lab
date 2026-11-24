# Period-end pseudo-possessions and no-action possessions in the RAPM row set (2022–23)

[Issue #82](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/82) asked whether run-out possessions with no action belong in the RAPM row set. The maintainer decided on 2026-11-23 ([ADR-0019](../DECISIONS.md)): variant **B** is canonical and excludes only accepted possessions whose first event is `period_end`. Variant **A** (the outcome-based no-action exclusion) and variant **C** (keep everything, `issue-59-v1`) remain as versioned sensitivity alternatives. The [row contract](rapm-historical-rows.md) specifies the rule. This report gives the audit that supports it, the rebuilt counts and the effect on the [#23 baseline](rapm-baseline-2022-23.md) and the [#24 context ablations](rapm-context-ablations-2022-23.md). The same change ships the ledger tightening of [#74](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/74).

**Provenance.** Variant A: the [v1 addendum protocol](rapm-no-action-protocol.md) was frozen before its runs (`issue-82-v1`, `issue-82-baseline-v1`, `issue-82-context-v1`). Variant B: the [v2 addendum protocol](rapm-no-action-protocol-v2.md) was committed (`3863286`) before the B runs, and the row set was built at `d404c2d`. B's runs (`issue-82-B-baseline-v1`, `issue-82-B-context-v1`) and the common-cohort comparison (`issue-82-cohort-v1`) came from a clean tree. Source data are attributed to NBA.com and stay private under the [pilot terms](../data-pilot.md). Only 2022–23 was read. No 2023–24 or later data and no EPM value was read or used.

| Claim | Label |
| --- | --- |
| The period-end rule and the variants | **Original** BIL design |
| Counts, reconciliation and every metric below | **Experimental**, one development season, retrospective capture-bound |
| Reasons offered for the residual end-of-period effect | **Inferred** |

## Result in one paragraph

A `period_end` first event is sufficient evidence of a pseudo-possession: the audit found 962 such accepted possessions in 2022–23, and none has an action or jump-ball event, a score delta or allocation, a game-clock duration, or a period-boundary span. Excluding them (B) removes 962 stable-lineup rows. Total points are unchanged. B reproduces most of the earlier no-action result. Player RAPM's gain over the league mean goes from −14.09 to −13.16, the held-out time gain from −25.69 to −5.20 (−8.16 to −2.06), and the HST gain from −32.25 to −11.26. B and the broader A are close. On a common held-out cohort, a fit on B scores 2.46 better in MSE than a fit on C (95% interval −3.15 to −1.74), and A is 0.15 better than B (−0.21 to −0.09). This is evidence about the fit, not the reason for the rule, which the maintainer fixed before this comparison.

## Evidence that a `period_end` start is sufficient

`scripts/audit_period_end_possessions.py <pilot_dir>` on `issue-19-v6`. Of 256,456 accepted possessions, 962 have `period_end` as their first event.

| Check | Result |
| --- | --- |
| Contains a shot, free throw, turnover, foul, violation or jump ball | 0 |
| Has a score delta, or a score allocation inside or linked to it | 0 |
| Game-clock duration (max elapsed minus min elapsed) | 0 ms for all 962 (min, median, p99 and max are all 0), none over the 1 s tolerance |
| Spans a period boundary (an event in another period, or a `period_start`) | 0 |
| Next event | `period_start` for 233, none (end of the stream) for 729 |
| Most events in one such possession | 2 |
| Exceptions | none |

So none of these possessions offers a live-ball opportunity. The rule uses only the possession's first event, which is known before any action in it.

## Rebuilt row sets

`issue-82-B-v1`: build id `7b8c6449…eac3`, variant B, all 17 identity checks report 0 violations (including the period-end check and the new contiguity check).

| Scope | C eligible | A eligible | **B eligible** | B `period_end_pseudo` |
| --- | ---: | ---: | ---: | ---: |
| Regular season | 209,942 | 209,006 | **209,046** | 896 |
| Playoffs | 14,097 | 14,030 | **14,031** | 66 |
| Total | 224,039 | 223,036 | **223,077** | 962 |

All 962 B exclusions were eligible stable-lineup rows in C and score 0, so modeled points stay at 249,091 and the final points at 295,450. Against A, B keeps 41 eligible rows that A excluded (all score 0) and 36 multiple-lineup rows stay multiple-lineup. The B rows are a strict superset of A's. Dispositions (259,263), score classifications (155,440) and game rows (1,314) keep their keys. Multiple-lineup counts are the same as C (32,417). The #74 changes leave other rows alone: non-eligible dispositions carry NULL lineup IDs and the explicit `exposure` column sums to 223,077.

## Effect on the #23 baseline

Pooled R1–R4, delta against the league mean, 95% game-clustered bootstrap (2,000 resamples, seed 2023). $\lambda$ = 4,000 is selected in all three.

| Quantity | C (`issue-59-v1`) | A (`issue-82-v1`) | **B (`issue-82-B-v1`)** |
| --- | --- | --- | --- |
| Held-out possessions | 136,730 | 136,119 | 136,141 |
| Player RAPM vs league | −14.09 (−18.33 to −9.85) | −13.17 (−17.36 to −9.03) | **−13.16 (−17.36 to −8.99)** |
| P1 playoffs | −7.98 (−23.95 to +7.53) | −7.74 (−23.43 to +7.43) | −7.77 (−23.51 to +7.34) |
| Team-game RMSE, RAPM / league | 10.45 / 10.69 | 10.47 / 10.72 | 10.48 / 10.73 |
| Game-half total correlation | 0.382 | 0.385 | 0.386 |
| Final-fit offense/defense correlation | 0.057 | 0.091 | 0.091 |

## Effect on the #24 context results (B on its own cohort)

Δ is against zero-context C0 on the same possessions, pooled R1–R4 (P1 playoffs in the last column). Verdicts are unchanged in B.

| Variant | C Δ vs C0 | A Δ vs C0 | **B Δ vs C0** | Verdict | B, P1 |
| --- | --- | --- | --- | --- | --- |
| `H_fit` | −0.39 (−1.94 to +1.15) | −0.33 | −0.32 (−1.90 to +1.27) | inconclusive | −2.8 (−6.8 to +1.1) |
| `S_fit` | −6.32 (−9.64 to −3.02) | −5.83 | −5.80 (−8.96 to −2.63) | supported | −0.8 (−11.3 to +11.9) |
| `T_fit` | −25.69 (−31.47 to −19.72) | −4.76 | **−5.20 (−8.16 to −2.06)** | supported | −13.0 (−22.6 to −2.6) |
| `T_off` | −25.68 (−31.59 to −19.67) | −4.77 | −5.20 (−8.26 to −2.04) | supported | −12.9 (−22.9 to −2.4) |
| `HST_fit` | −32.25 (−39.03 to −25.39) | −10.85 | **−11.26 (−16.23 to −6.26)** | supported | −18.8 (−32.6 to −5.1) |
| `HST_off` | −32.68 (−39.11 to −26.07) | −11.25 | −11.66 (−16.06 to −7.33) | supported | −19.7 (−31.6 to −8.0) |
| `W_half` | +0.00 (−0.29 to +0.30) | +0.02 | +0.02 (−0.27 to +0.31) | rejected | +0.1 (−0.5 to +0.8) |
| `W_drop` | +0.17 (−0.44 to +0.78) | +0.20 | +0.20 (−0.39 to +0.80) | rejected | +0.3 (−0.9 to +1.5) |

By fold (B `T_fit`, R1–R4): −9.0, +0.8, −6.5 and −6.6, so R2's interval (−5.9 to +7.3) includes 0. Final in-sample gains (C, A, B): `T_fit` −26.9, −6.0, −6.5; `HST_fit` −38.5, −17.1, −17.5. B's fitted end-of-period coefficient is −16.3 (C: −30.2), with home +1.60 and margin −0.31 per point as before.

**Late blowouts (descriptive).** Regular-season held-out blowout `T_fit` is −4 (−14 to +6) in B against −116 (−143 to −91) in C. In the 641 playoff late-blowout possessions `T_fit` is +14.8 (+4.3 to +26.1), against −93.6 in C. That stratum is small and should not be given weight.

## Context-only comparator (#77), B

Against the league mean, pooled R1–R4: CTX time −5.68 (−8.74 to −2.52); CTX home + score + time −8.95 (−13.55 to −4.37). Against zero-context player RAPM (C0 = −13.16): CTX time is +7.48 (+2.53 to +12.64) and HST is +4.21 (−2.36 to +10.62). In C the HST context-only model was −16.42 (−24.60 to −8.47) against C0. Player RAPM adds to context: `HST_fit` is −24.42 (−30.74 to −17.79) against the league mean. Final context-only coefficients: end of period −16.6 (−19.9 to −13.6), where C had −30.5 (−33.4 to −27.7); final two minutes +0.0 (−2.6 to +2.6); home +1.52 (+1.03 to +2.02); margin −0.21 (−0.26 to −0.16). The B results sit within a few tenths of A on every comparison above.

This comparison describes the measured sample. It did not choose the rule. Under B, as under A, the earlier finding that a context-only model beats zero-context player RAPM does not survive, because it came mostly from the period-end pseudo-possessions.

## Common-cohort comparison of A, B and C

Each variant's zero-context RAPM ($\lambda$ = 4,000) is fit on that variant's rows at each fold (R1–R4) and scored on the same held-out possessions: the 136,119 rows eligible under A (primary). Lower MSE is better, and intervals are 95% game-clustered.

| | A fit | B fit | C fit |
| --- | --- | --- | --- |
| RAPM MSE on the A cohort | 14,102.66 | 14,102.81 | 14,105.27 |
| RAPM minus league (fit-window mean of the same rows) | −13.17 (−17.35 to −9.05) | −13.14 (−17.33 to −9.00) | −13.04 (−17.35 to −8.75) |

Paired differences in RAPM MSE on identical possessions: B − C = −2.46 (−3.15 to −1.74), A − C = −2.61 (−3.33 to −1.84) and A − B = −0.15 (−0.21 to −0.09). Secondary, own cohorts (RAPM minus league): A −13.17 (−17.35 to −9.05) on 136,119 rows, B −13.16 (−17.36 to −9.02) on 136,141 rows and C −14.09 (−18.41 to −9.84) on 136,730 rows. Own-cohort MSE levels differ by cohort and should not be compared.

Interpretation (**Inferred**): training on the zero-point pseudo-possessions slightly degrades the player fit on real possessions, by a small amount (about 2.5 of roughly 14,100 MSE). The extra 41 outcome-free rows that A drops carry almost no difference (0.15). Context terms were not part of this comparison.

## What remains of the end-of-period effect

A coefficient of about −16 survives in B (held-out `T_fit` −5.2, interval excluding 0). The pilot has no field that explains it. One **Inferred** candidate is game-final possessions (0.6 points per 100 in the #24 review). This report does not test it, and no rule was chosen from these numbers.

## Limitations

- One development season, retrospective and capture-bound. The C values are the published #23 and #24 results, not reruns, and the A values are from the v1 runs.
- The same variants were scored on the same folds without multiplicity adjustment. The common-cohort comparison covers zero-context RAPM only.
- B keeps 41 possessions that A excludes because they ended with no action (mostly dribble-outs and held balls). Under the maintainer's decision they stay in because eligibility cannot depend on how a possession turned out. A's exclusion of them filters held-out rows on how the possessions turned out.
- The audit and the rule apply to 2022–23. The audit script takes a pilot build path so other seasons can be checked with it.

## Reproduce

```sh
uv run python scripts/audit_period_end_possessions.py data/processed/2022-23/issue-19-v6
uv run python -m bil.data.rapm_rows data/processed/2022-23/issue-19-v6 data/processed/2022-23/issue-82-B-v1 \
  --pilot-manifest-sha256 89cb2e82af4d0fc4b7a95cf0f94b99b2b088361ffa893ce192de2b519d711570 \
  --code-commit d404c2da036ce0129914ae310cf53230c149f46f --variant B
PIN=2cc2b765c2f6ff4e1802098fa03c7040f458208c9a535906da8f804e08692c20
uv run python -m bil.models.rapm.baseline data/processed/2022-23/issue-82-B-v1 \
  data/processed/2022-23/issue-82-B-baseline-v1 --pin-manifest-sha256 $PIN \
  --protocol docs/research/rapm-no-action-protocol-v2.md
uv run python -m bil.models.rapm.context_ablation data/processed/2022-23/issue-82-B-v1 \
  data/processed/2022-23/issue-19-v6 data/processed/2022-23/issue-82-B-context-v1 \
  --pin-manifest-sha256 $PIN --protocol docs/research/rapm-no-action-protocol-v2.md
uv run python -m bil.models.rapm.cohort_comparison data/processed/2022-23/issue-82-cohort-v1 \
  --A-dir data/processed/2022-23/issue-82-v1 --A-pin 507e11c545027719f8c8580220862665bfb6803b5d6b95a6ef939d47c2556d7f \
  --B-dir data/processed/2022-23/issue-82-B-v1 --B-pin $PIN --C-dir data/processed/2022-23/issue-59-v1
```

Run facts: B baseline 53 fits in 18 s (872 MiB peak) and B context ablation 83 fits in 33 s (1,114 MiB), all LSQR converged.
