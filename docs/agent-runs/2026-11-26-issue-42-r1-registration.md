# Agent run: #42 R1 joint confirmatory registration (draft)

- **Date:** 2026-11-26
- **Status:** **Blocked.** The maintainer approved the plan, but stage B stopped before any code was written: the pinned pipeline's required V2 play-by-play feed does not exist for 2025–26. **No 2025–26 data captured or read** (metadata only, see below).
- **Related issues:** #42, #36, #39, #40, #38, #41, #55
- **Branch:** `claude/issue-42-r1-registration`

## Work completed

- **ADRs.** ADR-0030, ADR-0031 and ADR-0032 are marked Accepted on maintainer approval.
- **Draft.** The [registration draft](../research/r1-confirmatory-protocol.md) covers:
  - **P1 (primary):** EI vs context-offset RAPM, possession MSE.
  - **P2:** other comparators and ablations.
  - **T1 and T2:** team margin and win probability.
  - **S:** rating stability.
  - **D1:** EPM agreement, after scoring.
  - **Freeze:** two stages, with the code frozen and reproduced on 2024–25 before any holdout byte is fetched.
  - **Run rules:** a single capture, the unchanged quality gate with no discretion, explicit cutoffs, ordered pre-score freezing and a committed access log.
- **Review.** An independent pre-freeze review (Sonnet subagent) found 8 blockers, all addressed in the draft:
  - row seasons for `W2`;
  - unfrozen code and a circular digest guard;
  - an unregistered playoff cutoff;
  - discretion in the gate and capture rules;
  - an unimplementable order of operations;
  - a retrospective access log;
  - a verdict-rule inconsistency with #39;
  - discretionary D1 capture selection.

## Blocker found at stage B start (2026-11-26)

- **Check.** A metadata-only inventory: GitHub tree file names for `shufinskiy/nba_data`, Bentes release asset names, and header-only requests to the Bill Mill logs. No file body was downloaded. It is recorded in the draft's exposure table.
- **Finding.** For 2025–26 the archive has `nbastatsv3`, `cdnnba` (liveData) and `shotdetail` files, regular and playoff, but **no `nbastats` (V2), `datanba` or `pbpstats` file**. All three exist through 2024–25. The NBA retired the V2 play-by-play endpoint, so no newer archive revision is likely to add it. The Bill Mill team and player logs for 2025–26 exist (HTTP 200). The Bentes 2026 lineup files exist.
- **Why it blocks.** The build parses V2 events for every game (`event_games(nbastats…)` in `bil/data/pilot.py`). The V3-primary retry still needs V2, because V3 `actionNumber` is matched to V2 `EVENTNUM`. The draft's §4.1 says a missing play-by-play input ends R1, and §4.2 requires the unchanged default parser path. Freezing this plan would therefore freeze a run that cannot happen.
- **Missing `datanba`** alone would be handled by the existing `no_datanba` label. **Missing `pbpstats`** only removes one evidence comparison.

## Options for the maintainer

1. **Recommended: a V2-free event path, validated before freeze.** Build V2-schema events from V3 actions, with liveData as the cross-check. Validate on 2023–24 and 2024–25, where V2 also exists: compare accepted games, possession rows, lineups and #36 predictions against the V2 builds, against limits registered before the comparison. If it passes, amend R1 §4.1–4.2 to name that path and the validation, then freeze as planned. All of this uses pre-holdout data only. It is development work with its own issue.
2. **Declare R1 confirmatory unavailable** and report EI v1 on its development and outer-fold evidence only.

## Next actions

1. **Maintainer decision** on the options above. #42 is labelled blocked.
2. **If option 1:** the V2-free event path and its validation (new issue). Then amend §4.1–4.2.
3. **Implement §4.0:** parametrized runners, verdict rule and the code-constant guard. Reproduce #36's and #39's 2024–25 predictions exactly. Independent code review.
4. **Freeze commit (stage B).**
5. **Capture, gate, fit and freeze, score, D1, report,** each logged.
