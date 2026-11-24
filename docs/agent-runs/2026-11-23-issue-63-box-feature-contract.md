# Issue #63 box-score feature contract

- **Status:** Specification and fixture independently reviewed.
- **Related:** [#63](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/63), parent [#29](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/29), builder [#62](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/62).
- **Branch:** `codex/issue-63-box-feature-contract` from main at `d3d01f3`.

Defined the first offense and defense box features and their raw counts, denominators, availability, missingness, provenance and season-type handling. Rates use observed attempts or played time. Box-only coverage remains usable when a game lacks an accepted event stream. SPM will report its RAPM-target intersection separately.

A DuckDB profile of the pinned `issue-5-v2` logs verified 27,622 unique scoped player appearances, linkage to both team rows, 71 multi-team players, and the documented zero-attempt, zero-minute and integrity counts. Source rows remained outside Git. Confirmed the publisher dictionary and official NBA glossary and terms. Their evidence does not establish strict historical revision availability.

A separate local calculation passed all five synthetic window cases and 13 feature expectations, with date, team, score and exposure checks. The independent reviewer reproduced the window cases, all feature values, and pinned source counts and team joins. The review clarified cutoff inclusivity and snapshot provenance. Issue #62 uses these examples to validate the private builder and adds full-window reconciliation.
