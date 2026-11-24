# Agent run: backfill feasibility, 2017–18 event order and older feed eras

- **Date:** 2026-11-23
- **Status:** Awaiting review. Not pushed, no PR, and no issue edited.
- **Related issues:** [#90](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/90), parent [#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53). Policy language from [#89](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/89).
- **Branch / commits:** `claude/issue-90-backfill-feasibility`, rebased onto `99d558c`. Commits: pins and optional data.nba; diagnostics and the opt-in repair; the unresolved-possession extension; documentation. Manifests of the builds record the pre-rebase SHAs `c079ba8`, `899464b` and `4fc5cba`.

## Objective and scope

Bounded feasibility only: diagnose the 2017–18 event-order quarantines, probe one season per older feed era from local pinned captures, and recommend how to split #53. No downloads, no 2025–26 or 2026–27 payloads, no default pipeline change, no issues created.

## Work completed

- **`scripts/event_order_diagnostics.py`:** deterministic and read-only. Classifies order-class quarantines by parser failure signature, compares V2, V3 and data.nba order, tabulates the rate by week, and with `--simulate-repair` replays the failures with the opt-in repair.
- **`pilot_order.py` and `build --order-repair`:** the experimental data.nba entry-order repair (ADR-0023, proposed). Off by default. The manifest gains `order_repair` only when the flag is set.
- **Pins:** 2005, 2010, 2014 and 2016, generated from the #51 register CSVs. A new test compares every pin with the register. `pinned_season` still refuses 2025 and later.
- **Optional data.nba:** absent before 2016–17 (`no_datanba` stratum). The 2016–17 archives lack `ord`, so the reader keeps offense keys and no periods or order. `evidence` ignores rows without `ord`.
- **Docs:** `docs/research/backfill-feasibility.md`, ADR-0023, EXP-0013, a `data-pilot.md` note.

## Key findings

- 2017–18: 168 of 180 quarantines (166 of 178 in the regular season) are event-order failures caused by late-entered events whose stale clocks V2 sorts before the events they follow. Their rate falls from 78% of games in the first four weeks to 10% by March. Details in the research note.
- The repair recovers 137 of 168 and passes 26 of 26 checks, but 2017–18 still misses both hard gates (96.6% coverage, 0.283% unresolved). Residual unresolved possessions are not only an order problem.
- Older eras are cleaner than 2017–18: 2016–17 and 2005–06 pass both hard gates. 2014–15 misses 97% in the playoffs by one game. 2010–11 misses regular-season coverage by 8 games, from same-clock rebound sequences that no pre-2017 feed can order.
- V3 order equals V2 order in every older-era order-class quarantine, so V3 cannot help there.

## Failed or abandoned approaches

- The first repair kept the longest clock run by patience sorting, which on ties re-clocked the rebound instead of the late event. The tie rule now keeps the earliest-entered events.
- The first scratch build (`issue-90-order-repair-v1`) retried only failed games. It is kept as a comparison. The second (`-v2`) also offers games with unresolved possessions.
- No interrupted builds in this run. The earlier session left no partial output, and its worktree was gone, so this run restarted from `origin/main` and rebuilt everything into new directories.
- 2022–23 equivalence rebuild: `data/processed/2022-23/issue-90-rebuild-v1`, compared with `issue-19-v6`.

## Verification

| Check | Result |
| --- | --- |
| `uv sync --locked --offline --extra dev --extra pilot --extra rapm` | Pass |
| `uv run pytest -q` | 260 passed, 2 skipped (the archived-snapshot tests need `BIL_PILOT_SNAPSHOT`) |
| `uv run ruff check .`, `ruff format --check .`, `uv run mypy src` | Pass |
| Older-season `capture` and `capture-evidence --from-local` | Size and SHA-256 verified, no download |
| `build` and `check` for 2005–06, 2010–11, 2014–15, 2016–17 | 26 of 26 each, 42 to 52 s, at most 0.80 GB |
| `evidence` for those four | Runs |
| 2017–18 scratch builds with `--order-repair` | 26 of 26 each, `evidence` runs |
| 2022–23 rebuild vs `issue-19-v6` | 8 tables byte-identical. In `game` and `game_stream`, 0 differing rows either way excluding `ingested_at` |
| Independent review | Not run. Required before merge |

## Blockers and risks

- ADR-0023 re-clocks source timestamps for late-entered events. The maintainer decides whether to adopt it and whether to bound the shift.
- One season per era. 2001–02 to 2003–04 was not probed.
- The cause of the early-season rate in 2017–18 is Inferred.
- Private builds live under `data/processed/*/issue-90-*`. Nothing under `data/` is committed.

## Next actions

- Independent review of the diff from `99d558c`.
- The lead creates the batch issues from the recommendation in the research note and decides on ADR-0023.
