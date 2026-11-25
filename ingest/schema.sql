-- Rebuilt from scratch on every load, inside one transaction (ingest/load.py), so a load
-- either fully replaces the data or changes nothing. See docs/decisions.md D-011.
--
-- No CASCADE: if anything else (a view, another table) depends on these tables, the load
-- fails with an error instead of silently deleting it. Add such objects to this file.

-- Trigram similarity for player-name lookup with typos (api/stats.py, resolve_player).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP TABLE IF EXISTS charting_player_stats, charting_matches, player_matches, matches, players;
DROP TABLE IF EXISTS raw.matches, raw.sackmann_players, raw.tml_players,
                     raw.player_merges, raw.player_crosswalk, raw.special_events, raw.event_codes,
                     raw.charting_matches, raw.charting_serve_direction, raw.charting_rally,
                     raw.charting_net_points;

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

-- ATP tournament codes for the older Sackmann IDs that don't carry one ("2016-M006"), from the
-- reviewed ingest/event_codes.csv (D-036).
CREATE TABLE raw.event_codes (
  tourney_id  TEXT,
  event_code  TEXT,
  method      TEXT,
  note        TEXT
);

-- The Match Charting Project's files (D-030), as text. raw.charting_matches keeps the columns
-- this project uses (not the umpire or the volunteer who charted the match); the stats files
-- keep every column. Column names are the files' own, in snake case.
CREATE TABLE raw.charting_matches (
  row_num    INTEGER NOT NULL,
  match_id   TEXT,
  player1    TEXT,  -- "Player 1": always the player who served first
  player2    TEXT,
  date       TEXT,  -- YYYYMMDD
  tournament TEXT,
  round      TEXT,
  surface    TEXT,
  best_of    TEXT
);

CREATE TABLE raw.charting_serve_direction (
  match_id TEXT, player TEXT, row TEXT,  -- row '1': first serves in; '2': every second serve
  deuce_wide TEXT, deuce_middle TEXT, deuce_t TEXT, ad_wide TEXT, ad_middle TEXT, ad_t TEXT,
  err_net TEXT, err_wide TEXT, err_deep TEXT, err_wide_deep TEXT, err_foot TEXT, err_unknown TEXT
);

CREATE TABLE raw.charting_rally (
  match_id TEXT, server TEXT, returner TEXT, row TEXT,  -- pl1 is the `server` column's player
  pts TEXT, pl1_won TEXT, pl1_winners TEXT, pl1_forced TEXT, pl1_unforced TEXT,
  pl2_won TEXT, pl2_winners TEXT, pl2_forced TEXT, pl2_unforced TEXT
);

CREATE TABLE raw.charting_net_points (
  match_id TEXT, player TEXT, row TEXT,
  net_pts TEXT, pts_won TEXT, net_winner TEXT, induced_forced TEXT, net_unforced TEXT,
  passed_at_net TEXT, passing_shot_induced_forced TEXT, total_shots TEXT
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
  -- The ATP tournament code: the number after the season in the ID ("2025-0410" and "2026-410"
  -- are both 410), or from ingest/event_codes.csv for older IDs. It follows an event across
  -- seasons and sources. Davis Cup ties have none (D-036).
  event_code     INTEGER  CHECK (event_code > 0),
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
  CHECK ((event_code IS NULL) = (tourney_level = 'D')),
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

-- ---------------------------------------------------------------------------
-- Charted matches (D-030). Every charted men's match, with whether it is the same match as a
-- tour match in `matches` and, if not, why. Only linked matches have player stats.
-- ---------------------------------------------------------------------------
CREATE TABLE charting_matches (
  chart_id    TEXT PRIMARY KEY,  -- the Match Charting Project's match_id
  chart_date  DATE,
  round       TEXT,
  player1_id  INTEGER REFERENCES players (player_id),  -- NULL: the name didn't resolve
  player2_id  INTEGER REFERENCES players (player_id),
  match_id    TEXT REFERENCES matches (match_id),
  link        TEXT NOT NULL CHECK (link IN ('linked', 'before_data', 'name_not_resolved',
                                            'no_tour_match', 'several_tour_matches', 'charted_twice',
                                            'unreadable_row')),
  CHECK ((link = 'linked') = (match_id IS NOT NULL))
);
CREATE UNIQUE INDEX idx_charting_one_chart_per_match ON charting_matches (match_id);

-- One row per player of a linked charted match. A category is NULL when its file has no
-- usable row for that match (D-030): serve direction (first serves in, every second serve,
-- deuce and ad courts), points by rally length (shots including the serve, not counting the
-- final error), and net points.
CREATE TABLE charting_player_stats (
  chart_id   TEXT    NOT NULL REFERENCES charting_matches (chart_id),
  match_id   TEXT    NOT NULL REFERENCES matches (match_id),
  player_id  INTEGER NOT NULL REFERENCES players (player_id),
  first_deuce_wide INTEGER, first_deuce_body INTEGER, first_deuce_t INTEGER,
  first_ad_wide INTEGER, first_ad_body INTEGER, first_ad_t INTEGER,
  second_deuce_wide INTEGER, second_deuce_body INTEGER, second_deuce_t INTEGER,
  second_ad_wide INTEGER, second_ad_body INTEGER, second_ad_t INTEGER,
  rally_1_3_played INTEGER, rally_1_3_won INTEGER, rally_4_6_played INTEGER, rally_4_6_won INTEGER,
  rally_7_9_played INTEGER, rally_7_9_won INTEGER, rally_10_played INTEGER, rally_10_won INTEGER,
  points_played INTEGER,
  net_points INTEGER, net_points_won INTEGER,
  PRIMARY KEY (chart_id, player_id),
  CHECK (num_nulls(first_deuce_wide, first_deuce_body, first_deuce_t, first_ad_wide, first_ad_body,
                   first_ad_t, second_deuce_wide, second_deuce_body, second_deuce_t, second_ad_wide,
                   second_ad_body, second_ad_t) IN (0, 12)),
  CHECK (num_nulls(rally_1_3_played, rally_1_3_won, rally_4_6_played, rally_4_6_won, rally_7_9_played,
                   rally_7_9_won, rally_10_played, rally_10_won, points_played) IN (0, 9)),
  CHECK (num_nulls(net_points, net_points_won) IN (0, 2)),
  CHECK (rally_1_3_won <= rally_1_3_played AND rally_4_6_won <= rally_4_6_played
         AND rally_7_9_won <= rally_7_9_played AND rally_10_won <= rally_10_played),
  CHECK (rally_1_3_played + rally_4_6_played + rally_7_9_played + rally_10_played = points_played),
  CHECK (net_points_won <= net_points AND net_points <= points_played),
  CHECK (least(first_deuce_wide, first_deuce_body, first_deuce_t, first_ad_wide, first_ad_body, first_ad_t,
               second_deuce_wide, second_deuce_body, second_deuce_t, second_ad_wide, second_ad_body,
               second_ad_t, rally_1_3_won, rally_4_6_won, rally_7_9_won, rally_10_won, net_points_won) >= 0)
);
CREATE INDEX idx_charting_stats_player ON charting_player_stats (player_id);
