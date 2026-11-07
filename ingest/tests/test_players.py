"""Unit tests for the player matching rules in ingest/players.py.

Names are real cases from the pinned data; birth dates are made up (equal where the real
ones are equal), and the players and matches are synthetic, so expected results follow
from the rules alone.
"""

import collections

from ingest.players import (
    duplicate_groups,
    generate_crosswalk,
    generate_merges,
    name_keys,
    pair_matches,
    review_candidates,
    similar_names,
)


def player(pid, first, last, dob="", ioc="", wikidata=""):
    return {"player_id": pid, "name_first": first, "name_last": last, "dob": dob, "ioc": ioc, "wikidata_id": wikidata}


def test_name_keys_ignore_order_spacing_accents_and_apostrophes():
    assert name_keys("Bu Yunchaokete") & name_keys("Yunchaokete Bu")
    assert name_keys("Ji Sung Nam") & name_keys("Jisung Nam")
    assert name_keys("Christopher O'Connell") & name_keys("Christopher Oconnell")
    assert name_keys("Félix Auger-Aliassime") & name_keys("Felix Auger Aliassime")
    assert not name_keys("Alex Hernandez") & name_keys("Alejandro Hernandez")


def test_similar_names():
    assert similar_names("Roberto Cid Subervi", "Roberto Cid")  # words contained
    assert similar_names("Fares Zakaria", "Faris Zakaryia")  # close spelling
    assert not similar_names("Alex Hernandez", "Diego Duran")


def test_duplicate_groups_join_ids_across_both_name_keys():
    players = [
        player("1", "Ji Sung", "Nam", "18000101"),
        player("2", "Jisung", "Nam", "18000101"),
        player("3", "Nam", "Ji Sung", "18000101"),
        player("4", "Ji Sung", "Nam", "18000102"),  # different birth date: a different person
    ]
    assert duplicate_groups(players) == [["1", "2", "3"]]


def test_merges_keep_the_id_with_most_matches():
    players = [player("10", "Jakub", "Mensik", "18000103"), player("20", "Jakub", "Mensik", "18000103")]
    rows = generate_merges(players, collections.Counter({"20": 104}), existing=[])
    assert [(r["duplicate_id"], r["canonical_id"]) for r in rows] == [("10", "20")]


def test_pair_matches_skips_keys_that_are_not_unique():
    sackmann = [
        {"winner_name": "A B", "loser_name": "C D", "round": "RR", "id": "s1"},
        {"winner_name": "A B", "loser_name": "C D", "round": "RR", "id": "s2"},  # rematch in round robin
        {"winner_name": "E F", "loser_name": "G H", "round": "F", "id": "s3"},
    ]
    tml = [
        {"winner_name": "A B", "loser_name": "C D", "round": "RR", "id": "t1"},
        {"winner_name": "F E", "loser_name": "G H", "round": "F", "id": "t3"},  # word order differs
    ]
    assert [(s["id"], t["id"]) for s, t in pair_matches(sackmann, tml)] == [("s3", "t3")]


def test_crosswalk_steps_in_order():
    players = [
        player("100", "Bu", "Yunchaokete", "18000104", "CHN"),
        player("200", "Roberto", "Cid", "18000105", "DOM"),
        player("300", "Diego", "Duran", "", "ESA"),
        player("400", "Sam", "Same", "", "USA"),
    ]
    bios = {
        "LINK": {"player": "Anyone", "birthdate": "", "ioc": ""},
        "BU": {"player": "Yunchaokete Bu", "birthdate": "18000104", "ioc": "CHN"},
        "CID": {"player": "Roberto Cid Subervi", "birthdate": "18000105", "ioc": "DOM"},
        "DUR": {"player": "Diego Duran", "birthdate": "18000106", "ioc": "ESA"},
        "SAME": {"player": "Sam Same", "birthdate": "18000120", "ioc": "GBR"},  # country differs
        "NEW": {"player": "Nobody Known", "birthdate": "", "ioc": ""},
    }
    rows = generate_crosswalk(set(bios), bios, {"LINK": "400"}, players, merges={}, existing=[])
    got = {r["tml_id"]: (r["player_id"], r["method"]) for r in rows}
    assert got == {
        "LINK": ("400", "overlap_2025"),
        "BU": ("100", "name_birth_date"),
        "CID": ("200", "similar_name_birth_date"),
        "DUR": ("300", "name_only"),
        "NEW": ("900001", "new"),
        "SAME": ("900002", "new"),
    }


def test_review_list_finds_possible_duplicates_and_keeps_decisions():
    players = [
        player("208597", "Chak Lam Coleman", "Wong", "18000107", "HKG", "Q108498952"),
        player("209409", "Coleman", "Wong", "18000107", "HKG", "Q108498952"),
        player("102093", "Martin", "Damm", "18000108", "USA", "Q381173"),
        player("210013", "Martin", "Damm Sr", "18000109", "CZE", "Q381173"),  # not in the loaded data
        player("207834", "Juan Alejandro", "Hernandez Serrano", "18000110", "MEX"),
    ]
    loaded = {"208597", "209409", "102093"}
    crosswalk = [{"tml_id": "H0CD", "player_id": "900005", "method": "new", "tml_birth_date": "18000110"}]
    bios = {"H0CD": {"player": "Alex Hernandez", "birthdate": "18000110", "ioc": "MEX"}}
    existing = [{"player_ids": "208597 209409", "decision": "same person", "note": "kept"}]
    rows = review_candidates(players, loaded, collections.Counter({"209409": 30}), crosswalk, bios, existing)
    got = {r["player_ids"]: (r["signal"], r["decision"]) for r in rows}
    assert got == {
        "208597 209409": ("same Wikidata ID + same birth date and country", "same person"),
        "tml:H0CD 207834": ("new ID; Sackmann players born the same day", ""),
    }


def test_crosswalk_never_changes_existing_rows():
    existing = [{"tml_id": "K0P9", "player_id": "213933", "method": "manual", "tml_name": "", "tml_birth_date": "", "matched_name": "", "note": ""}]
    bios = {"K0P9": {"player": "Kaan Isik Kosaner", "birthdate": "18000111", "ioc": "TUR"}}
    rows = generate_crosswalk({"K0P9"}, bios, {}, [], merges={}, existing=existing)
    assert rows == existing
