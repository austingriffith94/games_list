"""Total War lord tracker: schema v7-v9 upgrades, constraints and scoring (scratch DB copy; never touches gamelist.db)."""
import os, sys, shutil, tempfile, sqlite3
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import schema, halo, tww

tmp = tempfile.mkdtemp()
db = os.path.join(tmp, 't.db')
shutil.copy('gamelist.db', db)

# --- v6 -> v9 upgrade (v7 adds the tracker, v8 rebuilds halo_levels, v9 adds my_score triggers), and again (no-op)
con = sqlite3.connect(db)
halo_before = con.execute('SELECT * FROM halo_levels ORDER BY id').fetchall()
con.execute('PRAGMA user_version=6')
for t in ('games_my_score_ins', 'games_my_score_upd'):
    con.execute(f'DROP TRIGGER IF EXISTS {t}')
for t in ('tww_campaigns', 'tww_lords', 'ref_tww_mode', 'ref_tww_status', 'ref_tww_difficulty', 'lk_twwratingweights'):
    con.execute(f'DROP TABLE IF EXISTS {t}')
con.commit(); con.close()
assert schema.upgrade(db) is True
assert schema.upgrade(db) is False
con = schema.connect(db)
assert con.execute('PRAGMA user_version').fetchone()[0] == schema.VERSION == 9
assert con.execute('SELECT count(*) FROM ref_tww_mode').fetchone()[0] == 3
assert [r[0] for r in con.execute('SELECT name FROM ref_tww_difficulty ORDER BY sort')] == ['Easy', 'Normal', 'Hard', 'Very Hard', 'Legendary']
assert [r[0] for r in con.execute('SELECT col FROM lk_twwratingweights ORDER BY rowid')] == tww.RATING_COLS

assert [tuple(r) for r in con.execute('SELECT * FROM halo_levels ORDER BY id')] == [tuple(r) for r in halo_before]   # rebuild kept every row and id
assert {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE tbl_name='halo_levels'")} >= {'ix_halo_game'}
assert not con.execute('PRAGMA foreign_key_check').fetchall()

# --- my_score is a whole number 1-10 in the database too
def score_set(v):
    try: con.execute("UPDATE games SET my_score=? WHERE title='WRC 8'", (v,))
    except sqlite3.IntegrityError: return False
    return True
keep = con.execute("SELECT my_score FROM games WHERE title='WRC 8'").fetchone()[0]
assert not any(score_set(v) for v in (7.5, 0, 11, 'abc', -3))
assert all(score_set(v) for v in (1, 10, 8.0, None))
con.execute("UPDATE games SET my_score=? WHERE title='WRC 8'", (keep,))
assert not con.execute("UPDATE games SET ign=ign WHERE title='WRC 8'").rowcount == 0   # other columns still editable
g = dict(con.execute("SELECT * FROM games WHERE title='WRC 8'").fetchone())
try:
    con.execute('INSERT INTO games(%s) VALUES (%s)' % (','.join(g), ','.join('?' * len(g))), [None if k == 'id' else ('x' if k == 'title' else (4.5 if k == 'my_score' else v)) for k, v in g.items()])
    raise SystemExit('FAILED: fractional my_score inserted')
except sqlite3.IntegrityError: pass

# --- HaloRank ratings are whole numbers in the database too
HALO9 = dict(zip(halo.RATING_COLS, [3] * 9))
def halo_refused(**kw):
    row = {'series_order': 99, 'game': 'G', 'level_order': 1, 'level': f'L{len(kw)}{kw}', **HALO9, **kw}
    try: con.execute(f'INSERT INTO halo_levels({",".join(row)}) VALUES ({",".join("?" * len(row))})', list(row.values()))
    except sqlite3.IntegrityError: return True
    return False
assert halo_refused(enemy=3.5) and halo_refused(enemy='abc') and halo_refused(enemy=6) and halo_refused(enemy=-1)
assert not halo_refused(enemy=0) and not halo_refused(enemy=5) and not halo_refused(**{c: None for c in halo.RATING_COLS})
assert halo_refused(enemy=None)                      # still all-or-none

# --- constraints
con.execute("INSERT INTO tww_lords(id, race, race_game, race_order, lord) VALUES (1, 'Empire', 1, 1, 'Karl Franz')")
def camp(**kw):
    row = {'lord_id': 1, 'mode': 'Immortal Empires', 'status': 'Long victory', **kw}
    con.execute(f'INSERT INTO tww_campaigns({",".join(row)}) VALUES ({",".join("?" * len(row))})', list(row.values()))
def refused(**kw):
    try: camp(**kw)
    except sqlite3.IntegrityError: return True
    return False
R = dict(zip(tww.RATING_COLS, [5, 4, 3, 2, 1, 0, 5]))
camp()                                    # only lord + mode + status
camp(**R); camp(**R)                      # same lord + mode twice is fine
assert refused(mechanics=3)               # some ratings but not all
assert refused(**{**R, 'enjoyment': 6})
assert refused(mode='Nope') and refused(status='Nope') and refused(campaign_difficulty='Nope')
assert refused(started='2026-13-40x') and refused(turns=0) and refused(hours=0)
assert refused(started='2026-13-40') and refused(finished='2026-02-30') and refused(started='2026-1-5') and refused(started='')
assert refused(**{**R, 'mechanics': 2.5}) and refused(**{**R, 'late_game': 'x'}) and refused(turns=10.5)
camp(started='2024-02-29', finished='2024-02-29')    # leap day is real; same-day is fine
con.execute("DELETE FROM tww_campaigns WHERE started='2024-02-29'")
camp(started='2026-01-02', finished='2026-02-03', turns=120, hours=30.5, campaign_difficulty='Legendary')
try:
    con.execute('DELETE FROM tww_lords WHERE id=1'); raise SystemExit('FAILED: lord with campaigns deleted')
except sqlite3.IntegrityError: pass
try:
    con.execute("INSERT INTO tww_lords(race, race_game, race_order, lord) VALUES ('X', 4, 1, 'Bad')"); raise SystemExit('FAILED: race_game 4')
except sqlite3.IntegrityError: pass
try:
    con.execute("INSERT INTO tww_lords(race, race_game, race_order, lord) VALUES ('Empire', 1, 1, 'KARL franz')"); raise SystemExit('FAILED: duplicate lord')
except sqlite3.IntegrityError: pass

# --- scoring: hand-worked example. weights 5,5,3,3,2,4,5 (sum 27); ratings 5,4,3,2,1,0,5
# 25 + 20 + 9 + 6 + 2 + 0 + 25 = 87 -> 87/27
weights, tiers = tww.load_scoring(con)
assert weights == [5, 5, 3, 3, 2, 4, 5] and tiers == halo.load_scoring(con)[1]
assert abs(tww.campaign_score(R, weights) - 87 / 27) < 1e-12
assert tww.campaign_score({}, weights) is None and tww.campaign_score({**R, 'roster': None}, weights) is None
assert tww.tier_of(87 / 27, tiers) == ('B', 3)       # 3.222 is in (3, 4]
for v in (5, 4.5, 4.0001, 4, 3.0001, 3, 2.0001, 2, 1.0001, 1, 0):   # band edges are the same as HaloRank's
    assert tww.tier_of(v, tiers) == halo.tier_of(v, tiers)
assert tww.tier_of(4.5, tiers)[0] == 'A' and tww.tier_of(4.51, tiers)[0] == 'S' and tww.tier_of(None, tiers) is None

# --- lord score: best rated campaign by default; unrated campaigns count as played only
rows = [dict(r) for r in con.execute('SELECT * FROM tww_campaigns')]
low = [r for r in rows if r['mechanics'] is None and r['turns'] is None][0]
con.execute('UPDATE tww_campaigns SET mechanics=1, roster=1, start_position=1, challenge=1, narrative=1, late_game=1, enjoyment=1 WHERE id=?', (low['id'],))
scored = tww.score_rows([dict(r) for r in con.execute('SELECT * FROM tww_campaigns')], weights, tiers)
assert sum(1 for c in scored if c['score'] is None) == 1          # the dated one has no ratings
ls = tww.lord_scores(scored, tiers)[1]
assert ls['campaigns'] == 4 and ls['rated'] == 3
assert abs(ls['score'] - 87 / 27) < 1e-12 and ls['tier'] == 'B'   # best of 1.0, 3.22, 3.22
avg = tww.lord_scores(scored, tiers, 'avg')[1]
assert abs(avg['score'] - (1 + 2 * 87 / 27) / 3) < 1e-12
none = tww.lord_scores(tww.score_rows([{'id': 9, 'lord_id': 2, 'mode': 'x'}], weights, tiers), tiers)[2]
assert none['score'] is None and none['tier'] is None and none['best_id'] is None and none['campaigns'] == 1

# --- race summary
lords = [dict(r) for r in con.execute('SELECT * FROM tww_lords')]
lords.append(dict(id=2, race='Skaven', race_game=2, race_order=1, lord='Queek'))
lords.append(dict(id=3, race='Empire', race_game=1, race_order=1, lord='Balthasar'))
rs = tww.race_summary(lords, scored)
assert [r['race'] for r in rs] == ['Empire', 'Skaven']
assert rs[0]['lords'] == 2 and rs[0]['played'] == 1 and rs[0]['campaigns'] == 4 and rs[0]['rated'] == 3
assert rs[0]['modes'] == {'Immortal Empires': 4} and rs[1]['played'] == 0 and rs[1]['ratings']['roster'] is None
assert abs(rs[0]['ratings']['roster'] - (1 + 4 + 4) / 3) < 1e-12

con.close(); shutil.rmtree(tmp, ignore_errors=True)
print('test_tww: ok')
