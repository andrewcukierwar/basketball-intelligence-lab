# Agent run: V2-free event path from V3 and liveData (#133)

- **Date:** 2026-11-26
- **Status:** Blocked. Both registered validations failed (the first on coverage, revision 2 on L8), and how R1 proceeds needs a maintainer decision.
- **Related issues:** #133, #42.
- **Branch / commit / PR:** `claude/issue-133-v3-event-path`. The registration commit is `8da7a7e`. The PR is listed on the issue.

## Objective and authorized scope

- **Goal.** Build event rows for seasons without V2 from V3 actions and liveData, validated on 2023–25 against a pre-registered protocol. This was the prerequisite for #42 (R1) on 2025–26.
- **Approval.** The maintainer approved it ("Approve #133").

## Work completed

- **Adapter.** `src/bil/data/pilot_v3_events.py` rebuilds V2-schema rows. `pilot build --event-source v3` uses it.
- **Check.** `pilot check` reads flagrant fouls from V3 in V3 builds.
- **Comparisons.** `event_source_comparison` gains `rows` and `fields`.
- **Scripts.** `scripts/v3_event_model_check.py` reruns #36, and `scripts/v3_event_verdict.py` applies the limits.
- **Documents.**
  - The protocol, [v3-event-path-protocol.md](../research/v3-event-path-protocol.md), reviewed before registration. A Sonnet reviewer found five blockers; they were fixed, and a focused re-review found none.
  - The result, [v3-event-path-validation.md](../research/v3-event-path-validation.md).
  - ADR-0033.

## Key decisions and discoveries

- **Development fidelity.** On 2020–23 the adapter matches V2 closely: about 0.1% row mismatch and at least 99.76% player-slot agreement.
- **Validation.** The run on 2023–24 and 2024–25 fails L2 and L3. The flopping technical (`('Foul', 'Flopping')`, new in 2023–24) is unmapped and quarantines 74 and 17 regular-season games. Every fidelity limit and the #36 rerun pass in the accepted games.
- **No tuning.** As registered, the adapter was not changed after the run.

## Verification performed

| Check | Actual result |
| --- | --- |
| `uv run pytest -q` | 453 passed, 3 skipped |
| ruff check and format, mypy strict | Pass |
| Development builds 2020–23, `check` | 26 of 26 in each |
| Validation, `scripts/v3_event_verdict.py` | FAIL: L2 and L3 in both seasons; L1, L4–L7 pass |
| Independent review | Sonnet pre-registration review and focused re-review; no blockers at registration |

## Revision 2 (maintainer chose "Revised protocol")

- **What changed.** `v3-live-events-2` maps `('Foul', 'Flopping')` to a non-unsportsmanlike technical by NBA rule. It adds a narrow class-preserving fallback for other unknown fouls and turnovers, and a new limit, L8: parser-class agreement of the revised events with V2.
- **Review.** The reviewer's pre-registration blockers were fixed: L8 added and the personal-foul default narrowed. A focused re-review found none left.
- **Registration and result.** Registered at `807463c`. The run passes L1–L7 (coverage 99.2% and 97.5%) and fails L8: V2 codes flopping as foul action 32, unknown to pbpstats, so 79 of 80 and 17 of 18 classes disagree. Not adopted, and no further revision under its rules.

| Check | Actual result |
| --- | --- |
| Revision-2 verdict | FAIL: L8 in both seasons; L1–L7 pass |
| `uv run pytest -q` | 454 passed, 3 skipped |

## Blockers and remaining risks

- **#42.** No registered path builds 2025–26 events.
- **Revised adapter.** One that maps flopping would be developed with 2023–25 exposed, so its evidence would be Experimental, not independent validation.

## Next actions (maintainer decision)

1. **Redesign R1.** Run it without 2025–26 play-by-play, for example on outcomes that need only box scores. This is what revision 2's outcome rule directs.
2. **Wait** for an archive that holds V2-equivalent 2025–26 events.
3. **Override L8 (maintainer only).** Accept revision 2 despite L8, as a recorded deviation, on the grounds that L1–L7 pass. An agent must not do this unilaterally.
