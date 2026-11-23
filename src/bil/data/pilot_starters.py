"""Choose period starters offline when parsed events leave them ambiguous.

The pinned parser infers each period's starters from that period's events. A player who is on
court for a whole period without recording an event is invisible to that rule, and a player whose
event precedes a missing substitution appears as a sixth starter. The parser would then request a
live time-filtered box score, which the offline pilot cannot use.

Instead, every candidate starter set is reconstructed with the full acceptance checks. A game is
accepted only when exactly one candidate assignment passes. Box minutes and plus-minus therefore
act as selection evidence for these games, while V3 period scores, the substitution signature and
the structural lineup, clock and possession invariants remain independent checks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import combinations, product
from typing import Generic, TypeVar

from bil.data.pilot_inputs import GameIssue, PlayerBox
from bil.data.pilot_parser import StarterGap, Starters

T = TypeVar("T")
MAX_ATTEMPTS = 256


@dataclass(frozen=True)
class StarterChoice(Generic[T]):
    result: T
    starters: Starters
    candidates_tried: int
    # Several candidates reconciled but all produced the same reconstruction.
    immaterial: bool = False


def candidate_starters(
    team: int, partial: tuple[int, ...], roster: dict[int, PlayerBox]
) -> list[tuple[int, ...]]:
    """List five-player sets consistent with the starters events already identify."""
    if len(set(partial)) != len(partial):
        return []
    if len(partial) > 5:
        return [tuple(sorted(chosen)) for chosen in combinations(sorted(partial), 5)]
    pool = sorted(
        player
        for player, box in roster.items()
        if box.team_id == team and box.minutes_ms > 0 and player not in partial
    )
    return [tuple(sorted((*partial, *extra))) for extra in combinations(pool, 5 - len(partial))]


def choose_starters(
    attempt: Callable[[Starters], T],
    roster: dict[int, PlayerBox],
    fingerprint: Callable[[T], str],
) -> StarterChoice[T]:
    """Run ``attempt`` with no choices, then search starter candidates if a period is ambiguous.

    ``attempt`` must raise ``GameIssue`` whenever a reconstruction fails acceptance. Accept one
    reconciling candidate, or several whose reconstructions have the same ``fingerprint``. The
    parser can discard an early starter choice, for example when it rebuilds events in V3 order.
    """
    try:
        return StarterChoice(attempt({}), {}, 0)
    except StarterGap as first:
        pending: list[tuple[Starters, StarterGap]] = [({}, first)]
    accepted: list[tuple[T, Starters]] = []
    tried = 0
    while pending:
        chosen, open_gap = pending.pop()
        options = [
            [(team, ids) for ids in candidate_starters(team, partial, roster)]
            for team, partial in sorted(open_gap.partial.items())
        ]
        for combination in product(*options):
            trial = {**chosen, **{(open_gap.period, team): ids for team, ids in combination}}
            tried += 1
            if tried > MAX_ATTEMPTS:
                raise GameIssue(
                    "unresolved_starters", f"Starter search exceeded {MAX_ATTEMPTS} candidates"
                )
            try:
                result = attempt(trial)
            except StarterGap as later:
                pending.append((trial, later))
                continue
            except GameIssue:
                continue
            accepted.append((result, trial))
    if len(accepted) == 1:
        result, starters = accepted[0]
        return StarterChoice(result, starters, tried)
    if accepted and len({fingerprint(result) for result, _ in accepted}) == 1:
        result, starters = accepted[0]
        return StarterChoice(result, starters, tried, immaterial=True)
    if not accepted:
        raise GameIssue(
            "unresolved_starters", f"No candidate starters reconcile ({tried} candidates)"
        )
    raise GameIssue(
        "ambiguous_starters", f"{len(accepted)} of {tried} candidate starter sets reconcile"
    )
