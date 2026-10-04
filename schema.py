"""Database schema (v2): real constraints replace the workbook's check columns.

* titles are unique ignoring case (Excel lookups ignored case; this keeps that behaviour but makes it explicit)
* releases -> games and play_log -> releases are foreign keys with ON UPDATE CASCADE, so renaming a game
  renames it everywhere, and deleting something that is still referenced is refused
* dropdown values live in ref_* tables (add a genre/system without touching code)
* audit records every change made through the app so it can be undone
"""
import sqlite3

VERSION = 2
STYLE_ORDER = ['2D', '2.5D', '3D']
SYSTEM_ORDER = ['PS1', 'PS2', 'PCSX2', 'PS4', 'PS5', 'Xbox', 'Xbox 360', 'Xbox One', 'Nintendo 64', 'Nintendo Gamecube',
                'Nintendo Switch', 'Wii', 'Steam', 'GOG', 'Origin', 'EPIC', 'Battle.net', 'Prime Gaming', 'Windows',
                'Gameboy', 'PSP', 'Mobile']
RELEASE_TYPES = ['Retail', 'DLC/Expansion', 'Demo', 'Mod']

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
  real INTEGER CHECK(real IS NULL OR real = 1),
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

GAME_COLS = ['title', 'series', 'graphic_style', 'camera_view', 'genre', 'sub_genre', 'singleplayer', 'local_co_op',
             'online_co_op', 'local_multiplayer', 'online_multiplayer', 'my_score', 'metacritic', 'pc_gamer', 'gamespot',
             'ign', 'destructoid', 'game_informer', 'zero_punctuation', 'goty_votes', 'wikipedia_goat',
             'soundtrack_owned', 'playthroughs', 'average_playthrough']
REL_COLS = ['title', 'release', 'system', 'ownership', 'original_release_date', 'version_release_date', 'added_date']
LOG_COLS = ['date', 'game', 'system', 'hours', 'real']

SUPERSEDED = ['lk_genretable', 'lk_viewstable', 'lk_stylestable', 'lk_ownershiptable', 'lk_gametypetable',
              'lk_systemtypemap', 'lk_zeropunctuationopinions', 'lk_subgenremaptable', 'lk_subgenrecontroldynamic',
              'lk_topranktable']


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con


def _col(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info({table})')]


def upgrade(path):
    """Upgrade a v1 database (plain tables copied from the workbook) to v2 in one transaction."""
    con = sqlite3.connect(path, isolation_level=None)
    if con.execute('PRAGMA user_version').fetchone()[0] >= VERSION:
        con.close(); return False
    con.execute('PRAGMA foreign_keys=OFF')
    con.execute('BEGIN')
    try:
        for t in ('games', 'releases', 'play_log'):
            con.execute(f'ALTER TABLE {t} RENAME TO {t}_v1')
        for stmt in DDL.split(';\n'):
            if stmt.strip(): con.execute(stmt)
        one = lambda t: [r[0] for r in con.execute(f'SELECT * FROM {t}')]
        ins = lambda t, rows: con.executemany(f'INSERT OR IGNORE INTO {t} VALUES ({",".join("?" * len(rows[0]))})', rows) if rows else None
        ins('ref_genre', [(g,) for g in sorted(one('lk_genretable'))])
        ins('ref_view', [(g,) for g in sorted(one('lk_viewstable'))])
        styles = one('lk_stylestable'); ins('ref_style', [(s,) for s in STYLE_ORDER + [x for x in styles if x not in STYLE_ORDER]])
        ins('ref_ownership', [(g,) for g in ['Paid', 'Free', 'Friend/Family'] if g in one('lk_ownershiptable')] +
            [(g,) for g in one('lk_ownershiptable') if g not in ('Paid', 'Free', 'Friend/Family')])
        ins('ref_release_type', [(g,) for g in RELEASE_TYPES + [x for x in one('lk_gametypetable') if x not in RELEASE_TYPES]])
        ins('ref_zp', [(g,) for g in ['Best', 'Good', 'Neutral', 'Bland', 'Bad', 'Worst'] + [x for x in one('lk_zeropunctuationopinions') if x not in ('Best', 'Good', 'Neutral', 'Bland', 'Bad', 'Worst')]])
        smap = {r[0]: r[1] for r in con.execute('SELECT system, type FROM lk_systemtypemap')}
        ins('ref_system', [(s, smap[s]) for s in SYSTEM_ORDER if s in smap] + [(s, t) for s, t in smap.items() if s not in SYSTEM_ORDER])
        ins('ref_subgenre', [(g, s) for g, s, *_ in con.execute('SELECT * FROM lk_subgenremaptable')])
        ins('top_rank', [(int(r), g) for g, r in con.execute('SELECT game, rank FROM lk_topranktable')])
        # copy data (columns that exist in v1 under the same names)
        for t, cols in (('games', GAME_COLS), ('releases', REL_COLS), ('play_log', LOG_COLS)):
            have = _col(con, t + '_v1')
            sel = ', '.join(c if c in have else 'NULL' for c in cols)
            con.execute(f'INSERT INTO {t}(id, {", ".join(cols)}) SELECT id, {sel} FROM {t}_v1')
        for t in ('games_v1', 'releases_v1', 'play_log_v1'): con.execute(f'DROP TABLE {t}')
        for t in SUPERSEDED: con.execute(f'DROP TABLE IF EXISTS {t}')
        con.execute('PRAGMA foreign_keys=ON')
        bad = con.execute('PRAGMA foreign_key_check').fetchall()
        if bad: raise sqlite3.IntegrityError(f'foreign key violations after upgrade: {bad[:5]}')
        con.execute(f'PRAGMA user_version={VERSION}')
        con.execute('COMMIT')
    except Exception:
        con.execute('ROLLBACK'); raise
    finally:
        con.close()
    return True


if __name__ == '__main__':
    import sys
    print('upgraded' if upgrade(sys.argv[1]) else 'already current')
