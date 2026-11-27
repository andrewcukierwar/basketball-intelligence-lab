# Agent run: per-origin source-revision resolution

- **Date:** 2026-11-27
- **Status:** Awaiting review
- **Related issues:** #143 (part of #43), #142
- **Branch / commit / PR:** `claude/issue-143-source-revisions`, built on #142's branch

## Objective and authorized scope

Resolve an immutable source revision per game for each refresh origin, and record it in the refresh manifest. Document the timing fields the pins actually carry, and the conservative rules where a time is missing.

## Work completed

- **`src/bil/refresh_sources.py`:**
  - `Capture`, `GameRecord` and `Resolution`;
  - `resolve(captures, origin, mode)` in two modes. `strict_rolling` reuses the evaluation resolver `resolve_revisions` and adds strictly-before availability and game refusal. `retrospective` handles single pins;
  - the `box_capture` and `possession_captures` adapters, which hash per-game content.
- **`src/bil/refresh.py`:**
  - the resolution digest is added to the identity, with `VERSION` bumped to `origin-refresh-issue-143-v2`;
  - `sources.json` and the manifest `source_resolution` summary are written;
  - `load_inputs` records the box-log capture instants;
  - `strict_rolling` is refused for the replay refresh.
- **`tests/test_refresh_sources.py`.** 9 tests:
  - a correction after the origin enters only later origins;
  - the strictly-before boundary;
  - a game finishing after midnight keeps its official date and is unavailable until captured;
  - unknown, naive, inconsistent and date-ambiguous times are refused;
  - capture order and mode checks;
  - the retrospective rule;
  - the digest is independent of exclusion counts;
  - the adapters;
  - the manifest records the resolution.
- **Docs.** `docs/refresh.md` gains a source-revisions section. ADR-0040.

## Key decisions and discoveries

- **No finish times.** Neither pin records when a game finished. In strict mode the capture instant bounds the finish. Otherwise the existing resolver refuses every row as `observation_time_unknown`.
- **Replay must be retrospective.** Replay pins were captured after their seasons, so strict resolution selects nothing. Corrections before capture are an irreducible limit of all replay results, now stated in ADR-0040.
- **Exclusion counts are kept out of the digest.** Later games change them, and they broke the #142 poisoning test until removed.
- **Unknown-time revisions refuse the whole game,** rather than falling back to an earlier known revision.

## Verification performed

| Check | Actual result |
| --- | --- |
| `pytest -q tests/test_refresh_sources.py tests/test_refresh.py` | 14 passed |
| Full suite, `ruff`, `ruff format`, `mypy src` | See PR |
| `verify-frozen` on real pins | 10 of 10 reproduced, gap 0.0. 7.0 s, 1.9 GiB. 2024-02-01 resolves 5,329 games |

## Blockers and remaining risks

- The possession capture time (`game_stream.available_at`) is dropped by the loaded rows. Retrospective mode does not need it, but strict possession resolution will need it read.
- Multi-capture assembly and live capture are not built.

## Next actions

Review and merge after #142. Then #144: checkpoints and warm/cold equality.
