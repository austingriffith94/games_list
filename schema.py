"""Database schema (v4). games_list.db is the master copy; this file documents its structure and applies upgrades.

* titles are unique ignoring case
* releases -> games and play_log -> releases are foreign keys with ON UPDATE CASCADE, so renaming a game
  renames it everywhere, and deleting something that is still referenced is refused
* dropdown values live in ref_* tables (add a genre/system without touching code)
* audit records every change made through the app so it can be undone
* halo_levels holds the HaloRank level ratings; the score/tier columns are derived (halo.py), never stored

DDL and HALO_DDL below are a reference for the current structure (the database already exists; they are not run).
"""
import sqlite3

VERSION = 4

DDL = """
CREATE TABLE ref_genre(name TEXT PRIMARY KEY COLLATE NOCASE);
CREATE TABLE ref_subgenre(genre TEXT NOT NULL COLLATE NOCASE REFERENCES ref_genre(name) ON UPDATE CASCADE,
                          name TEXT NOT NULL COLLATE NOCASE, PRIMARY KEY(genre, name));
CREATE TABLE ref_view(name TEXT PRIMARY KEY COLLATE NOCASE);
CREATE TABLE ref_style(name TEXT PRIMARY KEY COLLATE NOCASE);
CREATE TABLE ref_ownership(name TEXT PRIMARY KEY COLLATE NOCASE);
CREATE TABLE ref_release_type(name TEXT PRIMARY KEY COLLATE NOCASE);
CREATE TABLE ref_zp(name TEXT PRIMARY KEY COLLATE NOCASE);
CREATE TABLE ref_system(name TEXT PRIMARY KEY COLLATE NOCASE, type TEXT NOT NULL);

CREATE TABLE games(
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK(length(trim(title)) > 0),
  series TEXT NOT NULL,
  graphic_style TEXT NOT NULL REFERENCES ref_style(name) ON UPDATE CASCADE,
  camera_view TEXT NOT NULL REFERENCES ref_view(name) ON UPDATE CASCADE,
  genre TEXT NOT NULL REFERENCES ref_genre(name) ON UPDATE CASCADE,
  sub_genre TEXT,
  singleplayer INTEGER CHECK(singleplayer IS NULL OR singleplayer IN (0,1)),
  local_co_op INTEGER CHECK(local_co_op IS NULL OR local_co_op IN (0,1)),
  online_co_op INTEGER CHECK(online_co_op IS NULL OR online_co_op IN (0,1)),
  local_multiplayer INTEGER CHECK(local_multiplayer IS NULL OR local_multiplayer IN (0,1)),
  online_multiplayer INTEGER CHECK(online_multiplayer IS NULL OR online_multiplayer IN (0,1)),
  my_score NUMERIC, metacritic NUMERIC, pc_gamer NUMERIC, gamespot NUMERIC, ign NUMERIC,
  destructoid NUMERIC, game_informer NUMERIC,
  zero_punctuation TEXT REFERENCES ref_zp(name) ON UPDATE CASCADE,
  goty_votes NUMERIC,
  wikipedia_goat INTEGER NOT NULL DEFAULT 0 CHECK(wikipedia_goat IN (0,1)),
  soundtrack_owned INTEGER NOT NULL DEFAULT 0 CHECK(soundtrack_owned IN (0,1)),
  playthroughs NUMERIC, average_playthrough NUMERIC,
  FOREIGN KEY(genre, sub_genre) REFERENCES ref_subgenre(genre, name) ON UPDATE CASCADE
);

CREATE TABLE releases(
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL COLLATE NOCASE REFERENCES games(title) ON UPDATE CASCADE ON DELETE RESTRICT,
  release TEXT NOT NULL REFERENCES ref_release_type(name) ON UPDATE CASCADE,
  system TEXT NOT NULL COLLATE NOCASE REFERENCES ref_system(name) ON UPDATE CASCADE,
  ownership TEXT NOT NULL REFERENCES ref_ownership(name) ON UPDATE CASCADE,
  original_release_date TEXT NOT NULL CHECK(original_release_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  version_release_date TEXT NOT NULL CHECK(version_release_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  added_date TEXT NOT NULL CHECK(added_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  UNIQUE(title, system)
);

CREATE TABLE play_log(
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL CHECK(date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  game TEXT NOT NULL COLLATE NOCASE,
  system TEXT NOT NULL COLLATE NOCASE,
  hours NUMERIC NOT NULL CHECK(hours > 0),
  UNIQUE(date, game, system),
  FOREIGN KEY(game, system) REFERENCES releases(title, system) ON UPDATE CASCADE ON DELETE RESTRICT
);
CREATE INDEX ix_log_game ON play_log(game, system);
CREATE INDEX ix_log_date ON play_log(date);

CREATE TABLE top_rank(
  rank INTEGER PRIMARY KEY,
  title TEXT NOT NULL UNIQUE COLLATE NOCASE REFERENCES games(title) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE audit(
  id INTEGER PRIMARY KEY, batch TEXT NOT NULL, ts TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  action TEXT NOT NULL, tbl TEXT NOT NULL, row_id INTEGER, old TEXT, new TEXT, summary TEXT, undone INTEGER DEFAULT 0
);
CREATE INDEX ix_audit_batch ON audit(batch);
"""

HALO_DDL = """
CREATE TABLE halo_levels(
  id INTEGER PRIMARY KEY,
  series_order INTEGER NOT NULL,
  game TEXT NOT NULL COLLATE NOCASE,
  level_order INTEGER NOT NULL,
  level TEXT NOT NULL COLLATE NOCASE CHECK(length(trim(level)) > 0),
  enemy INTEGER CHECK(enemy BETWEEN 0 AND 5),
  weapon_vehicle INTEGER CHECK(weapon_vehicle BETWEEN 0 AND 5),
  design_set_piece INTEGER CHECK(design_set_piece BETWEEN 0 AND 5),
  replayability_pacing INTEGER CHECK(replayability_pacing BETWEEN 0 AND 5),
  difficulty INTEGER CHECK(difficulty BETWEEN 0 AND 5),
  visual INTEGER CHECK(visual BETWEEN 0 AND 5),
  music INTEGER CHECK(music BETWEEN 0 AND 5),
  story INTEGER CHECK(story BETWEEN 0 AND 5),
  enjoyment INTEGER CHECK(enjoyment BETWEEN 0 AND 5),
  notes TEXT,
  UNIQUE(game, level),
  CHECK((enemy IS NULL) = (weapon_vehicle IS NULL) AND (enemy IS NULL) = (design_set_piece IS NULL)
    AND (enemy IS NULL) = (replayability_pacing IS NULL) AND (enemy IS NULL) = (difficulty IS NULL)
    AND (enemy IS NULL) = (visual IS NULL) AND (enemy IS NULL) = (music IS NULL)
    AND (enemy IS NULL) = (story IS NULL) AND (enemy IS NULL) = (enjoyment IS NULL))
);
CREATE INDEX ix_halo_game ON halo_levels(series_order, level_order);
"""


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con


def upgrade(path):
    """Apply pending upgrades in one transaction. v3 -> v4 drops the unused play_log.real flag."""
    con = sqlite3.connect(path, isolation_level=None)
    try:
        ver = con.execute('PRAGMA user_version').fetchone()[0]
        if ver >= VERSION: return False
        if ver != 3: raise RuntimeError(f'unsupported schema version {ver}; expected 3 or {VERSION}')
        con.execute('BEGIN')
        try:
            con.execute('ALTER TABLE play_log DROP COLUMN real')
            con.execute(f'PRAGMA user_version={VERSION}')
            con.execute('COMMIT')
        except Exception:
            con.execute('ROLLBACK'); raise
        return True
    finally:
        con.close()


if __name__ == '__main__':
    import sys
    print('upgraded' if upgrade(sys.argv[1]) else 'already current')
