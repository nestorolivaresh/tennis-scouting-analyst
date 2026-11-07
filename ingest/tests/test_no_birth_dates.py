"""Guardrail: no real player birth date may appear in a file git would commit (D-013).

It compares every 8-digit or YYYY-MM-DD token in those files with the birth dates in the
raw player files. Only dates before 2012 are checked, so tournament dates (2014 onward) can't
match by accident. Skipped when the raw files haven't been downloaded.
"""

import csv
import re
import subprocess

import pytest

from ingest.download import RAW_DIR, ROOT

PLAYER_FILES = [(RAW_DIR / "sackmann" / "atp_players.csv", "dob"), (RAW_DIR / "tml" / "ATP_Database.csv", "birthdate")]
DATE_TOKEN = re.compile(r"\d{4}-\d{2}-\d{2}|\d{8}")


@pytest.mark.skipif(not all(path.exists() for path, _ in PLAYER_FILES), reason="raw data not downloaded")
def test_committed_files_contain_no_player_birth_dates():
    birth_dates = set()
    for path, column in PLAYER_FILES:
        with open(path, newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                value = row[column].strip()
                if re.fullmatch(r"\d{8}", value) and value < "20120101" and not value.endswith("0000"):
                    birth_dates |= {value, f"{value[:4]}-{value[4:6]}-{value[6:]}"}

    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip
    hits = []
    for name in listed:
        if name == "uv.lock":  # package hashes, not data
            continue
        text = (ROOT / name).read_text(encoding="utf-8", errors="ignore")
        for number, line in enumerate(text.splitlines(), start=1):
            hits += [f"{name}:{number}: {token}" for token in DATE_TOKEN.findall(line) if token in birth_dates]
    assert not hits, "player birth dates in committed files:\n" + "\n".join(hits)
