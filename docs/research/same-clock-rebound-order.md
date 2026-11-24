# Same-clock shot, tip and rebound ordering (rule `same-clock-v1`)

**Date** 2026-11-24. **Issue** [#111](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/111), under [#53](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/53). **Decision** [ADR-0028](../DECISIONS.md#adr-0028--opt-in-same-clock-rebound-ordering-rule-same-clock-v1). **Experiment** [EXP-0018](../experiment-log.md). Aggregates and cited event numbers only. NBA game data are attributed to NBA.com, for private noncommercial research ([sources](../data-sources.md)). Evidence classes: **Documented**, **Inferred**, **Experimental**, **Original** ([PROJECT_PLAN §2](../PROJECT_PLAN.md)). No EPM output was used for anything.

## What failed, and why

Backfill probes left 2010–11 below the 97% regular-season coverage floor (96.5%) and recorded the cause as a rebound that follows a rebound ([backfill feasibility](backfill-feasibility.md)). The new builds of 2008–09 through 2011–12 show the same mechanism in all four seasons.

- V2 rows are sorted by clock. Events that share one clock keep an order that is not event order and not game order. V3 action order equals V2 order in the older eras, and no archive before 2017–18 has data.nba `ord`, so no other feed can adjudicate it (**Inferred** from measured equality, #90).
- A tip-in or putback attempt is entered late and takes a high event number. At one clock V2 then lists, for example, `miss, rebound, rebound, tip miss`. The pinned parser reaches the second rebound, finds a rebound whose predecessor is not a missed shot, and raises `EventOrderError`. Its own repairs (`_fix_common_event_order_error`) only cover event numbers that differ by exactly one or two, so most of these games fall through to the V3 fallback and quarantine as `parser_error`, `unresolved_event_order` or `unsupported_reorder`.
- The most common signature among the quarantined games is `miss | rebound, rebound, miss` (a miss at an earlier clock, then two rebounds and a late tip attempt at one clock). The rule recovers 48 games in the four target seasons (4, 12, 23 and 9), shown in the table below.

Which seasons failed because of it: **2010–11** (regular 96.5%, below the floor) and **2011–12** (regular 96.97% before the rule). 2008–09 (97.7%) and 2009–10 (97.8%, playoffs 98.8%) already met coverage and gain a few games. The rule also recovers games in every older season it was tried on (below).

## The rule (`same-clock-v1`, **Original**, derived from basketball semantics)

Applied to one clock group (same period and same `PCTIMESTRING`), in V2 order, never across clocks:

1. Every rebound follows exactly one missed field goal or missed free throw. The pinned parser also accepts subs and timeouts in between, and one jump ball after a miss (a held ball after a blocked shot), so the rule does too.
2. A rebound without such a predecessor is an **orphan**. Its missed shot is a later missed field goal of the same group, entered late. Only a field goal can be a tip or putback, so free throws are never moved.
3. A shot at one clock is taken by the team that holds the ball. A rebound gives the ball to its team, and a made field goal or a turnover gives it to the other team, looking back through subs and timeouts. A candidate of another team is excluded. If the last event does not say who holds the ball (a foul, a free throw, a jump ball), the other tests decide. This is the only team test, and it does not look at downstream results.
4. A candidate is never taken from beyond a period start or end event. Only order inside the group changes. Clocks and rows are not edited.
5. Exactly one candidate must remain. With none (`no_candidate`), or with several of the same or different teams (`ambiguous_candidates`, `ambiguous_team`), the rule **declines the whole game** and it keeps its original quarantine. Several same-team candidates would swap shooters and rebounders between plays. That is not a possession change but it is a different attribution, so it is quarantined instead of settled by a tie-break.

Properties:

- Deterministic: a pure function of the V2 stream. No search, no permutation test, no reconciliation feedback. No evidence feed is used as an input.
- Opt-in and versioned: `build --same-clock-rule`, recorded in the manifest as `same_clock_rule.version = "same-clock-v1"`. The default build is unchanged.
- Retry only: it runs after the V2 order and the V3-primary retry both failed. A game that was accepted by those paths is never offered the rule, so previously accepted games cannot change by construction. (ADR-0023's `--order-repair` is untouched. If both are on, the rule runs first.)
- Every unchanged check still runs on the new stream: structure, identity, chronology, lineup, minutes, exact plus-minus, V3 box final, period scores and substitutions. Each accepted game carries stratum `same_clock_order` and a warning naming the moved shot and the rebound it now precedes. Declined or failed attempts leave a `same_clock_declined` or `same_clock_rejected` warning on the quarantined game. The manifest lists every game with its outcome.

The pinned parser's own jump-ball and substitution tolerances are mirrored, so orphans that the parser accepts are not touched. The choice of tests 2 to 5 is **Original**. The mechanism of the failure is **Inferred** from measured feed differences.

## Hand-adjudicated real examples

Event numbers are V2 `EVENTNUM`. V2 order is the order the parser receives.

| Game | Clock | V2 order | After rule | Adjudication |
| --- | --- | --- | --- | --- |
| `0021001016` | P2 7:51 | 134 miss (Roy), 166 rebound (Camby), 136 rebound (Aldridge), 169 miss tip (Camby), 135 made layup (Aldridge) | 134, 166, 169, 136, 135 | Camby offensive rebound, Camby tip misses, Aldridge offensive rebound, Aldridge scores. 136 had no miss before it, 169 is the only same-team candidate. Bentes' independently processed order is the same. Tip-in and putback chain |
| `0021001063` | P1 1:07 | 95 miss (Bayless), 103 rebound (Bargnani), 96 rebound (Evans), 105 miss tip (Bargnani) | 95, 103, 105, 96 | Bargnani rebound then tip miss, then Evans rebound. Same team, one candidate |
| `0021001077` | P3 1:59 | 348 miss (Okafor, blocked), 352 rebound (Landry), 349 rebound (Frye), 354 miss layup (Childress block on Landry) | 348, 352, 354, 349 | Blocked shot is an ordinary type-2 miss. Landry's rebound then blocked layup, then PHX defensive rebound by Frye |
| `0021000145` | P3 11:04 | 278 blocked miss, 279 rebound (Randolph), 287 rebound (Randolph), 289 miss layup (Randolph), 280 later | 279, 289, 287 | Putback attempt after a blocked miss. Self-rebound |
| `0020900207` | P1 6:52 | 44 miss, 49 rebound (Gasol), 45 rebound (Gallinari), 51 miss tip (Gasol) | 44, 49, 51, 45 | Gasol offensive rebound, tip miss, Gallinari defensive rebound. Bentes breaks the tie on a duplicate sequence number, so its disagreement carries no information |
| `0020600100` | P2 6:31 | 213 sub, 214 rebound (ATL Williams), 226 miss (MIL Blake) | 226, 214 | A MIL miss and an ATL defensive rebound: the miss comes first or the rebounding team could not have held the ball. Bentes keeps the late entry after the rebound, which is the unrepaired order |
| `0020600881` | P3 0:00 | 410 made FT, 413 team rebound (CLE), 418 miss (James 27' three), 414 end of 3rd | 410, 418, 413, 414 | Period-end shot: the buzzer-beater miss, then the team rebound placeholder, then the period end. The shot is not taken from beyond the period end event |

Declined by design:

- `0021000016` P2 7:40: two Camby tip misses (197, 218) are both same-team candidates for the second rebound (213). Which came first changes shooters, not possessions, but it is not settled by the feed, so the game stays quarantined (`ambiguous_candidates`). Bentes and the entry order disagree on which comes first.
- `0021000044` P3 4:19: team rebound 357 follows free throw 356 whose text has no `MISS ` marker and no points. That is a separate defect, below.

And-ones need no rule: a made field goal, a foul and a free throw at one clock carry no orphan rebound. Tests cover it.

### Corroboration with an independent feed

The rule never reads Bentes. After the builds, each applied move was compared with Bentes' `number_event` order (a different processing of the same V2 rows). In the four target seasons 47 of 48 moves agree (4 of 4, 11 of 12, 23 of 23 and 9 of 9). The one that does not, `0020900207`, has a tied sequence number in Bentes. In the other builds up to 2014–15 the moves agree in 35 of 40, and the five that do not, such as `0020600100` and `0020600881`, are cases where Bentes leaves the late-entered shot after its rebound. For 2015–16 and 2016–17 Bentes' order equals the unrepaired V2 order (1 of 6 and 0 of 7 moves agree), so it cannot corroborate there. Example `0021600004` P3 5:45: V2 lists ORL rebound 374, MIA rebound 371, then ORL tip miss 375, so an ORL shot would follow a MIA rebound at one clock. The rule gives 374, 375, 371, which is the only order where each rebound follows a miss and the shot follows its own team's rebound. The agreement is supporting evidence and not independent proof, because Bentes also processes V2 rows.

## Results

All builds pass 26 of 26 `check` invariants. Builds are the `issue-111-rule-v5` directories at `1055a39f` (default comparison builds `issue-111-base-v2` at the same commit). Accepted games before and after the rule are compared in six tables (`event`, `possession`, `lineup`, `stint`, `score_allocation`, `event_actor`, `ingested_at` excluded).

### Regression: previously accepted games

| Season | Base accepted (regular, playoffs) | With rule | Games accepted in both, rows differing | Newly accepted | Declined, rejected |
| --- | --- | --- | ---: | ---: | --- |
| 2018–19 (`issue-25-v1`) | 1,206, 80 | 1,206, 80 | 0 | 0 | 20, 0 |
| 2006–07 (`issue-97-v1`) | 1,209, 78 | 1,214, 78 | 0 | 5 | 1, 0 |
| all 15 other builds below | | | 0 | 0 to 23 | |

2018–19 is row-for-row unchanged in every table. For every season, the games accepted by the default build are row-identical, as predicted by the retry-only design. The only changes are newly accepted games, each listed in its manifest. Possession totals rise only by the possessions of those games, and the unresolved count by the unresolved possessions inside them (2006–07: 65 to 67 from the 5 new games).

### Rebuilds by season

| Season | Default regular (playoffs) | With rule regular (playoffs) | New games | Declined / rejected | Unresolved share | Revised class (ADR-0022) |
| --- | --- | --- | ---: | --- | ---: | --- |
| 2008–09 | 1,202 (85 of 85) | 1,206 (85 of 85) | 4 | 21 / 0 | 0.024% | Meets (also by default) |
| 2009–10 | 1,203 (81 of 82) | 1,214 (82 of 82) | 12 | 12 / 0 | 0.023% | Meets (also by default) |
| 2010–11 | 1,187 (80 of 81) | 1,209 (81 of 81) | 23 | 9 / 0 | 0.022% | **Meets, newly** (default fails) |
| 2011–12 | 960 of 990 (81 of 84) | 969 of 990 (81 of 84) | 9 | 13 / 1 | 0.021% | Fails: playoffs 81 of 84 (96.4%) |
| 2004–05 | 1,203 (81 of 84) | 1,204 (82 of 84) | 2 | 1 / 1 | 0.028% | **Meets, newly** (default fails) |
| 2014–15 | 1,210 (78 of 81) | 1,212 (79 of 81) | 3 | 10 / 0 | 0.016% | **Meets, newly** (default fails) |
| 2012–13 | 1,187 of 1,229 | 1,192 of 1,229 | 5 | 11 / 0 | 0.024% | Fails: regular 96.99% (6 short before, 1 game short now) |
| 2013–14 | 1,198 (86 of 89) | 1,203 (86 of 89) | 5 | 17 / 0 | 0.020% | Fails: playoffs 96.6% |
| 2001–02, 2002–03, 2003–04 | | | 4, 0, 4 | 5/1, 3/0, 6/0 | | Still fail (playoffs 63 of 71, 85 of 88, 79 of 82) |
| 2005–06, 2007–08, 2015–16, 2016–17 | | | 2, 9, 5, 7 | | | Unchanged class, a few more games |

Class changes: **2010–11, 2004–05 and 2014–15 move from "fails hard limit" to "meets"** under the rule. 2011–12 and 2012–13 miss by one game each, so the rule does not rescue them, and no threshold was relaxed. 2011–12's remaining playoff quarantines are two `unsupported_reorder` and one `parser_error` that is not a same-clock miss.

### Verification (pinned `evidence`, **Documented**)

Bentes lineups: time-weighted agreement 100% in 2008–09 through 2011–12 and 2004–05 (lowest game 100%), 99.996% in 2014–15 (lowest game 96.0%, the same outlier as before). pbpstats.com possession counts equal in 1,263 of 1,291 games (2008–09), 1,272 of 1,296 (2009–10), 1,266 of 1,290 (2010–11), 1,032 of 1,050 (2011–12), 1,254 of 1,286 (2004–05) and 1,272 of 1,291 (2014–15). Inferred starters agree with Bentes in 17 of 18, 14 of 15, 10 of 13, 15 of 18, 10 of 11 and 11 of 13 team-periods. No liveData, no data.nba and no `ord` exist for these seasons, so period-score and event-order comparisons against another feed are unavailable.

### A defect the first review found, and the fix

The first independent review of the PR found that an earlier version checked the ball only when the previous event was a rebound. In 2015–16 game `0021500061` P3 8:04 V2 lists 272 (Aldridge made putback), 271 (Aldridge rebound), 270 (Leonard miss). The earlier rule moved 270 before 271 and produced 272, 270, 271: SAS scored and then missed with no change of possession, and the game's three unresolved possessions sat at that clock. The real order is 270, 271, 272. Of 101 moves, 16 had no prior same-team rebound, and this was the only one inconsistent with possession. The current rule infers the ball from the last non-skippable event (rebound, made field goal, turnover) through subs and timeouts, so the putback case is declined. Rebuilding every season changes exactly one game against the earlier build: `0021500061` is now quarantined (2015–16 regular 1,214 to 1,213). Nothing else changed in any of 17 builds, and eligibility classes are unchanged. The rule's output is also now the only order offered to the parser on the retry, so the parser's data.nba fallback cannot swap in the V3 order.

## What the rule does not fix

44 of the 55 declined games in 2008–09 through 2011–12 hold a **team rebound that follows a free throw with no `MISS ` marker and no points**. The parser reads that free throw as made and the rebound as orphaned. Whether that free throw was a miss is settled by a score that did not change, which is a different evidence rule. It would recover most remaining quarantines in these seasons and deserves its own issue and ADR. The rest are cross-clock reorders (`unsupported_reorder`), plus-minus mismatches and missing period ends, which this rule does not touch.

## Limits

- The rule resolves the order of events inside one clock. Which of two same-team tip attempts came first is declined, not guessed.
- Bentes agreement is supporting, not independent. The unchanged reconciliation (box minutes, exact plus-minus, V3 scores) is the independent check, and the pbpstats counts are a coarse one.
- The shooter's team test relies on `PLAYER1_TEAM_ID`. A blank team falls back to `PLAYER1_ID` for team rebounds. Rows with neither skip the team test.
- 2011–12 and 2012–13 are one game from eligibility. That is a threshold result, not a data quality statement.

## Reproduce

```sh
M=/path/to/repo; A=$M/data/raw/historical-feed-audit/2026-11-23
uv run python -m bil.data.pilot capture $M/data/raw/2011-12/issue-111-v1 --season 2011 --from-local "$A"
uv run python -m bil.data.pilot capture-evidence $M/data/raw/2011-12/issue-111-evidence-v1 --season 2011 --from-local "$A"
uv run python -m bil.data.pilot build $M/data/raw/2011-12/issue-111-v1 $M/data/processed/2011-12/issue-111-rule-v5 \
  --code-commit <sha> --same-clock-rule
uv run python -m bil.data.pilot check $M/data/processed/2011-12/issue-111-rule-v5 $M/data/raw/2011-12/issue-111-v1
```

Pins for 2008–09, 2009–10 and 2011–12 were generated from the #51 register, and the existing register test covers them. No payload was downloaded, and no 2025–26 or later file was read.
