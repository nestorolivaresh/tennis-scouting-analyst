"""Milestone 0 data audit.

Checks the raw files against the data dictionary and records the facts the schema
depends on, then writes docs/data-audit.md. It only reads files; it changes nothing.

Usage: uv run python -m ingest.audit
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

from ingest.download import LOCK_PATH, RAW_DIR, SACKMANN_SEASONS, verify
from ingest.players import name_dob_index, name_keys, overlap_links, pair_matches
from ingest.transform import SPECIAL_NAME_RE, STAT_FIELDS, result_type, sets_won_lost

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "docs" / "data-audit.md"
STAT_COLUMNS = [f"{side}_{field}" for side in ("w", "l") for field in STAT_FIELDS]
# The last date in Sackmann's final commit ("thru 8 jun 2026"), for comparing 2026 coverage.
SACKMANN_2026_CUTOFF = "20260607"


# ---------- helpers ----------


def read_csv(path: Path) -> pd.DataFrame:
    """Read every column as text, keeping empty cells as '' so nothing is coerced."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def counts(series: pd.Series) -> str:
    """Render value counts inline, most common first, with '(empty)' for blanks."""
    items = series.replace("", "(empty)").value_counts()
    return ", ".join(f"`{value}` {count:,}" for value, count in items.items())


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def has_stats(df: pd.DataFrame) -> pd.Series:
    return (df["w_svpt"] != "") & (df["l_svpt"] != "")


def dictionary_columns(text: str) -> list[str]:
    """Column names are the bare identifier lines before the doubles notes."""
    singles = text.split("* _doubles_")[0]
    return [line.strip() for line in singles.splitlines() if re.fullmatch(r"[A-Za-z0-9_]+", line.strip())]


# ---------- checks ----------


def check_hashes(lock: dict) -> tuple[int, list[str]]:
    total, failures = 0, []
    for source, spec in lock.items():
        for name, entry in spec["files"].items():
            total += 1
            path = RAW_DIR / source / name
            problem = verify(path.read_bytes(), entry) if path.exists() else "missing"
            if problem:
                failures.append(f"{source}/{name}: {problem}")
    return total, failures


def score_checks(df: pd.DataFrame) -> dict:
    types = df["score"].map(result_type)
    completed = df[types == "completed"]
    bad_sets = []
    for row in completed.itertuples():
        won, lost = sets_won_lost(row.score)
        needed = int(row.best_of) // 2 + 1 if row.best_of.isdigit() else None
        if needed is None or won != needed or lost >= needed:
            bad_sets.append((row.tourney_level, f"`{row.score}` (best of {row.best_of}, {row.tourney_name} {row.round})"))
    return {
        "types": types,
        "unknown": df.loc[types == "unknown", "score"].value_counts().head(10),
        "bad_sets": bad_sets,
    }


def compare_stats(pairs) -> dict:
    result = collections.Counter()
    fields = collections.Counter()
    swaps = []
    for s, t in pairs:
        if not (s["w_svpt"] and s["l_svpt"] and t["w_svpt"] and t["l_svpt"]):
            result["stats missing in one or both"] += 1
            continue
        sw = [s[f"w_{f}"] for f in STAT_FIELDS]
        sl = [s[f"l_{f}"] for f in STAT_FIELDS]
        tw = [t[f"w_{f}"] for f in STAT_FIELDS]
        tl = [t[f"l_{f}"] for f in STAT_FIELDS]
        if sw == tw and sl == tl:
            result["identical"] += 1
        elif sw == tl and sl == tw:
            result["winner and loser stats swapped"] += 1
            swaps.append(f"{s['tourney_name']} {s['round']}: {s['winner_name']} d. {s['loser_name']}")
        else:
            result["at least one field differs"] += 1
            for i, field in enumerate(STAT_FIELDS):
                if sw[i] != tw[i] or sl[i] != tl[i]:
                    fields[field] += 1
    return {"result": result, "fields": fields, "swaps": swaps}


# ---------- report ----------


def main() -> int:
    lock = json.loads(LOCK_PATH.read_text())
    sackmann_dir, tml_dir = RAW_DIR / "sackmann", RAW_DIR / "tml"
    out: list[str] = []
    add = out.append

    sack_by_season = {year: read_csv(sackmann_dir / f"atp_matches_{year}.csv") for year in SACKMANN_SEASONS}
    sack = pd.concat([df.assign(season=year) for year, df in sack_by_season.items()], ignore_index=True)
    tml26 = read_csv(tml_dir / "2026.csv").assign(season=2026)
    tml25 = read_csv(tml_dir / "2025.csv").assign(season=2025)
    sack26 = read_csv(sackmann_dir / "atp_matches_2026.csv").assign(season=2026)
    players = read_csv(sackmann_dir / "atp_players.csv")
    tml_players = read_csv(tml_dir / "ATP_Database.csv")
    dict_cols = dictionary_columns((sackmann_dir / "matches_data_dictionary.txt").read_text())
    ingested = {"Sackmann 2015-2025": sack, "TML 2026": tml26}

    add("# Data audit (Milestone 0)")
    add("")
    add(
        f"Generated by `ingest/audit.py` on {dt.date.today().isoformat()} from the files pinned in "
        "`ingest/data.lock.json`. Do not edit by hand; rerun `uv run python -m ingest.audit`."
    )

    # 1. Provenance
    total, failures = check_hashes(lock)
    add("\n## 1. Sources and integrity\n")
    add(
        table(
            ["Source", "Pinned as", "Used for", "Terms"],
            [
                [
                    "Jeff Sackmann `tennis_atp`",
                    f"commit `{lock['sackmann']['commit'][:12]}` (git blob hash per file)",
                    "Seasons 2015-2025, player bios, data dictionary",
                    lock["sackmann"]["license"],
                ],
                [
                    "TennisMyLife (TML)",
                    f"SHA-256 per file, downloaded {lock['tml']['retrieved_on']}",
                    "Season 2026 (`2026.csv`), player bios for ID mapping; `2025.csv` for cross-checking only",
                    lock["tml"]["terms"],
                ],
            ],
        )
    )
    add(f"\nHash check: {total - len(failures)} of {total} files match the lock file.")
    for failure in failures:
        add(f"- FAILED: {failure}")

    # 2. Years and row counts
    add("\n## 2. Years available and row counts\n")
    rows = []
    for label, df in [(f"Sackmann {y}", sack_by_season[y].assign(season=y)) for y in SACKMANN_SEASONS] + [
        ("Sackmann 2026 (cross-check only)", sack26),
        ("TML 2026 (ingested)", tml26),
        ("TML 2025 (cross-check only)", tml25),
    ]:
        stats = has_stats(df)
        walkovers = (df["score"].map(result_type) == "walkover").sum()
        rows.append(
            [
                label,
                f"{len(df):,}",
                f"{df['tourney_date'].min()} to {df['tourney_date'].max()}",
                f"{stats.sum():,} ({pct(stats.sum(), len(df))})",
                f"{(df['tourney_level'] == 'D').sum():,}",
                f"{walkovers:,}",
            ]
        )
    add(table(["File", "Matches", "tourney_date range", "With stats", "Davis Cup rows", "Walkovers"], rows))
    add(
        "\n'With stats' means both `w_svpt` and `l_svpt` are filled. The latest complete Sackmann season is 2025; "
        f"TML 2026 runs to {tml26['tourney_date'].max()}."
    )
    tml_overlap = tml26[tml26["tourney_date"] <= SACKMANN_2026_CUTOFF]  # TML dates are match dates
    add(
        f"\nFor 2026 up to {SACKMANN_2026_CUTOFF}, the period both sources cover: Sackmann has stats for "
        f"{has_stats(sack26).sum():,} of {len(sack26):,} matches ({pct(has_stats(sack26).sum(), len(sack26))}); "
        f"TML has stats for {has_stats(tml_overlap).sum():,} of {len(tml_overlap):,} "
        f"({pct(has_stats(tml_overlap).sum(), len(tml_overlap))}). This is why 2026 comes from TML (D-001)."
    )

    # 3. Columns vs data dictionary
    add("\n## 3. Columns checked against `matches_data_dictionary.txt`\n")
    add(f"The dictionary lists {len(dict_cols)} singles columns: {', '.join(f'`{c}`' for c in dict_cols)}.\n")
    rows = []
    for label, path in [(f"atp_matches_{y}.csv", sackmann_dir / f"atp_matches_{y}.csv") for y in SACKMANN_SEASONS] + [
        ("TML 2026.csv", tml_dir / "2026.csv"),
        ("TML 2025.csv", tml_dir / "2025.csv"),
    ]:
        header = list(read_csv(path).columns)
        missing = [c for c in dict_cols if c not in header]
        extra = [c for c in header if c not in dict_cols]
        rows.append([label, len(header), ", ".join(missing) or "none", ", ".join(f"`{c}`" for c in extra) or "none"])
    add(table(["File", "Columns", "Missing vs dictionary", "Extra vs dictionary"], rows))
    add(
        f"\n`atp_players.csv` header: {', '.join(f'`{c}`' for c in players.columns)}. The Sackmann README "
        "describes these as player_id, first_name, last_name, hand, birth_date, country_code, height; the "
        "file header is what ingestion uses."
    )
    add(f"\nTML `ATP_Database.csv` header: {', '.join(f'`{c}`' for c in tml_players.columns)}.")

    # 4. Values the schema depends on
    add("\n## 4. Values the schema depends on\n")
    for label, df in ingested.items():
        add(f"### {label}\n")
        add(f"- `tourney_level`: {counts(df['tourney_level'])}")
        add(f"- `surface`: {counts(df['surface'])}")
        add(f"- `round`: {counts(df['round'])}")
        add(f"- `best_of`: {counts(df['best_of'])}")
        checks = score_checks(df)
        add(f"- Result type parsed from `score`: {counts(checks['types'])}")
        if len(checks["unknown"]):
            add("- Scores classified as `unknown`: " + ", ".join(f"`{s or '(empty)'}` x{n}" for s, n in checks["unknown"].items()))
        bad_by_level = collections.Counter(level for level, _ in checks["bad_sets"])
        non_davis = [text for level, text in checks["bad_sets"] if level != "D"]
        add(
            f"- Scores that look complete but whose set count doesn't fit `best_of`: {len(checks['bad_sets'])}"
            + (f", by level: {', '.join(f'`{k}` {v}' for k, v in bad_by_level.most_common())}" if checks["bad_sets"] else "")
            + (f". Outside Davis Cup, e.g. {'; '.join(non_davis[:2])}" if non_davis else "")
        )
        match_ids = df["tourney_id"] + "-" + df["match_num"]
        dupes = match_ids[match_ids.duplicated(keep=False)]
        add(
            f"- `tourney_id-match_num` duplicates: {dupes.nunique():,} IDs on {len(dupes):,} rows"
            + (f" (e.g. {', '.join(dupes.unique()[:3])})" if len(dupes) else "")
        )
        off_season = df[df["tourney_date"].str[:4] != df["season"].astype(str)]
        add(
            f"- Rows whose `tourney_date` year differs from the file's season: {len(off_season):,}"
            + (f" ({', '.join(sorted(set(off_season['tourney_name'] + ' ' + off_season['tourney_date'].str[:4])))[:300]})" if len(off_season) else "")
        )
        dates_per_tourney = df.groupby("tourney_id")["tourney_date"].nunique()
        add(
            f"- Tournaments with more than one distinct `tourney_date`: {(dates_per_tourney > 1).sum():,} of {len(dates_per_tourney):,}"
        )
        filled = (df[STAT_COLUMNS] != "").sum(axis=1)
        add(f"- Rows with partial stats (some of the 18 stat columns filled, not all): {((filled > 0) & (filled < 18)).sum():,}")
        add(f"- Rows with an empty `round`: {(df['round'] == '').sum():,}; empty `surface`: {(df['surface'] == '').sum():,}")
        add("")

    # Player IDs and bios
    add("### Player IDs and bios\n")
    ids = set(sack["winner_id"]) | set(sack["loser_id"])
    missing = ids - set(players["player_id"])
    add(f"- Sackmann: {len(ids):,} distinct players in 2015-2025 matches; {len(missing):,} missing from `atp_players.csv`.")
    active = players[players["player_id"].isin(ids)]
    dob_ok = active["dob"].str.fullmatch(r"\d{8}") & ~active["dob"].str.endswith("0000")
    add(f"- Of those players: `hand` {counts(active['hand'])}; full birth date {dob_ok.sum():,} ({pct(dob_ok.sum(), len(active))}); height {(active['height'] != '').sum():,} ({pct((active['height'] != '').sum(), len(active))}).")
    groups = [sorted(g, key=int) for g in name_dob_index(players.to_dict("records")).values() if len(g) > 1]
    groups = [list(g) for g in {tuple(g) for g in groups}]  # each player has two name keys
    in_matches = sorted(g for g in groups if any(pid in ids for pid in g))
    add(
        f"- `atp_players.csv` has {len(groups):,} name and birth date pairs listed under more than one `player_id`; "
        f"{len(in_matches):,} of them include a player in 2015-2025 matches"
        + (f" (e.g. IDs {', '.join('/'.join(g) for g in in_matches[:3])})" if in_matches else "")
        + ". Players listed without a birth date can also be duplicates, which this check does not catch."
    )
    tml_ids = set(tml26["winner_id"]) | set(tml26["loser_id"])
    add(
        f"- TML 2026: {len(tml_ids):,} distinct players; {len(tml_ids - set(tml_players['id'])):,} missing from `ATP_Database.csv`. "
        "TML uses ATP's alphanumeric player codes (for example `B0BI`), not Sackmann's numeric IDs."
    )

    # Special events
    add("\n### Team events, finals and other non-standard formats (excluding Davis Cup)\n")
    combined = pd.concat([sack, tml26], ignore_index=True)
    special = combined[(combined["tourney_level"] != "D") & combined["tourney_name"].str.contains(SPECIAL_NAME_RE)]
    rows = []
    for name, group in special.groupby("tourney_name"):
        seasons = sorted(group["season"].unique())
        rows.append(
            [
                name,
                f"{seasons[0]}-{seasons[-1]}" if len(seasons) > 1 else seasons[0],
                ", ".join(sorted(group["tourney_level"].unique())),
                f"{len(group):,}",
                pct(has_stats(group).sum(), len(group)),
                ", ".join(sorted(group["round"].unique())),
                ", ".join(sorted(group["best_of"].unique())),
            ]
        )
    add(table(["Event", "Seasons", "Level", "Matches", "With stats", "Rounds", "best_of"], rows))
    davis = combined[combined["tourney_level"] == "D"]
    add(
        f"\nDavis Cup: {len(davis):,} matches across {davis['tourney_id'].nunique():,} ties; "
        f"{pct(has_stats(davis).sum(), len(davis))} have stats."
    )

    # 5. TML to Sackmann player mapping
    pairs = pair_matches(sack_by_season[2025].to_dict("records"), tml25.to_dict("records"))
    crosswalk, conflicts = overlap_links(pairs)
    lookup = name_dob_index(players.to_dict("records"))
    tml_bio = tml_players.set_index("id")
    via_overlap = {i for i in tml_ids if i in crosswalk}
    via_name_dob, no_match, ambiguous, examples = set(), set(), set(), []
    agree = disagree = 0
    for tml_id in sorted(tml_ids):
        bio = tml_bio.loc[tml_id] if tml_id in tml_bio.index else None
        candidates = (
            sorted(set().union(*(lookup.get((key, bio["birthdate"]), set()) for key in name_keys(bio["player"]))))
            if bio is not None
            else []
        )
        if tml_id in crosswalk:
            if len(candidates) == 1:
                agree += candidates[0] == crosswalk[tml_id]
                disagree += candidates[0] != crosswalk[tml_id]
            continue
        if len(candidates) == 1:
            via_name_dob.add(tml_id)
        elif len(candidates) > 1:
            ambiguous.add(tml_id)
        else:
            no_match.add(tml_id)
            if bio is not None and len(examples) < 8:
                examples.append(bio["player"])  # names only: no birth dates in committed files (D-013)
    add("\n## 5. Mapping TML player IDs to Sackmann IDs\n")
    add(
        table(
            ["Step", "TML 2026 players"],
            [
                ["Total distinct players", f"{len(tml_ids):,}"],
                ["Mapped by matches both sources have in 2025", f"{len(via_overlap):,}"],
                ["Mapped by exact name and birth date (one candidate)", f"{len(via_name_dob):,}"],
                ["Name and birth date match more than one Sackmann player", f"{len(ambiguous):,}"],
                ["Not mapped", f"{len(no_match):,}"],
            ],
        )
    )
    add(
        f"\nThe 2025 overlap links {len(crosswalk):,} TML IDs to Sackmann IDs, with {conflicts} conflicting links. "
        f"Where both methods apply, name and birth date agree with the overlap {agree} times and disagree {disagree} times. "
        "This section only shows the first two matching steps; the mapping used for loading, with more steps "
        "and a manual review, is `ingest/player_crosswalk.csv` (Milestone 1)."
    )
    if examples:
        add(f"\nExamples not mapped: {'; '.join(examples)}.")

    # 6. Cross-source agreement
    comparison = compare_stats(pairs)
    add("\n## 6. Sackmann vs TML on the 2025 season\n")
    add(
        f"Matches paired by winner, loser and round (unique in both files): {len(pairs):,} of "
        f"{len(sack_by_season[2025]):,} Sackmann rows and {len(tml25):,} TML rows.\n"
    )
    add(table(["Outcome for the 18 stat columns", "Matches"], [[k, f"{v:,}"] for k, v in comparison["result"].most_common()]))
    add(f"\nFields that differ, by number of matches: {', '.join(f'`{k}` {v}' for k, v in comparison['fields'].most_common())}.")
    if comparison["swaps"]:
        add(f"\nSwapped examples: {'; '.join(comparison['swaps'][:5])}.")
    add(
        "\nThis shows the two sources disagree on some matches; it does not show which one is right. "
        "Each season is taken from one source only, so the two are never mixed within a season."
    )

    OUT_PATH.write_text("\n".join(out) + "\n")
    print(f"wrote {OUT_PATH.relative_to(ROOT)} ({len(out)} lines)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
