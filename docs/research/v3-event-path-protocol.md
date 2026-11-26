# V2-free event path: validation protocol

**Registration:** [#133](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/133). This protocol is committed before any V3-event build of 2023–24 or 2024–25 is run.

**Classification:**
- **Development validation** of a data-pipeline component (Inferred). It is not model evidence.
- **Holdout.** The 2025–26 holdout is not read. Only file names and HTTP headers of its files were seen (#42 exposure table).

**Why.** The NBA retired the V2 play-by-play endpoint. The pinned archive has no 2025–26 `nbastats` (V2) file, and the pilot build parses V2 events for every game. For 2025–26 the archive does hold V3 actions (`nbastatsv3`) and liveData (`cdnnba`).

## 1. Method (frozen at the registration commit)

**Where.** `bil/data/pilot_v3_events.py`, version `v3-live-events-1`, opt-in through `pilot build --event-source v3`.

**What it does.** For each game it rebuilds the V2 rows the parser and build read, from V3 actions and liveData. V2 is never opened. Everything downstream of the event rows is unchanged: the parser, checks, repairs, row builder and models.

- **Event identity.** V3 `actionNumber` is the V2 `EVENTNUM`. The rows of one number form one event. The first typed row is the primary action, and untyped rows carry its block or steal.
- **Event order.** V3 action order (`actionId`), except that a period's start row leads its period.
- **Types.** V2 `EVENTMSGTYPE` and `EVENTMSGACTIONTYPE` come from a table of 186 V3 `(actionType, subType)` pairs.
  - The table was learned on 2020–23. Every pair maps to one V2 code except one-off source quirks.
  - A new shot subtype becomes a plain made or missed shot (shot codes are unread).
  - Any other unknown pair quarantines the game.
- **Clock.** `PTmmMss.ffS` becomes `m:ss` with tenths truncated, as in V2.
- **Descriptions.** Each V3 row's text goes to the home, visitor or neutral column by its team. Double fouls and double technicals are neutral.
- **Home team.** Inferred from V3 running scores: a team's baskets move `scoreHome` exactly when it is home.
  - At least 90% of each team's scoring changes must agree, with at least 5 per team.
  - A conflict with a box home flag quarantines the game.
  - Games without a box flag take the inferred side.
- **Players.**
  - **Player 1 and its team:** from the primary V3 row. Team actions keep the team ID as the player and no team.
  - **Assist:** from the liveData row with the same event number and period.
  - **Steal and block:** from V3's untyped rows, with liveData as the fallback.
  - **Foul drawn and both jump-ball players:** from liveData.
  - **Double-foul partner:** from liveData.
  - **Incoming substitute:**
    1. The surname in the V3 text "SUB: X FOR Y", if it names exactly one player of that team in the game's own V3 rows.
    2. Otherwise a liveData `in` row of the same team in the same substitution batch.
    3. Otherwise one at the same clock.
    4. Otherwise the game is quarantined.
  - **Secondary player teams:** from the box roster.

**Known losses of independence.**
- **liveData** supplies player IDs here, so liveData starters and checks are no longer fully independent of the events.
- **V3 cross-checks** become self-checks: the period scores, the substitution counts and the V3-order fallback.

## 2. Development seasons and exposure

- **Development.** The table and every rule were developed on **2020–21, 2021–22 and 2022–23** only. The work used field-level agreement with archived V2 and full builds compared with the canonical `issue-93-v1` rows.
- **Exposure of the validation seasons.** Before registration, the agent printed about 30 rows of one 2024–25 game (`0022400001`) from V2, V3 and liveData, to read the schema. No 2023–24 or 2024–25 V3-event build, field comparison or row comparison has been run.

Development results at the registration code (`issue-133-dev-v3`):

| Season | Regular games V2 / V3 | Playoff games V2 / V3 | Rows differing | Points V3 − V2 | Lowest non-description field agreement |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2020–21 | 1,072 / 1,072 | 85 / 85 | 0.113% | −40 (−0.018%) | 99.983% |
| 2021–22 | 1,219 / 1,218 | 87 / 86 | 0.113% | −43 (−0.018%) | 99.979% |
| 2022–23 | 1,208 / 1,219 | 84 / 84 | 0.151% | −125 (−0.050%) | 99.985% |

- **Checks.** All 26 `check` invariants pass in every development build, and no game failed to rebuild.
- **Row differences.** They come mostly from substitutions between free throws: V3 and V2 store some of them in different places, so a few possessions change lineup, or become multi-lineup and drop out.

## 3. Validation runs

For each validation season, 2023–24 and 2024–25, from snapshot `issue-52-v1`:
1. `pilot build --event-source v3` with default flags, into a new directory.
2. `pilot check`.
3. `rapm_rows`, canonical variant.
4. `event_source_comparison rows`, against the season's `issue-93-v1` row set.
5. `event_source_comparison fields`.

Then, once for both seasons:
- `scripts/season_quality.py --run-checks` on the two builds.
- `scripts/v3_event_model_check.py`, with the 2023 and 2024 rows replaced by the V3-event row sets. This reruns the frozen #36 outer evaluation unchanged.

## 4. Limits

All limits must hold in both seasons.

| ID | Limit |
| --- | --- |
| L1 | Every `check` invariant passes. |
| L2 | The ADR-0022 hard limits pass: at least 97% of expected games accepted for each season type, and at most 0.1% unresolved possessions. |
| L3 | Regular-season accepted games: V3 is at least V2 minus 15. |
| L4 | Row mismatch share is at most 0.5%. It counts possession rows that differ in period, offense team, either lineup or points, in games both builds accept. |
| L5 | Modeled points differ by at most 0.2% in games both accept. |
| L6 | Field agreement is at least 99.5% for event type, action type, period, clock and the three player IDs. Descriptions are excluded because sources differ in name formatting. |
| L7 | In the #36 rerun, the pooled regular-season `ei` − `rapm_context` delta moves by at most 0.5 (points per 100)². Both of its intervals still exclude 0, and every #36 verdict is unchanged. |

## 5. Outcome rules

- **All pass.** A proposed ADR adopts the path for seasons without V2. Its use in R1 then needs an amendment of #42 §4.1–4.2:
  - 2025–26 is built with `--event-source v3` at the frozen code.
  - The 2023–24 and 2024–25 rows stay the V2-built `issue-93-v1` sets.
  - Everything else is unchanged.
- **Any fail.** The failure is reported and the path is not adopted. The adapter is not tuned on 2023–24 or 2024–25: they would then be development seasons, and no V2-paired validation season with liveData would remain. #42 stays blocked.
- **Single shot.** A crash before a comparison is written allows a rerun at the same code.

**Residual risk.** The 2025–26 V3 and liveData formats cannot be inspected before R1 freezes. New action types, changed numbering or missing liveData there would show up as quarantined games at the #42 quality gate, which ends the confirmatory attempt.
