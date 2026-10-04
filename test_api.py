"""API tests against a scratch copy of the database (never touches gamelist.db)."""
import os, shutil, tempfile, io, json, zipfile, sqlite3
import app as A

tmp = tempfile.mkdtemp()
A.DB = os.path.join(tmp, 't.db'); A.COVERS = os.path.join(tmp, 'covers'); A.BACKUPS = os.path.join(tmp, 'bk')
A.REPORT_HTML = os.path.join(tmp, 'd.html'); A.REPORT_PDF = os.path.join(tmp, 'r.pdf'); os.makedirs(A.COVERS)
shutil.copy('gamelist.db', A.DB)
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
r = put(f'/api/log/{lid}', {**log, 'hours': 2.25, 'real': True}); check(r.status_code == 200 and get(f'/api/log?game={T}').get_json()['total'] == 3, 'edit log entry')
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
ck = get('/api/checks').get_json(); errs = [i for i in ck['items'] if i['severity'] == 'error']
check({(e['title']) for e in errs} == {'WRC 8', 'Overwatch 2'}, 'checks flag the two out-of-range scores: ' + str([e['title'] for e in errs]))
print('   checks summary:', ck['summary'], {k: sum(1 for i in ck['items'] if i['kind'] == k) for k in {i['kind'] for i in ck['items']}})
# fixing a flagged row through the API works
wrc = [g for g in get('/api/games').get_json() if g['title'] == 'WRC 8'][0]; full = get(f'/api/games/{wrc["id"]}').get_json()['game']
check(put(f'/api/games/{wrc["id"]}', full).status_code == 400, 'saving WRC 8 with IGN=84 is refused')
check(put(f'/api/games/{wrc["id"]}', {**full, 'ign': 8.4}).status_code == 200, 'IGN corrected to 8.4')
# --- refs, backup, export
check(post('/api/ref/system', {'name': 'Steam Deck', 'type': 'Handheld'}).status_code == 200 and 'Steam Deck' in [s['name'] for s in get('/api/meta').get_json()['systems']], 'add a new system')
check(post('/api/ref/system', {'name': 'steam deck', 'type': 'PC'}).status_code == 409, 'duplicate system (any case) rejected')
check(os.path.exists(post('/api/backup').get_json()['path']), 'backup created')
z = zipfile.ZipFile(io.BytesIO(get('/api/export.zip').data)); check(set(z.namelist()) == {'games.csv', 'releases.csv', 'play_log.csv', 'top_rank.csv'}, 'export zip')
check(len(z.read('play_log.csv').decode().splitlines()) == counts()['play_log'] + 1, 'export has every log row plus header')
print(f'ALL {ok} API CHECKS PASSED')
shutil.rmtree(tmp)
