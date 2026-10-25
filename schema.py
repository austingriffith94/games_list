"""Database schema (v9). games_list.db is the master copy; this file documents its structure and applies upgrades.

* titles are unique ignoring case
* releases -> games and play_log -> releases are foreign keys with ON UPDATE CASCADE, so renaming a game
  renames it everywhere, and deleting something that is still referenced is refused
* dropdown values live in ref_* tables (add a genre/system without touching code)
* audit records every change made through the app so it can be undone
* halo_levels holds the HaloRank level ratings; the score/tier columns are derived (halo.py), never stored
* tww_lords / tww_campaigns hold the Total War: Warhammer III legendary lord tracker (scored in tww.py, like halo_levels)
* reviews holds one write-up per game; games.tier (a ref_tier name, worst to best) may only be set on a game
  that has a review - triggers enforce it, so tiers arrive with write-ups rather than on every game

DDL, HALO_DDL and REVIEW_DDL below are a reference for the current structure (the database already exists; they are
not run - REVIEW_DDL is applied by the v4 -> v5 upgrade; the v5 -> v6 upgrade gave ref_tier an id column so tier edits
can be audited and undone like everything else, and made `rank` an ordinary (non-unique) sort column).
"""
import sqlite3

VERSION = 9

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


def _rating(col):
    """A 0-5 whole-number rating. typeof() matters: INTEGER affinity keeps 3.5 and 'abc' as they are."""
    return f"{col} INTEGER CHECK({col} IS NULL OR (typeof({col}) = 'integer' AND {col} BETWEEN 0 AND 5))"


def _opt_date(col):
    """Optional YYYY-MM-DD that is a real calendar date (the GLOB alone lets 2026-13-40 through; date() gives NULL for it, and NULL would pass a CHECK, hence IS)."""
    return f"{col} TEXT CHECK({col} IS NULL OR ({col} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' AND date({col}) IS {col}))"


_HALO_RATINGS = ['enemy', 'weapon_vehicle', 'design_set_piece', 'replayability_pacing', 'difficulty', 'visual', 'music',
                 'story', 'enjoyment']
_TWW_RATINGS = ['mechanics', 'roster', 'start_position', 'challenge', 'narrative', 'late_game', 'enjoyment']


def _all_or_none(cols):
    return ' AND '.join(f'({cols[0]} IS NULL) = ({c} IS NULL)' for c in cols[1:])


HALO_DDL = f"""
CREATE TABLE halo_levels(
  id INTEGER PRIMARY KEY,
  series_order INTEGER NOT NULL,
  game TEXT NOT NULL COLLATE NOCASE,
  level_order INTEGER NOT NULL,
  level TEXT NOT NULL COLLATE NOCASE CHECK(length(trim(level)) > 0),
  {(',' + chr(10) + '  ').join(_rating(c) for c in _HALO_RATINGS)},
  notes TEXT,
  UNIQUE(game, level),
  CHECK({_all_or_none(_HALO_RATINGS)})
);
CREATE INDEX ix_halo_game ON halo_levels(series_order, level_order);
"""

# rank 1 = worst. Seeded by the v5 upgrade from the original "Game Reviews" page; edit them in ref_tier afterwards.
TIERS = [
    ('Worstest', 'The worst of the worst. These games are outright terrible, objective failures. Broken messes that are nearly unplayable due to both poorly conceived and executed designs, and a soul sapping lack of fun. It will make one question whether gaming is a hobby worth pursuing, and wonder aloud if the human race is destined to fail. Offensive wastes of money and time, playing one of these games will make you dream of the “pushing a hoop with a stick good old days” before video games your grandparents always told you about when growing up.'),
    ('Old and Busted', 'A bad game, plain and simple. Though there may a redeeming quality, such as respectable art design or a unique feature, it is buried beneath broken gameplay and lack of polish. The final product is a painful mess with little enjoyment to be had that will leave a sense of yearning for the mundane routines of everyday life. Many Ragrets.'),
    ('Perfectly Mediocre', 'A middling game throughout. For every good gameplay loop or enjoyable moment, there is an equally bad design or a poorly integrated feature. Many aspects of this game have been seen before and done better. Its greatest accomplishment is making you appreciate the truly great games even more.'),
    ('Round Peg in a Square Hole', 'Something that just didn’t click. There was good, there was bad. Either way I ultimately didn’t enjoy my time here.'),
    ('Forgettable', 'Who? What? I played this game?'),
    ('Watching Paint Dry', 'A duller-than-dirt experience from start to finish, assuming you can even make it to the finish line without falling asleep. While not objectively terrible, they instill no passion outside of frustration from the perceived waste time by not enjoying the game. Something just didn’t click. These are beige saltine crackers of video games.'),
    ('Flawed Gem', 'Though there are redeeming qualities, there is something off in the design that brings it down. An overall dip in quality or game components not reaching their full potential can make an otherwise promising experience, with unique or well executed mechanics, fall short of being good.'),
    ('Bueno', 'This game does exactly what it sets out to do. While not much bad to go around, there is not much that stands out as truly great either. Typically a game of modest or focused ambitions, it doesn’t have the fluff that may have otherwise dragged it down, and could instead focus on having a unique story or gameplay hook to sell itself. For the right person, an experience like this can stand on its own as something worth playing at least once, and may even be masterpieces to people other than me.'),
    ('Almost There', 'Falling just short of greatness. There might be a lot of fun to be had or a grand story to be told, but it is weighed down by a handful of features that hurt the overall experience or could have been implemented better. It could be a great game that just doesn’t stick the landing, or has an extended rough patch that taints what came before. It may be part of a series where its peers outshine it. You might not always go back to it, but you can still remember your time spent fondly while thinking “what if?”'),
    ('New Hotness', 'Expertly executed features and stories, addictive gameplay loops, or countless hours of fun make up this category. This game distinguishes itself with unique, polished mechanics or executing on familiar designs better than the rest of the competition. Any shortcomings are minor enough to pale in comparison to the overall enjoyable experience, but still hold it back from being the best of the best. These games leave a lasting impact and are cherished for years to come.'),
    ('Masterpiece', 'A profound, life changing experience, my favorite games regardless of any flaws you might point out. Michael Jordan, Franklin’s BBQ, the 2005 Rose Bowl, Tom Hanks, The Godfather, George Strait, Cane’s fried chicken, Gregg Popovich and Tim Duncan. These are things that come to mind when playing these games.'),
]

TWW_DDL = f"""
CREATE TABLE ref_tww_mode(name TEXT PRIMARY KEY COLLATE NOCASE);
CREATE TABLE ref_tww_status(name TEXT PRIMARY KEY COLLATE NOCASE);
CREATE TABLE ref_tww_difficulty(name TEXT PRIMARY KEY COLLATE NOCASE, sort INTEGER NOT NULL);
CREATE TABLE lk_twwratingweights(col TEXT PRIMARY KEY, label TEXT NOT NULL, weight NUMERIC NOT NULL);

CREATE TABLE tww_lords(
  id INTEGER PRIMARY KEY,
  race TEXT NOT NULL COLLATE NOCASE,
  race_game INTEGER NOT NULL CHECK(race_game IN (1,2,3)),
  race_order INTEGER NOT NULL,
  lord TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK(length(trim(lord)) > 0),
  faction TEXT, start_location TEXT, dlc TEXT, wiki_page TEXT,
  roc_playable INTEGER NOT NULL DEFAULT 0 CHECK(roc_playable IN (0,1)),
  card TEXT, portrait TEXT, faction_icon TEXT
);

CREATE TABLE tww_campaigns(
  id INTEGER PRIMARY KEY,
  lord_id INTEGER NOT NULL REFERENCES tww_lords(id) ON DELETE RESTRICT,
  mode TEXT NOT NULL REFERENCES ref_tww_mode(name) ON UPDATE CASCADE,
  status TEXT NOT NULL REFERENCES ref_tww_status(name) ON UPDATE CASCADE,
  campaign_difficulty TEXT REFERENCES ref_tww_difficulty(name) ON UPDATE CASCADE,
  battle_difficulty TEXT REFERENCES ref_tww_difficulty(name) ON UPDATE CASCADE,
  {_opt_date('started')},
  {_opt_date('finished')},
  turns INTEGER CHECK(turns IS NULL OR (typeof(turns) = 'integer' AND turns > 0)),
  hours NUMERIC CHECK(hours IS NULL OR hours > 0),
  patch TEXT, mods TEXT, coop_with TEXT, notes TEXT,
  {(',' + chr(10) + '  ').join(_rating(c) for c in _TWW_RATINGS)},
  CHECK({_all_or_none(_TWW_RATINGS)})
);
CREATE INDEX ix_tww_camp_lord ON tww_campaigns(lord_id);
"""

TWW_SEEDS = {
    'ref_tww_mode': [('Realms of Chaos',), ('Immortal Empires',), ('Old World',)],
    'ref_tww_status': [('In progress',), ('Short victory',), ('Long victory',), ('Abandoned',), ('Lost',)],
    'ref_tww_difficulty': [('Easy', 1), ('Normal', 2), ('Hard', 3), ('Very Hard', 4), ('Legendary', 5)],
    'lk_twwratingweights': [('mechanics', 'Faction mechanics', 5), ('roster', 'Roster', 5), ('start_position', 'Start position', 3),
                            ('challenge', 'Challenge', 3), ('narrative', 'Narrative / lore', 2), ('late_game', 'Late game', 4),
                            ('enjoyment', 'Enjoyment', 5)],
}

# games can't take a CHECK without a rebuild (releases, top_rank and reviews all point at it), so triggers do it. NUMERIC
# affinity turns 8.0 into 8 but keeps 7.5 as a real, which typeof() catches.
MY_SCORE_DDL = """
CREATE TRIGGER games_my_score_ins BEFORE INSERT ON games
  WHEN NEW.my_score IS NOT NULL AND NOT (typeof(NEW.my_score) = 'integer' AND NEW.my_score BETWEEN 1 AND 10)
  BEGIN SELECT RAISE(ABORT, 'my_score must be a whole number from 1 to 10'); END;
CREATE TRIGGER games_my_score_upd BEFORE UPDATE OF my_score ON games
  WHEN NEW.my_score IS NOT NULL AND NOT (typeof(NEW.my_score) = 'integer' AND NEW.my_score BETWEEN 1 AND 10)
  BEGIN SELECT RAISE(ABORT, 'my_score must be a whole number from 1 to 10'); END;
"""

REVIEW_DDL = """
CREATE TABLE ref_tier(rank INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, description TEXT NOT NULL DEFAULT '');
ALTER TABLE games ADD COLUMN tier TEXT REFERENCES ref_tier(name) ON UPDATE CASCADE;
CREATE TABLE reviews(
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL UNIQUE COLLATE NOCASE REFERENCES games(title) ON UPDATE CASCADE ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published')),
  body TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  updated TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
-- a tier only arrives with a write-up (checked when the tier changes, so renames and undo of unrelated edits pass)
CREATE TRIGGER games_tier_ins BEFORE INSERT ON games
  WHEN NEW.tier IS NOT NULL AND NOT EXISTS (SELECT 1 FROM reviews WHERE title=NEW.title)
  BEGIN SELECT RAISE(ABORT, 'A tier can only be set on a game that has a review'); END;
CREATE TRIGGER games_tier_upd BEFORE UPDATE OF tier ON games
  WHEN NEW.tier IS NOT NULL AND NEW.tier IS NOT OLD.tier AND NOT EXISTS (SELECT 1 FROM reviews WHERE title IN (NEW.title, OLD.title))
  BEGIN SELECT RAISE(ABORT, 'A tier can only be set on a game that has a review'); END;
CREATE TRIGGER reviews_del BEFORE DELETE ON reviews
  WHEN (SELECT tier FROM games WHERE title=OLD.title) IS NOT NULL
  BEGIN SELECT RAISE(ABORT, 'Clear the game''s tier before deleting its review'); END;
"""


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con


def _v4(con):
    con.execute('ALTER TABLE play_log DROP COLUMN real')


def _v5(con):
    for stmt in _statements(REVIEW_DDL):
        con.execute(stmt)
    con.executemany('INSERT INTO ref_tier(rank, name, description) VALUES (?,?,?)', [(i, n, d) for i, (n, d) in enumerate(TIERS, 1)])


def _v6(con):
    """ref_tier gets an id (= its old rank) so edits go through the audit/undo machinery; rank becomes a plain sort column.
    Table rebuild per the SQLite docs; foreign keys are off on this connection, so games.tier keeps pointing at the name."""
    con.execute("""CREATE TABLE ref_tier_new(id INTEGER PRIMARY KEY, rank INTEGER NOT NULL,
                   name TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK(length(trim(name)) > 0), description TEXT NOT NULL DEFAULT '')""")
    con.execute('INSERT INTO ref_tier_new(id, rank, name, description) SELECT rank, rank, name, description FROM ref_tier')
    con.execute('DROP TABLE ref_tier')
    con.execute('ALTER TABLE ref_tier_new RENAME TO ref_tier')


def _v7(con):
    for stmt in _statements(TWW_DDL):
        con.execute(stmt)
    for tbl, rows in TWW_SEEDS.items():
        con.executemany(f'INSERT INTO {tbl} VALUES ({",".join("?" * len(rows[0]))})', rows)


def _v8(con):
    """Ratings must be whole numbers: rebuild halo_levels with the stricter checks (ids kept, so the audit trail still
    points at the right rows). Nothing references halo_levels, so no foreign keys are involved."""
    cols = ', '.join(['id', 'series_order', 'game', 'level_order', 'level'] + _HALO_RATINGS + ['notes'])
    con.execute('ALTER TABLE halo_levels RENAME TO halo_levels_old')
    con.execute('DROP INDEX ix_halo_game')
    for stmt in _statements(HALO_DDL):
        con.execute(stmt)
    con.execute(f'INSERT INTO halo_levels({cols}) SELECT {cols} FROM halo_levels_old')
    con.execute('DROP TABLE halo_levels_old')


def _v9(con):
    for stmt in _statements(MY_SCORE_DDL):
        con.execute(stmt)


def _statements(ddl):
    """Split DDL on ';' at statement ends, keeping trigger bodies (BEGIN ... END;) whole."""
    out, cur = [], ''
    for line in ddl.splitlines():
        if line.strip().startswith('--'): continue
        cur += line + '\n'
        if sqlite3.complete_statement(cur):
            out.append(cur.strip()); cur = ''
    return out


STEPS = {4: _v4, 5: _v5, 6: _v6, 7: _v7, 8: _v8, 9: _v9}     # target version -> upgrade from the version before it


def upgrade(path):
    """Apply pending upgrades in one transaction. v3 -> v4 drops the unused play_log.real flag;
    v4 -> v5 adds tiers and reviews; v5 -> v6 gives tiers an id; v6 -> v7 adds the Total War: Warhammer III lord tracker;
    v7 -> v8 makes HaloRank ratings whole numbers at the database level too;
    v8 -> v9 does the same for games.my_score (1-10), with triggers."""
    con = sqlite3.connect(path, isolation_level=None)
    try:
        ver = con.execute('PRAGMA user_version').fetchone()[0]
        if ver >= VERSION: return False
        if ver < 3: raise RuntimeError(f'unsupported schema version {ver}; expected 3 to {VERSION}')
        con.execute('BEGIN')
        try:
            for v in range(ver + 1, VERSION + 1):
                STEPS[v](con)
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
