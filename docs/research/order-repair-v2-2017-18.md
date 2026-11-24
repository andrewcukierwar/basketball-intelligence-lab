# Safeguarded event-order repair `order-repair-v2`, 2017–18 ([#99](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/99))

- **Evidence class:** Experimental, Original design (applies the maintainer conditions of 2026-11-24 in ADR-0023). No EPM output was used. No model was fitted.
- **Status:** Proposed ([ADR-0029](../DECISIONS.md)). Canonical use needs independent review, then lead acceptance under the maintainer conditions. Outputs are experimental until then.
- **Code:** `src/bil/data/pilot_order_v2.py`, `build --order-repair-v2`, commit `d50e7695`. Builds: `data/processed/2017-18/issue-99-order-repair-v2-a` (v2) and `-b` (v2 plus `--same-clock-rule`). Both pass 26 of 26 `check` invariants. Version 1 (`--order-repair`) is unchanged for failed games.

## The rule

1. Raw records are never edited. A repaired event is a copy with a new `PCTIMESTRING`. The original clock stays in the modification log and in the snapshot rows that `source_refs` point to.
2. Replays (type 18) and timeouts (type 9) are non-substantive metadata. They are excluded from the order solve, never re-clocked and never anchor another event. They are merged back by their own clock.
3. Substantive events are placed in data.nba `ord` order. The longest non-increasing clock run keeps its clocks (earliest entered on ties). Any other event takes the valid clock nearest its original clock between its kept neighbours, and never later in the stream than the event before it. A displaced period boundary declines the repair.
4. A substantive event may shift at most 24 s. A larger correction rejects the repair and the game keeps its original quarantine. Nothing is truncated. **The ceiling bounds the harm from a wrong correction and does not validate a correction.** A 3 s shift can still put a rebound after the wrong shot.
5. A moved shot, free throw, turnover, rebound or substitution needs corroboration, otherwise the game is declined. Either V3 action order places the event between its nearest unmoved `ord` neighbours that V3 lists (`data.nba ord + V3 action order`), or, for a rebound only, `ord` puts it after a missed shot or free throw, skipping substitutions, timeouts and replays (`data.nba ord + rebound follows a missed shot`). Other types need only `ord`.
6. Every modification is logged (`order_repair_v2_log.csv`, summarized in the manifest under `order_repair_v2`, with its SHA-256) and appears as `quality_issue` rows `order_repair_v2_applied`, `_declined` and `_rejected`. Declined and rejected games log what they would have changed.
7. Repaired games carry the stratum `datanba_event_order_v2`, which is included in the evidence comparison's lower-trust list.
8. The repair runs only after the V2, V3-primary and optional same-clock attempts fail. v1's second use, which offered the repair to accepted games with unresolved possessions, is removed. It selected on the hard-gate metric.

## Results, 2017–18

| Quantity | Value |
| --- | --- |
| Quarantined games before the repair | 180 (178 regular, 2 playoffs). 168 are order-class. |
| Games offered the repair | 172 |
| Recovered (applied, all checks pass) | 27 (v1 recovered 137) |
| Declined, by first reason | 118 uncorroborated, 7 incomplete `ord`, 4 shift over 24 s |
| Rejected: repaired stream failed reconciliation | 16 |
| Regular season accepted | 1,079 of 1,230 (87.7%). Default 1,052 (85.5%) |
| Playoffs | 80 of 82, unchanged |
| Unresolved possessions, full season | 0.388% (884 of 227,616). Default 0.391% |
| `pilot check` | 26 of 26 for both v2 builds |

The same-clock rule (`-b`) applied to 0 of 163 offered games in this season, so the two builds are identical in outcome. Its quarantines in this season are not the missed-shot-rebound pattern.

**Uncorroborated declines.** Of the events that failed corroboration, substitutions (144 event rows) and turnovers (76) dominate, then field goals (93). They are mostly same-clock events whose data.nba order differs from V2 and where V3 agrees with V2. Games reach this retry only after the V3-primary parse failed, so V3 is a weaker witness here than in the games it recovered earlier. The rule declines these on purpose. The 118 declines are the cost of the corroboration requirement, not a defect to tune away. Relaxing it to recover more games would be a maintainer decision and would mean accepting `ord` alone for substitutions and turnovers.

**Shift distribution.** Applied (67 modifications): 28 reorderings with no clock change, 63 within 5 s, median 1 s, maximum 11 s, 27 earlier and 12 later. Declined proposals (578): median 1 s, 8 above 24 s (largest 208 s) in 4 games. Rejected (31): maximum 3 s. v1 gave 17 events more than 60 s. Under v2 none of the applied events moves more than 11 s.

**Applied modifications by type:** rebound 33, free throw 18, foul 9, violation 3, missed shot 2, turnover 1, substitution 1.

## Possession and lineup verification

`scripts/order_repair_verification.py` compares the 27 repaired games with the other 1,132 accepted regular games. The unrepaired attempt cannot serve as a comparator, because it failed a hard check and produced no rows. Possession counts and lineup seconds are compared with independent feeds instead. All feeds share the NBA's event log, so this is consistency evidence.

| Measure | Repaired (27 games) | Other accepted (1,132) |
| --- | --- | --- |
| Lineup seconds equal to Bentes | 99.979% | 99.972% |
| Lowest single-game lineup share | 99.93% | 99.85% |
| Accepted possession count equals pbpstats.com | 20 of 27 (74%) | 871 of 1,132 (77%) |
| Within 2 possessions of pbpstats.com | 23 of 27 | 942 of 1,132 |
| Live-ball offense equals data.nba | 99.835% (6,651 of 6,662) | 99.830% |
| Unresolved possessions | 16 of 5,361 (0.30%) | 868 of 222,255 (0.39%) |

Repaired games look like the others on these measures. Lineup seconds and the box plus-minus reconciliation are the strongest checks, since they are independent of the event clocks that the repair rewrote. The data.nba offense comparison is circular for ordering, because the repair uses the same feed's `ord`.

## Checks that lose power on repaired games

Corrected clocks are monotone by construction, so `unsupported_reorder` and `unresolved_clock_reset` cannot fire on a moved event. Event order, within a clock, is chosen from `ord`, so any check that the parser applies to order is no longer an independent test of the repair. Minutes, plus-minus, score, lineup and period-score reconciliation keep their full power. Plus-minus and minutes are insensitive to some same-clock reorderings, so an ordering error that changes no total cannot be ruled out.

## ADR-0022 eligibility

2017–18 stays **excluded**. Regular-season coverage is 87.7% (floor 97%) and the full-season unresolved share is 0.388% (limit 0.1%). `scripts/season_quality.py --run-checks` classifies it as `fails_hard_limit` (output `data/quality/issue-99-2017-18-v2a`, not committed). Nothing was relaxed. The repair cannot close either gap: reaching 97% needs 1,193 regular games (114 more), and the unresolved share is dominated by accepted games the repair never touches.

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
