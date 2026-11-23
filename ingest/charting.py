"""The Match Charting Project's files: link each charted match to a tour match, and read its
per-match stats (D-030).

A charted match counts only when it is the same match as a tour match in our data: each
player's name resolves to exactly one loaded player, the round is the same (any round for a
Davis Cup tie, which the match files write as "RR"), and the tour
match's tournament starts between 14 days before and 3 days after the charted date. Exactly
one tour match must fit. Everything else is kept with the reason it doesn't count.

The stats files hold Sackmann's own totals for each match, the ones Tennis Abstract's match
pages show. Nothing here parses the shot notation. A category with no usable row for a match
(missing, not whole numbers, or totals that don't add up) is left empty for that match and
counted, never filled with 0.
"""

from __future__ import annotations

import collections
import dataclasses
import datetime as dt
from collections.abc import Iterable
from typing import Any

from ingest.players import name_keys

LINK_WINDOW_DAYS = (-14, 3)  # tour tourney_date minus charted date, inclusive
RALLY_BUCKETS = ("1-3", "4-6", "7-9", "10")  # "10" means 10 shots or more
SERVE_COLUMNS = ("deuce_wide", "deuce_middle", "deuce_t", "ad_wide", "ad_middle", "ad_t")

MATCH_FIELDS = ["match_id", "Player 1", "Player 2", "Date", "Tournament", "Round", "Surface", "Best of"]
RAW_MATCH_COLUMNS = ["row_num", "match_id", "player1", "player2", "date", "tournament", "round", "surface", "best_of"]
SERVE_DIRECTION_COLUMNS = ["match_id", "player", "row", *SERVE_COLUMNS, "err_net", "err_wide", "err_deep",
                           "err_wide_deep", "err_foot", "err_unknown"]  # fmt: skip
RALLY_COLUMNS = ["match_id", "server", "returner", "row", "pts", "pl1_won", "pl1_winners", "pl1_forced",
                 "pl1_unforced", "pl2_won", "pl2_winners", "pl2_forced", "pl2_unforced"]  # fmt: skip
NET_POINTS_COLUMNS = ["match_id", "player", "row", "net_pts", "pts_won", "net_winner", "induced_forced",
                      "net_unforced", "passed_at_net", "passing_shot_induced_forced", "total_shots"]  # fmt: skip

CHART_COLUMNS = ["chart_id", "chart_date", "round", "player1_id", "player2_id", "match_id", "link"]
STATS_COLUMNS = [
    "chart_id", "match_id", "player_id",
    *(f"{serve}_{court}_{side}" for serve in ("first", "second") for court in ("deuce", "ad")
      for side in ("wide", "body", "t")),
    "rally_1_3_played", "rally_1_3_won", "rally_4_6_played", "rally_4_6_won",
    "rally_7_9_played", "rally_7_9_won", "rally_10_played", "rally_10_won", "points_played",
    "net_points", "net_points_won",
]  # fmt: skip


@dataclasses.dataclass
class Charting:
    """What the load writes: charting_matches rows, charting_player_stats rows, and counts of
    categories left empty, by reason."""

    charts: list[tuple]
    stats: list[tuple]
    empty_categories: collections.Counter


def whole(value: Any) -> int | None:
    """A non-negative whole number written as digits, or None."""
    text = (value or "").strip()
    return int(text) if text.isdigit() else None


def parse_date(value: str) -> dt.date | None:
    try:
        return dt.datetime.strptime((value or "").strip(), "%Y%m%d").date()
    except ValueError:
        return None


def resolver(players: Iterable[tuple[int, str]]):
    """A function from a charted name to the one loaded player it names, or None. Names compare
    by the keys player matching already uses (D-009): letters in order, and words sorted."""
    by_key: dict[str, set[int]] = collections.defaultdict(set)
    for player_id, full_name in players:
        for key in name_keys(full_name):
            by_key[key].add(player_id)

    def resolve(name: str) -> int | None:
        found = set().union(*(by_key.get(key, set()) for key in name_keys(name or "")))
        return found.pop() if len(found) == 1 else None

    return resolve


def same_round(match: dict, chart_round: str) -> bool:
    """The round must agree, except for a Davis Cup tie: the match files write every tie as
    "RR", with its stage in the tie's name, while a chart says QF, SF or F."""
    return match["round"] == chart_round or (match["tourney_level"] == "D" and match["round"] == "RR")


def link_charts(chart_rows: list[dict], players: Iterable[tuple[int, str]], matches: list[dict]) -> list[dict]:
    """One entry per charted match ID: its date, round, player IDs, linked tour match and link
    status. `matches` are the loaded tour matches (match_id, winner_id, loser_id, round,
    tourney_level, tourney_date)."""
    resolve = resolver(players)
    first_date = min(m["tourney_date"] for m in matches)
    tour: dict[frozenset, list[dict]] = collections.defaultdict(list)
    for m in matches:
        tour[frozenset((m["winner_id"], m["loser_id"]))].append(m)

    by_id: dict[str, list[dict]] = collections.defaultdict(list)
    for row in chart_rows:
        by_id[(row.get("match_id") or "").strip()].append(row)

    links = []
    for chart_id, rows in by_id.items():
        row = rows[0]
        kept = {tuple((r.get(f) or "").strip() for f in MATCH_FIELDS) for r in rows}
        chart_date, round_ = parse_date(row.get("Date")), (row.get("Round") or "").strip()
        p1, p2 = resolve(row.get("Player 1")), resolve(row.get("Player 2"))
        link = {"chart_id": chart_id, "chart_date": chart_date, "round": round_ or None,
                "player1": (row.get("Player 1") or "").strip(), "player2": (row.get("Player 2") or "").strip(),
                "player1_id": p1, "player2_id": p2, "match_id": None}  # fmt: skip
        if not chart_id or chart_date is None or len(kept) > 1:
            link["link"] = "unreadable_row"  # no ID or date, or the same ID with different details
        elif chart_date < first_date:
            link["link"] = "before_data"
        elif p1 is None or p2 is None or p1 == p2:
            link["link"] = "name_not_resolved"
        else:
            low, high = LINK_WINDOW_DAYS
            fits = [
                m for m in tour.get(frozenset((p1, p2)), [])
                if same_round(m, round_) and low <= (m["tourney_date"] - chart_date).days <= high
            ]  # fmt: skip
            # Back-to-back events (Canada, then Cincinnati) can both fit. A chart is dated during
            # its event, and only rarely a day or three before it starts (D-030), so take the
            # event that started most recently on or before the charted date.
            started = sorted((m for m in fits if m["tourney_date"] <= chart_date), key=lambda m: m["tourney_date"])
            if len(fits) > 1 and started and (len(started) == 1 or started[-1]["tourney_date"] > started[-2]["tourney_date"]):
                fits = [started[-1]]
            link["link"] = "linked" if len(fits) == 1 else "no_tour_match" if not fits else "several_tour_matches"
            if len(fits) == 1:
                link["match_id"] = fits[0]["match_id"]
        links.append(link)

    # A tour match charted twice keeps neither chart: there is no way to tell which is right.
    charted = collections.Counter(link["match_id"] for link in links if link["match_id"])
    for link in links:
        if link["match_id"] and charted[link["match_id"]] > 1:
            link["link"], link["match_id"] = "charted_twice", None
    return links


def _serve(rows: dict, chart_id: str, name: str) -> list[int | None] | None:
    """12 counts: first serves in, then every second serve, each by deuce and ad court and
    wide, body, T. None if either row is missing or not whole numbers."""
    values = []
    for serve in ("1", "2"):
        row = rows.get((chart_id, name, serve))
        counts = [whole(row[c]) for c in SERVE_COLUMNS] if row else [None]
        if None in counts:
            return None
        values += counts
    return values


def _rally(rows: dict, chart_id: str, player1: str) -> dict[int, list[int]] | None:
    """Points played and won by rally length, and points in the match, for players 1 and 2.
    Uses the rows whose `server` column is player 1 (their pl1 is player 1). None unless the
    buckets add up to the match total and each side's points won add up to it too."""
    total = rows.get((chart_id, player1, "Total"))
    if total is None:
        return None
    points, won1, won2 = whole(total["pts"]), whole(total["pl1_won"]), whole(total["pl2_won"])
    if None in (points, won1, won2) or won1 + won2 != points:
        return None
    sides: dict[int, list[int]] = {1: [], 2: []}
    played_sum = 0
    for bucket in RALLY_BUCKETS:
        row = rows.get((chart_id, player1, bucket))  # a bucket with no points has no row
        played, w1, w2 = (whole(row["pts"]), whole(row["pl1_won"]), whole(row["pl2_won"])) if row else (0, 0, 0)
        if None in (played, w1, w2) or w1 + w2 != played:
            return None
        played_sum += played
        sides[1] += [played, w1]
        sides[2] += [played, w2]
    if played_sum != points:
        return None
    return {side: values + [points] for side, values in sides.items()}


def _net(rows: dict, chart_id: str, name: str) -> list[int] | None:
    row = rows.get((chart_id, name, "NetPoints"))
    values = [whole(row["net_pts"]), whole(row["pts_won"])] if row else [None]
    return None if None in values or values[1] > values[0] else values


def player_stats(links: list[dict], serve_rows: list[dict], rally_rows: list[dict], net_rows: list[dict]) -> Charting:
    """charting_matches rows for every chart, and charting_player_stats rows for both players of
    every linked chart."""
    serve = {(r["match_id"], r["player"], r["row"]): r for r in serve_rows}
    rally = {(r["match_id"], r["server"], r["row"]): r for r in rally_rows if r["row"] in ("Total", *RALLY_BUCKETS)}
    net = {(r["match_id"], r["player"], r["row"]): r for r in net_rows if r["row"] == "NetPoints"}
    empty: collections.Counter = collections.Counter()
    charts, stats = [], []
    for link in links:
        charts.append(tuple(link[c] for c in CHART_COLUMNS))
        if link["link"] != "linked":
            continue
        chart_id = link["chart_id"]
        rallies = _rally(rally, chart_id, link["player1"])
        for side, name, player_id in ((1, link["player1"], link["player1_id"]), (2, link["player2"], link["player2_id"])):
            directions = _serve(serve, chart_id, name)
            rally_values = rallies[side] if rallies else None
            net_values = _net(net, chart_id, name)
            if net_values and rally_values and net_values[0] > rally_values[-1]:
                net_values = None  # more net points than points in the match
            for category, values in (("serve_direction", directions), ("rally_length", rally_values), ("net_points", net_values)):
                if values is None:
                    empty[category] += 1
            stats.append((
                chart_id, link["match_id"], player_id,
                *(directions or [None] * 12), *(rally_values or [None] * 9), *(net_values or [None] * 2),
            ))  # fmt: skip
    return Charting(charts, stats, empty)
