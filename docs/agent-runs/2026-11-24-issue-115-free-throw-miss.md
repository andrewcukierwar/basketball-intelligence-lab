# Issue #115 missed free-throw markers

- **Status** Implementation independently reviewed and all season checks passed.
- **Issue** [#115](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/115), follow-up to #111 under #53.
- **Branch** `codex/issue-115-free-throw-rebound-evidence` from `3749944`. Archived verification at `d138e23`. Commit `be75f92` renames a local variable for mypy.

Added an opt-in parser retry. A bare numbered attempt and immediate scoreless team rebound need corroboration from the affected shooter's exact pinned box totals. The rule rejects conflicting score transitions and competing missed shots. The parser must link the rebound back to the identified attempt. Raw sources and prior accepted rows stay intact.

An independent reviewer reproduced the initial rule's stale cumulative-score ambiguity. Commit `46b4c4b` requires the shooter's established makes to increase that side's score exactly one point. The reviewer verified the repair against the archived fixture and cleared the later ambiguity guard at `d138e23`.

- Full suite with private fixtures enabled: 357 passed. Ruff and format passed. Mypy caught a reused variable name with two types. The rename passed mypy and the focused public tests.
- Eight season rebuilds passed 26 of 26 checks each. The existing accepted rows matched across ten tables apart from ingestion timestamps. The opt-in rule recovered 66 games and rejected three retries.
- Ran pinned evidence for 2011–12 through 2013–14 and the full quality diagnostic for those three seasons. The 2012–13 variant meets the hard limits, with April quarantine and margin-band unresolved flags. The playoff floor still excludes 2011–12 and 2013–14.

Keep the incomplete seasons and missingness evidence visible in #53. Use the [versioned report](../research/missing-free-throw-miss.md) for any later cohort decision. No canonical cohort or reserved evaluation window changed. The private `issue-115-v1` builds record the earlier trial, and `issue-115-v2` records the reviewed rule.
