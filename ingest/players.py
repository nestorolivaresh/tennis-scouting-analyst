"""Player identity files that ingestion depends on. All three are committed and reviewed by hand.

- ingest/player_merges.csv: Sackmann player IDs that belong to the same person. Rows are
  added automatically for the same name and full birth date, or by hand after review. Each
  duplicate maps to one canonical ID so a player's matches aren't split across two IDs.
- ingest/player_crosswalk.csv: TML player codes (ATP codes such as B0BI) mapped to the
  project's player_id. Players who aren't in Sackmann's file get new IDs from 900001 up.
- ingest/player_review.csv: possible duplicates the rules above didn't resolve, for a
  person to decide. Decisions typed into it are kept when the file is regenerated.

See docs/decisions.md D-009.

Usage: uv run python -m ingest.players
    Adds rows for IDs that aren't in the files yet and never changes existing rows, so IDs
    stay stable. Review new rows, especially any method other than 'overlap_2025', and
    every review row without a decision.
"""

from __future__ import annotations

import collections
import csv
import difflib
import re
import unicodedata
from pathlib import Path

from ingest.download import RAW_DIR, SACKMANN_SEASONS, TML_SEASON
from ingest.transform import parse_date

ROOT = Path(__file__).resolve().parent.parent
MERGES_PATH = ROOT / "ingest" / "player_merges.csv"
CROSSWALK_PATH = ROOT / "ingest" / "player_crosswalk.csv"
REVIEW_PATH = ROOT / "ingest" / "player_review.csv"
NEW_ID_START = 900001
# The committed files hold IDs, methods and decisions only: no names or birth dates, since
# the repo is public and some players are minors (D-013). The review output printed by main()
# looks those details up in the gitignored raw files.
MERGE_FIELDS = ["duplicate_id", "canonical_id", "duplicate_matches", "canonical_matches", "reason"]
CROSSWALK_FIELDS = ["tml_id", "player_id", "method", "note"]
REVIEW_FIELDS = ["signal", "player_ids", "decision", "note"]


# ---------- file helpers ----------


def read_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def write_rows(path: Path, fields: list[str], rows: list[dict]) -> None:
    """Write only `fields`; any other keys in the rows are left out of the file."""
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------- name matching ----------


def full_name(player: dict) -> str:
    return f"{player['name_first']} {player['name_last']}".strip()


def name_tokens(name: str) -> list[str]:
    """Lowercase ASCII words: "Christopher O'Connell" -> ['christopher', 'oconnell']."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z]+", ascii_name.lower().replace("'", ""))


def name_keys(name: str) -> set[str]:
    """Two keys per name. Letters in order ignores spacing ('Ji Sung Nam' = 'Jisung Nam');
    words sorted ignores word order ('Bu Yunchaokete' = 'Yunchaokete Bu')."""
    tokens = name_tokens(name)
    return {"".join(tokens), "".join(sorted(tokens))} if tokens else set()


def similar_names(a: str, b: str) -> bool:
    """True when one name's words are all in the other ('Roberto Cid' / 'Roberto Cid
    Subervi') or the spellings are close ('Fares Zakaria' / 'Faris Zakaryia').
    Only used together with an identical birth date."""
    words_a, words_b = set(name_tokens(a)), set(name_tokens(b))
    if words_a and words_b and (words_a <= words_b or words_b <= words_a):
        return True
    return difflib.SequenceMatcher(None, "".join(sorted(words_a)), "".join(sorted(words_b))).ratio() >= 0.8


def name_dob_index(players: list[dict]) -> dict[tuple[str, str], set[str]]:
    """(name key, birth date) -> Sackmann IDs, for players with a full birth date."""
    index = collections.defaultdict(set)
    for player in players:
        if parse_date(player["dob"]) is not None:
            for key in name_keys(full_name(player)):
                index[(key, player["dob"])].add(player["player_id"])
    return index


def pair_matches(sackmann_rows: list[dict], tml_rows: list[dict]) -> list[tuple[dict, dict]]:
    """Pair rows from one season that describe the same match: same winner, loser and
    round. A key must occur exactly once in each source to be used."""
    pairs: dict[int, tuple[dict, dict]] = {}
    for key_of in (lambda n: "".join(name_tokens(n)), lambda n: "".join(sorted(name_tokens(n)))):

        def unique(rows):
            groups = collections.defaultdict(list)
            for row in rows:
                groups[(key_of(row["winner_name"]), key_of(row["loser_name"]), row["round"])].append(row)
            return {key: group[0] for key, group in groups.items() if len(group) == 1}

        sackmann, tml = unique(sackmann_rows), unique(tml_rows)
        for key in sorted(sackmann.keys() & tml.keys()):  # sorted: same order on every run
            pairs.setdefault(id(sackmann[key]), (sackmann[key], tml[key]))
    return list(pairs.values())


def overlap_links(pairs: list[tuple[dict, dict]]) -> tuple[dict[str, str], int]:
    """TML ID -> Sackmann ID from paired matches, and how many TML IDs had conflicting links."""
    links = collections.defaultdict(set)
    for sackmann, tml in pairs:
        links[tml["winner_id"]].add(sackmann["winner_id"])
        links[tml["loser_id"]].add(sackmann["loser_id"])
    conflicts = sum(1 for ids in links.values() if len(ids) > 1)
    return {tml_id: next(iter(ids)) for tml_id, ids in links.items() if len(ids) == 1}, conflicts


# ---------- merges ----------


def duplicate_groups(players: list[dict]) -> list[list[str]]:
    """Groups of Sackmann IDs that share a name key and a full birth date, joined
    transitively (union-find) because each player has two name keys."""
    parent: dict[str, str] = {}

    def find(pid: str) -> str:
        while parent.setdefault(pid, pid) != pid:
            pid = parent[pid]
        return pid

    for ids in name_dob_index(players).values():
        first, *others = sorted(ids)
        for other in others:
            parent[find(other)] = find(first)
    groups = collections.defaultdict(list)
    for pid in parent:
        groups[find(pid)].append(pid)
    return [sorted(group, key=int) for group in groups.values() if len(group) > 1]


def generate_merges(players: list[dict], match_counts: collections.Counter, existing: list[dict]) -> list[dict]:
    """Merge rows for duplicate groups where at least one ID plays in the loaded matches.
    The canonical ID is the one with the most matches, then the lowest ID."""
    rows = list(existing)
    already = {row["duplicate_id"] for row in existing}
    by_id = {player["player_id"]: player for player in players}
    for group in sorted(duplicate_groups(players), key=lambda g: full_name(by_id[g[0]])):
        if not any(match_counts[pid] for pid in group):
            continue
        canonical = max(group, key=lambda pid: (match_counts[pid], -int(pid)))
        for pid in group:
            if pid != canonical and pid not in already:
                rows.append(
                    {
                        "duplicate_id": pid,
                        "canonical_id": canonical,
                        "duplicate_matches": match_counts[pid],
                        "canonical_matches": match_counts[canonical],
                        "reason": "same name and birth date",
                    }
                )
    return rows


# ---------- review list ----------


def review_candidates(
    players: list[dict],
    loaded_ids: set[str],
    match_counts: collections.Counter,
    crosswalk_rows: list[dict],
    tml_bios: dict[str, dict],
    existing: list[dict],
) -> list[dict]:
    """Possible duplicates for a person to decide, keeping decisions already made:
    - Sackmann IDs used in the loaded data that share a full birth date and country, or a
      Wikidata ID (a strong signal, but not proof: father and son Martin Damm share one);
    - every crosswalk row given a new ID, with any Sackmann player born the same day."""
    by_id = {player["player_id"]: player for player in players}
    signals: dict[tuple[str, ...], set[str]] = collections.defaultdict(set)
    by_birth_country, by_wikidata = collections.defaultdict(set), collections.defaultdict(set)
    for pid in loaded_ids:
        player = by_id[pid]
        if parse_date(player["dob"]) and player["ioc"].strip():
            by_birth_country[(player["dob"], player["ioc"])].add(pid)
        if player["wikidata_id"].strip():
            by_wikidata[player["wikidata_id"]].add(pid)
    for signal, index in (("same birth date and country", by_birth_country), ("same Wikidata ID", by_wikidata)):
        for ids in index.values():
            if len(ids) > 1:
                signals[tuple(sorted(ids, key=int))].add(signal)

    born_on = collections.defaultdict(list)
    for player in players:
        if parse_date(player["dob"]):
            born_on[player["dob"]].append(player["player_id"])
    for row in crosswalk_rows:
        if row["method"] == "new":
            bio = tml_bios.get(row["tml_id"], {})
            country = bio.get("ioc", "").strip()
            candidates = [
                pid for pid in born_on.get(bio.get("birthdate", ""), [])
                if not country or not by_id[pid]["ioc"].strip() or by_id[pid]["ioc"].strip() == country
            ]  # fmt: skip
            signals[(f"tml:{row['tml_id']}", *sorted(candidates, key=int))].add("new ID; Sackmann players born the same day")

    decided = {row["player_ids"]: row for row in existing}
    rows = []
    for ids, found in sorted(signals.items()):
        key = " ".join(ids)
        rows.append(
            {
                "signal": " + ".join(sorted(found)),
                "player_ids": key,
                "decision": decided.get(key, {}).get("decision", ""),
                "note": decided.get(key, {}).get("note", ""),
            }
        )
    return rows


def describe(pid: str, by_id: dict[str, dict], tml_bios: dict[str, dict], match_counts: collections.Counter) -> str:
    """Name, birth date, country and match count, for review output in the terminal only."""
    if pid.startswith("tml:"):
        bio = tml_bios.get(pid[4:], {})
        return f"TML {pid[4:]} {bio.get('player', '?')} (born {bio.get('birthdate') or '?'}, {bio.get('ioc') or '?'})"
    player = by_id.get(pid)
    if player is None:
        return f"{pid} (new ID)"
    return f"{pid} {full_name(player)} (born {player['dob'] or '?'}, {player['ioc'] or '?'}, {match_counts[pid]} matches 2015-2025)"


# ---------- crosswalk ----------


def generate_crosswalk(
    tml_ids: set[str],
    tml_bios: dict[str, dict],
    links: dict[str, str],
    players: list[dict],
    merges: dict[int, int],
    existing: list[dict],
) -> list[dict]:
    """Map each TML ID, trying in order (D-009):
    1. overlap_2025: the same player in matches both sources have for 2025;
    2. name_birth_date: same name (either key) and same birth date;
    3. similar_name_birth_date: same birth date and a close name, one candidate only;
    4. name_only: same name, and the only Sackmann player with that name has no birth date;
    5. new: a new ID from 900001 up.
    Steps 3 and 4 say 'check' in the note, for review."""
    canonical = lambda pid: str(merges.get(int(pid), int(pid)))  # noqa: E731
    by_id = {player["player_id"]: player for player in players}
    exact = name_dob_index(players)
    by_dob, by_name = collections.defaultdict(list), collections.defaultdict(set)
    for player in players:
        for key in name_keys(full_name(player)):
            by_name[key].add(player["player_id"])
        if parse_date(player["dob"]) is not None:
            by_dob[player["dob"]].append(player)
    rows = list(existing)
    done = {row["tml_id"] for row in existing}
    next_new = max([int(r["player_id"]) for r in existing if int(r["player_id"]) >= NEW_ID_START] + [NEW_ID_START - 1]) + 1

    for tml_id in sorted(tml_ids - done):
        bio = tml_bios.get(tml_id, {"player": "", "birthdate": ""})
        name, dob = bio["player"], bio["birthdate"]
        keys = name_keys(name)
        # The weaker steps (3 and 4) also refuse a link when both sources give a country
        # and the countries differ.
        same_country = lambda p: not bio.get("ioc", "").strip() or not p["ioc"].strip() or bio["ioc"].strip() == p["ioc"].strip()  # noqa: E731
        exact_ids = sorted({canonical(pid) for key in keys for pid in exact.get((key, dob), set())}, key=int)
        similar_ids = sorted(
            {canonical(p["player_id"]) for p in by_dob.get(dob, []) if similar_names(name, full_name(p)) and same_country(p)},
            key=int,
        )
        same_name = sorted({pid for key in keys for pid in by_name.get(key, set())}, key=int)
        note = ""
        if tml_id in links:
            player_id, method = canonical(links[tml_id]), "overlap_2025"
        elif exact_ids:
            player_id, method = exact_ids[0], "name_birth_date"
            if len(exact_ids) > 1:
                note = f"several Sackmann IDs ({'/'.join(exact_ids)}) not merged; picked the lowest"
        elif len(similar_ids) == 1:
            player_id, method = similar_ids[0], "similar_name_birth_date"
            note = "name spelled differently; check"
        elif len(same_name) == 1 and parse_date(by_id[same_name[0]]["dob"]) is None and same_country(by_id[same_name[0]]):
            player_id, method = canonical(same_name[0]), "name_only"
            note = "Sackmann has no birth date for this player; check"
        else:
            player_id, method = str(next_new), "new"
            next_new += 1
            if same_name:
                note = f"{len(same_name)} Sackmann players share this name; not linked"
        rows.append({"tml_id": tml_id, "player_id": player_id, "method": method, "note": note})
    return rows


def main() -> int:
    sackmann_dir, tml_dir = RAW_DIR / "sackmann", RAW_DIR / "tml"
    players = read_rows(sackmann_dir / "atp_players.csv")
    sackmann_by_season = {y: read_rows(sackmann_dir / f"atp_matches_{y}.csv") for y in SACKMANN_SEASONS}
    match_counts = collections.Counter(
        pid for rows in sackmann_by_season.values() for row in rows for pid in (row["winner_id"], row["loser_id"])
    )

    by_id = {player["player_id"]: player for player in players}
    tml_bios = {row["id"]: row for row in read_rows(tml_dir / "ATP_Database.csv")}
    show = lambda pid: describe(pid, by_id, tml_bios, match_counts)  # noqa: E731

    merge_rows = generate_merges(players, match_counts, read_rows(MERGES_PATH) if MERGES_PATH.exists() else [])
    write_rows(MERGES_PATH, MERGE_FIELDS, merge_rows)
    merges = {int(r["duplicate_id"]): int(r["canonical_id"]) for r in merge_rows}
    print(f"{MERGES_PATH.relative_to(ROOT)}: {len(merge_rows)} duplicate IDs")
    for row in merge_rows:
        print(f"  {show(row['duplicate_id'])} -> {show(row['canonical_id'])}  [{row['reason']}]")

    tml_rows = read_rows(tml_dir / f"{TML_SEASON}.csv")
    tml_ids = {row["winner_id"] for row in tml_rows} | {row["loser_id"] for row in tml_rows}
    overlap_season = SACKMANN_SEASONS[-1]  # the last Sackmann season, also downloaded from TML
    links, conflicts = overlap_links(pair_matches(sackmann_by_season[overlap_season], read_rows(tml_dir / f"{overlap_season}.csv")))
    existing = read_rows(CROSSWALK_PATH) if CROSSWALK_PATH.exists() else []
    crosswalk = generate_crosswalk(tml_ids, tml_bios, links, players, merges, existing)
    write_rows(CROSSWALK_PATH, CROSSWALK_FIELDS, crosswalk)
    methods = collections.Counter(row["method"] for row in crosswalk)
    print(f"{CROSSWALK_PATH.relative_to(ROOT)}: {len(crosswalk)} TML IDs, {dict(methods)}; overlap conflicts: {conflicts}")
    for row in crosswalk:
        if row["method"] not in ("overlap_2025", "name_birth_date") or row["note"]:
            print(f"  {show('tml:' + row['tml_id'])} -> {show(row['player_id'])} {row['method']}"
                  f"{'  [' + row['note'] + ']' if row['note'] else ''}")

    # Sackmann IDs that the loaded data uses: in 2015-2025 matches, or as crosswalk targets.
    loaded_ids = {pid for pid in match_counts if pid in {p["player_id"] for p in players}}
    loaded_ids |= {row["player_id"] for row in crosswalk if int(row["player_id"]) < NEW_ID_START}
    review = review_candidates(players, loaded_ids, match_counts, crosswalk, tml_bios, read_rows(REVIEW_PATH) if REVIEW_PATH.exists() else [])
    write_rows(REVIEW_PATH, REVIEW_FIELDS, review)
    pending = [row for row in review if not row["decision"]]
    print(f"{REVIEW_PATH.relative_to(ROOT)}: {len(review)} possible duplicates, {len(pending)} without a decision")
    for row in pending:
        print(f"  [{row['signal']}] " + " | ".join(show(pid) for pid in row["player_ids"].split()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
