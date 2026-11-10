"""Download the raw data files listed in ingest/data.lock.json and verify their hashes.

There are two sources (docs/decisions.md explains why):

- sackmann: Jeff Sackmann's tennis_atp repository at its final commit. The original
  repository was deleted in 2026, so files are fetched from forks that still contain
  that exact commit. Git addresses files by hash, so every fork serves identical bytes,
  and each file is checked against the git blob hash recorded in the commit.
- tml: TennisMyLife yearly CSVs. They have no versions upstream, so the lock file records
  the SHA-256 of the copy we downloaded and the date we downloaded it.

Usage:
    uv run python -m ingest.download            # fetch missing files, verify every file
    uv run python -m ingest.download --relock   # rebuild the lock file from the sources

Re-locking TML replaces the data snapshot, which changes eval ground truth. Only do it on purpose.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = ROOT / "ingest" / "data.lock.json"
RAW_DIR = ROOT / "data" / "raw"
USER_AGENT = "tennis-scouting-analyst/0.1 (non-commercial personal project)"

# Which seasons come from which source (D-001). Every module imports these.
SACKMANN_SEASONS = range(2015, 2026)
TML_SEASON = 2026

SACKMANN_COMMIT = "712be0c5ade693cdab9e69c23a71a0edf5a23c44"
# Forks that contain SACKMANN_COMMIT, checked 2026-11-06. Any of them works.
SACKMANN_MIRRORS = [
    "oli5679/tennis_atp",
    "akshatagnihotri/tennis_atp",
    "Kadantte/tennis_atp",
]
SACKMANN_FILES = [f"atp_matches_{year}.csv" for year in SACKMANN_SEASONS] + [
    "atp_matches_2026.csv",  # not ingested: used only to compare 2026 coverage with TML
    "atp_players.csv",
    "matches_data_dictionary.txt",
    "README.md",  # kept as the record of the license terms
]

TML_BASE_URL = "https://stats.tennismylife.org/data/"
TML_FILES = [
    "2026.csv",  # ingested: the 2026 season
    "2025.csv",  # not ingested: used only to cross-check TML against Sackmann
    "ATP_Database.csv",  # player bios with birth dates, used to map TML IDs to Sackmann IDs
]


def git_blob_sha1(data: bytes) -> str:
    """Return the hash git gives this content (same as `git hash-object`)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, attempts: int = 3, timeout: float = 60.0) -> bytes:
    """GET a URL, retrying transient failures with a short backoff."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == attempts:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts:
                raise
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def sackmann_urls(name: str) -> list[str]:
    return [
        f"https://raw.githubusercontent.com/{repo}/{SACKMANN_COMMIT}/{name}"
        for repo in SACKMANN_MIRRORS
    ]


def fetch_first(urls: list[str]) -> tuple[bytes, str]:
    """Try each URL in order and return the first successful body and its URL."""
    errors = []
    for url in urls:
        try:
            return fetch(url), url
        except (urllib.error.URLError, TimeoutError) as error:
            errors.append(f"{url}: {error}")
    raise RuntimeError("all sources failed:\n  " + "\n  ".join(errors))


def sackmann_blob_hashes() -> dict[str, str]:
    """Read the git blob hash of every file in the pinned commit from the GitHub API."""
    urls = [
        f"https://api.github.com/repos/{repo}/git/trees/{SACKMANN_COMMIT}"
        for repo in SACKMANN_MIRRORS
    ]
    body, _ = fetch_first(urls)
    tree = json.loads(body)
    return {item["path"]: item["sha"] for item in tree["tree"] if item["type"] == "blob"}


def verify(data: bytes, entry: dict) -> str | None:
    """Return None if the bytes match the lock entry, or a description of the mismatch."""
    if sha256(data) != entry["sha256"]:
        return f"sha256 {sha256(data)} != expected {entry['sha256']}"
    if "git_blob_sha1" in entry and git_blob_sha1(data) != entry["git_blob_sha1"]:
        return f"git blob {git_blob_sha1(data)} != expected {entry['git_blob_sha1']}"
    return None


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def relock() -> dict:
    """Download every file from its source and build a new lock file."""
    blob_hashes = sackmann_blob_hashes()
    sackmann_files = {}
    for name in SACKMANN_FILES:
        data, url = fetch_first(sackmann_urls(name))
        if git_blob_sha1(data) != blob_hashes[name]:
            raise RuntimeError(f"{name} from {url} does not match commit {SACKMANN_COMMIT}")
        write_atomic(RAW_DIR / "sackmann" / name, data)
        sackmann_files[name] = {
            "sha256": sha256(data),
            "git_blob_sha1": blob_hashes[name],
            "bytes": len(data),
        }
        print(f"locked sackmann/{name} ({len(data):,} bytes, matches commit)")

    tml_files = {}
    for name in TML_FILES:
        data = fetch(TML_BASE_URL + name)
        write_atomic(RAW_DIR / "tml" / name, data)
        tml_files[name] = {"sha256": sha256(data), "bytes": len(data)}
        print(f"locked tml/{name} ({len(data):,} bytes)")

    return {
        "sackmann": {
            "description": "Jeff Sackmann tennis_atp, final commit before the repository was deleted",
            "license": "CC BY-NC-SA 4.0",
            "attribution": "Jeff Sackmann / Tennis Abstract",
            "commit": SACKMANN_COMMIT,
            "mirrors": SACKMANN_MIRRORS,
            "files": sackmann_files,
        },
        "tml": {
            "description": "TennisMyLife ATP match database, yearly CSV files",
            "terms": "Personal, educational and non-commercial research use only; "
            "no redistribution of the raw CSV files",
            "terms_url": "https://stats.tennismylife.org/tennis-match-database",
            "base_url": TML_BASE_URL,
            "retrieved_on": dt.date.today().isoformat(),
            "files": tml_files,
        },
    }


def sync(lock: dict) -> list[str]:
    """Make data/raw match the lock file. Returns a list of problems (empty means OK)."""
    problems = []
    for source, spec in lock.items():
        for name, entry in spec["files"].items():
            path = RAW_DIR / source / name
            if path.exists() and verify(path.read_bytes(), entry) is None:
                print(f"ok      {source}/{name}")
                continue
            urls = sackmann_urls(name) if source == "sackmann" else [spec["base_url"] + name]
            try:
                data, url = fetch_first(urls)
            except RuntimeError as error:
                problems.append(f"{source}/{name}: download failed: {error}")
                continue
            mismatch = verify(data, entry)
            if mismatch:
                hint = " (TML changed upstream; --relock accepts a new snapshot)" if source == "tml" else ""
                problems.append(f"{source}/{name} from {url}: {mismatch}{hint}")
                continue
            write_atomic(path, data)
            print(f"fetched {source}/{name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--relock", action="store_true", help="download from sources and rewrite the lock file")
    args = parser.parse_args(argv)

    if args.relock or not LOCK_PATH.exists():
        lock = relock()
        LOCK_PATH.write_text(json.dumps(lock, indent=2) + "\n")
        print(f"wrote {LOCK_PATH.relative_to(ROOT)}")
        return 0

    problems = sync(json.loads(LOCK_PATH.read_text()))
    for problem in problems:
        print(f"ERROR   {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
