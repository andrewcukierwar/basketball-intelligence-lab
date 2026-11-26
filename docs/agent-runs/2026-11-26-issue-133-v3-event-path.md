# Agent run: V2-free event path from V3 and liveData (#133)

- **Date:** 2026-11-26
- **Status:** Blocked. The registered validation failed, and how to proceed needs a maintainer decision.
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

## Blockers and remaining risks

- **#42.** No registered path builds 2025–26 events.
- **Revised adapter.** One that maps flopping would be developed with 2023–25 exposed, so its evidence would be Experimental, not independent validation.

## Next actions (maintainer decision)

1. **Accept the failure.** Redesign R1 without 2025–26 play-by-play.
2. **Register a revised protocol.** Disclose the exposure, map unknown foul and turnover subtypes by a structural fallback, rerun on 2023–25 as Experimental evidence, and accept weaker assurance for 2025–26.
3. **Wait** for an archive that holds V2-equivalent 2025–26 events.
