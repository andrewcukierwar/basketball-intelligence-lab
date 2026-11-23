# Agent run: review the reconciled GitHub backlog

- **Date:** 2026-11-23
- **Status:** GitHub changes applied. The documentation changes await the maintainer's decision to commit.
- **Related:** [PR #50](https://github.com/andrewcukierwar/basketball-intelligence-lab/pull/50), issues #19–#55
- **Branch:** `claude/roadmap-backlog-review`, based on `codex/project-roadmap-reconciliation`

## Objective and authorized scope

The maintainer asked for an independent review of the backlog filed in #19–#49, then approved applying the recommended changes.

## Work completed

- Removed blocked-by links that encoded milestone order rather than real prerequisites:

  | Issue | Was blocked by | Now blocked by |
  | --- | --- | --- |
  | #29 box-score features | #27 | #19, #3 |
  | #34 prior-centered solver | #30 | #6 |
  | #37 tracking audit | #29 | #2 |
  | #28 SPM targets | #27 | #26, #53 |
  | #45, #46 DARKO and LEBRON | #44 | #42 |

- Split the old #25, which expanded to every season at once:
  - #51 audits source-feed coverage for each season.
  - #52 builds the 2023–24 and 2024–25 outer-validation seasons.
  - #25 now covers 2017–18 through 2021–22.
  - #53 backfills 2001–02 through 2016–17 for the SPM window.

  Season data now depends on the pilot pipeline (#19), not on the RAPM row contract (#20).
- Kept 2025–26 out of every build issue. #42 now builds it only after registration, with every access logged.
- Added two issues:
  - #54 covers the deferred review items from #15.
  - #55 covers time-sensitive capture of pregame inputs for 2026–27. It needs separate authorization before work starts.
- Labels and conventions:
  - Added a `scope: provisional` label, applied to #35, #36 and #38–#44.
  - The `complexity: high` label now says to split the issue before starting.
  - Set #19 to not yet started and low complexity.
  - Added a falsification field to the issue form, and tracking-convention notes to the plan and backlog.

## Verification

| Check | Result |
| --- | --- |
| Issue bodies compared with native Blocked by links for #19–#55 | Every Dependencies section matches. Each issue has exactly one complexity label and one state label. |
| Graph check | 53 edges, no cycles. The longest chain to #42 fell from 14 issues to 10. |
| Ready issues | Went from #19, #21 and #22 to #19, #21, #22, #34, #37, #51 and #55. #55 still needs authorization. |
| Issue-form YAML | Parses. |

## Next actions

- Land #19 first. Its branch conflicts with `main` only in the append order of `docs/DECISIONS.md` and `docs/experiment-log.md`.
- Merge PR #50, then these documentation changes.
