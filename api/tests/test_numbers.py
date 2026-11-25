"""The check on numbers in model text (D-031). Expected results are written from the rules in
api/numbers.py and the number formats the prompts ask for (D-027): no database is needed."""

from api.numbers import Pairs, check_answer, check_report_text, check_text, numbers_in, pairs_in, words_in

RESULT = {
    "tool_call_id": "c1",
    "stats": {"first_serve_in": {"value": 0.616, "numerator": 1262, "denominator": 2049}},
    "record": {"wins": 11, "losses": 8, "matches": 19},
    "matches": [{"score": "6-4 7-6(5)", "tourney_date": "2024-05-26"}],
}


def spans(check):
    return [(s["text"], s["start"], s["end"]) for s in check["not_found"]]


def test_a_number_not_in_the_results_is_marked_where_it_is():
    text = "He made 61.6% of first serves (1,262 of 2,049) and won 75 matches."
    check = check_answer(text, [RESULT])
    assert check["checked"] == 4
    assert spans(check) == [("75", text.index("75"), text.index("75") + 2)]


def test_positions_stay_true_after_a_date():
    text = "On 2024-05-26 he won 6-4 7-6(5), with 64.1% in."
    [(seen, start, end)] = spans(check_answer(text, [RESULT]))
    assert (seen, text[start:end]) == ("64.1%", "64.1%")


def test_a_count_made_of_real_numbers_is_marked_whole():
    text = "He won 11 of 18."  # 11 and 18? 18 isn't in the results either; the pair is one mark
    assert spans(check_answer(text, [RESULT])) == [("11 of 18", 7, 15)]
    assert spans(check_answer("He went 11-8, then 8-11 from the other side.", [RESULT])) == []
    assert spans(check_answer("They split 10-9.", [RESULT])) == [("10-9", 11, 15)]


def test_a_count_must_be_exact_but_a_rounded_rate_passes():
    assert spans(check_answer("He won 20 matches, 1,263 points; 62% and 61% in.", [RESULT])) == [("20", 7, 9), ("1,263", 19, 24)]
    assert spans(check_answer("He averages 4 aces.", [{"aces_per_match": 4.4}])) == []  # rounded from a decimal


def test_the_users_own_numbers_count_but_earlier_answers_do_not():
    assert spans(check_answer("Against the top 20 he won 11 of 19.", [RESULT], ["How does he do against the top 20?"])) == []
    assert spans(check_answer("Against the top 20 he won 11 of 19.", [RESULT])) == [("20", 16, 18)]


def test_a_failed_call_adds_nothing():
    assert spans(check_answer("He won 11 of 19.", [None])) == [("11 of 19", 7, 15)]


def test_spanish_and_french_decimals_spaces_and_counts():
    es = "Metió el 61,6 % de primeros saques (1.262 de 2.049) y ganó 11 de 19 partidos."
    assert [(n.value, n.percent) for n in numbers_in(es, "es")] == [(61.6, True), (1262, False), (2049, False), (11, False), (19, False)]
    assert spans(check_answer(es, [RESULT], language="es")) == []
    fr = "Il a passé 61,6 % de premières balles (1 262 sur 2 049) et gagné 11 de ses 18 matchs."
    assert spans(check_answer(fr, [RESULT], language="fr")) == [("11 de ses 18", fr.index("11 de"), fr.index(" matchs"))]
    assert spans(check_answer("Ganó 12 de 19.", [RESULT], language="es")) == [("12 de 19", 5, 13)]


def test_an_english_answer_to_a_spanish_visitor_is_read_either_way():
    """A visitor who writes in English gets an English answer, whatever the page's language."""
    text = "He made 61.6% of first serves, 1,262 of 2,049."
    assert spans(check_answer(text, [RESULT], language="es")) == []
    assert spans(check_answer("Ganó 1.262 puntos.", [RESULT], language="es")) == []
    assert spans(check_answer("Ganó 1,263 puntos.", [RESULT], language="es")) == [("1,263", 5, 10)]


def test_spanish_and_french_years_dates_and_ordinals_are_skipped():
    text = "En 2024, el 26 de mayo, en el 2.º saque y el 5.º set, quedó 1.º de 66."
    assert [n.value for n in numbers_in(text, "es")] == [26, 1, 66]
    assert [n.value for n in numbers_in("Le 3 de 2024 ? Non : 5e set, 1er sur 66.", "fr")] == [3, 1, 66]
    assert spans(check_answer("Ganó 3 de 2024.", [{"n": 3}], language="es")) == []  # "de 2024" is a year


def test_a_day_range_next_to_a_month_is_not_a_record():
    for text, language in (("from May 2-23", "en"), ("from 2-23 May", "en"), ("del 2-23 de mayo", "es"), ("du 2-23 mai", "fr")):
        assert spans(check_answer(text, [{"days": [2, 23]}], language=language)) == [], text
    assert spans(check_answer("A 3-3 may suggest", [{"days": [3]}])) == [("3-3", 2, 5)]  # "may" is not a month here


def test_overlapping_marks_are_one():
    pool, pairs = {11.0}, Pairs(counts=frozenset({(11, 19)}))
    assert check_text("won 11 of 18", pool, pairs)[1][0].text == "11 of 18"
    count, marks = check_text("won 12 of 18", pool, pairs)
    assert count == 2 and [(m.text, m.start, m.end) for m in marks] == [("12 of 18", 4, 12)]


def test_a_reports_text_fields_are_checked_and_named():
    report = {
        "summary": "Sinner won 11 of 19.",
        "strengths": ["61.6% first serves in.", "Holds 70.2% of service games."],
        "weaknesses": [],
        "game_plan": ["Make him play a 4th set."],
        "data_caveats": ["Based on 19 matches."],
        "key_stats": [{"label": "Not checked here: 99.9%", "value": 0.616}],
    }
    check = check_report_text(report, [RESULT])
    assert check["checked"] == 5  # 11, 19, 61.6%, 70.2%, 19; "4th set" names a set; key stat labels aren't text on screen
    assert check["not_found"] == [{"field": "strengths.1", "text": "70.2%", "start": 6, "end": 11}]
    assert check_report_text(None, [RESULT]) == {"checked": 0, "not_found": []}


def test_pairs_come_from_every_result():
    pairs = pairs_in(RESULT)
    assert (11, 8) in pairs.records and (11, 19) in pairs.counts and (1262, 2049) in pairs.counts


def test_charted_matches_are_part_of_the_matches_counted():
    """shot_patterns (D-030): its charted matches are among the matches counted, as the live
    answer to eval P10 wrote them (D-039)."""
    shots = {"sample": {"matches_counted": 21, "matches_with_stats": 21}, "excluded": {"walkovers": 0},
             "charting": {"charted_matches": 13}}  # fmt: skip
    assert spans(check_answer("13 of his 21 Grand Slam matches were charted.", [shots])) == []
    assert spans(check_answer("13 of his 22 Grand Slam matches were charted.", [shots])) == [("13 of his 22", 0, 12)]
    assert spans(check_answer("14 of his 21 Grand Slam matches were charted.", [shots])) == [("14 of his 21", 0, 12)]


def test_a_record_with_three_or_four_digits_is_checked_as_a_pair():
    career = {"record": {"wins": 309, "losses": 69, "matches": 378}}
    assert spans(check_answer("He is 309-69 overall, 69-309 seen from the other side.", [career])) == []
    assert spans(check_answer("He is 309-68 overall.", [career])) == [("309-68", 6, 12)]
    assert spans(check_answer("He is 7-128 overall.", [career, RESULT])) == [("7-128", 6, 11)]  # not "7-12"
    assert spans(check_answer("From 2019-2024 and 2019-24.", [career])) == []  # year ranges


def test_number_words_that_count_something_are_checked():
    record = {"record": {"wins": 5, "losses": 1, "matches": 6}}
    text = "He won five of his last six, beat him five times, and one of the best; no one; a one-handed backhand; a two-time champion."
    assert [n.text for n in words_in(text)] == ["five", "six", "five"]
    assert spans(check_answer(text, [record])) == []
    assert spans(check_answer("He won four of his last six matches.", [record])) == [("four of his last six", 7, 27)]
    assert spans(check_answer("Nadal won seven straight matches.", [record])) == [("seven", 10, 15)]


def test_number_words_in_spanish_and_french():
    record = {"record": {"wins": 5, "losses": 1, "matches": 6}}
    assert [n.value for n in words_in("Ganó cinco de sus seis partidos y una victoria clara.", "es")] == [5, 6]
    assert spans(check_answer("Ganó cinco de sus seis partidos.", [record], language="es")) == []
    assert spans(check_answer("Il a gagné quatre de ses six matchs, dix-sept fois.", [record], language="fr")) == [
        ("quatre de ses six", 11, 28), ("dix-sept", 37, 45),
    ]


def test_rally_length_ranges_and_years_after_of_are_not_counts():
    """False flags found in the m10-final evals (R01, P07, R07)."""
    shots = {"points_won": {"1_3": {"value": 0.531}, "7_9": {"value": 0.563}}, "charted_matches": 68}
    text = "He won 53.1% of 1–3 shots and 56.3% in 7–9 shot rallies; 68 of his 2024 matches were charted."
    assert spans(check_answer(text, [shots])) == []
    assert spans(check_answer("Ganó el 53,1 % de 1-3 golpes.", [shots], language="es")) == []
    assert spans(check_answer("He went 1–3 against him.", [shots])) == [("1–3", 8, 11)]  # a record is still a record


def test_only_a_short_year_after_a_year_and_a_hyphen_is_skipped():
    """Found by the review: "In 2024 — 15 wins" checked no number at all."""
    assert [n.value for n in numbers_in("In 2024 — 15 wins, 2019-24 and 2019–24.")] == [15]
    assert [n.value for n in numbers_in("Only two digits make a year: 2019-5 and 2019-150.")] == [5, 150]
