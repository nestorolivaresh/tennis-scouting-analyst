"""Reading match scores: the sets in a score, and the score from one player's side (D-029).

Both sources write a score from the winner's side: "6-4 3-6 7-6(5)" means the winner took the
first set 6-4. A tiebreak's loser's points follow in parentheses, and a match tiebreak played
instead of a deciding set is written in brackets ("[10-8]").
"""

from __future__ import annotations

import dataclasses
import re

SET_RE = re.compile(r"^(\d{1,2})-(\d{1,2})(\(\d+\))?$")
MATCH_TIEBREAK_RE = re.compile(r"^\[(\d{1,2})-(\d{1,2})\]$")


@dataclasses.dataclass(frozen=True)
class SetScore:
    """One set, as games (or points, for a match tiebreak) for one side and the other."""

    mine: int
    theirs: int
    tiebreak: bool  # a set decided by a tiebreak: "7-6(5)", "13-12(3)", or a bare "7-6"
    match_tiebreak: bool  # "[10-8]", played instead of a deciding set

    @property
    def won(self) -> bool:
        return self.mine > self.theirs


def parse_sets(score: str | None) -> list[SetScore] | None:
    """The sets of a score, from the winner's side. None unless every token is a set score,
    which is true of every completed match (D-007), and false of retirements ("RET")."""
    tokens = (score or "").split()
    sets = []
    for token in tokens:
        if match := SET_RE.match(token):
            first, second = int(match.group(1)), int(match.group(2))
            tiebreak = match.group(3) is not None or {first, second} == {6, 7}
            sets.append(SetScore(first, second, tiebreak, False))
        elif match := MATCH_TIEBREAK_RE.match(token):
            sets.append(SetScore(int(match.group(1)), int(match.group(2)), False, True))
        else:
            return None
    return sets or None


def player_sets(score: str | None, won: bool) -> list[SetScore] | None:
    """The sets from one player's side: as written for the winner, swapped for the loser."""
    sets = parse_sets(score)
    if sets is None or won:
        return sets
    return [SetScore(s.theirs, s.mine, s.tiebreak, s.match_tiebreak) for s in sets]


def _flip(token: str) -> str:
    if match := SET_RE.match(token):
        return f"{match.group(2)}-{match.group(1)}{match.group(3) or ''}"
    if match := MATCH_TIEBREAK_RE.match(token):
        return f"[{match.group(2)}-{match.group(1)}]"
    return token  # "RET", "W/O", "DEF" and anything else stay as written


def score_from_side(score: str | None, won: bool) -> str | None:
    """The score as the given player would say it: unchanged for the winner, each set swapped
    for the loser ("6-4 6-7(4)" becomes "4-6 7-6(4)"). Words such as RET are kept."""
    if score is None or won:
        return score
    return " ".join(_flip(token) for token in score.split())
