"""API tests against a scratch copy of the database (never touches gamelist.db)."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)   # tests use root-relative paths (gamelist.db, app.py, covers/)
import os, shutil, tempfile, io, json, zipfile, sqlite3
import app as A

tmp = tempfile.mkdtemp()
A.DB = os.path.join(tmp, 't.db'); A.COVERS = os.path.join(tmp, 'covers'); A.BACKUPS = os.path.join(tmp, 'bk')
A.REPORT_HTML = os.path.join(tmp, 'd.html'); A.REPORT_PDF = os.path.join(tmp, 'r.pdf'); os.makedirs(A.COVERS)
A.REVIEW_IMAGES = os.path.join(tmp, 'rimg'); A.REPORT_REVIEWS = os.path.join(tmp, 'rv.html'); os.makedirs(A.REVIEW_IMAGES)
shutil.copy('gamelist.db', A.DB)
import schema; schema.upgrade(A.DB)    # app.main() does this on start; the test client skips main()
_seed = sqlite3.connect(A.DB)   # re-seed the two out-of-range scores the checks test below expects to find,
try:                             # since the real production data got fixed for real; must close explicitly (see counts() above)
    _seed.execute("UPDATE games SET ign=84 WHERE title='WRC 8'")
    _seed.execute("UPDATE games SET gamespot=80 WHERE title='Overwatch 2'")
    _seed.commit()
finally:
    _seed.close()
c = A.app.test_client(); H = {'X-Requested-With': 'gamelist'}
def get(u): return c.get(u, headers=H)
def post(u, j=None, **kw): return c.post(u, json=j, headers=H, **kw)
def put(u, j): return c.put(u, json=j, headers=H)
def delete(u): return c.delete(u, headers=H)
def counts():
    con = sqlite3.connect(A.DB)   # must close explicitly: `with` only commits/rolls back, doesn't close -
    try:                          # an open handle keeps the file locked, so Windows' final rmtree fails
        return {t: con.execute(f'select count(*) from {t}').fetchone()[0] for t in ('games', 'releases', 'play_log')}
    finally:
        con.close()
base = counts(); ok = 0
def check(cond, msg):
    global ok
    assert cond, 'FAILED: ' + msg
    ok += 1

# --- security
check(c.post('/api/log', json={}).status_code == 403, 'POST without header is blocked')
check(c.get('/api/meta', headers={'Host': 'evil.example.com'}).status_code == 403, 'foreign Host blocked')
# --- meta
m = get('/api/meta').get_json()
check(len(m['genre']) == 13 and 'Steam' in [s['name'] for s in m['systems']] and m['counts']['games'] == 656, 'meta lists')
check('Role-playing' in m['subgenres'] and 'Action RPG' in m['subgenres']['Role-playing'], 'subgenres by genre')
# --- create game: validation
r = post('/api/games', {'game': {'title': 'halo 2'}, 'releases': []}); j = r.get_json()
check(r.status_code == 400 and 'title' in j['fields'] and 'genre' in j['fields'] and 'modes' in j['fields'] and 'releases' in j['fields'], 'new game validation: ' + str(j['fields']))
good = {'title': 'Test Game: Alpha', 'series': '', 'graphic_style': '3D', 'camera_view': 'First Person', 'genre': 'Shooter',
        'sub_genre': 'Tactical Shooter', 'singleplayer': True, 'my_score': 8, 'metacritic': 85, 'ign': 8.5}
rel = {'release': 'Retail', 'system': 'Steam', 'ownership': 'Paid', 'original_release_date': '2025-03-01', 'version_release_date': '2025-03-01', 'added_date': '2025-04-01'}
r = post('/api/games', {'game': good, 'releases': [rel]}); j = r.get_json()
check(r.status_code == 201, 'create valid game: ' + str(j)); gid = j['id']
check(post('/api/games', {'game': {**good, 'title': 'TEST GAME: ALPHA'}, 'releases': [rel]}).status_code == 400, 'duplicate title (case-insensitive) rejected')
g = get(f'/api/games/{gid}').get_json()
check(g['game']['series'] == 'Test Game: Alpha' and g['game']['singleplayer'] == 1 and len(g['releases']) == 1, 'series defaults to title; modes saved')
bad = post('/api/games', {'game': {**good, 'title': 'Bad Scores', 'my_score': 11, 'metacritic': 101, 'ign': 'abc', 'sub_genre': 'MMORPG'}, 'releases': [rel]}).get_json()['fields']
check({'my_score', 'metacritic', 'ign', 'sub_genre'} <= set(bad), 'score range + wrong sub-genre rejected: ' + str(bad))
bad = post('/api/games', {'game': {**good, 'title': 'Frac Score', 'my_score': 7.5}, 'releases': [rel]}).get_json()['fields']
check('my_score' in bad, 'fractional my_score rejected: ' + str(bad))
bad = post('/api/games', {'game': {**good, 'title': 'Bad Rel'}, 'releases': [{**rel, 'original_release_date': '2025-13-40'}, {**rel}]}).get_json()['fields']
check('releases.0.original_release_date' in bad and 'releases.1.system' in bad, 'bad date + duplicate system in one entry: ' + str(bad))
# --- releases
r = post(f'/api/games/{gid}/releases', {**rel, 'system': 'Steam'})
check(r.status_code == 400 and 'system' in r.get_json()['fields'], 'duplicate title+system release rejected')
r = post(f'/api/games/{gid}/releases', {**rel, 'system': 'GOG', 'added_date': '2024-01-01'}); check(r.status_code == 201 and r.get_json()['warnings'], 'second release saved with date warning: ' + str(r.get_json()))
gog_id = r.get_json()['id']
# --- time log
T = 'Test Game: Alpha'
log = {'date': '2026-10-01', 'game': T, 'system': 'Steam', 'hours': 2}
prev = get(f'/api/log/preview?game={T}&system=Steam&date=2026-10-01').get_json()
check(prev['game_total'] == 0 and prev['existing'] is None and prev['systems'] == ['Steam', 'GOG'], 'preview before logging')
r = post('/api/log', log); j = r.get_json(); check(r.status_code == 201 and j['action'] == 'new' and j['game_total_before'] == 0 and j['game_total_after'] == 2, 'log new entry: ' + str(j)); lid = j['id']
r = post('/api/log', log); check(r.status_code == 409 and r.get_json()['needs_confirm'] == 'exists' and r.get_json()['existing']['hours'] == 2, 'duplicate asks add/overwrite')
r = post('/api/log', {**log, 'hours': 1.5, 'mode': 'add'}); check(r.get_json()['hours'] == 3.5 and r.get_json()['game_total_after'] == 3.5, 'mode=add sums hours')
r = post('/api/log', {**log, 'hours': 1, 'mode': 'overwrite'}); check(r.get_json()['hours'] == 1 and r.get_json()['game_total_after'] == 1, 'mode=overwrite replaces hours')
check(counts()['play_log'] == base['play_log'] + 1, 'still only one row for that date/game/system')
r = post('/api/log', {**log, 'date': '2026-10-02', 'hours': 30}); check(r.status_code == 409 and r.get_json()['needs_confirm'] == 'large', '>24h needs confirmation')
r = post('/api/log', {**log, 'date': '2026-10-02', 'hours': 30, 'allow_large': True}); check(r.status_code == 201, '>24h saved once confirmed')
check(post('/api/log', {**log, 'date': '2099-01-01'}).status_code == 400, 'future date rejected')
check(post('/api/log', {**log, 'system': 'Wii'}).status_code == 400, 'system without a release rejected')
check(post('/api/log', {**log, 'game': 'No Such Game'}).status_code == 400, 'unknown game rejected')
check(post('/api/log', {**log, 'hours': 0}).status_code == 400 and post('/api/log', {**log, 'hours': -1}).status_code == 400, 'zero/negative hours rejected')
check(post('/api/log', {**log, 'game': T.upper(), 'date': '2026-09-30'}).status_code == 201, 'game name matched ignoring case, stored canonically')
check(get('/api/log?game=' + T).get_json()['rows'][0]['game'] == T, 'canonical title stored')
r = put(f'/api/log/{lid}', {**log, 'hours': 2.25}); check(r.status_code == 200 and get(f'/api/log?game={T}').get_json()['total'] == 3, 'edit log entry')
r = put(f'/api/log/{lid}', {**log, 'date': '2026-09-30'}); check(r.status_code == 409, 'edit into duplicate rejected')
# --- rename cascades (+ cover follows)
from PIL import Image
buf = io.BytesIO(); Image.new('RGB', (60, 90), 'orange').save(buf, 'PNG'); buf.seek(0)
r = c.post(f'/api/games/{gid}/cover', data={'file': (buf, 'x.png')}, headers=H, content_type='multipart/form-data')
check(r.status_code == 201 or r.status_code == 200, 'cover upload'); check(os.path.exists(os.path.join(A.COVERS, 'Test Game Alpha.png')), 'cover saved without colon')
r = c.post(f'/api/games/{gid}/cover', data={'file': (io.BytesIO(b'not an image'), 'x.png')}, headers=H, content_type='multipart/form-data'); check(r.status_code == 400, 'non-image rejected')
gm = get(f'/api/games/{gid}').get_json()['game']
r = put(f'/api/games/{gid}', {**gm, 'title': 'Test Game: Beta'}); check(r.status_code == 200, 'rename game')
check(get('/api/log?game=Test Game: Beta').get_json()['total'] == 3 and not get('/api/log?game=Test Game: Alpha').get_json()['total'], 'rename cascaded to time log')
check(os.path.exists(os.path.join(A.COVERS, 'Test Game Beta.png')) and not os.path.exists(os.path.join(A.COVERS, 'Test Game Alpha.png')), 'cover file renamed with game')
r = put('/api/games/1', {**get('/api/games/1').get_json()['game'], 'title': 'Test Game: Beta'}); check(r.status_code == 400, 'rename onto existing title rejected')
# --- delete protection and force
r = delete(f'/api/games/{gid}'); j = r.get_json(); check(r.status_code == 409 and j['needs_force'] and j['releases'] == 2 and j['log'] == 3, 'delete blocked: ' + str(j))
r = delete(f'/api/releases/{gog_id}'); check(r.status_code == 200, 'release with no log entries deletes')
r = delete(f'/api/games/{gid}?force=1'); check(r.status_code == 200 and counts() == base, 'forced delete removes game, releases and log: ' + str(counts()))
# --- undo
batches = get('/api/audit').get_json(); check(batches[0]['summary'].startswith('Deleted'), 'audit lists newest first')
r = post(f'/api/undo/{batches[0]["batch"]}'); check(r.status_code == 200 and counts()['games'] == base['games'] + 1 and counts()['play_log'] == base['play_log'] + 3, 'undo of forced delete restores everything: ' + str(counts()))
check(post(f'/api/undo/{batches[0]["batch"]}').status_code == 409, 'cannot undo twice')
lastlog = [b for b in get('/api/audit').get_json() if b['summary'].startswith('Logged')][0]
check(post(f'/api/undo/{lastlog["batch"]}').status_code in (200, 409), 'undo log insert handled')
# --- top list
top = get('/api/top').get_json(); check(len(top) == 20 and top[0]['title'] == 'Mass Effect 2', 'top list')
titles = [t['title'] for t in top]; titles[0], titles[1] = titles[1], titles[0]
check(put('/api/top', {'titles': titles}).status_code == 200 and get('/api/top').get_json()[0]['title'] == 'The Witcher 3: Wild Hunt', 'reorder top list')
check(put('/api/top', {'titles': titles + ['Nope']}).status_code == 400, 'unknown title in top list rejected')
# --- checks reflect the two bad review scores
ck = get('/api/checks').get_json(); errs = [i for i in ck['items'] if i['severity'] == 'error' and i['kind'] == 'score_range']
check({(e['title']) for e in errs} == {'WRC 8', 'Overwatch 2'}, 'checks flag the two out-of-range scores: ' + str([e['title'] for e in errs]))
print('   checks summary:', ck['summary'], {k: sum(1 for i in ck['items'] if i['kind'] == k) for k in {i['kind'] for i in ck['items']}})
# fixing a flagged row through the API works
wrc = [g for g in get('/api/games').get_json() if g['title'] == 'WRC 8'][0]; full = get(f'/api/games/{wrc["id"]}').get_json()['game']
check(put(f'/api/games/{wrc["id"]}', full).status_code == 400, 'saving WRC 8 with IGN=84 is refused')
check(put(f'/api/games/{wrc["id"]}', {**full, 'ign': 8.4}).status_code == 200, 'IGN corrected to 8.4')
# --- HaloRank
hr = get('/api/halo').get_json()
check(len(hr['levels']) == 85 and len(hr['games']) == 8 and hr['weights'] == [5, 5, 5, 5, 2, 3, 2, 2, 5], 'halo levels, games, weights')
lv = {x['level']: x for x in hr['levels'] if x['game'] == 'Halo: Combat Evolved'}
check(abs(lv['The Pillar of Autumn']['variable_score'] - 4.088235294117647) < 1e-12 and lv['The Pillar of Autumn']['tier'] == 'A', 'halo score + tier match the workbook')
check(lv['Halo']['tier'] == 'S' and abs(lv['Halo']['variable_score'] - 4.529411764705882) < 1e-12, 'upper-inclusive S band')
check(sum(1 for x in hr['levels'] if x['variable_score'] is None) == 26 and all(x['tier'] is None for x in hr['levels'] if x['variable_score'] is None), '26 unrated levels have no tier')
g5 = [g for g in hr['games'] if g['game'] == 'Halo 5: Guardians'][0]
check(g5['rated'] == 0 and g5['avg_score'] is None and g5['levels'] == 12, 'unrated levels are excluded from averages')
rated = {k: 5 for k in hr['cols']}
check(post('/api/halo', {'game': 'Halo 5: Guardians', 'level': 'Test Level', 'enemy': 3}).status_code == 400, 'partly rated level refused')
check(post('/api/halo', {'game': 'Halo 5: Guardians', 'level': 'Test Level', **{**rated, 'enemy': 6}}).status_code == 400, 'rating above 5 refused')
check(post('/api/halo', {'game': 'Halo 5: Guardians', 'level': 'Test Level', **{**rated, 'enemy': 3.5}}).status_code == 400, 'fractional rating refused')
check(post('/api/halo', {'game': 'Halo 5: Guardians', 'level': 'Test Level', **{**rated, 'enemy': 'nan'}}).status_code == 400, 'nan rating refused (not a 500)')
r = post('/api/halo', {'game': 'halo 5: guardians', 'level': 'Test Level', **rated}); check(r.status_code == 201, 'add a halo level (game name any case)')
new = [x for x in get('/api/halo').get_json()['levels'] if x['level'] == 'Test Level'][0]
check(new['game'] == 'Halo 5: Guardians' and new['series_order'] == 7 and new['level_order'] == 13 and new['tier'] == 'S' and new['variable_score'] == 5, 'new level joins its game, scores S')
check(post('/api/halo', {'game': 'Halo 5: Guardians', 'level': 'test level'}).status_code == 400, 'duplicate level name refused')
check(put(f'/api/halo/{new["id"]}', {'enemy': 0, 'weapon_vehicle': 0, 'design_set_piece': 0, 'replayability_pacing': 0, 'difficulty': 0, 'visual': 0, 'music': 0, 'story': 0, 'enjoyment': 0}).status_code == 200, 'all-zero ratings are a real (F) rating')
check([x for x in get('/api/halo').get_json()['levels'] if x['id'] == new['id']][0]['tier'] == 'F', 'rated 0 lands in F')
check(put(f'/api/halo/{new["id"]}', {k: None for k in hr['cols']}).status_code == 200 and [x for x in get('/api/halo').get_json()['levels'] if x['id'] == new['id']][0]['tier'] is None, 'clearing ratings makes it unrated')
r = delete(f'/api/halo/{new["id"]}'); check(r.status_code == 200 and len(get('/api/halo').get_json()['levels']) == 85, 'delete a halo level')
check(post(f'/api/undo/{r.headers["X-Batch"]}').status_code == 200 and len(get('/api/halo').get_json()['levels']) == 86, 'undo restores the deleted halo level')
# --- Warhammer III lords
lr = get('/api/lords').get_json(); LID = lr['lords'][0]['id']; lords_n = len(lr['lords'])
check(lords_n >= 100 and not lr['campaigns'] and lr['weights'] == [5, 5, 3, 3, 2, 4, 5] and lr['modes'] == ['Realms of Chaos', 'Immortal Empires', 'Old World'], 'lords payload')
check(lr['lords'][0]['card_url'] is None or lr['lords'][0]['card_url'].startswith('/lords/'), 'lord image urls')
cbase = {'lord_id': LID, 'mode': 'Immortal Empires', 'status': 'In progress'}
r = post('/api/lords/campaigns', cbase); check(r.status_code == 201, 'campaign with only lord + mode + status saves: ' + str(r.get_json())); c1 = r.get_json()['id']
check(get('/api/lords').get_json()['campaigns'][0]['score'] is None, 'unrated campaign has no score')
rated7 = {k: 5 for k in lr['cols']}
check(post('/api/lords/campaigns', {**cbase, 'mechanics': 3}).status_code == 400, 'partly rated campaign refused')
check(post('/api/lords/campaigns', {**cbase, **rated7, 'roster': 6}).status_code == 400, 'rating above 5 refused')
check(post('/api/lords/campaigns', {**cbase, **rated7, 'roster': 'nan'}).status_code == 400, 'nan rating refused')
check(post('/api/lords/campaigns', {**cbase, 'mode': 'Mars'}).status_code == 400, 'unknown mode refused')
check(post('/api/lords/campaigns', {**cbase, 'status': 'Napping'}).status_code == 400, 'unknown status refused')
check(post('/api/lords/campaigns', {**cbase, 'battle_difficulty': 'Impossible'}).status_code == 400, 'unknown difficulty refused')
check(post('/api/lords/campaigns', {**cbase, 'lord_id': 999999}).status_code == 400, 'unknown lord refused')
check(post('/api/lords/campaigns', {**cbase, 'started': '2026-05-02', 'finished': '2026-05-01'}).status_code == 400, 'finished before started refused')
check(post('/api/lords/campaigns', {**cbase, 'turns': 0}).status_code == 400, 'zero turns refused')
r = post('/api/lords/campaigns', {**cbase, **rated7}); check(r.status_code == 201, 'second campaign, same lord and mode, saves'); c2 = r.get_json()['id']
r = post('/api/lords/campaigns', {**cbase, **{k: 3 for k in lr['cols']}, 'campaign_difficulty': 'very hard', 'coop_with': 'Sam'}); c3 = r.get_json()['id']
lr = get('/api/lords').get_json(); sc = lr['scores']['best'][str(LID)]
check(sc['campaigns'] == 3 and sc['rated'] == 2 and sc['score'] == 5 and sc['best_id'] == c2, 'lord score is the best rated campaign')
check(abs(lr['scores']['avg'][str(LID)]['score'] - 4) < 1e-12, 'average mode averages rated campaigns only')
check([c for c in lr['campaigns'] if c['id'] == c3][0]['campaign_difficulty'] == 'Very Hard', 'difficulty stored in canonical case')
check(sum(r['played'] for r in lr['races']) == 1 and sum(r['campaigns'] for r in lr['races']) == 3, 'race summary counts played lords and campaigns')
check(delete(f'/api/lords/{LID}').status_code == 409, 'lord with campaigns cannot be deleted')
r = put(f'/api/lords/campaigns/{c3}', {'mechanics': None, **{k: None for k in lr['cols']}}); check(r.status_code == 200, 'clear ratings')
r = delete(f'/api/lords/campaigns/{c2}'); check(r.status_code == 200 and get('/api/lords').get_json()['scores']['best'][str(LID)]['rated'] == 0, 'delete a campaign')
check(post(f'/api/undo/{r.headers["X-Batch"]}').status_code == 200 and get('/api/lords').get_json()['scores']['best'][str(LID)]['rated'] == 1, 'undo restores the deleted campaign')
# the Checks tab: RoC campaign for a lord who is not RoC-playable
nonroc = [l for l in lr['lords'] if not l['roc_playable']][0]
post('/api/lords/campaigns', {'lord_id': nonroc['id'], 'mode': 'Realms of Chaos', 'status': 'Lost'})
check(any(i['kind'] == 'lord_roc' and i.get('lord_id') == nonroc['id'] for i in get('/api/checks').get_json()['items']), 'checks flag a RoC campaign for a lord who is not RoC-playable')
# adding and editing lords by hand
r = post('/api/lords', {'lord': 'Test Lord', 'race': 'the empire', 'race_game': 1, 'roc_playable': True}); check(r.status_code == 201, 'add a lord: ' + str(r.get_json())); tl = r.get_json()['id']
t = [l for l in get('/api/lords').get_json()['lords'] if l['id'] == tl][0]
check(t['race'] == 'The Empire' and t['race_order'] == [l for l in lr['lords'] if l['race'] == 'The Empire'][0]['race_order'] and t['roc_playable'] == 1, 'new lord joins the existing race section')
check(post('/api/lords', {'lord': 'test lord', 'race': 'The Empire', 'race_game': 1}).status_code == 400, 'duplicate lord name refused')
check(post('/api/lords', {'lord': 'X', 'race': 'Y', 'race_game': 4}).status_code == 400, 'race_game must be 1-3')
check(put(f'/api/lords/{tl}', {'card': '../secret.png'}).status_code == 400, 'image file name cannot be a path')
check(put(f'/api/lords/{tl}', {'dlc': 'Test DLC'}).status_code == 200, 'edit a lord')
r = delete(f'/api/lords/{tl}'); check(r.status_code == 200 and len(get('/api/lords').get_json()['lords']) == lords_n, 'delete a lord with no campaigns')
check(post(f'/api/undo/{r.headers["X-Batch"]}').status_code == 200 and len(get('/api/lords').get_json()['lords']) == lords_n + 1, 'undo restores the lord')
# --- reviews (tier lives on the game but only arrives with a review)
import reviews as RVM
check(RVM.parse_body('One\ntwo.\n\n![A cap](a.jpg){small}\nThree') == [{'t': 'p', 'h': 'One two.'}, {'t': 'fig', 'img': 'a.jpg', 'cap': 'A cap', 'small': True}, {'t': 'p', 'h': 'Three'}], 'body format parses')
check(RVM.text_stats(RVM.parse_body('Short one. Second sentence that pushes past seventy characters overall here. Third.'))['excerpt'].endswith('here.'), 'excerpt stops after ~70 chars')
m = get('/api/meta').get_json(); check(len(m['tiers']) == 11 and m['tiers'][0]['name'] == 'Worstest' and m['tiers'][-1]['name'] == 'Masterpiece', 'tiers in meta')
RT = 'Test Game: Beta'; rg = [g for g in get('/api/games').get_json() if g['title'] == RT][0]['id']
n_rev = len(get('/api/reviews').get_json())
check(post('/api/reviews', {'title': RT}).status_code == 400, 'review needs a tier')
check(post('/api/reviews', {'title': 'No Such Game', 'tier': 'Bueno'}).status_code == 400, 'review needs a known game')
r = post('/api/reviews', {'title': RT.upper(), 'tier': 'bueno'}); check(r.status_code == 201, 'start a draft review'); rid = r.get_json()['id']
check(get(f'/api/games/{rg}').get_json()['game']['tier'] == 'Bueno' and get(f'/api/games/{rg}').get_json()['review']['status'] == 'draft', 'tier saved on the game (canonical name)')
check(post('/api/reviews', {'title': RT, 'tier': 'Bueno'}).status_code == 400, 'one review per game')
gm = get(f'/api/games/{rg}').get_json()['game']
check(put(f'/api/games/{rg}', {**gm, 'tier': 'Masterpiece', 'my_score': 7}).status_code == 200 and get(f'/api/games/{rg}').get_json()['game']['tier'] == 'Bueno', 'game form cannot change the tier')
plain = [g for g in get('/api/games').get_json() if g['title'] == 'Halo 2'][0]['id']
try:
    con_ = sqlite3.connect(A.DB); con_.execute("UPDATE games SET tier='Bueno' WHERE id=?", (plain,)); con_.commit(); check(False, 'tier without a review must be refused')
except sqlite3.IntegrityError as e:
    check('review' in str(e), 'database refuses a tier on a game without a review')
finally:
    con_.close()
buf = io.BytesIO(); Image.new('RGB', (1900, 1000), 'teal').save(buf, 'JPEG'); jpg = buf.getvalue(); buf.seek(0)
r = c.post('/api/review-images', data={'file': (buf, 'My Shot!.jpg'), 'title': RT}, headers=H, content_type='multipart/form-data'); img = r.get_json()['file']
check(r.status_code == 201 and img == 'test-game-beta_My_Shot.jpg' and os.path.exists(os.path.join(A.REVIEW_IMAGES, img)), 'review image saved with a safe name: ' + img)
check(c.post('/api/review-images', data={'file': (io.BytesIO(jpg), 'My Shot!.jpg'), 'title': RT}, headers=H, content_type='multipart/form-data').get_json()['file'] == 'test-game-beta_My_Shot-2.jpg', 'same name gets a suffix')
body = 'First paragraph. It is about the game and runs on long enough for an excerpt.\n\n' + f'![A caption]({img})\n\n![Gone](missing.jpg)\n\nSecond paragraph.'
r = put(f'/api/reviews/{rid}', {'tier': 'Bueno', 'status': 'draft', 'body': body}); check(r.status_code == 200 and r.get_json()['warnings'] == ['Image not found: missing.jpg'], 'draft saves with a missing-image warning')
check(put(f'/api/reviews/{rid}', {'tier': 'Bueno', 'status': 'published', 'body': body}).status_code == 400, 'publishing with a missing image refused')
check(put(f'/api/reviews/{rid}', {'tier': 'Bueno', 'status': 'published', 'body': ''}).status_code == 400, 'publishing an empty review refused')
body = body.replace('\n\n![Gone](missing.jpg)', '')
r = put(f'/api/reviews/{rid}', {'tier': 'Flawed Gem', 'status': 'published', 'body': body}); check(r.status_code == 200, 'publish + move tier')
check(get(f'/api/games/{rg}').get_json()['game']['tier'] == 'Flawed Gem', 'tier change saved on the game')
lst = get('/api/reviews').get_json(); me = [x for x in lst if x['id'] == rid][0]
check(len(lst) == n_rev + 1 and me['words'] == 17 and me['mins'] == 1 and me['tier'] == 'Flawed Gem', 'review list with stats: ' + str(me))
pv = c.post(f'/api/reviews/{rid}/preview', json={'tier': 'Masterpiece', 'body': 'Unsaved words here.'}, headers=H).get_data(as_text=True)
check('Unsaved words here.' in pv and '"preview":' + str(rid) in pv and '"name":"Masterpiece","desc"' in pv, 'preview renders unsaved text and tier')
check(delete(f'/api/games/{rg}?force=1').status_code == 409, 'game with a review cannot be deleted')
# undoing an older game edit must not wipe the tier set since
edit = [b for b in get('/api/audit').get_json() if b['summary'] == f'Edited game {RT}'][0]
check(post(f'/api/undo/{edit["batch"]}').status_code == 200, 'undo older game edit')
g2 = get(f'/api/games/{rg}').get_json()['game']; check(g2['tier'] == 'Flawed Gem' and g2['my_score'] == 8, 'undo restored only what that edit changed: ' + str((g2['tier'], g2['my_score'])))
rb = post('/api/rebuild?only=reviews'); j = rb.get_json()
check(rb.status_code == 200 and set(j) == {'reviews'} and os.path.exists(A.REPORT_REVIEWS), 'build the reviews page alone: ' + str(j))
rp = get('/api/reports').get_json(); check(rp['reviews']['ts'] >= rp['last_review_change'], 'freshly built page is not out of date: ' + str((rp['reviews']['ts'], rp['last_review_change'])))
html = get('/reviews').get_data(as_text=True)
check(RT in html and 'data:image/jpeg;base64,' in html and 'Unsaved words' not in html, 'built page embeds the published review and its image')
os.remove(os.path.join(A.REVIEW_IMAGES, img))
check(any(i['kind'] == 'review_image' and i['severity'] == 'error' for i in get('/api/checks').get_json()['items']), 'checks flag a published review missing its image')
r = delete(f'/api/reviews/{rid}'); check(r.status_code == 200 and get(f'/api/games/{rg}').get_json()['game']['tier'] is None and len(get('/api/reviews').get_json()) == n_rev, 'delete review clears the tier')
check(post(f'/api/undo/{r.headers["X-Batch"]}').status_code == 200 and get(f'/api/games/{rg}').get_json()['game']['tier'] == 'Flawed Gem', 'undo brings back review and tier')
# --- editing the tiers
tl = get('/api/tiers').get_json(); orig = [t['name'] for t in tl]
check(len(tl) == 11 and all('id' in t and 'n_games' in t for t in tl) and [t['name'] for t in tl if t['n_games']].count('Flawed Gem') == 1, 'tier list with counts')
keep = [{'id': t['id'], 'name': t['name'], 'description': t['description']} for t in tl]
fg = next(t for t in keep if t['name'] == 'Flawed Gem'); mp = next(t for t in keep if t['name'] == 'Masterpiece')
put_t = lambda lst: put('/api/tiers', {'tiers': lst})
check(put_t([]).status_code == 400, 'cannot save an empty tier list')
r = put_t([{**keep[0], 'name': '  '}] + keep[1:]); check(r.status_code == 400 and 'tiers.0.name' in r.get_json()['fields'], 'blank name refused')
r = put_t([{**keep[0], 'name': 'BUENO'}] + keep[1:]); check(r.status_code == 400 and 'tiers.7.name' in r.get_json()['fields'], 'duplicate name (any case) refused')
r = put_t([t for t in keep if t['id'] != fg['id']]); check(r.status_code == 400 and 'Flawed Gem' in r.get_json()['fields']['tiers'], 'cannot delete a tier that has reviews: ' + str(r.get_json()))
check(put_t(keep + [{'id': 9999, 'name': 'Ghost', 'description': ''}]).status_code == 409, 'unknown tier id refused')
# rename (cascades to the game), edit text, move the first tier to the end, add one, drop an unused one
new = [dict(t) for t in keep if t['id'] != mp['id']]
for t in new:
    if t['id'] == fg['id']: t.update(name='Cracked Gem', description='Edited text.')
new = new[1:] + new[:1] + [{'id': None, 'name': 'Brand  New', 'description': 'Fresh.'}]
r = put_t(new); j = r.get_json(); check(r.status_code == 200 and j['renamed'] == {'Flawed Gem': 'Cracked Gem'}, 'save tier edits: ' + str(j)); tb = r.headers['X-Batch']
tl2 = get('/api/tiers').get_json()
check([t['name'] for t in tl2] == [t['name'] for t in new[:-1]] + ['Brand New'] and [t['rank'] for t in tl2] == list(range(1, 12)), 'order, new tier (spaces tidied) and delete applied: ' + str([t['name'] for t in tl2]))
check(next(t for t in tl2 if t['name'] == 'Cracked Gem')['description'] == 'Edited text.', 'description saved')
check(get(f'/api/games/{rg}').get_json()['game']['tier'] == 'Cracked Gem', 'rename cascaded to the game')
check([t['name'] for t in get('/api/meta').get_json()['tiers']] == [t['name'] for t in tl2], 'meta tiers follow the edit')
_c = schema.connect(A.DB)
try: pg_tiers = [t['name'] for t in RVM.gather(_c, A.COVERS, A.REVIEW_IMAGES)['tiers']]
finally: _c.close()
check('Cracked Gem' in pg_tiers and 'Flawed Gem' not in pg_tiers and pg_tiers[-1] == 'Brand New', 'reviews page data uses the new tier names and order')
check(post(f'/api/undo/{tb}').status_code == 200 and [t['name'] for t in get('/api/tiers').get_json()] == orig, 'one undo restores names, order and the deleted tier')
check(get(f'/api/games/{rg}').get_json()['game']['tier'] == 'Flawed Gem', 'undo cascaded the name back to the game')
# swapping two names needs the temporary-name path
a, b = keep[3], keep[4]
sw = [dict(t) for t in keep]; sw[3] = {**a, 'name': b['name']}; sw[4] = {**b, 'name': a['name']}
r = put_t(sw); check(r.status_code == 200 and [t['name'] for t in get('/api/tiers').get_json()][3:5] == [b['name'], a['name']], 'swap two tier names: ' + str(r.get_json()))
check(post(f'/api/undo/{r.headers["X-Batch"]}').status_code == 200 and [t['name'] for t in get('/api/tiers').get_json()] == orig, 'undo of the swap')
# --- refs, backup, export
check(post('/api/ref/system', {'name': 'Steam Deck', 'type': 'Handheld'}).status_code == 200 and 'Steam Deck' in [s['name'] for s in get('/api/meta').get_json()['systems']], 'add a new system')
check(post('/api/ref/system', {'name': 'steam deck', 'type': 'PC'}).status_code == 409, 'duplicate system (any case) rejected')
check(os.path.exists(post('/api/backup').get_json()['path']), 'backup created')
z = zipfile.ZipFile(io.BytesIO(get('/api/export.zip').data)); check(set(z.namelist()) == {'games.csv', 'releases.csv', 'play_log.csv', 'top_rank.csv', 'halo_levels.csv', 'tww_lords.csv', 'tww_campaigns.csv', 'reviews.csv', 'ref_tier.csv'}, 'export zip')
check(len(z.read('play_log.csv').decode().splitlines()) == counts()['play_log'] + 1, 'export has every log row plus header')
print(f'ALL {ok} API CHECKS PASSED')
shutil.rmtree(tmp)
