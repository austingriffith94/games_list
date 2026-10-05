"""End-to-end UI test: runs the real server on a scratch copy of the data and drives it with a headless browser."""
import os, sys, shutil, sqlite3, subprocess, tempfile, time, json, urllib.request, urllib.error
from urllib.parse import quote
from playwright.sync_api import sync_playwright
SC = os.path.join(tempfile.gettempdir(), 'games_list_e2e') + os.sep   # screenshots go here, not the repo
os.makedirs(SC, exist_ok=True)
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'covers') + os.sep   # real cover art as upload fixtures
tmp = tempfile.mkdtemp(); db = os.path.join(tmp, 't.db'); cov = os.path.join(tmp, 'covers'); out = os.path.join(tmp, 'out')
os.makedirs(cov); os.makedirs(out); shutil.copy('gamelist.db', db)
_seed = sqlite3.connect(db)   # re-seed the two out-of-range scores the Checks flow below fixes through the UI,
try:                           # since the real production data got fixed for real; `with` only commits, doesn't close
    _seed.execute("UPDATE games SET ign=84 WHERE title='WRC 8'")
    _seed.execute("UPDATE games SET gamespot=80 WHERE title='Overwatch 2'")
    _seed.commit()
finally:
    _seed.close()
env = dict(os.environ, GAMELIST_DB=db, GAMELIST_COVERS=cov, GAMELIST_OUT=out, GAMELIST_BACKUPS=os.path.join(tmp, 'bk'))
PORT = 8799; URL = f'http://127.0.0.1:{PORT}'
srvlog = open(os.path.join(tmp, 'server.log'), 'w')   # a pipe here deadlocks the whole server once Werkzeug's
# per-request logging fills Windows' small (4KB) anonymous-pipe buffer and nobody drains it; a file never blocks
srv = subprocess.Popen([sys.executable, 'app.py', '--db', db, '--covers', cov, '--port', str(PORT), '--no-browser'], env=env, stdout=srvlog, stderr=subprocess.STDOUT)
for _ in range(50):
    try: urllib.request.urlopen(URL + '/api/meta'); break
    except Exception: time.sleep(.2)
def api(path, method='GET', body=None):
    req = urllib.request.Request(URL + quote(path, safe='/?&=:%'), method=method, headers={'X-Requested-With': 'gamelist', 'Content-Type': 'application/json'}, data=json.dumps(body).encode() if body is not None else None)
    try: return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e: return {'_status': e.code, **json.loads(e.read() or b'{}')}
n = 0
def ok(c, m):
    global n; assert c, 'FAILED: ' + m; n += 1
errors = []
try:
  with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1280, 'height': 900})   # use the browser `playwright install` set up
    pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' and 'favicon' not in m.text else None)
    pg.on('pageerror', lambda e: errors.append('PAGEERROR ' + str(e)))
    bad = []
    pg.on('response', lambda r: bad.append(f'{r.status} {r.request.method} {r.url.replace(URL, "")[:70]}') if r.status >= 400 else None)
    def toast(text, timeout=20000): pg.wait_for_selector(f'.toast:has-text("{text}")', timeout=timeout)   # Windows + headless Chromium can take several seconds per concurrent XHR burst against the dev server; 8s was too tight
    pg.goto(URL + '/'); pg.wait_for_selector('#logform'); pg.wait_for_function("document.querySelector('[name=date]').value")
    today = api('/api/meta')['today']; ok(pg.input_value('[name=date]') == today, 'date defaults to today')

    # ---- LOG TIME
    pg.fill('[name=game]', 'Halo 2'); pg.wait_for_selector('#logpreview .preview'); ok(pg.locator('[name=system] option').count() >= 1, 'system options load for the game')
    sysname = pg.input_value('[name=system]'); ok(sysname in api('/api/meta')['releases']['Halo 2'], 'a valid system is preselected: ' + sysname)
    pg.click('#hourchips button[data-h="1"]'); pg.wait_for_selector('#logpreview:has-text("after this entry")'); pg.click('#logsave'); toast('Logged 1 h')
    r = api('/api/log?game=Halo 2&limit=1')['rows'][0]; ok(r['date'] == today and r['hours'] == 1, 'entry saved via UI')
    ok(pg.input_value('[name=game]') == '' and pg.input_value('[name=date]') == today, 'form clears game but keeps the date')
    pg.fill('[name=game]', 'Halo 2'); pg.fill('[name=hours]', '2'); pg.wait_for_selector('#logexisting:not([hidden])'); ok('Already logged' in pg.inner_text('#logexisting'), 'duplicate banner shown')
    pg.click('#logsave'); toast('Added to'); ok(api('/api/log?game=Halo 2&limit=1')['rows'][0]['hours'] == 3, 'add-to-existing summed the hours')
    pg.click('.toast:has-text("Added to") button:has-text("Undo")'); toast('Undone'); pg.wait_for_timeout(300); ok(api('/api/log?game=Halo 2&limit=1')['rows'][0]['hours'] == 1, 'undo restored previous hours')
    pg.fill('[name=game]', 'Not A Real Game'); pg.fill('[name=hours]', '1'); pg.click('#logsave'); pg.wait_for_selector('[data-f=game] .err:not(:empty)'); ok('Choose a game' in pg.inner_text('[data-f=game] .err'), 'unknown game shows inline error')
    pg.fill('[name=game]', ''); pg.fill('[name=hours]', '')
    pg.click('#recentchips .chip >> nth=0'); pg.wait_for_selector('#logpreview .preview'); ok(pg.input_value('[name=game]') != '', 'recent-game chip fills the form')
    pg.fill('[name=hours]', '0.5'); pg.click('#logsave'); toast('Added to')   # the recent chip reselects the game already logged above, so this adds to it rather than logging fresh
    ok(api('/api/log?limit=1')['rows'][0]['hours'] == 1.5, 'recent-chip entry added to the existing today-entry')
    pg.screenshot(path=SC + 'e2e_log.png', full_page=True)
    pg.click('#logtable button[data-edit] >> nth=0'); pg.wait_for_selector('dialog[open]'); pg.fill('dialog [name=hours]', '2.5'); pg.click('#dok'); toast('Entry updated')
    ok(api('/api/log?limit=1')['rows'][0]['hours'] == 2.5, 'edit entry via dialog')
    rid = api('/api/log?limit=1')['rows'][0]['id']; pg.click('#logtable button[data-del] >> nth=0'); pg.wait_for_selector('dialog[open]'); pg.click('#dok'); toast('Entry deleted')
    ok(api('/api/log?limit=1')['rows'][0]['id'] != rid, 'delete entry via dialog')

    # ---- GAMES: edit + validation + cover
    shutil.copy(S + 'Bioshock.png', os.path.join(cov, 'Bioshock.png'))        # simulates an existing covers folder
    pg.click('nav a[data-k=games]'); pg.wait_for_selector('#glist .it'); pg.fill('#gsearch', 'bioshock'); pg.click('#glist .it:has-text("Bioshock") >> nth=0')
    pg.wait_for_selector('#gform [name=title]'); ok(pg.input_value('#gform [name=title]') == 'Bioshock', 'editor opens the game'); ok(pg.locator('#coverbox img').count() == 1, 'existing cover shown')
    pg.fill('#gform [name=my_score]', '11'); pg.click('#gsave'); pg.wait_for_selector('[data-f=my_score] .err:not(:empty)'); ok('between' in pg.inner_text('[data-f=my_score] .err'), 'score out of range blocked inline')
    pg.fill('#gform [name=my_score]', '9'); pg.fill('#gform [name=playthroughs]', '3'); pg.click('#gsave'); toast('Saved')
    gid = [g for g in api('/api/games') if g['title'] == 'Bioshock'][0]['id']; gg = api(f'/api/games/{gid}')['game']; ok(gg['my_score'] == 9 and gg['playthroughs'] == 3, 'edit saved')
    pg.screenshot(path=SC + 'e2e_games.png', full_page=True)
    pg.fill('#gsearch', 'abzu'); pg.click('#glist .it:has-text("Abzu") >> nth=0'); pg.wait_for_selector('#gform [name=title][value="Abzu"]'); pg.set_input_files('#coverfile', S + 'Abzu.png'); toast('Cover saved')
    ok(os.path.exists(os.path.join(cov, 'Abzu.png')), 'cover uploaded through the UI is stored under the game title'); ok(pg.locator('#coverbox img').count() == 1, 'cover preview refreshed')

    # ---- GAMES: new game
    pg.click('#gnew'); pg.wait_for_selector('#gform [name=title]'); pg.click('#gform button.primary')
    pg.wait_for_selector('[data-f=title] .err:not(:empty)'); ok(all(pg.inner_text(f'#gform [data-f="{f}"] .err') for f in ('title', 'genre', 'graphic_style', 'camera_view', 'releases.0.system', 'releases.0.ownership')), 'empty new-game form shows every missing field')
    pg.fill('#gform [name=title]', 'E2E Test Game: One'); pg.select_option('#gform [name=genre]', 'Role-playing')
    subs = pg.locator('#gform [name=sub_genre] option').all_inner_texts(); ok('Action RPG' in subs and 'FPS' not in subs, 'sub-genre list follows the genre')
    pg.select_option('#gform [name=sub_genre]', 'Action RPG'); pg.select_option('#gform [name=graphic_style]', '3D'); pg.select_option('#gform [name=camera_view]', 'First Person')
    pg.select_option('.relrow [name=system]', 'Steam'); pg.select_option('.relrow [name=ownership]', 'Paid'); pg.fill('.relrow [name=original_release_date]', '2024-05-01')
    ok(pg.input_value('.relrow [name=version_release_date]') == '2024-05-01', 'version date follows original until edited')
    pg.set_input_files('#coverfile', S + 'A Short Hike.jpg'); pg.wait_for_selector('#coverbox img')
    pg.click('#gform button.primary'); toast('Added E2E Test Game: One')
    pg.wait_for_selector('#gform [name=title][value="E2E Test Game: One"]'); ok(os.path.exists(os.path.join(cov, 'E2E Test Game One.jpg')), 'cover chosen on the new-game form was saved (colon removed)')
    ng = [g for g in api('/api/games') if g['title'] == 'E2E Test Game: One'][0]; nid = ng['id']; ok(api(f'/api/games/{nid}')['releases'][0]['system'] == 'Steam', 'game and release created together')
    pg.screenshot(path=SC + 'e2e_editor.png', full_page=True)
    # add / edit / delete release
    pg.click('#raddbtn'); pg.wait_for_selector('dialog[open] [name=system]'); pg.select_option('dialog [name=system]', 'GOG'); pg.select_option('dialog [name=ownership]', 'Free'); pg.fill('dialog [name=original_release_date]', '2024-05-01'); pg.click('#dok'); toast('Release saved')
    ok(len(api(f'/api/games/{nid}')['releases']) == 2, 'release added through dialog')
    pg.click('button[data-redit] >> nth=1'); pg.wait_for_selector('dialog[open] [name=system]'); pg.select_option('dialog [name=ownership]', 'Paid'); pg.click('#dok'); toast('Release saved')
    ok(api(f'/api/games/{nid}')['releases'][1]['ownership'] == 'Paid', 'release edited')
    pg.click('button[data-rdel] >> nth=1'); pg.wait_for_selector('dialog[open]'); pg.click('#dok'); toast('Release deleted'); ok(len(api(f'/api/games/{nid}')['releases']) == 1, 'release deleted')
    # log time from the game page, then force-delete the game
    pg.click('#gtolog'); pg.wait_for_selector('#logpreview .preview'); ok(pg.input_value('[name=game]') == 'E2E Test Game: One', 'log button carries the game over'); pg.fill('[name=hours]', '2'); pg.click('#logsave'); toast('Logged 2 h')
    pg.click('nav a[data-k=games]'); pg.fill('#gsearch', 'E2E Test'); pg.click('#glist .it >> nth=0'); pg.wait_for_selector('#gdel'); pg.click('#gdel'); pg.wait_for_selector('dialog[open]'); pg.click('#dok')
    pg.wait_for_selector('dialog[open]:has-text("Delete everything")'); pg.click('#dok'); toast('Game deleted'); ok(api(f'/api/games/{nid}').get('_status') == 404, 'game with time log deleted after the second confirmation')
    pg.click('.toast:has-text("Game deleted") button:has-text("Undo")'); toast('Undone'); pg.wait_for_timeout(300); ok(api(f'/api/games/{nid}').get('game', {}).get('title') == 'E2E Test Game: One' and len(api(f'/api/log?game=E2E Test Game: One')['rows']) == 1, 'undo brought back the game, release and log entry')

    # ---- TOP LIST
    pg.click('nav a[data-k=top]'); pg.wait_for_selector('#toplist .ord'); first = api('/api/top')[0]['title']; ok(pg.locator('#topsave').is_disabled(), 'save disabled until changed')
    pg.click('#toplist button[data-dn="0"]'); pg.click('#topsave'); toast('Top list saved'); ok(api('/api/top')[1]['title'] == first, 'reorder saved')
    ok(pg.locator('#toplist img').count() >= 1, 'top list shows covers when present'); pg.screenshot(path=SC + 'e2e_top.png', full_page=True)

    # ---- CHECKS: fix the two bad scores through the UI
    pg.click('nav a[data-k=checks]'); pg.wait_for_selector('#checklist table'); ok('2' in pg.inner_text('#checksum'), 'checks show errors'); ok(pg.locator('#chkbadge').is_visible(), 'badge on Checks tab')
    pg.screenshot(path=SC + 'e2e_checks.png', full_page=True)
    for title, field, val in (('WRC 8', 'ign', '8.4'), ('Overwatch 2', 'gamespot', '8')):
        pg.click('nav a[data-k=checks]'); pg.wait_for_selector(f'#checklist tr:has-text("{title}") button'); pg.click(f'#checklist tr:has-text("{title}") button')
        pg.wait_for_selector(f'#gform [name=title][value="{title}"]'); pg.fill(f'#gform [name={field}]', val); pg.click('#gsave'); toast('Saved')
    pg.click('nav a[data-k=checks]'); pg.wait_for_function("document.querySelector('#checksum').innerText.trim().startsWith('0')"); ok(not pg.locator('#chkbadge').is_visible(), 'badge clears once the data is fixed')

    # ---- HISTORY
    pg.click('nav a[data-k=history]'); pg.wait_for_selector('#histtable button[data-undo]'); pg.click('#histtable button[data-undo] >> nth=0'); toast('Undone'); ok(True, 'history undo')
    pg.click('#backupbtn'); toast('Backup saved')

    # ---- REPORTS
    pg.click('nav a[data-k=reports]'); pg.click('#rebuildbtn'); toast('Reports rebuilt', timeout=180000)
    ok(os.path.getsize(os.path.join(out, 'games_list_dashboard.html')) > 1e5 and os.path.getsize(os.path.join(out, 'games_list_report.pdf')) > 1e4, 'dashboard and pdf rebuilt from the app')
    ok(urllib.request.urlopen(URL + '/dashboard').status == 200 and urllib.request.urlopen(URL + '/report.pdf').status == 200, 'served at /dashboard and /report.pdf')
    pg.click('nav a[data-k=log]'); pg.wait_for_selector('#logtable tr')
    pg.screenshot(path=SC + 'e2e_final.png')
    b.close()
  print('HTTP errors seen by the browser (expected: deliberate invalid input):'); [print('   ', x) for x in bad]
  ok(not [e for e in errors if 'Failed to load resource' not in e], 'no JavaScript errors: ' + str(errors))
  print(f'ALL {n} UI CHECKS PASSED')
finally:
    srv.terminate()
    try: srv.wait(timeout=5)
    except Exception: pass
    srvlog.close()
    try: print('\n'.join(l for l in open(srvlog.name).read().splitlines() if 'Traceback' in l or 'Error' in l)[:1500])
    except Exception: pass
    shutil.copytree(out, SC + 'rebuilt', dirs_exist_ok=True) if os.path.exists(out) else None
    shutil.rmtree(tmp, ignore_errors=True)
