"""Citations in model text (D-032). Expected text is written from the page's number formats
(web/lib/evidence.ts formatValue and the language files) and the rules in api/citations.py."""

import itertools

from api.citations import Renderer, format_int, render, resolve

RESULTS = {
    "c1": {
        "stats": {
            "first_serve_in": {"value": 1262 / 2049, "numerator": 1262, "denominator": 2049, "unit": "fraction"},
            "tiebreaks_won": {"value": 0.8, "numerator": 8, "denominator": 10, "unit": "fraction", "matches": 122},
            "aces_per_match": {"value": 334 / 76, "numerator": 334, "denominator": 76, "unit": "per_match"},
            "return_points_won": {"value": {"value": 0.417, "numerator": 417, "denominator": 1000, "unit": "fraction"},
                                  "rank": 8, "tour_median": 0.6815},
        },
        "record": {"wins": 11, "losses": 8, "matches": 19},
        "matches": [{"player_score": "6-4 7-6(5)", "won": True}],
        "points": 12345,
    },
}


def test_values_are_written_as_the_page_writes_them():
    cases = {
        "stats.first_serve_in.value": ("61.6%", "61,6 %", "61,6 %"),
        "stats.first_serve_in.numerator": ("1,262", "1262", "1 262"),
        "stats.aces_per_match.value": ("4.4", "4,4", "4,4"),
        "stats.return_points_won.tour_median": ("68.2%", "68,2 %", "68,2 %"),  # a fraction, by the rate beside it
        "stats.return_points_won.value": ("41.7%", "41,7 %", "41,7 %"),  # a rate cited itself: its value
        "stats.first_serve_in": ("61.6%", "61,6 %", "61,6 %"),
        "stats.return_points_won.rank": ("8", "8", "8"),
        "record.wins": ("11", "11", "11"),
        "stats.tiebreaks_won.matches": ("122", "122", "122"),  # a count kept inside a rate
        "matches.0.player_score": ("6-4 7-6(5)",) * 3,
        "points": ("12,345", "12.345", "12 345"),
    }
    for field, expected in cases.items():
        assert tuple(resolve(RESULTS, "c1", field, lang) for lang in ("en", "es", "fr")) == expected, field


def test_a_percentage_rounds_like_the_page():
    """Math.round rounds halves up: 61.55 shows as 61.6, from the counts, not the float."""
    results = {"c1": {"r": {"value": 0.6155, "numerator": 1231, "denominator": 2000, "unit": "fraction"}}}
    assert resolve(results, "c1", "r.value", "en") == "61.6%"
    assert format_int(-1262, "en") == "-1,262"


def test_a_cited_rate_names_its_value_field():
    """tour_comparison's line holds its figure as a rate; citing the line's rate or its counts
    means the rate's (found in the m10 evals, P05)."""
    rendered, cited = render("[[c1:stats.return_points_won.value]] ([[c1:stats.return_points_won.numerator]] of "
                             "[[c1:stats.return_points_won.denominator]], rank [[c1:stats.return_points_won.rank]])", RESULTS)
    assert rendered == "41.7% (417 of 1,000, rank 8)"
    assert [c.field for c in cited] == [
        "stats.return_points_won.value.value", "stats.return_points_won.value.numerator",
        "stats.return_points_won.value.denominator", "stats.return_points_won.rank",
    ]
    assert render("[[c1:record.numerator]]", RESULTS)[0] == "[?]"  # no rate on that line: nothing guessed


def test_a_citation_that_names_nothing_is_shown_as_unresolved():
    text = "A [[c1:nope]], B [[c9:record.wins]], C [[c1:record]], D [[c1:matches.0.won]], E [[c1 record.wins]]."
    rendered, cited = render(text, RESULTS)
    assert rendered == "A [?], B [?], C [?], D [?], E [?]."
    assert [c.ok for c in cited] == [False] * 5


def test_brackets_that_are_not_citations_stay_as_written():
    for text in ("a match tiebreak [10-8]", "a [ bracket", "x" * 10 + "[[" + "y" * 200 + "]]", "ends with [["):
        assert render(text, RESULTS)[0] == text, text


def test_positions_point_at_the_written_numbers():
    text = "He made [[c1:stats.first_serve_in.value]] ([[c1:stats.first_serve_in.numerator]] of 2,049), and went [[c1:record.wins]]-[[c1:record.losses]]."
    rendered, cited = render(text, RESULTS)
    assert rendered == "He made 61.6% (1,262 of 2,049), and went 11-8."
    assert [(rendered[c.start : c.end], c.field) for c in cited] == [
        ("61.6%", "stats.first_serve_in.value"), ("1,262", "stats.first_serve_in.numerator"), ("11", "record.wins"), ("8", "record.losses"),
    ]


def test_streaming_in_any_pieces_gives_the_same_text_and_positions():
    text = "Serve: [[c1:stats.first_serve_in.value]], [ok] [[c1:record.wins]]-[[c1:nope]] end"
    whole, whole_cited = render(text, RESULTS)
    for a, b in itertools.combinations(range(1, len(text)), 2):
        renderer = Renderer(lambda: RESULTS)
        shown = "".join(renderer.feed(piece) for piece in (text[:a], text[a:b], text[b:])) + renderer.flush()
        assert (shown, renderer.citations) == (whole, whole_cited), (a, b)


def test_a_citation_is_resolved_with_the_calls_made_by_then():
    calls: dict = {}
    renderer = Renderer(lambda: calls)
    first = renderer.feed("Before: [[c1:record.wins]]. ")
    calls.update(RESULTS)
    second = renderer.feed("After: [[c1:record.wins]].")
    assert (first, second) == ("Before: [?]. ", "After: 11.")


def test_an_average_rounds_halves_up_like_the_page():
    """toFixed(1) on the page: 17 aces in 4 matches (4.25) is 4.3; Python's own format gives 4.2.
    Found by the review."""
    results = {"c1": {"aces": {"value": 4.25, "numerator": 17, "denominator": 4, "unit": "per_match"},
                      "line": {"value": {"value": 0.5, "numerator": 1, "denominator": 2, "unit": "per_match"}, "tour_median": 1.25}}}
    assert resolve(results, "c1", "aces.value", "en") == "4.3"
    assert resolve(results, "c1", "line.tour_median", "es") == "1,3"


def test_text_written_in_opens_no_source_card():
    rendered, cited = render("Won [[c1:matches.0.player_score]], [[c1:record.wins]] wins.", RESULTS)
    assert rendered == "Won 6-4 7-6(5), 11 wins."
    assert [(c.text, c.numeric) for c in cited] == [("6-4 7-6(5)", False), ("11", True)]


def test_a_mistyped_citation_does_not_swallow_what_follows():
    """Found by the review: "[[c1:record.wins] and ..." took everything up to the next "]]"."""
    assert render("[[c1:record.wins] and [[c1:record.losses]] after", RESULTS)[0] == "[?] and 8 after"
    assert render("[[[c1:record.wins]]]", RESULTS)[0] == "[11]"
    assert render("a [[ b [[c1:record.wins]] c", RESULTS)[0] == "a [[ b 11 c"
