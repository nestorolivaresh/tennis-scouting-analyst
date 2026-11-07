# Where the stats-layer test values come from

Every expected number in `api/tests/test_stats.py` comes from one of two sources that share
no code with the stats layer (spec rule: "Test values must come from a named source").

- **TA**: [Tennis Abstract](https://www.tennisabstract.com/cgi-bin/player-classic.cgi?p=JannikSinner&f=A2024qq),
  Jannik Sinner, "Time Span: 2024" totals row, read on 2026-11-07. Tennis Abstract rounds to
  0.1%, so tests allow 0.05 percentage points. Its definitions (1stIn, 1st%, 2nd%, SPW, RPW,
  Ace%) are the same formulas as the spec's stat definitions.
- **Hand N**: check N in `api/tests/hand_checks.sh`, which computes values with `awk` straight
  from the raw CSV files. Run it with `sh api/tests/hand_checks.sh` after `ingest.download`.

| Tool | Check | Expected | Source | Tool result |
| --- | --- | --- | --- | --- |
| `resolve_player` | IDs for Sinner, both Zverevs, Auger Aliassime, Bu Yunchaokete, Alcaraz, Djokovic, Medvedev, Gasquet, Hassan, Catarina | 206173, 100644 / 104999, 200000, 207352, 207989, 104925, 106421, 104755, 133975, 200031 | Hand 9 | match |
| `player_profile` | Sinner's hand, country, height | R, ITA, 191 cm | Hand 16 | match |
| `player_profile` | Sinner's newest match and latest rank | Wimbledon 2026 final on 2026-07-12, won; rank 1 | Hand 6 | match |
| `player_profile` | Latest rank when the newest match has none (Catarina) | newest match Davis Cup FIN v MON, 2026-09-18, no rank; latest rank 452 at Davis Cup MON v ECU (2023) | Hand 19 | match |
| all stats tools | Data window | first tournament 2015-01-04, last tournament start 2026-10-26, last match 2026-11-01 | Hand 17 | match |
| `surface_splits` | Sinner 2024 record | 73-6 | TA | 73-6 |
| `surface_splits` | Sinner 2024 by surface | Hard 53-3, Clay 11-2, Grass 9-1 | Hand 1 | match |
| `surface_splits` | Sinner 2024 walkovers excluded | 2 | Hand 2 | 2 |
| `surface_splits` | Sinner 2024 matches ended by the opponent quitting / by Sinner quitting | 1 (Raonic, Rotterdam) / 0 | Hand 18 | 1 / 0 |
| `surface_splits` | Sinner 2024 against left-handers / right-handers | 6-0 / 67-6, no unknown hands | Hand 10, TA | match |
| `surface_splits` | Djokovic 2024 against right-handers / left-handers, unknown hand excluded | 32-8 / 4-1, 1 excluded (Xilas) | Hand 20 | match |
| `surface_splits` | Sinner, tournaments starting 2024-01-15 to 2024-01-15 (inclusive bounds) | 7-0 (Australian Open) | Hand 11 | 7-0 |
| `surface_splits` | Sinner 2024 by level: G, D, G+M, A+F | 23-2, 3-0, 51-5, 19-1 | Hand 12 | match |
| `surface_splits` | Gasquet 2018: matches counted, unknown results excluded | 57, 1 (Davis Cup FRA v ESP, score contradicts the winner) | Hand 14 | 57, 1 |
| `surface_splits` | Hassan 2023 on hard: matches with no surface excluded | 2 (Davis Cup UKR v LBN) | Hand 15 | 2 |
| `surface_splits` | Alcaraz 2026 record (TML season) | 37-5 | Hand 7 | 37-5 |
| `surface_splits` | Zverev 2024 matches, without and with exhibitions | 88, 90 (2 Laver Cup) | Hand 8 | 88, 90 |
| `serve_return_stats` | Sinner 2024 first serve in | 61.6% | TA | 61.59% (3,693 / 5,996) |
| `serve_return_stats` | Sinner 2024 first-serve points won | 79.3% | TA | 79.34% |
| `serve_return_stats` | Sinner 2024 second-serve points won | 57.8% | TA | 57.84% |
| `serve_return_stats` | Sinner 2024 service points won | 71.1% | TA | 71.08% |
| `serve_return_stats` | Sinner 2024 return points won | 40.9% | TA | 40.87% |
| `serve_return_stats` | Sinner 2024 aces per serve point | 9.9% | TA | 9.91% (594 / 5,996) |
| `serve_return_stats` | Alcaraz 2023 clay: first serves in, aces per match | 1,346 / 1,999; 95 aces in 28 matches | Hand 4 | match |
| `serve_return_stats` | Alcaraz 2022: matches, matches with stats, aces per match | 70, 68; 259 aces over the 68 with stats | Hand 13 | match |
| `pressure_stats` | Sinner 2024 clay: break points saved, converted | 47 / 68; 57 / 120 | Hand 3 | match |
| `head_to_head` | Sinner v Alcaraz record and by surface | 7-10; Hard 3-7, Clay 2-3, Grass 2-0 | Hand 5 | match |
| `head_to_head` | Newest meeting | 2026 Monte Carlo final, Sinner won | Hand 5 | match |
| `recent_form` | Sinner's last 5 matches | Wimbledon 2026 R32 to F, all wins (Brooksby, Mochizuki, Struff, Djokovic, Zverev), final on 2026-07-12 | Hand 6 | match |

Also cross-checked on Tennis Abstract on 2026-11-07: Sinner's latest match listed there is the
Wimbledon 2026 final, the same as in the TML data, so the gap from July to November is real
(he didn't play) and not missing data.

## Can the tests fail?

A passing test is only evidence if it fails when its rule is broken. On 2026-11-07 each rule
below was broken on purpose in a copy of `api/`, and the test suite was run against the copy.

| Bug put back | Caught by |
| --- | --- |
| A close spelling is accepted as the player | `test_resolve_player_never_accepts_a_close_spelling` |
| Opponent-hand filter inverted | `test_opponent_hand_filter` |
| Opponents of unknown hand counted | `test_unknown_opponent_hand_is_excluded_and_counted` |
| `date_from` or `date_to` exclusive | `test_date_bounds_are_inclusive` |
| Tournament level ignored | `test_tourney_level_filter` |
| Unknown results counted | `test_unknown_result_is_excluded_and_counted` |
| Matches with no surface dropped without being counted | `test_unknown_surface_is_excluded_and_counted_when_filtering_by_surface` |
| Aces per match divided by all matches, not matches with stats | `test_aces_per_match_divides_by_matches_with_stats` |
| Latest rank taken from a match with no rank | `test_latest_rank_skips_matches_without_a_rank` |
| Who quit a retirement swapped | `test_surface_splits_sinner_2024` |
| Last match reports the tournament start as the match date | `test_player_profile` |
| No name length cap; Unicode digits accepted; filters not checked to be an object | `test_argument_checks_happen_before_any_query`, `test_parse_rejects_bad_filters` |
| `more_candidates` never set | `test_resolve_player_flags_more_candidates` |
| Session not read-only; no statement timeout | `test_connection_is_read_only_outside_tool_transactions` |
| `match_date` dropped from the match order | **Not caught.** In the pinned TML file, match numbers already follow match dates in every round robin, so the order is the same either way (D-014). |

## Disagreements with Tennis Abstract

The pinned data is the source of truth for the tests (D-015). Tennis Abstract keeps updating,
so a difference from it is investigated and written down here, not "fixed" by changing the
test. No differences were found on 2026-11-07.
