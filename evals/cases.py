"""The eval questions (spec, Evals), with what each answer must contain: the spec's 40, plus
one for each bug found by hand.

Every question names its years, so it covers only the pinned Sackmann seasons 2015-2025
(D-002) and its answer can't change when the TML 2026 data is refreshed. Expected numbers are
never written here: each `Expect` says which number to compute, and `evals/truth.py` computes
it from the raw tables. A year in a question means that season (D-010).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from evals.truth import Filters

# Player IDs from raw.sackmann_players (hand check 9 for the ones it covers).
SINNER, ALCARAZ, DJOKOVIC, NADAL, FEDERER = 206173, 207989, 104925, 104745, 103819
MEDVEDEV, ZVEREV, THIEM, TSITSIPAS, RUUD = 106421, 100644, 106233, 126774, 134770
MURRAY, ISNER, KYRGIOS, FRITZ, RUBLEV = 104918, 104545, 106401, 126203, 126094
# Last names, for the checks on who leads or who is better (built from the ground truth).
NAMES = {SINNER: "Sinner", ALCARAZ: "Alcaraz", DJOKOVIC: "Djokovic", NADAL: "Nadal", FEDERER: "Federer",
         MEDVEDEV: "Medvedev", ZVEREV: "Zverev", THIEM: "Thiem", TSITSIPAS: "Tsitsipas", RUUD: "Ruud",
         MURRAY: "Murray", ISNER: "Isner", KYRGIOS: "Kyrgios", FRITZ: "Fritz", RUBLEV: "Rublev"}  # fmt: skip
STATS_TOOLS = ("player_profile", "surface_splits", "serve_return_stats", "pressure_stats", "head_to_head", "recent_form")

COUNTS = {"matches", "wins", "losses"}  # checked exactly; every other stat is a rate or average


@dataclass(frozen=True)
class Expect:
    """One number the answer must contain: `stat` for `player` (against `opponent`, if set)."""

    stat: str
    player: int
    filters: Filters
    opponent: int | None = None


@dataclass(frozen=True)
class ToolCheck:
    """A tool call the answer must rest on. `filters` lists the values that must be passed;
    other filters may be absent. For head_to_head, the two players may come in either order.
    `player` None means any input (resolve_player takes a name)."""

    tool: str
    player: int | None
    filters: dict = field(default_factory=dict)
    opponent: int | None = None


@dataclass(frozen=True)
class Refusal:
    """For should-refuse-or-caveat questions: patterns the answer must contain (all of them,
    case-insensitive regular expressions), and patterns it must not."""

    must: tuple[str, ...]
    must_not: tuple[str, ...] = ()
    forbid_tools: tuple[str, ...] = ()  # e.g. no stats for a player the user didn't confirm


@dataclass(frozen=True)
class Claims:
    """A claim in words the answer must make (all `must` patterns) or must not make. Used for
    bugs found by hand, such as saying the wrong player leads a head-to-head."""

    must: tuple[str, ...] = ()
    must_not: tuple[str, ...] = ()


@dataclass(frozen=True)
class Case:
    """One question. Head-to-head answers must not name the wrong leader, and comparison
    answers must name the better player in their first sentence; the runner builds both
    checks from the ground truth (`evals/run.py`, `leader_claims`). `asks_who_leads` also
    requires the head-to-head answer to name the leader."""

    id: str
    category: str
    question: str
    expects: tuple[Expect, ...] = ()
    tools: tuple[ToolCheck, ...] = ()
    refusal: Refusal | None = None
    claims: Claims | None = None
    asks_who_leads: bool = False


def season(year: int, **filters) -> Filters:
    return Filters(season=year, **filters)


# A probability stated anyway, after a disclaimer: "about a 41% chance", "odds of 3 in 5".
PROBABILITY_GIVEN = (
    r"\d+(\.\d+)?\s*(%|percent)[^.;]{0,40}\b(chance|probability|likely|likelihood|odds)\b"
    r"|\b(chance|probability|likelihood|odds)\b[^.;]{0,40}\d+(\.\d+)?\s*(%|percent|in \d+)"
)
NEGATION = r"(\bno\b|\bnot\b|n't|\bnone\b|unavailable|\bisn|\bdoesn|\bcannot\b|outside|only covers|doesn’t|isn’t|can’t)"

CASES: tuple[Case, ...] = (
    # ---------- single stat: one player, one season, one number ----------
    Case("S01", "single_stat", "What was Jannik Sinner's aces per match in the 2024 season?",
         (Expect("aces_per_match", SINNER, season(2024)),),
         (ToolCheck("serve_return_stats", SINNER, {"season": 2024}),)),
    Case("S02", "single_stat", "What percentage of first serves did Novak Djokovic get in during 2023?",
         (Expect("first_serve_in", DJOKOVIC, season(2023)),),
         (ToolCheck("serve_return_stats", DJOKOVIC, {"season": 2023}),)),
    Case("S03", "single_stat", "What share of break points faced did Daniil Medvedev save in 2021?",
         (Expect("break_points_saved", MEDVEDEV, season(2021)),),
         (ToolCheck("pressure_stats", MEDVEDEV, {"season": 2021}),)),
    Case("S04", "single_stat", "What percentage of return points did Rafael Nadal win in 2019?",
         (Expect("return_points_won", NADAL, season(2019)),),
         (ToolCheck("serve_return_stats", NADAL, {"season": 2019}),)),
    Case("S05", "single_stat", "What percentage of his service points did Roger Federer win in 2017?",
         (Expect("service_points_won", FEDERER, season(2017)),),
         (ToolCheck("serve_return_stats", FEDERER, {"season": 2017}),)),
    Case("S06", "single_stat", "How often did Alexander Zverev win points behind his second serve in 2019?",
         (Expect("second_serve_points_won", ZVEREV, season(2019)),),
         (ToolCheck("serve_return_stats", ZVEREV, {"season": 2019}),)),
    Case("S07", "single_stat", "What was John Isner's first-serve points won percentage in 2018?",
         (Expect("first_serve_points_won", ISNER, season(2018)),),
         (ToolCheck("serve_return_stats", ISNER, {"season": 2018}),)),
    Case("S08", "single_stat", "What percentage of break point chances did Casper Ruud convert in 2022?",
         (Expect("break_points_converted", RUUD, season(2022)),),
         (ToolCheck("pressure_stats", RUUD, {"season": 2022}),)),
    Case("S09", "single_stat", "What was Carlos Alcaraz's win-loss record in 2023?",
         (Expect("wins", ALCARAZ, season(2023)), Expect("losses", ALCARAZ, season(2023))),
         (ToolCheck("surface_splits", ALCARAZ, {"season": 2023}),)),
    Case("S10", "single_stat", "How many aces per match did Nick Kyrgios hit in 2019?",
         (Expect("aces_per_match", KYRGIOS, season(2019)),),
         (ToolCheck("serve_return_stats", KYRGIOS, {"season": 2019}),)),
    # ---------- filtered stat: surface, opponent hand, level or a date range ----------
    Case("F01", "filtered_stat", "What percentage of break points did Rafael Nadal save on clay in 2019?",
         (Expect("break_points_saved", NADAL, season(2019, surface="Clay")),),
         (ToolCheck("pressure_stats", NADAL, {"season": 2019, "surface": "Clay"}),)),
    Case("F02", "filtered_stat", "What percentage of return points did Novak Djokovic win against left-handers in 2016?",
         (Expect("return_points_won", DJOKOVIC, season(2016, opponent_hand="L")),),
         (ToolCheck("serve_return_stats", DJOKOVIC, {"season": 2016, "opponent_hand": "L"}),)),
    Case("F03", "filtered_stat", "What was Roger Federer's win-loss record at Grand Slams in 2017?",
         (Expect("wins", FEDERER, season(2017, levels=("G",))), Expect("losses", FEDERER, season(2017, levels=("G",)))),
         (ToolCheck("surface_splits", FEDERER, {"season": 2017, "tourney_level": "G"}),)),
    Case("F04", "filtered_stat", "What was Daniil Medvedev's first serve in percentage at Masters 1000 events in 2019?",
         (Expect("first_serve_in", MEDVEDEV, season(2019, levels=("M",))),),
         (ToolCheck("serve_return_stats", MEDVEDEV, {"season": 2019, "tourney_level": "M"}),)),
    Case("F05", "filtered_stat",
         "What percentage of break points did Dominic Thiem save on clay against left-handers from 2016 through 2019?",
         (Expect("break_points_saved", THIEM, Filters(date_from="2016-01-01", date_to="2019-12-31", surface="Clay", opponent_hand="L")),),
         (ToolCheck("pressure_stats", THIEM, {"date_from": "2016-01-01", "date_to": "2019-12-31", "surface": "Clay", "opponent_hand": "L"}),)),
    Case("F06", "filtered_stat",
         "What percentage of service points did Novak Djokovic win on grass from 2015 through 2019?",
         (Expect("service_points_won", DJOKOVIC, Filters(date_from="2015-01-01", date_to="2019-12-31", surface="Grass")),),
         (ToolCheck("serve_return_stats", DJOKOVIC, {"date_to": "2019-12-31", "surface": "Grass"}),)),
    Case("F07", "filtered_stat", "What percentage of second-serve points did Jannik Sinner win on hard courts in 2024?",
         (Expect("second_serve_points_won", SINNER, season(2024, surface="Hard")),),
         (ToolCheck("serve_return_stats", SINNER, {"season": 2024, "surface": "Hard"}),)),
    Case("F08", "filtered_stat", "What was Carlos Alcaraz's win-loss record on clay in 2022?",
         (Expect("wins", ALCARAZ, season(2022, surface="Clay")), Expect("losses", ALCARAZ, season(2022, surface="Clay"))),
         (ToolCheck("surface_splits", ALCARAZ, {"season": 2022}),)),
    Case("F09", "filtered_stat", "What percentage of break points did Alexander Zverev convert against right-handers in 2021?",
         (Expect("break_points_converted", ZVEREV, season(2021, opponent_hand="R")),),
         (ToolCheck("pressure_stats", ZVEREV, {"season": 2021, "opponent_hand": "R"}),)),
    Case("F10", "filtered_stat", "How many aces per match did Stefanos Tsitsipas hit on clay in 2021?",
         (Expect("aces_per_match", TSITSIPAS, season(2021, surface="Clay")),),
         (ToolCheck("serve_return_stats", TSITSIPAS, {"season": 2021, "surface": "Clay"}),)),
    # ---------- head-to-head: two players, a surface, level or date range ----------
    Case("H01", "head_to_head", "What is the head-to-head between Novak Djokovic and Rafael Nadal on clay from 2015 through 2025?",
         (Expect("wins", DJOKOVIC, Filters(date_to="2025-12-31", surface="Clay"), NADAL),
          Expect("losses", DJOKOVIC, Filters(date_to="2025-12-31", surface="Clay"), NADAL)),
         (ToolCheck("head_to_head", DJOKOVIC, {"surface": "Clay"}, NADAL),)),
    Case("H02", "head_to_head", "What was Roger Federer's record against Rafael Nadal on hard courts from 2015 through 2019?",
         (Expect("wins", FEDERER, Filters(date_to="2019-12-31", surface="Hard"), NADAL),
          Expect("losses", FEDERER, Filters(date_to="2019-12-31", surface="Hard"), NADAL)),
         (ToolCheck("head_to_head", FEDERER, {"surface": "Hard", "date_to": "2019-12-31"}, NADAL),)),
    Case("H03", "head_to_head", "What is the head-to-head between Daniil Medvedev and Alexander Zverev on hard courts from 2015 through 2025?",
         (Expect("wins", MEDVEDEV, Filters(date_to="2025-12-31", surface="Hard"), ZVEREV),
          Expect("losses", MEDVEDEV, Filters(date_to="2025-12-31", surface="Hard"), ZVEREV)),
         (ToolCheck("head_to_head", MEDVEDEV, {"surface": "Hard", "date_to": "2025-12-31"}, ZVEREV),)),
    Case("H04", "head_to_head", "What was the head-to-head between Jannik Sinner and Carlos Alcaraz up to the end of 2025?",
         (Expect("wins", SINNER, Filters(date_to="2025-12-31"), ALCARAZ), Expect("losses", SINNER, Filters(date_to="2025-12-31"), ALCARAZ)),
         (ToolCheck("head_to_head", SINNER, {"date_to": "2025-12-31"}, ALCARAZ),)),
    Case("H05", "head_to_head", "How did Novak Djokovic and Roger Federer do against each other at Grand Slams from 2015 through 2020?",
         (Expect("wins", DJOKOVIC, Filters(date_to="2020-12-31", levels=("G",)), FEDERER),
          Expect("losses", DJOKOVIC, Filters(date_to="2020-12-31", levels=("G",)), FEDERER)),
         (ToolCheck("head_to_head", DJOKOVIC, {"tourney_level": "G", "date_to": "2020-12-31"}, FEDERER),)),
    Case("H06", "head_to_head", "What was Dominic Thiem's record against Rafael Nadal on clay from 2015 through 2020?",
         (Expect("wins", THIEM, Filters(date_to="2020-12-31", surface="Clay"), NADAL),
          Expect("losses", THIEM, Filters(date_to="2020-12-31", surface="Clay"), NADAL)),
         (ToolCheck("head_to_head", THIEM, {"surface": "Clay", "date_to": "2020-12-31"}, NADAL),)),
    Case("H07", "head_to_head", "What is the head-to-head between Stefanos Tsitsipas and Daniil Medvedev from 2015 through 2025?",
         (Expect("wins", TSITSIPAS, Filters(date_to="2025-12-31"), MEDVEDEV),
          Expect("losses", TSITSIPAS, Filters(date_to="2025-12-31"), MEDVEDEV)),
         (ToolCheck("head_to_head", TSITSIPAS, {"date_to": "2025-12-31"}, MEDVEDEV),)),
    Case("H08", "head_to_head", "What was the head-to-head between Novak Djokovic and Andy Murray from 2015 through 2017?",
         (Expect("wins", DJOKOVIC, Filters(date_to="2017-12-31"), MURRAY), Expect("losses", DJOKOVIC, Filters(date_to="2017-12-31"), MURRAY)),
         (ToolCheck("head_to_head", DJOKOVIC, {"date_to": "2017-12-31"}, MURRAY),)),
    # Added from bugs found by hand (spec: add every bug found by hand as a new case).
    # The Milestone 3 live report said the 2-3 clay head-to-head was in Sinner's favour (D-022).
    Case("H09", "head_to_head", "Through the end of 2025, who led the clay head-to-head between Jannik Sinner and Carlos Alcaraz?",
         (Expect("wins", SINNER, Filters(date_to="2025-12-31", surface="Clay"), ALCARAZ),
          Expect("losses", SINNER, Filters(date_to="2025-12-31", surface="Clay"), ALCARAZ)),
         (ToolCheck("head_to_head", SINNER, {"date_to": "2025-12-31"}, ALCARAZ),),
         asks_who_leads=True),
    # The baseline answer to H04 said their last six meetings "split 3-3"; it was 4-2 to Alcaraz.
    Case("H10", "head_to_head", "What was the head-to-head between Jannik Sinner and Carlos Alcaraz in 2025?",
         (Expect("wins", SINNER, season(2025), ALCARAZ), Expect("losses", SINNER, season(2025), ALCARAZ)),
         (ToolCheck("head_to_head", SINNER, {"season": 2025}, ALCARAZ),)),
    # The baseline answer to H03 said Medvedev "won 10 of 14" from 2019 to 2024; it was 10 of 13.
    Case("H11", "head_to_head", "What was the head-to-head between Daniil Medvedev and Alexander Zverev on hard courts from 2019 through 2024?",
         (Expect("wins", MEDVEDEV, Filters(date_from="2019-01-01", date_to="2024-12-31", surface="Hard"), ZVEREV),
          Expect("losses", MEDVEDEV, Filters(date_from="2019-01-01", date_to="2024-12-31", surface="Hard"), ZVEREV)),
         (ToolCheck("head_to_head", MEDVEDEV, {"date_from": "2019-01-01", "date_to": "2024-12-31", "surface": "Hard"}, ZVEREV),)),
    # ---------- comparison: the same number for two players ----------
    Case("C01", "comparison", "Which of Daniil Medvedev and Alexander Zverev won more of their second-serve points in 2022?",
         (Expect("second_serve_points_won", MEDVEDEV, season(2022)), Expect("second_serve_points_won", ZVEREV, season(2022))),
         (ToolCheck("serve_return_stats", MEDVEDEV, {"season": 2022}), ToolCheck("serve_return_stats", ZVEREV, {"season": 2022}))),
    Case("C02", "comparison", "Who got a higher share of first serves in during 2023, Jannik Sinner or Carlos Alcaraz?",
         (Expect("first_serve_in", SINNER, season(2023)), Expect("first_serve_in", ALCARAZ, season(2023))),
         (ToolCheck("serve_return_stats", SINNER, {"season": 2023}), ToolCheck("serve_return_stats", ALCARAZ, {"season": 2023}))),
    Case("C03", "comparison", "Who saved a higher percentage of break points on clay in 2022, Rafael Nadal or Casper Ruud?",
         (Expect("break_points_saved", NADAL, season(2022, surface="Clay")), Expect("break_points_saved", RUUD, season(2022, surface="Clay"))),
         (ToolCheck("pressure_stats", NADAL, {"season": 2022, "surface": "Clay"}),
          ToolCheck("pressure_stats", RUUD, {"season": 2022, "surface": "Clay"}))),
    Case("C04", "comparison", "Who hit more aces per match in 2019, John Isner or Nick Kyrgios?",
         (Expect("aces_per_match", ISNER, season(2019)), Expect("aces_per_match", KYRGIOS, season(2019))),
         (ToolCheck("serve_return_stats", ISNER, {"season": 2019}), ToolCheck("serve_return_stats", KYRGIOS, {"season": 2019}))),
    Case("C05", "comparison", "On hard courts in 2021, who won a higher percentage of return points: Novak Djokovic or Daniil Medvedev?",
         (Expect("return_points_won", DJOKOVIC, season(2021, surface="Hard")), Expect("return_points_won", MEDVEDEV, season(2021, surface="Hard"))),
         (ToolCheck("serve_return_stats", DJOKOVIC, {"season": 2021, "surface": "Hard"}),
          ToolCheck("serve_return_stats", MEDVEDEV, {"season": 2021, "surface": "Hard"}))),
    Case("C06", "comparison", "Who had the better win rate on grass from 2015 through 2019, Roger Federer or Novak Djokovic?",
         (Expect("win_rate", FEDERER, Filters(date_to="2019-12-31", surface="Grass")),
          Expect("win_rate", DJOKOVIC, Filters(date_to="2019-12-31", surface="Grass"))),
         (ToolCheck("surface_splits", FEDERER, {"date_to": "2019-12-31"}), ToolCheck("surface_splits", DJOKOVIC, {"date_to": "2019-12-31"}))),
    # ---------- should refuse or caveat ----------
    Case("R01", "refuse_or_caveat", "What was Carlos Alcaraz's average rally length on clay in 2023?",
         refusal=Refusal(must=(r"rally", NEGATION))),
    Case("R02", "refuse_or_caveat", "How well did Roger Federer serve in 2022?",
         tools=(ToolCheck("serve_return_stats", FEDERER, {"season": 2022}),),
         refusal=Refusal(must=(r"(\bno (counted |tour-level |official |singles |regular )?matches\b|\b0 matches\b|\bzero matches\b"
                               r"|\bdid(n't|n’t| not) play\b|\bno (2022 )?(serve )?(data|stats)\b)",))),
    Case("R03", "refuse_or_caveat", "What was Rafael Nadal's win-loss record on clay in 2013?",
         refusal=Refusal(must=(r"2015", NEGATION + r"|\bonly\b|\bbefore\b|\bbegins?\b|\bstarts?\b"))),
    Case("R04", "refuse_or_caveat", "What was Iga Swiatek's first serve percentage in 2024?",
         tools=(ToolCheck("resolve_player", None),),
         refusal=Refusal(must=(NEGATION,), forbid_tools=STATS_TOOLS)),  # no stats for someone else instead
    Case("R05", "refuse_or_caveat", "How many aces per match did Zverev hit in 2019?",
         tools=(ToolCheck("resolve_player", None),),
         refusal=Refusal(must=(r"(which|mean|Alexander|Mischa)", r"(which|mean|\?)"),
                         forbid_tools=("serve_return_stats",))),
    Case("R06", "refuse_or_caveat", "What is the probability that Jannik Sinner beats Carlos Alcaraz in their next match?",
         refusal=Refusal(must=(r"predict|probabilit|forecast|odds", NEGATION),
                         must_not=(PROBABILITY_GIVEN,))),
)
