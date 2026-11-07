-- Rebuilt from scratch on every load, inside one transaction (ingest/load.py), so a load
-- either fully replaces the data or changes nothing. See docs/decisions.md D-011.
--
-- No CASCADE: if anything else (a view, another table) depends on these tables, the load
-- fails with an error instead of silently deleting it. Add such objects to this file.

-- Trigram similarity for player-name lookup with typos (api/stats.py, resolve_player).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP TABLE IF EXISTS player_matches, matches, players;
DROP TABLE IF EXISTS raw.matches, raw.sackmann_players, raw.tml_players,
                     raw.player_merges, raw.player_crosswalk, raw.special_events;

-- ---------------------------------------------------------------------------
-- raw: the source files exactly as published, every value as text, plus the reviewed
-- mapping files. Eval ground truth is computed from these tables only, so a bug in the
-- transform below can't also hide itself in the expected answers (D-012).
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE raw.matches (
  source             TEXT    NOT NULL,  -- 'sackmann' or 'tml'
  season             INTEGER NOT NULL,  -- the file's season
  row_num            INTEGER NOT NULL,  -- 1-based data row in that file
  tourney_id         TEXT,
  tourney_name       TEXT,
  surface            TEXT,
  draw_size          TEXT,
  tourney_level      TEXT,
  indoor             TEXT,              -- TML only
  tourney_date       TEXT,
  match_num          TEXT,
  winner_id          TEXT,
  winner_seed        TEXT,
  winner_entry       TEXT,
  winner_name        TEXT,
  winner_hand        TEXT,
  winner_ht          TEXT,
  winner_ioc         TEXT,
  winner_age         TEXT,
  loser_id           TEXT,
  loser_seed         TEXT,
  loser_entry        TEXT,
  loser_name         TEXT,
  loser_hand         TEXT,
  loser_ht           TEXT,
  loser_ioc          TEXT,
  loser_age          TEXT,
  score              TEXT,
  best_of            TEXT,
  round              TEXT,
  minutes            TEXT,
  w_ace              TEXT,
  w_df               TEXT,
  w_svpt             TEXT,
  "w_1stIn"          TEXT,
  "w_1stWon"         TEXT,
  "w_2ndWon"         TEXT,
  "w_SvGms"          TEXT,
  "w_bpSaved"        TEXT,
  "w_bpFaced"        TEXT,
  l_ace              TEXT,
  l_df               TEXT,
  l_svpt             TEXT,
  "l_1stIn"          TEXT,
  "l_1stWon"         TEXT,
  "l_2ndWon"         TEXT,
  "l_SvGms"          TEXT,
  "l_bpSaved"        TEXT,
  "l_bpFaced"        TEXT,
  winner_rank        TEXT,
  winner_rank_points TEXT,
  loser_rank         TEXT,
  loser_rank_points  TEXT,
  PRIMARY KEY (source, season, row_num)
);

CREATE TABLE raw.sackmann_players (
  player_id   TEXT,
  name_first  TEXT,
  name_last   TEXT,
  hand        TEXT,
  dob         TEXT,
  ioc         TEXT,
  height      TEXT,
  wikidata_id TEXT
);

CREATE TABLE raw.tml_players (
  id         TEXT,
  player     TEXT,
  atpname    TEXT,
  birthdate  TEXT,
  weight     TEXT,
  height     TEXT,
  turnedpro  TEXT,
  birthplace TEXT,
  coaches    TEXT,
  hand       TEXT,
  backhand   TEXT,
  ioc        TEXT
);

-- The reviewed files from ingest/ (D-006, D-009, D-010), copied as text. They are shared
-- assumptions: the evals use them but can't check them (D-012).
CREATE TABLE raw.player_merges (
  duplicate_id      TEXT,
  canonical_id      TEXT,
  duplicate_matches TEXT,
  canonical_matches TEXT,
  reason            TEXT
);

CREATE TABLE raw.player_crosswalk (
  tml_id    TEXT,
  player_id TEXT,
  method    TEXT,
  note      TEXT
);

CREATE TABLE raw.special_events (
  tourney_name  TEXT,
  level         TEXT,
  is_exhibition TEXT,
  note          TEXT
);

-- ---------------------------------------------------------------------------
-- Core tables used by the stats layer.
-- ---------------------------------------------------------------------------
CREATE TABLE players (
  player_id   INTEGER PRIMARY KEY,  -- Sackmann ID; 900001+ for players only in TML (D-009)
  full_name   TEXT NOT NULL,
  hand        TEXT CHECK (hand IN ('R', 'L')),  -- NULL means unknown
  birth_date  DATE,
  country     TEXT,
  height_cm   INTEGER,
  -- Lowercase ASCII words of full_name, from ingest.players.name_tokens; the API normalizes
  -- search text with the same function, so both sides compare the same way.
  search_name TEXT NOT NULL
);

CREATE TABLE matches (
  match_id       TEXT PRIMARY KEY,  -- tourney_id || '-' || match_num
  source         TEXT     NOT NULL CHECK (source IN ('sackmann', 'tml')),
  season         INTEGER  NOT NULL,
  source_row     INTEGER  NOT NULL,  -- raw.matches.row_num of the same source and season
  tourney_id     TEXT     NOT NULL,
  tourney_name   TEXT     NOT NULL,
  tourney_level  TEXT     NOT NULL CHECK (tourney_level IN ('G', 'M', 'A', 'F', 'D', 'O')),
  source_level   TEXT     NOT NULL,  -- tourney_level as written in the file
  is_exhibition  BOOLEAN  NOT NULL,  -- Laver Cup, NextGen Finals (D-006)
  tourney_date   DATE     NOT NULL,  -- tournament start date, for both sources
  match_date     DATE,               -- the match's own date, when the source gives it (TML)
  surface        TEXT CHECK (surface IN ('Hard', 'Clay', 'Grass', 'Carpet')),
  round          TEXT     NOT NULL,
  round_order    SMALLINT NOT NULL,
  match_num      INTEGER  NOT NULL,
  best_of        SMALLINT NOT NULL CHECK (best_of IN (3, 5)),
  score          TEXT,
  minutes        INTEGER,
  winner_id      INTEGER  NOT NULL REFERENCES players (player_id),
  loser_id       INTEGER  NOT NULL REFERENCES players (player_id),
  result_type    TEXT     NOT NULL CHECK (result_type IN ('completed', 'retired', 'walkover', 'defaulted', 'unknown')),
  has_stats      BOOLEAN  NOT NULL,
  CHECK (winner_id <> loser_id),
  UNIQUE (source, season, source_row)
);

CREATE TABLE player_matches (
  match_id       TEXT    NOT NULL REFERENCES matches (match_id),
  player_id      INTEGER NOT NULL REFERENCES players (player_id),
  opponent_id    INTEGER NOT NULL REFERENCES players (player_id),
  won            BOOLEAN NOT NULL,
  rank           INTEGER,
  aces           INTEGER,
  double_faults  INTEGER,
  serve_points   INTEGER,
  first_in       INTEGER,
  first_won      INTEGER,
  second_won     INTEGER,
  service_games  INTEGER,
  bp_saved       INTEGER,
  bp_faced       INTEGER,
  PRIMARY KEY (match_id, player_id),
  CHECK (player_id <> opponent_id),
  -- Stats are all present or all missing, never partial (D-008).
  CHECK (num_nulls(aces, double_faults, serve_points, first_in, first_won,
                   second_won, service_games, bp_saved, bp_faced) IN (0, 9)),
  CHECK (least(aces, double_faults, serve_points, first_in, first_won,
               second_won, service_games, bp_saved, bp_faced) >= 0),
  -- Single-row rules only. Rules that need the score or both players (no serve points only
  -- in a match cut short; at least 4 points per service game) live in ingest/transform.py
  -- and are re-checked in the quality report.
  CHECK (serve_points = 0 OR service_games > 0),
  CHECK (serve_points >= service_games),
  CHECK (first_in <= serve_points),
  CHECK (first_won <= first_in),
  CHECK (second_won + double_faults <= serve_points - first_in),
  CHECK (bp_saved <= bp_faced),
  CHECK (aces <= first_won + second_won)
);

CREATE INDEX idx_pm_player_opponent ON player_matches (player_id, opponent_id);
CREATE INDEX idx_matches_date ON matches (tourney_date);
