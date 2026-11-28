# Validated game-level possession source fallback

Design checkpoint for [#165](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/165). The smallest implementation accepts a complete, independently qualified alternate game stream through the existing pilot checks and row builder. Candidate or conditionally usable streams can be exercised in a separate development build. Canonical selection depends on [#133](https://github.com/andrewcukierwar/basketball-intelligence-lab/issues/133) and explicit approval of the source and scope. [Machine-evidence audit](machine-only-possession-source-audit.md)

## Capability and mapping

Pin one capability record per provider and adapter revision, with allowed seasons and game types, leaf asset IDs and data digests, deterministic crosswalk, availability and rights evidence, event taxonomy and known coverage gaps. Each qualification names the precise output grain, event families and reliability status. Ten-player clock intervals, individual plus-minus and final scores cannot certify action order or scoreless possession ownership. Rosters, box scores, officiating evidence and independently qualified companion fields have their own pins and authority. Use them to reconcile a proposed stream. A companion field enters a normalized event only through its pinned one-to-one mapping, with a source ref on the field’s event or actor. Unmatched fields remain missing under their declared failure rule.

At the adapter boundary, map official game and team keys, period and effective clock, event order and taxonomy, actor roles, scores and adjustments, full lineups and control. Provider keys remain opaque. Require the existing explicit identity crosswalk for non-NBA IDs and valid NBA date/team/type assertions. Normalize to the current [data contract](../data-contracts.md) and retain raw event locators. A corrected provider action keeps its raw clock and a documented effective clock. The same-clock substitution/free-throw fixture must validate both control and credited lineup separately.

| Candidate | Potential scope from current evidence | Open gate |
| --- | --- | --- |
| Existing V2 and supported retries | Already-registered historical snapshots and existing approved repairs | Existing coverage and documented policy |
| Bill Mill V3 and game rotations | Development event/lineup corroboration and candidate raw V3 stream | Complete companion roles, ownership and independent lineup/event evidence |
| Bentes event, possession and stint tables | Development cross-check on declared table grain, possible newer CDN companion | Game-level score allocation and event/owner joins, field lineage and independent reference |
| NBA Lineup Model | Development segmentation and lineup implementation comparator | Same NBA upstream and validation on an actual eligible holdout |
| ESPN and targeted official reports | Event actor, clock or official scoring corroboration for matched cases | Complementary use only under proven grain and rights, with unmatched and ambiguous records counted |

## Selection and revision rules

Resolve the set of input revisions for exactly one official game and cutoff using the existing availability rules. For research, a later capture may enter only a separately labelled retrospective version. Pin the preferred source first for each explicit eligibility scope and order at most one alternate source after it for the first implementation. A candidate's status includes the gates failed, evidence coverage, comparison revision and reason. Use the following table after resolving revisions.

| Preferred result | Alternate result | Decision |
| --- | --- | --- |
| Accepted with valid pins | Any | Use the preferred stream. Log the comparison if one ran. |
| Missing or ordinary supported-parse failure | Independently qualified and all gates clear | Use the whole alternate stream in an approved scope. Otherwise only emit a development candidate. |
| Missing or ordinary supported-parse failure | Missing, conditional, ambiguous, or failed any check | Keep the game quarantined for that scope. |
| Unresolved identity, rights, authority, official score or revision conflict | Any | Quarantine until the official conflict is resolved and the affected revisions are revalidated. |
| Previously accepted stream is invalidated by a later visible correction or retraction | Any | Make the prior stream ineligible from the new visibility time. Re-run selection against the new official revision and evidence. Earlier origins still resolve their original revisions. |

Generate one canonical stream revision per accepted or quarantined decision. The decision identity uses the official game and revision, source and adapter revisions, ordered immutable leaf digests, reconciliation view, eligibility scope, capability/policy versions and disposition. Assign revision numbers within the game by canonical correction order. Preserve original winning and failed source decisions with reconciliation receipts. Identical retry input gives the same result and identity. Conflicting bytes under a provider revision require adjudication. Publish all child tables for an accepted stream atomically, then expose the new manifest. An interrupted build leaves no partial winning stream. No event or lineup from a failed candidate may be interleaved with another source's stream.

## Staged implementation and validation

1. Define the capability and reconciliation receipt and test deterministic selection over normalized fixture streams. Cover duplicate provider rows and games, ambiguous keys, source outage, preferred-source recovery, retraction, late correction, missing period, and failed publication. Include fixtures for a scoreless wrong-side possession, minute/plus-minus agreement hiding a lineup swap, and credit during substitutions. Use the current pilot and RAPM row checks and chronological revision resolver as the contract.
2. Qualify one alternate with #133 using frozen counts, all existing hard checks and separately observed ownership/lineup evidence. Reconcile final and period score, cross-source ordering and clocks, player minutes and plus-minus, five valid players per team, total score allocation and decisive attempts and turnovers. Keep unresolved and conditional counts for all expected games. On games both paths accept, report exact event, lineup, possession and modeled-row differences by reason and exposure. Report recovered games and losses by time, team, source and event family, and run the paired outcome test from the approved registration. A fallback cannot mask a hard conflict with the official game. Preserve earlier #133 verdicts.
3. Separately approve production selection and recurring capture. #166 and #167 consume only versions accepted for their exact scope. The historical leads in #162 and #163 can exercise this design on exposed games with retrospective findings.

Keep the alternate out of canonical output if any required independent evidence grain, crosswalk, source-clock proof or reconciliation is unavailable. Publish performance, input coverage and the failure record even when no alternate can be accepted.
