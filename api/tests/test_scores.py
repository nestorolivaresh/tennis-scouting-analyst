"""Reading scores (api/scores.py, D-029). These need no database."""

from api.scores import SetScore, parse_sets, player_sets, score_from_side


def test_a_score_reads_as_sets_from_the_winners_side():
    assert parse_sets("6-4 3-6 7-6(5)") == [
        SetScore(6, 4, False, False),
        SetScore(3, 6, False, False),
        SetScore(7, 6, True, False),
    ]


def test_tiebreaks_are_read_from_the_tiebreak_score_or_a_seven_six_set():
    # Wimbledon's final-set tiebreak at 12-12, NextGen's short sets, and a 7-6 written bare.
    assert [s.tiebreak for s in parse_sets("13-12(3) 4-3(5) 6-7 6-4")] == [True, True, True, False]


def test_a_match_tiebreak_counts_as_a_set_but_not_as_a_tiebreak():
    sets = parse_sets("6-4 4-6 [10-8]")
    assert sets[-1] == SetScore(10, 8, False, True)
    assert [s.tiebreak for s in sets] == [False, False, False]


def test_scores_that_are_not_all_sets_are_not_read():
    for score in ("6-3 2-1 RET", "W/O", "", None, "6-4 ABD", "6-4 6-x"):
        assert parse_sets(score) is None


def test_the_loser_sees_every_set_swapped():
    sets = player_sets("6-4 3-6 7-6(5)", won=False)
    assert [(s.mine, s.theirs, s.won) for s in sets] == [(4, 6, False), (6, 3, True), (6, 7, False)]
    assert player_sets("6-4 3-6 7-6(5)", won=True) == parse_sets("6-4 3-6 7-6(5)")


def test_a_score_from_the_losers_side_keeps_tiebreak_points_and_words():
    # The H04 case (D-023): a winner-first final, said from the loser's side.
    assert score_from_side("4-6 7-6(4) 4-6 7-6(3) 7-6(2)", won=False) == "6-4 6-7(4) 6-4 6-7(3) 6-7(2)"
    assert score_from_side("6-4 4-6 [10-8]", won=False) == "4-6 6-4 [8-10]"
    assert score_from_side("6-3 2-1 RET", won=False) == "3-6 1-2 RET"
    assert score_from_side("W/O", won=False) == "W/O"


def test_the_winners_score_and_a_missing_score_are_unchanged():
    assert score_from_side("6-4 6-4", won=True) == "6-4 6-4"
    assert score_from_side(None, won=False) is None
