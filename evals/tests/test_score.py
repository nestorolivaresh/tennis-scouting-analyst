"""Scoring (evals/score.py). The numbers are Sinner's 2024 season from Tennis Abstract and the
hand checks (docs/stat-checks.md): 73-6, first serve in 61.59% (3,693 of 5,996), 594 aces."""

from evals import score
from evals.score import contains_expected, invented, numbers_in

FIRST_IN = 3693 / 5996  # TA
RESULT = {"overall": {"wins": 73, "losses": 6}, "stats": {"first_serve_in": {"value": 0.6159, "numerator": 3693,
          "denominator": 5996}}, "sample": {"first_tourney_date": "2024-01-01"}, "score": "7-6(5) 6-3"}  # fmt: skip


def test_numbers_in_skips_years_dates_and_ordinals():
    text = "In 2024 (from 2024-01-01) Sinner went 73-6, won 61.6% of 1st serves and hit 1,262 aces."
    assert [(n.value, n.percent) for n in numbers_in(text)] == [(73, False), (6, False), (61.6, True), (1262, False)]
    assert [n.value for n in numbers_in("**61.6 percent**, rank No. 1, R32")] == [61.6, 1]


def test_expected_numbers():
    assert contains_expected("He went 73-6.", 73, "count") and contains_expected("He went 73-6.", 6, "count")
    assert not contains_expected("He went 73-7.", 6, "count")
    assert not contains_expected("6.0 of them", 6, "count")  # a count is written as a whole number
    assert contains_expected("61.6% of first serves", FIRST_IN, "rate")
    assert contains_expected("62% of first serves", FIRST_IN, "rate")  # within 0.5 points
    assert not contains_expected("62.2% of first serves", FIRST_IN, "rate")  # 0.61 points off
    assert contains_expected("a rate of 0.616", FIRST_IN, "rate")
    assert contains_expected("7.5 aces per match", 594 / 79, "average")  # 7.519
    assert not contains_expected("7.6 aces per match", 594 / 79, "average")


def test_invented_numbers():
    pool = score.values_in(RESULT)
    ok = "Sinner went 73-6 and got 61.6% (3,693 of 5,996) of first serves in; he won 7-6(5) 6-3."
    assert invented(ok, pool) == []
    assert invented("He got 61.59% in, about 62%.", pool) == []  # more or fewer decimals
    assert invented("He got 64.1% of first serves in and won 75 matches.", pool) == ["64.1%", "75"]
    assert invented("He improved by 3.4 points.", pool) == ["3.4"]  # a computed difference is not from a tool


def test_tool_calls():
    call = {"tool": "head_to_head", "input": {"player_id": 207989, "opponent_id": "206173",
            "filters": {"surface": "clay", "date_to": "2025-12-31", "tourney_level": ["G"]}}, "error": None}  # fmt: skip
    assert score.call_matches(call, "head_to_head", 206173, 207989, {"surface": "Clay", "tourney_level": "G"})
    assert not score.call_matches(call, "head_to_head", 206173, 104925, {})
    assert not score.call_matches(call, "head_to_head", 206173, 207989, {"date_to": "2024-12-31"})
    assert not score.call_matches({**call, "error": "bad filter"}, "head_to_head", 206173, 207989, {})
    season = {"tool": "serve_return_stats", "input": {"player_id": 206173, "filters": {"season": "2024"}}, "error": None}
    assert score.call_matches(season, "serve_return_stats", 206173, None, {"season": 2024})
    assert score.call_matches({"tool": "resolve_player", "input": {"name": "Zverev"}}, "resolve_player", None, None, {})


def test_pairs_must_appear_as_pairs():
    """Sinner v Alcaraz through 2026 (hand 5): 7-10; Hard 3-7, Clay 2-3, Grass 2-0. The
    baseline's wrong tallies ("split 3-3", "10 of 14") were made of numbers that each appear
    somewhere, so they passed a number-by-number check."""
    h2h = {"record": {"matches": 17, "wins": 7, "losses": 10},
           "by_surface": [{"surface": "Hard", "matches": 10, "wins": 3, "losses": 7},
                          {"surface": "Clay", "matches": 5, "wins": 2, "losses": 3},
                          {"surface": "Grass", "matches": 2, "wins": 2, "losses": 0}],
           "matches": [{"score": "7-6(4) 7-5"}]}  # fmt: skip
    pairs = score.pairs_in(h2h)
    ok = "Alcaraz leads 10–7. On hard, Sinner is 3-7; he won 2 of 5 on clay, 7-6(4) 7-5 in the final."
    assert score.unsupported_pairs(ok, pairs) == []
    assert score.unsupported_pairs("They split 3–3, and Alcaraz won 10 of 14.", pairs) == ["3–3", "10 of 14"]
    assert score.unsupported_pairs("From 2019–2024, and from May 2–23, 2022.", pairs) == []  # years and days
    assert score.unsupported_pairs("905 of 1,774 points", score.pairs_in({"numerator": 905, "denominator": 1774})) == []


def h09(answer):
    """Score an answer to H09. Through 2025 Sinner was 1-3 against Alcaraz on clay (hand 5:
    2-3 through 2026, and the 2026 Monte Carlo final, which Sinner won, is the newest meeting)."""
    from evals.cases import CASES
    from evals.run import score_case

    case = next(c for c in CASES if c.id == "H09")
    expected = [{"stat": "wins", "player": 206173, "opponent": 207989, "value": 1, "kind": "count"},
                {"stat": "losses", "player": 206173, "opponent": 207989, "value": 3, "kind": "count"}]  # fmt: skip
    calls = [{"tool": "head_to_head", "input": {"player_id": 206173, "opponent_id": 207989,
              "filters": {"date_to": "2025-12-31"}}, "result": {"record": {"matches": 4, "wins": 1, "losses": 3}},
              "error": None}]  # fmt: skip
    return score_case(case, expected, answer, calls, "completed")


def test_who_leads():
    """The reviewer's examples (D-023), right and wrong."""
    right = [
        "Alcaraz led the clay head-to-head 3-1.",
        "The clay head-to-head between Jannik Sinner and Carlos Alcaraz was led by Alcaraz, 3-1.",
        "Carlos Alcaraz holds a 3-1 lead on clay.",
        "Between Jannik Sinner and Carlos Alcaraz, Alcaraz leads 3-1 on clay.",
        "Sinner trails Alcaraz, who led 3-1 on clay.",
    ]
    wrong = [
        "The clay head-to-head through 2025 is in Sinner's favour. Alcaraz edged him at Roland Garros, "
        "and the record is 1-3 from Sinner's side over 4 matches.",
        "On clay the record is 1-3, but Sinner holds the edge.",
        "Sinner led the clay head-to-head, though the record is 1-3.",
        "The record is 1-3 and the two split evenly in finals.",
    ]
    for answer in right:
        assert h09(answer)["claims_ok"], answer
    for answer in wrong:
        result = h09(answer)
        assert not result["claims_ok"] and not result["passed"], answer


def test_who_is_better():
    """C01's shape: Medvedev 51.0% (905 of 1,774) v Zverev 48.4% (400 of 827), 2022."""
    from evals.cases import CASES
    from evals.run import score_case

    case = next(c for c in CASES if c.id == "C01")
    expected = [{"stat": "second_serve_points_won", "player": 106421, "opponent": None, "value": 905 / 1774, "kind": "rate"},
                {"stat": "second_serve_points_won", "player": 100644, "opponent": None, "value": 400 / 827, "kind": "rate"}]  # fmt: skip
    calls = [{"tool": "serve_return_stats", "input": {"player_id": pid, "filters": {"season": 2022}}, "error": None,
              "result": {"stats": {"second_serve_points_won": {"value": round(n / d, 4), "numerator": n, "denominator": d}}}}
             for pid, n, d in ((106421, 905, 1774), (100644, 400, 827))]  # fmt: skip
    ok = "Daniil Medvedev won more of his second-serve points: 51.0% (905 of 1,774) against Zverev's 48.4% (400 of 827)."
    swapped = "Zverev won more of his second-serve points than Medvedev: 48.4% (400 of 827) against 51.0% (905 of 1,774)."
    assert score_case(case, expected, ok, calls, "completed")["passed"]
    result = score_case(case, expected, swapped, calls, "completed")
    assert not result["claims_ok"] and not result["passed"]


def test_refusals_from_review():
    from evals.cases import CASES
    from evals.run import score_case

    cases = {c.id: c for c in CASES}
    federer = [{"tool": "serve_return_stats", "input": {"player_id": 103819, "filters": {"season": 2022}},
                "result": {"sample": {"matches_counted": 0}}, "error": None}]  # fmt: skip
    assert score_case(cases["R02"], [], "The data has no matches for Federer in 2022.", federer, "completed")["passed"]
    assert not score_case(cases["R02"], [], "Federer served well in 2022 across 10 matches.", federer, "completed")["refusal_ok"]
    h2h = [{"tool": "head_to_head", "input": {"player_id": 206173, "opponent_id": 207989},
            "result": {"record": {"matches": 17, "wins": 7, "losses": 10, "win_rate": {"value": 0.4118}}}, "error": None}]  # fmt: skip
    hedge = "I can't predict with certainty, but Sinner has about a 41% chance."
    assert not score_case(cases["R06"], [], hedge, h2h, "completed")["refusal_ok"]
    assert score_case(cases["R06"], [], "I can't predict that; the data only has past results.", h2h, "completed")["passed"]
    substitute = [{"tool": "resolve_player", "input": {"name": "Iga Swiatek"}, "result": {"status": "not_found"}, "error": None},
                  {"tool": "serve_return_stats", "input": {"player_id": 104527}, "result": {}, "error": None}]  # fmt: skip
    assert not score_case(cases["R04"], [], "I couldn't find Iga Swiatek, so here is Stan Wawrinka instead.", substitute,
                          "completed")["refusal_ok"]  # fmt: skip
    begins = "The data begins with the 2015 season, so 2013 is before the period it covers."
    assert score_case(cases["R03"], [], begins, [], "completed")["passed"]


# Found in review (D-023): wrong tallies that still passed, and right answers that failed.
H2H = {"record": {"matches": 17, "wins": 7, "losses": 10},  # hand 5
       "by_surface": [{"surface": "Clay", "matches": 5, "wins": 2, "losses": 3}],
       "matches": [{"score": "6-2 6-3"}, {"score": "7-6(4) 7-5"}, {"score": "5-0 RET"}]}  # fmt: skip
SINNER_2024 = {"sample": {"matches_counted": 79, "matches_with_stats": 79, "opponent_retired_or_defaulted": 1,
               "excluded": {"walkovers": 2, "exhibitions": 0}}}  # TA 73-6; hand 2 and hand 18  # fmt: skip


def test_review_pairs_that_used_to_pass():
    pairs = score.pairs_in(H2H)
    for wrong in ("Sinner won 2 of the 6 meetings.",  # 2 and 6 only appear together in a set score
                  "Alcaraz won 10 out of 14.", "Alcaraz won 10 of the last 14.",
                  "a remarkable 3-3 split", "In summary 3-3.", "a decisive 5-4 edge",
                  "He won 6-4 6-4 in the final."):  # fmt: skip
        assert score.unsupported_pairs(wrong, pairs) != [], wrong


def test_review_right_answers_that_used_to_fail():
    pairs = score.pairs_in(H2H) | score.pairs_in(SINNER_2024)
    for right in ("Sinner retired at 5–0.", "He won 7–6(4) 7–5.", "Alcaraz leads 10-7; on clay Sinner won 2 of 5.",
                  "1 of the 79 ended with his opponent retiring.", "2 of his 81 matches were walkovers.",
                  "From 2019-24 they met often.", "Between May 2–23 they met twice."):  # fmt: skip
        assert score.unsupported_pairs(right, pairs) == [], right
    assert contains_expected("Djokovic won all 5; Federer won none.", 0, "count")
    assert not contains_expected("Djokovic won 5 of them.", 0, "count")


def test_ordinals_are_checked_unless_they_name_a_serve_set_or_round():
    assert [n.value for n in numbers_in("ranked 161st, on his 2nd serve, in the 5th set")] == [161]
    assert invented("He was ranked 161st.", {1.0}) == ["161st"]


def test_dates_may_differ_by_a_week():
    call = {"tool": "pressure_stats", "input": {"player_id": 1, "filters": {"date_from": "2018-12-31"}}, "error": None}
    assert score.call_matches(call, "pressure_stats", 1, None, {"date_from": "2019-01-01"})
    assert not score.call_matches(call, "pressure_stats", 1, None, {"date_from": "2019-02-01"})
