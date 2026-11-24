# Safeguarded event-order repair `order-repair-v2`, 2017–18 ([#99](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/99))

- **Evidence class:** Experimental, Original design (applies the maintainer conditions of 2026-11-24 in ADR-0023). No EPM output was used. No model was fitted.
- **Status:** Proposed ([ADR-0029](../DECISIONS.md)). **Not validated for canonical use.** The independent review of the first version found two blockers, addressed here and awaiting re-review. Outputs stay experimental.
- **Code:** `src/bil/data/pilot_order_v2.py`, `build --order-repair-v2`, commit `76bb03d4`. Build `data/processed/2017-18/issue-99-order-repair-v2-c` passes 26 of 26 `check` invariants (superseded first-version builds: `-a`, `-b`). Version 1 (`--order-repair`) is unchanged for failed games. The scratch build `issue-90-order-repair-v2` used v1's removed second use and can be rebuilt only at its old commit.

## The rule

1. Raw records are never edited. A repaired event is a copy with a new `PCTIMESTRING`. The original clock stays in the modification log and in the snapshot rows that `source_refs` point to.
2. Replays (type 18) and timeouts (type 9) are non-substantive metadata. They are excluded from the order solve, never re-clocked and never anchor another event. They are merged back by their own clock.
3. Substantive events are placed in data.nba `ord` order. The longest non-increasing clock run keeps its clocks (earliest entered on ties). Any other event takes the valid clock nearest its original clock between its kept neighbours, and never later in the stream than the event before it. A displaced period boundary declines the repair.
4. A substantive event may shift at most 24 s. A larger correction rejects the repair and the game keeps its original quarantine. Nothing is truncated. **The ceiling bounds the harm from a wrong correction and does not validate a correction.** A 3 s shift can still put a rebound after the wrong shot.
5. A moved shot, free throw, turnover, rebound or substitution needs corroboration, otherwise the game is declined. Either V3 action order places the event between its nearest unmoved `ord` neighbours that V3 lists (`data.nba ord + V3 action order`), or, for a rebound only, `ord` puts it after a missed shot or free throw, skipping substitutions, timeouts and replays (`data.nba ord + rebound follows a missed shot`). Other types need only `ord`.
6. Every modification is logged (`order_repair_v2_log.csv`, summarized in the manifest under `order_repair_v2`, with its SHA-256) and appears as `quality_issue` rows `order_repair_v2_applied`, `_declined` and `_rejected`. Declined and rejected games log what they would have changed.
7. Repaired games carry the stratum `datanba_event_order_v2`, which is included in the evidence comparison's lower-trust list.
8. The repair runs only after the V2, V3-primary and optional same-clock attempts fail, so in code it touches only failed games. Not applying it to seasons that already pass is a procedural rule: nobody should run the flag for such a season, and a game that passes without it is never offered it. v1's second use, which offered the repair to accepted games with unresolved possessions, is removed. It selected on the hard-gate metric.

## Review outcome and the second version of the rules

Independent review of the first version (commit `d50e7695`, builds `-a` and `-b`) concluded the repair is **not validated for canonical use**. Of its 5 applied shifts of 5 s or more, 3 were wrong in feed evidence: a defensive rebound placed before a tip miss and the offensive rebound after it (`0021700067` event 187, -11 s, creating 2 unresolved possessions), and players' printed Off/Def rebound counters running backwards (`0021700269` events 10 and 601, `0021700216` event 84). The V3 tier corroborated none of the clock changes. Every re-clock rested on "follows a miss" or on `ord` alone. Commit `76bb03d4` adds these safeguards, and the results below are from build `-c`:

- The printed running totals (`Off:/Def:` rebounds, `PTS`, `P#.T#` fouls) must stay monotone in the repaired order at every moved event, otherwise the game is declined (`counter_inversion`).
- Jump balls (type 10) change possession and need the same corroboration as shots.
- A repaired stream with an unresolved possession touching a moved event (the possession containing it or the event next to it) is rejected.

The team and possession sequence is checked by these three rules and by the unchanged reconciliation. There is no separate team-sequence rule. Builds `-a` and `-b` are superseded and kept only as the reviewed record.

## Results, 2017–18 (build `-c`)

| Quantity | Value |
| --- | --- |
| Quarantined games before the repair | 180 (178 regular, 2 playoffs). 168 are order-class. |
| Games offered the repair | 172 |
| Recovered (applied, all checks pass) | 15 (version 1 recovered 138 in total, 137 of them order-class) |
| Declined | 118 uncorroborated, 14 counter inversion, 7 incomplete `ord`, 4 shift over 24 s |
| Rejected by the reconciliation or an unresolved possession at a moved event | 14 |
| Regular season accepted | 1,067 of 1,230 (86.7%). Default 1,052 (85.5%) |
| Playoffs | 80 of 82, unchanged |
| Unresolved possessions, full season | 0.388% (875 of 225,248). Default 0.391% |
| `pilot check` | 26 of 26 |

The same-clock rule applied to 0 of 163 offered games in the first version, so it was not rerun with the new safeguards. Its quarantines in this season are not the missed-shot-rebound pattern.

**Shift distribution.** Applied (33 modifications): 15 reorderings with no clock change, all within 5 s, median 1 s, maximum 4 s, 14 earlier and 4 later. Version 1 gave 17 events more than 60 s. Applied by type: rebound 17, free throw 8, missed shot 2, violation 3, turnover 1, substitution 1, foul 1. The 14 rebound moves are the least corroborated tier (a preceding missed shot). A reviewer should treat them as plausible and not validated.

## Possession and lineup verification

`scripts/order_repair_verification.py` compares the 15 repaired games with the 1,132 other accepted games (1,052 regular season and 80 playoff). The unrepaired attempt cannot serve as a comparator, because it failed a hard check and produced no rows. All feeds share the NBA's event log, so this is consistency evidence.

| Measure | Repaired (15 games) | Other accepted (1,132) |
| --- | --- | --- |
| Lineup seconds equal to Bentes | 99.978% | 99.972% |
| Lowest single-game lineup share | 99.93% | 99.85% |
| Accepted possession count equals pbpstats.com | 12 of 15 | 871 of 1,132 (77%) |
| Live-ball offense equals data.nba | 99.813% (3,735 of 3,742) | 99.830% |
| Unresolved possessions | 7 of 2,993 | 868 of 222,255 |

**Event-local check (the aggregate table cannot show this).** 33 moved events touch 50 possessions, none unresolved. All 112 live-ball events within 3 events of a moved event agree with data.nba on offense. In the reviewed first version, 4 of 16 unresolved possessions in repaired games touched moved events. The in-build rejection rule now removes any such game. These local checks use data.nba, which shares `ord`'s lineage. They are necessary and not sufficient.

**Lineup seconds are not independent of the rewritten clocks.** Substitution clocks can be rewritten, so a lineup-seconds match shows consistency with the box minutes, not independence from the repair. In this build only one substitution moved. The box minutes and plus-minus reconciliation remain the independent guards.

## Checks that lose power on repaired games

Corrected clocks are monotone by construction, so `unsupported_reorder` and `unresolved_clock_reset` cannot fire on a moved event. Event order within a clock is chosen from `ord`, so any parser order check is no longer an independent test of the repair. Minutes, plus-minus, score, lineup and period-score reconciliation keep their full power. Plus-minus and minutes are insensitive to some same-clock reorderings, so an ordering error that changes no total cannot be ruled out.

## ADR-0022 eligibility

2017–18 stays **excluded**. Regular-season coverage is 86.7% (1,067 of 1,230, floor 97%) and the full-season unresolved share is 0.388% (limit 0.1%). `scripts/season_quality.py --run-checks` classifies it as `fails_hard_limit` (output `data/quality/issue-99-2017-18-v2c`, not committed). Nothing was relaxed. The repair cannot close either gap: reaching 97% needs 1,193 regular games (126 more), and the unresolved share is dominated by accepted games the repair never touches.

## Residual unresolved possessions (diagnosis, not fixed)

884 unresolved possessions in 269 accepted games (largest game 15; the 20 worst games hold 180). Only 16 are in repaired games. Findings on the v2-a build:

- 706 of 884 (80%) include or touch a same-clock group, the pattern that ADR-0028 targets.
- 517 are followed, and 504 preceded, by a possession with the same offense, the signature of a missing or misplaced possession boundary (defensive rebound 269, final free throw 234, made shot 226, turnover 133).
- 569 sit in games with a technical-free-throw label, 111 in games with exact source repeats, 60 in games parsed in V3 event order and 28 in V3-primary games.
- 333 (38%) have a data.nba `ord` descent within one event of the possession. So a share is order-related after all, but in accepted games, where ADR-0023 forbids offering the repair. The issue text called them not order-related. That holds for most of them (62%) and not for all.
- All 884 are in `no_livedata` games, so no liveData possession field is available to adjudicate them.

Candidate causes, in order of size: same-clock free-throw and substitution ordering, technical-free-throw sequences, and ordering residue in accepted games. They are not fixed here.

## Limitations

- The 27 recoveries rest on corroboration by V3 or rebound semantics. V3 and `ord` derive from the same upstream log.
- The ceiling and the corroboration tiers are a first policy. The 24 s ceiling is the maintainer's value. The tier definitions are mine and are proposals for review.
- The comparison with an unrepaired build is impossible by construction. Plausibility rests on Bentes, pbpstats.com and data.nba.
- `event.parquet` has no per-event re-clock flag. Adding a column would change the shared output schema of every build. The log CSV and the `order_repair_v2_*` issue rows identify every moved event instead.
- Residual counts above are from the first-version build `-a`. Build `-c` has 875 unresolved possessions and the same causes.
