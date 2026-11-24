# Backfill feasibility: 2017–18 event order and older feed eras

**Date** 2026-11-23. **Issue** [#90](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/90), under [#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53). Aggregates only: no game rows, events or lineups. NBA game data are attributed to NBA.com, for private noncommercial research ([sources](../data-sources.md)). Evidence classes follow [PROJECT_PLAN §2](../PROJECT_PLAN.md): **Documented**, **Inferred**, **Experimental**, **Original**.

The policy gates are the [#89](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/89) revision of M1. The hard limits are 97% game coverage for each season type and 0.1% unresolved possessions over the full season. Stratum coverage of 95% is a target and a warning. Structural, identity, chronology, scoring, lineup, minutes and plus-minus checks are never relaxed. All 26 `check` invariants pass for every build below, including the scratch builds with the opt-in repair.

## Part 1: why 2017–18 early-season games fail event order

The diagnosis comes from `scripts/event_order_diagnostics.py`, which is deterministic and read-only over a pinned snapshot and a finished build. It replays the order-class quarantines offline to find where the pinned parser fails. It also compares V2 file order, V3 action order and data.nba entry order (`ord`) for every game. The build is `issue-25-v1`.

### The mechanism (Inferred from measured feed differences)

- V2 rows are sorted by game clock. In all 1,230 regular-season games and the 2 order-class playoff games, V2 never has a clock that moves backwards.
- V2 event numbers do not rise monotonically in file order. They fall about 4.2 times per accepted game and 6.6 times per order-class quarantine. Most such falls are harmless late stat corrections.
- A late correction keeps the clock of the play it describes, but the feed enters it after later plays. Example class: a turnover stamped with the clock of the missed shot, entered after the offensive rebound that preceded it. V2 sorts it by that stale clock, so it sits before the rebound. The pinned parser then finds a rebound that does not follow a missed shot.
- data.nba `ord` records the entry sequence. Where it disagrees with the clock order, the late event is placed after the rebound and keeps its stale clock.
- V3 action order equals V2 order in 63 of 168 order-class quarantines (37%). So V3 cannot adjudicate the others, and its retry only helps when it differs. It fails, or does not apply, for all 168 games.

### Counts (regular season unless stated)

| Quantity | Value |
| --- | --- |
| Games, quarantined | 1,230, 178 |
| Order-class quarantines (both season types) | 168: 101 `parser_error`, 65 `unsupported_reorder` regular, plus 2 `unsupported_reorder` playoff |
| Other quarantines | 12: 4 `missing_period_start`, 4 plus-minus, 2 box-final, 1 period-score, 1 starters |
| `parser_error` signature | all `EventOrderError` at a rebound whose previous event is not a missed shot, except 2 `AttributeError`. The previous event is a rebound (35), turnover (19), free throw (13), violation (11), field goal (9), substitution (7), foul (3), replay (2) |
| `unsupported_reorder` | the parser's own rebound repair moved events across clocks, always including a rebound. The moved set also includes substitutions, timeouts, replays, fouls and turnovers |
| Order-class quarantines with a clock-breaking entry in data.nba order | 158 of 168 (94%); 161 have complete `ord` |
| Accepted regular games with one | 181 of 1,052 (17%) |

An entry is "clock-breaking" when removing the fewest events (latest-entered on ties) would make the entry-order clocks monotone. Those removed events are called displaced events. In order-class quarantines, 393 events are displaced, and rebounds (122) and turnovers (62) lead. Displaced clocks sit a median of 2 s from their predecessor in entry order. Only 16 of 393 carry an event number past their period's end event, so the "number beyond the period end" test is a poor detector. The entry order is the evidence.

### Why October to December

158 of 178 regular-season quarantines fall from October to December 2017, and the cause follows the rate of late-entered clock breaks, which falls steeply through the season. It does not follow quarantine-specific rules, which are unchanged.

| Window | Games | Quarantines | Order-class | Games with a clock-breaking entry | Displaced events per game |
| --- | ---: | ---: | ---: | ---: | ---: |
| Oct 16 to Nov 12 | 191 | 108 | 105 (55%) | 149 (78%) | 2.08 |
| Nov 13 to Dec 31 | 353 | 50 | 46 (13%) | 101 (29%) | 0.52 |
| Jan to Feb | 351 | 8 | 5 (1.4%) | 56 (16%) | 0.20 |
| Mar to Apr | 335 | 12 | 10 (3.0%) | 34 (10%) | 0.11 |

The unresolved-possession rate has the same shape: 1.61% in October, 0.99% in November, 0.59% in December, 0.32% in January and 0.08% to 0.12% from February. The step at mid-November is sharp (78% to 29%). The data show that the defect declines. They do not show why. A change in stat-keeping practice or a feed correction is plausible and is Inferred, not established.

### Proposed remediation (ADR-0023, proposed): entry-order repair

Retry a failed game in data.nba entry order and re-clock the late-entered events, subject to every existing check.

1. Apply only when the V2 attempt and the V3-primary retry both fail. A second use, offered to accepted games with unresolved possessions, is kept only when it leaves fewer unresolved possessions.
2. `ord` must be present for every V2 event, distinct, and period-monotone. Otherwise the game keeps its original failure.
3. Within each period, find the longest run of non-increasing clocks in entry order, preferring the earliest-entered events on ties. Each other event takes the clock of its predecessor in entry order. Period boundary events are never re-clocked, and a re-clocked first event fails the repair.
4. Parse that stream with the unchanged parser and run every unchanged reconciliation: V3 box final, period scores and substitutions, chronology, lineup, minutes within tolerance and exact plus-minus. A failure keeps the original quarantine.
5. Label the game `datanba_event_order`, a lower-trust stratum, with a warning that gives the largest clock shift.

This relaxes no hard check, but it rewrites source timestamps, and the shifts are not all small or all in one direction (see the next section). The repaired stream has monotone clocks by construction, so `unsupported_reorder` and `unresolved_clock_reset` cannot fire on the re-clocked events. Those two checks lose discriminating power on repaired games. Minutes, plus-minus, lineup and score reconciliation, the V3 checks, Bentes and pbpstats.com remain. data.nba shares upstream lineage with V2 and V3 (ADR-0010), so it is not independent proof of the true clock. The independent evidence is the unchanged reconciliation against box minutes and plus-minus, Bentes lineups and pbpstats.com possession counts. The pinned parser already uses this feed's order as its documented fallback, so this reuses its intent offline (**Documented**). The choice of predecessor-clock and of the tie rule is **Original**.

### Prototype (flag `--order-repair`, off by default)

Measured in new scratch builds of the `issue-25-v1` snapshot, which the build never modifies:

| Build | Regular accepted | Playoffs accepted | Unresolved possessions | Notes |
| --- | ---: | ---: | ---: | --- |
| `issue-25-v1` (baseline) | 1,052 of 1,230 (85.5%) | 80 of 82 | 0.391% | recorded in #25 |
| `issue-90-order-repair-v1` (failed games only) | 1,188 (96.6%) | 82 of 82 | 1,004 of 249,539 (0.402%) | +136 regular, +2 playoff |
| `issue-90-order-repair-v2` (also offers unresolved games) | 1,188 (96.6%) | 82 of 82 | 706 of 249,536 (0.283%) | 225 games carry the new stratum |

- The offline replay recovered 137 of the 168 order-class quarantines: 79 of 101 `parser_error` and 58 of 67 `unsupported_reorder` (both playoff games included). The two builds also recover the one `unresolved_starters` game. Both accept 1,188 regular games, 5 short of the 1,193 that the 97% limit needs.
- 31 order-class games stay quarantined: 22 `parser_error` and 9 `unsupported_reorder`. The 11 other quarantines are untouched.
- `check` passes 26 of 26 on both builds. Bentes lineups agree on 99.97% of court time over 1,270 covered games, lowest game 99.85%. In the 225 repaired games the lowest game is 99.88%. pbpstats.com possession counts are equal in 1,020 of 1,270 games, up from 871 of 1,132.
- Signed clock shifts in the 225 repaired games of `issue-90-order-repair-v2`, from `event_order_diagnostics.py --shifts` (positive means later in game time). 384 events were re-clocked: 160 (42%) moved earlier and 224 later. The median absolute shift is 3 s. 41 events moved more than 24 s and 17 more than 60 s. 33 games have a shift above 24 s and 17 above 60 s. The largest are +518 s, +498 s and +289 s (all replays), then a jump ball at +208 s and a turnover at +156 s. The largest earlier shift is -47 s.
- 377 re-clocked events have an actor, and 38 of those moved more than 24 s. The re-clocked events include 44 made field goals (12 earlier, from -41 s to +25 s), 8 free throws (-14 s to +47 s) and 21 substitutions (+1 s to +2 s). Median signed shift by type: rebounds -4 s (108 of 110 earlier), missed shots -7 s, made shots +3 s, turnovers +1 s, replays +26 s (20 of 39 over 24 s), fouls +1 s. The earlier example is game `0021700131`, where a miss and an offensive rebound move from 10:23 to 10:37, a shift of -14 s.
- Reconciliation accepted every one of these games, so the shifts did not break minutes or plus-minus. Whether they are right in time is not established. Safeguards are listed in ADR-0023 for the maintainer. None is implemented.
- **2017–18 still fails the 0.1% limit** (0.283%), and misses coverage by 5 games. The residual unresolved rate keeps the early-season shape (0.88% in October after repair), so order is not the only cause. That residual is the next investigation.

### Residual and other order-class patterns

- **Same-clock tip sequences (older eras).** In 2010–11, 22 of the 28 `parser_error` games are a rebound that follows a rebound. In the one inspected game the missed tip shot has the highest event number among three events at one clock, so V2's tie order puts it last. No archive before 2017–18 has `ord`, and V3 order equals V2 order in every older-era order-class quarantine measured (75 of 75 games). A rule for this needs its own evidence.
- **Quarantines that no order feed explains:** 4 `missing_period_start`, 4 plus-minus mismatches and 3 box or period-score mismatches in 2017–18.

## Part 2: older feed eras

One representative season per era of the [#51 batch plan](nba-feed-coverage.md#build-sequence). Each chosen season is the cleanest representative in its batch: it has no documented one-off exception in the register, so its result reflects the era. 2001–02 to 2003–04 was left out to stay within about four seasons. Its register entry has the same V2, V3, shot detail, box, Bentes and pbpstats.com files. A first build for that batch should come first.

| Era in the #51 plan | Seasons | Feeds | Representative |
| --- | --- | --- | --- |
| Transition | 2016–17 | V2, V3, data.nba without `ord`, no liveData | 2016–17 |
| V2/V3 baseline | 2012–13 to 2015–16 | V2, V3, no data.nba | 2014–15 (2012–13 lacks 16 V3 games, 2015–16 has V3 period anomalies) |
| V2/V3 baseline | 2008–09 to 2011–12 | same | 2010–11 (2009–10 has a pbpstats.com gap) |
| V2/V3 baseline | 2004–05 to 2007–08 | same | 2005–06 |
| V2/V3 baseline | 2001–02 to 2003–04 | same | not built |

### Setup (`pilot_sources.py` and loaders, minimal and tested)

- Pins for 2005, 2010, 2014 and 2016 were generated from the #51 register CSVs, and a test now compares every pin with the register. `pinned_season` still refuses 2025 and later.
- The archive's data.nba feed is optional where the register lists it as absent (before 2016–17). Its games get the `no_datanba` stratum, which is lower trust. Without data.nba, those seasons have no offense relabel and no data.nba period scores.
- The 2016–17 archives have offense keys without `ord`: the reader keeps offense and drops periods and order. `evidence` now ignores rows without `ord` for period scores and order agreement, so 2016–17 cannot report a false comparison.
- Captures use `--from-local` on the #51 audit directory with size and SHA-256 verification: 10 inputs and 6 evidence files for 2016–17, 8 and 4 for each older season. No download was made, and every payload was present locally.
- A 2022–23 rebuild at the final code is row-identical to `issue-19-v6` with `ingested_at` excluded. The 8 tables other than `game` and `game_stream` are byte-identical. In those two, 0 rows differ in either direction. Only `code_commit`, `generated_at` and the two table digests differ in the manifest.

### Results

All four builds pass 26 of 26 `check` invariants. Each build took 42 to 52 s with a peak of 0.74 to 0.80 GB.

| Season | Regular accepted | Playoffs accepted | Unresolved share | Hard gates | Quarantine causes |
| --- | ---: | ---: | ---: | --- | --- |
| 2016–17 | 1,209 of 1,230 (98.3%) | 79 of 79 | 132 of 251,344 (0.053%) | Pass | 14 `parser_error`, 4 `unresolved_event_order`, 2 plus-minus, 1 starters |
| 2014–15 | 1,210 of 1,230 (98.4%) | 78 of 81 (96.3%) | 40 of 246,347 (0.016%) | Regular passes. Playoffs miss 97% by one game | 9 `parser_error`, 7 `unsupported_reorder`, 3 `unresolved_event_order`, 1 each plus-minus, starters, period end, unknown possession |
| 2010–11 | 1,187 of 1,230 (96.5%) | 80 of 81 (98.8%) | 52 of 236,896 (0.022%) | Regular misses 97% by 8 games | 28 `parser_error`, 9 plus-minus, 4 `unresolved_event_order`, 1 each `unsupported_reorder`, shooter outside lineup, V3 period score |
| 2005–06 | 1,220 of 1,230 (99.2%) | 88 of 89 (98.9%) | 47 of 242,144 (0.019%) | Pass | 3 `parser_error`, 2 starters, 2 `unsupported_reorder`, 1 each period end, shooter outside lineup, V3 box final, V3 period score |

Stratum warnings (target 95%) among the overtime, technical-free-throw and same-clock substitution strata: 2016–17 regular overtime 66 of 70 (94.3%) and 2005–06 playoff overtime 9 of 10. All other strata of these kinds are at or above 95%.

Verification strength, all **Documented** by the pinned `evidence` command:

| Season | Bentes lineups, time-weighted (lowest game) | pbpstats.com possessions equal / within 2 | V3 final, period and substitution checks | Missing evidence |
| --- | --- | --- | --- | --- |
| 2016–17 | 99.97% (99.78%) over 1,288 games | 1,240 / 1,259 of 1,288 | all games checked | `ord`: no period scores or order. Offense keys agree on 313,274 of 313,280 accepted events. No liveData |
| 2014–15 | 99.996% (96.03%) over 1,288 | 1,269 / 1,278 of 1,288 | 3 playoff games unchecked for periods | no data.nba, no liveData |
| 2010–11 | 100% (100%) over 1,267 | 1,243 / 1,253 of 1,267 | all checked | no data.nba, no liveData |
| 2005–06 | 100% (100%) over 1,308 | 1,287 / 1,298 of 1,308 | all checked | no data.nba, no liveData |

The 2014–15 lowest game of 96.0% is one outlier. The other three seasons have no game below 99.7% for Bentes. Starter inference depends on the box-guided search: 9, 13, 13 and 14 team-periods were inferred, and Bentes agrees with 9 of 9, 11 of 13, 10 of 13 and 13 of 14. Older seasons therefore carry weaker starter verification, as ADR-0020 recorded for 2017–19.

### Older-era order-class quarantines

Order-class quarantines are 18, 17, 32 and 4 regular games respectively (plus 0, 2, 1 and 1 playoff). V3 order equals V2 order in all of them. 2010–11 is dominated by the same-clock rebound-after-rebound pattern. No data.nba `ord` exists for repair in these eras, so a different rule is needed (see above).

## Part 3: recommended split of #53

Evidence is one season per era, so viability is an estimate. A batch is "viable" if its seasons are expected to meet the hard gates for both season types, or miss only by a few games on a small denominator.

| Batch | Seasons | Expected viability | Estimated effort | Notes |
| --- | --- | --- | --- | --- |
| 1. 2016–17 | 2016–17 | **Viable now.** Built and checked at the gates. | Small. About half a session: pins exist, review and record | Documented evidence tier weaker: data.nba without `ord`, no liveData |
| 2. 2004–05 to 2007–08 | 4 seasons | **Likely viable** from the 2005–06 result | Small to medium. One session: 4 pins, 4 builds of about 1 min, strata review | Check 2005–06 V3 anomaly games in sibling seasons |
| 3. 2012–13 to 2015–16 | 4 seasons | **Probably viable** (2014–15 passes except one playoff game). 2012–13 may fall near 97% because 16 games have no V3 | Medium. One session | Playoff denominators of 80 games make a one-game miss a warning under the revised policy |
| 4. 2008–09 to 2011–12 | 4 seasons | **Uncertain.** 2010–11 regular is 96.5% from a same-clock rebound pattern | Medium to large if a new repair rule is needed (separate ADR), small to just build and record | Decide whether to accept coverage warnings or write the rule first |
| 5. 2001–02 to 2003–04 | 3 seasons | **Unknown.** Not probed | Small first probe, then as batch 2 | Run one build before committing the batch |
| 6. 2017–18 remediation | 2017–18 | **Not viable yet.** The repair reaches 96.6% coverage, 5 games short, and 0.283% unresolved against 0.1% | Medium. Decide ADR-0023, then diagnose the residual unresolved rate | Needs the maintainer's decision on re-clocking late-entered events |
| 7. Other `ord` seasons | 2018–19 to 2021–22, 2022–23 to 2024–25 | **Optional.** All pass or are conditioned already | Small experiment | Measure whether the repair lowers unresolved shares in these seasons before any default change |

Recommended order: batches 1, 2 and 3 first, since they need no pipeline change. Batch 5 as a one-season probe at the same time. Batch 4 after a decision on a same-clock rebound rule. Batch 6 in parallel with an ADR-0023 decision. A first-pass total of about 4 to 6 sessions, including independent review, is a rough estimate (**Inferred** from the build times and diffs here).

## Reproduce

```sh
M=/path/to/repo; A=$M/data/raw/historical-feed-audit/2026-11-23
.venv/bin/python -m bil.data.pilot capture $M/data/raw/2016-17/issue-90-v1 --season 2016 --from-local "$A"
.venv/bin/python -m bil.data.pilot capture-evidence $M/data/raw/2016-17/issue-90-evidence-v1 --season 2016 --from-local "$A"
.venv/bin/python -m bil.data.pilot build $M/data/raw/2016-17/issue-90-v1 $M/data/processed/2016-17/issue-90-v1 --code-commit <sha>
.venv/bin/python -m bil.data.pilot check $M/data/processed/2016-17/issue-90-v1 $M/data/raw/2016-17/issue-90-v1
PYTHONPATH=src .venv/bin/python scripts/event_order_diagnostics.py \
  $M/data/raw/2017-18/issue-25-v1 $M/data/processed/2017-18/issue-25-v1 --simulate-repair --report diag.json
.venv/bin/python -m bil.data.pilot build $M/data/raw/2017-18/issue-25-v1 $M/data/processed/2017-18/issue-90-order-repair-v2 \
  --code-commit <sha> --order-repair
PYTHONPATH=src .venv/bin/python scripts/event_order_diagnostics.py \
  $M/data/raw/2017-18/issue-25-v1 $M/data/processed/2017-18/issue-90-order-repair-v2 --shifts
```

The older builds ran at `c079ba8`, before the opt-in flag existed. The default path is unchanged since, and the 2022–23 equivalence above holds at the final code. The 2025–26 and 2026–27 payloads were never listed, opened or read.
