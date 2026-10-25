"""Game list entry app.  Run:  python app.py [--db gamelist.db] [--covers covers] [--port 8765]

A local web app (127.0.0.1 only) for logging time, adding/editing games and releases, writing reviews, checking data
quality, managing cover art and rebuilding the dashboard, PDF and reviews page.  Replaces the workbook's
Control/TimeControl sheets and macros.
"""
import argparse, csv, datetime as dt, glob, io, json, os, re, shutil, sqlite3, subprocess, sys, threading, uuid, webbrowser, zipfile
from urllib.parse import quote
from flask import Flask, Response, g as G, jsonify, request, send_file, send_from_directory
from PIL import Image
import halo
import reviews as RV
import schema

BASE = os.path.dirname(os.path.abspath(__file__))


def load_config():
    """Per-machine settings from config.json next to app.py (optional, gitignored)."""
    try:
        with open(os.path.join(BASE, 'config.json'), encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        print(f'WARNING: ignoring config.json ({e})', file=sys.stderr)
        return {}


CONFIG = load_config()
# precedence: --flag > environment variable > config.json > default next to app.py
DB = os.environ.get('GAMELIST_DB') or CONFIG.get('db') or os.path.join(BASE, 'gamelist.db')
COVERS = os.environ.get('GAMELIST_COVERS') or CONFIG.get('covers') or os.path.join(BASE, 'covers')
REVIEW_IMAGES = os.environ.get('GAMELIST_REVIEW_IMAGES') or CONFIG.get('review_images') or os.path.join(BASE, 'review_images')
BACKUPS = os.environ.get('GAMELIST_BACKUPS', os.path.join(BASE, 'backups'))
OUT = os.environ.get('GAMELIST_OUT', BASE)
REPORT_HTML = os.path.join(OUT, 'games_list_dashboard.html')
REPORT_PDF = os.path.join(OUT, 'games_list_report.pdf')
REPORT_REVIEWS = os.path.join(OUT, 'games_list_reviews.html')

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024

SCORES = {'my_score': (1, 10, True), 'metacritic': (0, 100, False), 'pc_gamer': (0, 100, False),
          'gamespot': (0, 10, False), 'ign': (0, 10, False), 'destructoid': (0, 10, False), 'game_informer': (0, 10, False)}
MODES = ['singleplayer', 'local_co_op', 'online_co_op', 'local_multiplayer', 'online_multiplayer']
COVER_EXTS = ('.jpg', '.jpeg', '.png', '.webp')
REF_TABLES = {'genre': 'ref_genre', 'view': 'ref_view', 'style': 'ref_style', 'ownership': 'ref_ownership',
              'release_type': 'ref_release_type', 'zp': 'ref_zp'}


# ----------------------------------------------------------------------------- plumbing
class ApiError(Exception):
    def __init__(self, message, status=400, fields=None, **extra):
        self.message, self.status, self.fields, self.extra = message, status, fields or {}, extra


def con():
    if 'db' not in G:
        G.db = schema.connect(DB)
        G.batch = uuid.uuid4().hex
    return G.db


@app.teardown_appcontext
def _close(_):
    db = G.pop('db', None)
    if db is not None:
        db.close()


@app.before_request
def _guard():
    host = (request.host or '').split(':')[0]
    if host not in ('127.0.0.1', 'localhost', '[::1]'):
        return jsonify(error='Forbidden host'), 403          # blocks DNS-rebinding
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.headers.get('X-Requested-With') != 'gamelist':
        return jsonify(error='Missing X-Requested-With header'), 403   # blocks cross-site form posts


@app.after_request
def _commit(resp):
    db = G.get('db')
    if db is not None:
        (db.commit if resp.status_code < 400 else db.rollback)()
        if request.method not in ('GET', 'HEAD') and resp.status_code < 400:
            resp.headers['X-Batch'] = G.batch          # lets the UI offer "Undo" for the change it just made
    return resp


@app.errorhandler(ApiError)
def _api_error(e):
    return jsonify(error=e.message, fields=e.fields, **e.extra), e.status


@app.errorhandler(sqlite3.IntegrityError)
def _integrity(e):
    msg = str(e)
    if 'UNIQUE' in msg: msg = 'That would create a duplicate entry.'
    elif 'FOREIGN KEY' in msg: msg = 'That change conflicts with related data (e.g. a game/system that does not exist, or one still in use).'
    return jsonify(error=msg, fields={}), 409


@app.errorhandler(413)
def _too_big(_):
    return jsonify(error='File too large (limit 20 MB).'), 413


def today():
    return dt.date.today()


def rows(sql, args=()):
    return [dict(r) for r in con().execute(sql, args)]


def one(sql, args=()):
    r = con().execute(sql, args).fetchone()
    return dict(r) if r else None


def scalar(sql, args=()):
    r = con().execute(sql, args).fetchone()
    return r[0] if r else None


# ----------------------------------------------------------------------------- audit / undo
def _audit(action, tbl, rid, old, new, summary):
    con().execute('INSERT INTO audit(batch,action,tbl,row_id,old,new,summary) VALUES (?,?,?,?,?,?,?)',
                  (G.batch, action, tbl, rid, None if old is None else json.dumps(old),
                   None if new is None else json.dumps(new), summary))


def get_row(tbl, rid):
    return one(f'SELECT * FROM {tbl} WHERE id=?', (rid,))


def insert_row(tbl, data, summary):
    cols = list(data)
    cur = con().execute(f'INSERT INTO {tbl}({",".join(cols)}) VALUES ({",".join("?" * len(cols))})', [data[c] for c in cols])
    _audit('insert', tbl, cur.lastrowid, None, get_row(tbl, cur.lastrowid), summary)
    return cur.lastrowid


def update_row(tbl, rid, data, summary):
    old = get_row(tbl, rid)
    con().execute(f'UPDATE {tbl} SET {",".join(c + "=?" for c in data)} WHERE id=?', [*data.values(), rid])
    _audit('update', tbl, rid, old, get_row(tbl, rid), summary)


def delete_row(tbl, rid, summary):
    old = get_row(tbl, rid)
    con().execute(f'DELETE FROM {tbl} WHERE id=?', (rid,))
    _audit('delete', tbl, rid, old, None, summary)


# ----------------------------------------------------------------------------- reference data
def refs():
    r = {k: [x['name'] for x in rows(f'SELECT name FROM {t} ORDER BY rowid')] for k, t in REF_TABLES.items()}
    r['systems'] = rows('SELECT name, type FROM ref_system ORDER BY rowid')
    sub = {}
    for x in rows('SELECT genre, name FROM ref_subgenre ORDER BY rowid'):
        sub.setdefault(x['genre'], []).append(x['name'])
    r['subgenres'] = sub
    return r


def canon(value, options):
    for o in options:
        if o.lower() == str(value).strip().lower():
            return o
    return None


def cover_base(title):
    return re.sub(r'[<>:"/\\|?*]', '', title).strip()          # same rule as the workbook (colons removed)


def cover_file(title):
    base = os.path.join(COVERS, cover_base(title))
    for ext in COVER_EXTS:
        if os.path.exists(base + ext):
            return base + ext
    return None


def cover_url(title):
    f = cover_file(title)
    return '/covers/' + quote(os.path.basename(f)) + f'?v={int(os.path.getmtime(f))}' if f else None


# ----------------------------------------------------------------------------- validation
def _num(v, name, errs, lo=None, hi=None, integer=False, gt=None):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        errs[name] = 'Must be a number'; return None
    if integer and x != int(x):
        errs[name] = 'Must be a whole number'; return None
    if lo is not None and x < lo or hi is not None and x > hi:
        errs[name] = f'Must be between {lo} and {hi}'; return None
    if gt is not None and x <= gt:
        errs[name] = f'Must be greater than {gt}'; return None
    return int(x) if x == int(x) else round(x, 2)


def _bool(v):
    return 1 if v in (True, 1, '1', 'true', 'True', 'on') else 0


def _date(v, name, errs, allow_future=True):
    try:
        d = dt.date.fromisoformat(str(v)[:10])
        if not allow_future and d > today():
            errs[name] = 'Date is in the future'
        return d.isoformat()
    except (TypeError, ValueError):
        errs[name] = 'Enter a valid date (YYYY-MM-DD)'
        return None


def clean_game(d, gid=None):
    R, errs, out = refs(), {}, {}
    title = (d.get('title') or '').strip()
    if not title: errs['title'] = 'Title is required'
    elif len(title) > 200: errs['title'] = 'Title is too long'
    elif scalar('SELECT 1 FROM games WHERE title=? AND id IS NOT ?', (title, gid)):
        errs['title'] = 'A game with this title already exists (titles ignore upper/lower case)'
    out['title'] = title
    out['series'] = (d.get('series') or '').strip() or title
    for key, ref, label in (('graphic_style', 'style', 'Graphic style'), ('camera_view', 'view', 'Camera view'), ('genre', 'genre', 'Genre')):
        v = canon(d.get(key) or '', R[ref])
        if v is None: errs[key] = f'{label} is required'
        out[key] = v
    subs = R['subgenres'].get(out['genre'] or '', [])
    sg = d.get('sub_genre')
    if subs:
        v = canon(sg or '', subs)
        if v is None: errs['sub_genre'] = 'Choose a sub-genre for this genre'
        out['sub_genre'] = v
    else:
        out['sub_genre'] = None
    for m in MODES:
        out[m] = 1 if _bool(d.get(m)) else None
    if not any(out[m] for m in MODES): errs['modes'] = 'Select at least one mode'
    for k, (lo, hi, integer) in SCORES.items():
        out[k] = _num(d.get(k), k, errs, lo, hi, integer)
    zp = d.get('zero_punctuation')
    out['zero_punctuation'] = canon(zp, R['zp']) if zp not in (None, '') else None
    if zp not in (None, '') and out['zero_punctuation'] is None: errs['zero_punctuation'] = 'Unknown opinion'
    out['goty_votes'] = _num(d.get('goty_votes'), 'goty_votes', errs, 0, None, True)
    out['playthroughs'] = _num(d.get('playthroughs'), 'playthroughs', errs, 0, 99, True)
    out['average_playthrough'] = _num(d.get('average_playthrough'), 'average_playthrough', errs, None, 1000, False, gt=0)
    out['wikipedia_goat'] = _bool(d.get('wikipedia_goat'))
    out['soundtrack_owned'] = _bool(d.get('soundtrack_owned'))
    return out, errs


def clean_release(d, title, rid=None, prefix=''):
    R, errs, out = refs(), {}, {'title': title}
    for key, ref, label in (('release', 'release_type', 'Release type'), ('ownership', 'ownership', 'Ownership')):
        v = canon(d.get(key) or '', R[ref])
        if v is None: errs[prefix + key] = f'{label} is required'
        out[key] = v
    v = canon(d.get('system') or '', [s['name'] for s in R['systems']])
    if v is None: errs[prefix + 'system'] = 'Choose a system'
    elif title and scalar('SELECT 1 FROM releases WHERE title=? AND system=? AND id IS NOT ?', (title, v, rid)):
        errs[prefix + 'system'] = f'{title} already has a release on {v}'
    out['system'] = v
    for key in ('original_release_date', 'version_release_date', 'added_date'):
        e2 = {}
        out[key] = _date(d.get(key), key, e2)
        errs.update({prefix + k: m for k, m in e2.items()})
    return out, errs


def release_warnings(rel, first_played=None):
    """The workbook's 'Date Check' as warnings (non-blocking)."""
    w = []
    if rel['release'] == 'Demo' or not all(rel.get(k) for k in ('version_release_date', 'added_date')):
        return w
    if rel['version_release_date'] > rel['added_date']:
        w.append('Added date is before the version release date')
    if first_played and first_played < rel['version_release_date']:
        w.append('First played before the version release date')
    if first_played and rel['added_date'] > first_played:
        w.append('Added date is after the first played date')
    return w


def raise_if(errs):
    if errs:
        raise ApiError('Please fix the highlighted fields.', 400, errs)


def find_game(title):
    return one('SELECT * FROM games WHERE title=?', ((title or '').strip(),))


def game_total(title):
    return round(scalar('SELECT COALESCE(SUM(hours),0) FROM play_log WHERE game=?', (title,)) or 0, 4)


# ----------------------------------------------------------------------------- pages / static
@app.get('/')
def index():
    return send_from_directory(os.path.join(BASE, 'static'), 'app.html')


@app.get('/covers/<path:name>')
def covers(name):
    return send_from_directory(COVERS, name, max_age=0)


@app.get('/dashboard')
def dashboard():
    if not os.path.exists(REPORT_HTML): raise ApiError('Dashboard not built yet - use Rebuild reports.', 404)
    return send_file(REPORT_HTML, max_age=0)


@app.get('/report.pdf')
def report_pdf():
    if not os.path.exists(REPORT_PDF): raise ApiError('PDF not built yet - use Rebuild reports.', 404)
    return send_file(REPORT_PDF, max_age=0, mimetype='application/pdf')


@app.get('/reviews')
def reviews_page():
    if not os.path.exists(REPORT_REVIEWS): raise ApiError('Reviews page not built yet - use Build reviews page.', 404)
    return send_file(REPORT_REVIEWS, max_age=0)


@app.get('/review-images/<path:name>')
def review_images(name):
    return send_from_directory(REVIEW_IMAGES, name, max_age=0)


# ----------------------------------------------------------------------------- meta
@app.get('/api/meta')
def meta():
    R = refs()
    releases = {}
    for r in rows('SELECT title, system FROM releases ORDER BY title, rowid'):
        releases.setdefault(r['title'], []).append(r['system'])
    R.update(today=today().isoformat(),
             titles=rows('SELECT id, title, series FROM games ORDER BY title COLLATE NOCASE'),
             series=[x['series'] for x in rows('SELECT DISTINCT series FROM games ORDER BY series COLLATE NOCASE')],
             releases=releases, score_ranges={k: v[:2] for k, v in SCORES.items()}, covers_dir=COVERS,
             tiers=RV.tiers(con()),
             covers={t: cover_url(t) for t in releases if cover_file(t)},
             counts=dict(games=scalar('SELECT COUNT(*) FROM games'), releases=scalar('SELECT COUNT(*) FROM releases'),
                         log=scalar('SELECT COUNT(*) FROM play_log')))
    return jsonify(R)


@app.post('/api/ref/<kind>')
def add_ref(kind):
    d = request.get_json(force=True)
    name = (d.get('name') or '').strip()
    if not name: raise ApiError('Name is required', 400, {'name': 'Name is required'})
    if kind in REF_TABLES:
        con().execute(f'INSERT INTO {REF_TABLES[kind]}(name) VALUES (?)', (name,))
    elif kind == 'subgenre':
        g = canon(d.get('genre') or '', [x['name'] for x in rows('SELECT name FROM ref_genre')])
        if not g: raise ApiError('Choose a genre', 400, {'genre': 'Choose a genre'})
        con().execute('INSERT INTO ref_subgenre(genre,name) VALUES (?,?)', (g, name))
    elif kind == 'system':
        typ = (d.get('type') or '').strip()
        if typ not in ('Console', 'PC', 'Handheld', 'Mobile') and not typ:
            raise ApiError('Choose a system type', 400, {'type': 'Choose a type'})
        con().execute('INSERT INTO ref_system(name,type) VALUES (?,?)', (name, typ))
    else:
        raise ApiError('Unknown list', 404)
    return jsonify(ok=True)


# ----------------------------------------------------------------------------- games
@app.get('/api/games')
def list_games():
    out = rows('''SELECT g.id, g.title, g.series, g.genre, g.sub_genre, g.camera_view, g.my_score, g.metacritic, g.wikipedia_goat,
        (SELECT group_concat(system, ', ') FROM releases r WHERE r.title=g.title) AS systems,
        (SELECT round(SUM(hours),2) FROM play_log l WHERE l.game=g.title) AS hours,
        (SELECT MAX(date) FROM play_log l WHERE l.game=g.title) AS last_played
        FROM games g ORDER BY g.title COLLATE NOCASE''')
    have = {os.path.splitext(f)[0].lower(): f for f in os.listdir(COVERS)} if os.path.isdir(COVERS) else {}
    extra = {r['title']: r for r in rows('SELECT title, MIN(substr(original_release_date,1,4)) AS year FROM releases GROUP BY title')}
    for g in out:
        f = have.get(cover_base(g['title']).lower())
        g['has_cover'] = bool(f)
        g['cover'] = '/covers/' + quote(f) if f else None
        g['year'] = (extra.get(g['title']) or {}).get('year')
    return jsonify(out)


@app.get('/api/games/<int:gid>/timeline')
def game_timeline(gid):
    game = get_row('games', gid)
    if not game: raise ApiError('Game not found', 404)
    by_month = rows('''SELECT substr(date,1,7) AS month, round(SUM(hours),2) AS hours, COUNT(DISTINCT date) AS days
                       FROM play_log WHERE game=? GROUP BY month ORDER BY month''', (game['title'],))
    by_system = rows('SELECT system, round(SUM(hours),2) AS hours FROM play_log WHERE game=? GROUP BY system ORDER BY 2 DESC', (game['title'],))
    return jsonify(by_month=by_month, by_system=by_system, total=game_total(game['title']),
                   first=scalar('SELECT MIN(date) FROM play_log WHERE game=?', (game['title'],)),
                   last=scalar('SELECT MAX(date) FROM play_log WHERE game=?', (game['title'],)))


@app.get('/api/stats')
def stats():
    yr = request.args.get('year')
    w, a = (' WHERE substr(date,1,4)=?', (yr,)) if yr else ('', ())
    tot = one(f'SELECT round(COALESCE(SUM(hours),0),1) AS hours, COUNT(DISTINCT game) AS games, COUNT(DISTINCT date) AS days FROM play_log{w}', a)
    sys_type = {r['name']: r['type'] for r in rows('SELECT name, type FROM ref_system')}
    return jsonify(
        total=tot,
        years=rows('''SELECT substr(date,1,4) AS year, round(SUM(hours),1) AS hours, COUNT(DISTINCT game) AS games, COUNT(DISTINCT date) AS days
                      FROM play_log GROUP BY year ORDER BY year'''),
        systems=rows(f'SELECT system AS name, round(SUM(hours),1) AS hours, COUNT(DISTINCT game) AS games FROM play_log{w} GROUP BY system ORDER BY 2 DESC', a),
        genres=rows(f'''SELECT g.genre AS name, round(SUM(l.hours),1) AS hours, COUNT(DISTINCT l.game) AS games
                        FROM play_log l JOIN games g ON g.title=l.game{w.replace('date', 'l.date')} GROUP BY g.genre ORDER BY 2 DESC''', a),
        top_games=rows(f'SELECT game AS name, round(SUM(hours),1) AS hours FROM play_log{w} GROUP BY game ORDER BY 2 DESC LIMIT 15', a),
        months=rows(f'''SELECT substr(date,1,7) AS month, round(SUM(hours),1) AS hours FROM play_log{w} GROUP BY month ORDER BY month''', a),
        new_games=rows('''SELECT substr(f,1,4) AS year, COUNT(*) AS n FROM (SELECT MIN(date) AS f FROM play_log GROUP BY game) GROUP BY year ORDER BY year'''),
        system_types={k: v for k, v in sys_type.items()})


@app.get('/api/games/<int:gid>')
def get_game(gid):
    game = get_row('games', gid)
    if not game: raise ApiError('Game not found', 404)
    rel = rows('''SELECT r.*, (SELECT round(SUM(hours),2) FROM play_log l WHERE l.game=r.title AND l.system=r.system) AS hours,
        (SELECT MIN(date) FROM play_log l WHERE l.game=r.title AND l.system=r.system) AS first_played,
        (SELECT MAX(date) FROM play_log l WHERE l.game=r.title AND l.system=r.system) AS last_played
        FROM releases r WHERE r.title=? ORDER BY r.id''', (game['title'],))
    for r in rel: r['warnings'] = release_warnings(r, r['first_played'])
    log = rows('SELECT * FROM play_log WHERE game=? ORDER BY date DESC LIMIT 15', (game['title'],))
    return jsonify(game=game, releases=rel, log=log, total_hours=game_total(game['title']), cover=cover_url(game['title']),
                   in_top=scalar('SELECT rank FROM top_rank WHERE title=?', (game['title'],)),
                   review=one('SELECT id, status FROM reviews WHERE title=?', (game['title'],)))


@app.post('/api/games')
def create_game():
    d = request.get_json(force=True)
    game, errs = clean_game(d.get('game') or {})
    rels = d.get('releases') or []
    if not rels: errs['releases'] = 'Add at least one release (system and dates)'
    clean_rels, seen = [], set()
    for i, r in enumerate(rels):
        cr, e = clean_release(r, game['title'], prefix=f'releases.{i}.')
        if cr['system'] in seen: e[f'releases.{i}.system'] = 'Duplicate system in this entry'
        seen.add(cr['system']); errs.update(e); clean_rels.append(cr)
    raise_if(errs)
    gid = insert_row('games', game, f'Added game {game["title"]}')
    for cr in clean_rels:
        insert_row('releases', cr, f'Added release {game["title"]} ({cr["system"]})')
    return jsonify(id=gid, title=game['title']), 201


@app.put('/api/games/<int:gid>')
def update_game(gid):
    old = get_row('games', gid)
    if not old: raise ApiError('Game not found', 404)
    game, errs = clean_game(request.get_json(force=True), gid)
    raise_if(errs)
    update_row('games', gid, game, f'Edited game {game["title"]}')
    if game['title'] != old['title']:                        # keep cover art attached to the renamed game
        for ext in COVER_EXTS:
            src = os.path.join(COVERS, cover_base(old['title']) + ext)
            if os.path.exists(src):
                os.replace(src, os.path.join(COVERS, cover_base(game['title']) + ext))
    return jsonify(id=gid, title=game['title'])


@app.delete('/api/games/<int:gid>')
def delete_game(gid):
    game = get_row('games', gid)
    if not game: raise ApiError('Game not found', 404)
    if scalar('SELECT 1 FROM reviews WHERE title=?', (game['title'],)):
        raise ApiError(f'{game["title"]} has a review. Delete the review first (Reviews tab) if you really want to remove the game.', 409)
    n_rel = scalar('SELECT COUNT(*) FROM releases WHERE title=?', (game['title'],))
    n_log = scalar('SELECT COUNT(*) FROM play_log WHERE game=?', (game['title'],))
    if (n_rel or n_log) and request.args.get('force') != '1':
        raise ApiError(f'{game["title"]} still has {n_rel} release(s) and {n_log} time log entr{"y" if n_log == 1 else "ies"}.', 409,
                       needs_force=True, releases=n_rel, log=n_log, hours=game_total(game['title']))
    for r in rows('SELECT id, system FROM play_log WHERE game=?', (game['title'],)):
        delete_row('play_log', r['id'], f'Deleted log entry for {game["title"]}')
    for r in rows('SELECT id, system FROM releases WHERE title=?', (game['title'],)):
        delete_row('releases', r['id'], f'Deleted release {game["title"]} ({r["system"]})')
    delete_row('games', gid, f'Deleted game {game["title"]}')
    return jsonify(ok=True)


# ----------------------------------------------------------------------------- releases
@app.post('/api/games/<int:gid>/releases')
def add_release(gid):
    game = get_row('games', gid)
    if not game: raise ApiError('Game not found', 404)
    rel, errs = clean_release(request.get_json(force=True), game['title'])
    raise_if(errs)
    rid = insert_row('releases', rel, f'Added release {game["title"]} ({rel["system"]})')
    return jsonify(id=rid, warnings=release_warnings(rel)), 201


@app.put('/api/releases/<int:rid>')
def update_release(rid):
    old = get_row('releases', rid)
    if not old: raise ApiError('Release not found', 404)
    rel, errs = clean_release(request.get_json(force=True), old['title'], rid)
    raise_if(errs)
    update_row('releases', rid, rel, f'Edited release {old["title"]} ({rel["system"]})')
    fp = scalar('SELECT MIN(date) FROM play_log WHERE game=? AND system=?', (old['title'], rel['system']))
    return jsonify(id=rid, warnings=release_warnings(rel, fp))


@app.delete('/api/releases/<int:rid>')
def delete_release(rid):
    rel = get_row('releases', rid)
    if not rel: raise ApiError('Release not found', 404)
    n_log = scalar('SELECT COUNT(*) FROM play_log WHERE game=? AND system=?', (rel['title'], rel['system']))
    if n_log and request.args.get('force') != '1':
        hrs = scalar('SELECT round(SUM(hours),2) FROM play_log WHERE game=? AND system=?', (rel['title'], rel['system']))
        raise ApiError(f'{rel["title"]} on {rel["system"]} has {n_log} time log entries ({hrs} h).', 409, needs_force=True, log=n_log, hours=hrs)
    for r in rows('SELECT id FROM play_log WHERE game=? AND system=?', (rel['title'], rel['system'])):
        delete_row('play_log', r['id'], f'Deleted log entry for {rel["title"]}')
    delete_row('releases', rid, f'Deleted release {rel["title"]} ({rel["system"]})')
    return jsonify(ok=True)


# ----------------------------------------------------------------------------- time log
def clean_log(d, lid=None):
    errs = {}
    out = {}
    out['date'] = _date(d.get('date'), 'date', errs, allow_future=False)
    game = find_game(d.get('game'))
    if not game: errs['game'] = 'Choose a game from the list'
    else: out['game'] = game['title']
    sys_names = [r['system'] for r in rows('SELECT system FROM releases WHERE title=?', (out.get('game'),))] if game else []
    s = canon(d.get('system') or '', sys_names)
    if game and s is None:
        errs['system'] = f'{game["title"]} has no release on {d.get("system") or "that system"} - add the release first'
    out['system'] = s
    hrs = _num(d.get('hours'), 'hours', errs, gt=0)
    if hrs is None and 'hours' not in errs: errs['hours'] = 'Enter the hours played'
    out['hours'] = hrs
    return out, errs


def _log_label(e):
    return f'{e["hours"]:g} h {e["game"]} ({e["system"]}) on {e["date"]}'


@app.get('/api/log')
def list_log():
    q, args = 'SELECT * FROM play_log', []
    where = []
    if request.args.get('game'): where.append('game=?'); args.append(request.args['game'])
    if request.args.get('system'): where.append('system=?'); args.append(request.args['system'])
    if request.args.get('from'): where.append('date>=?'); args.append(request.args['from'])
    if request.args.get('to'): where.append('date<=?'); args.append(request.args['to'])
    if where: q += ' WHERE ' + ' AND '.join(where)
    limit = min(int(request.args.get('limit', 100)), 5000)
    out = rows(q + ' ORDER BY date DESC, id DESC LIMIT ? OFFSET ?', (*args, limit, int(request.args.get('offset', 0))))
    total = scalar('SELECT COUNT(*) FROM play_log' + (' WHERE ' + ' AND '.join(where) if where else ''), args)
    return jsonify(rows=out, total=total)


@app.get('/api/log/preview')
def log_preview():
    game = find_game(request.args.get('game'))
    if not game: return jsonify(game_total=None)
    system, date = request.args.get('system'), request.args.get('date')
    ex = one('SELECT id, hours FROM play_log WHERE game=? AND system=? AND date=?', (game['title'], system, date))
    return jsonify(title=game['title'], game_total=game_total(game['title']), existing=ex,
                   release_total=round(scalar('SELECT COALESCE(SUM(hours),0) FROM play_log WHERE game=? AND system=?', (game['title'], system)) or 0, 4),
                   last_played=scalar('SELECT MAX(date) FROM play_log WHERE game=?', (game['title'],)),
                   last_system=scalar('SELECT system FROM play_log WHERE game=? ORDER BY date DESC, id DESC LIMIT 1', (game['title'],)),
                   cover=cover_url(game['title']), systems=[r['system'] for r in rows('SELECT system FROM releases WHERE title=? ORDER BY id', (game['title'],))])


@app.post('/api/log')
def add_log():
    d = request.get_json(force=True)
    e, errs = clean_log(d)
    raise_if(errs)
    if e['hours'] > 24 and not d.get('allow_large'):
        raise ApiError(f'{e["hours"]:g} hours is more than a day. If this is a backfilled total, confirm to save it anyway.', 409,
                       {'hours': 'More than 24 hours'}, needs_confirm='large')
    before = game_total(e['game'])
    ex = one('SELECT * FROM play_log WHERE date=? AND game=? AND system=?', (e['date'], e['game'], e['system']))
    mode = d.get('mode')
    if ex and mode not in ('add', 'overwrite'):
        raise ApiError(f'You already logged {ex["hours"]:g} h for this game, system and date.', 409, existing=ex, needs_confirm='exists')
    if ex:
        new_hours = round(ex['hours'] + e['hours'], 4) if mode == 'add' else e['hours']
        update_row('play_log', ex['id'], {'hours': new_hours}, f'{"Added to" if mode == "add" else "Overwrote"} log: {_log_label({**e, "hours": new_hours})}')
        lid, action, e['hours'] = ex['id'], mode, new_hours
    else:
        lid, action = insert_row('play_log', e, f'Logged {_log_label(e)}'), 'new'
    return jsonify(id=lid, action=action, hours=e['hours'], game=e['game'], game_total_before=before, game_total_after=game_total(e['game'])), 201


@app.put('/api/log/<int:lid>')
def update_log(lid):
    old = get_row('play_log', lid)
    if not old: raise ApiError('Log entry not found', 404)
    d = request.get_json(force=True)
    e, errs = clean_log(d, lid)
    raise_if(errs)
    if e['hours'] > 24 and not d.get('allow_large') and e['hours'] != old['hours']:
        raise ApiError(f'{e["hours"]:g} hours is more than a day.', 409, {'hours': 'More than 24 hours'}, needs_confirm='large')
    if scalar('SELECT 1 FROM play_log WHERE date=? AND game=? AND system=? AND id!=?', (e['date'], e['game'], e['system'], lid)):
        raise ApiError('Another entry already exists for that date, game and system.', 409, {'date': 'Duplicate date/game/system'})
    update_row('play_log', lid, e, f'Edited log: {_log_label(e)}')
    return jsonify(id=lid)


@app.delete('/api/log/<int:lid>')
def delete_log(lid):
    old = get_row('play_log', lid)
    if not old: raise ApiError('Log entry not found', 404)
    delete_row('play_log', lid, f'Deleted log: {_log_label(old)}')
    return jsonify(ok=True)


# ----------------------------------------------------------------------------- top list
@app.get('/api/top')
def get_top():
    return jsonify(rows('SELECT rank, title FROM top_rank ORDER BY rank'))


@app.put('/api/top')
def put_top():
    titles = request.get_json(force=True).get('titles') or []
    clean = []
    for t in titles:
        g = find_game(t)
        if not g: raise ApiError(f'Unknown game: {t}', 400)
        if g['title'] in clean: raise ApiError(f'{g["title"]} appears twice', 400)
        clean.append(g['title'])
    old = rows('SELECT rank, title FROM top_rank ORDER BY rank')
    con().execute('DELETE FROM top_rank')
    con().executemany('INSERT INTO top_rank(rank,title) VALUES (?,?)', list(enumerate(clean, 1)))
    _audit('update', 'top_rank', None, old, [{'rank': i, 'title': t} for i, t in enumerate(clean, 1)], 'Edited top list')
    return jsonify(ok=True)


# ----------------------------------------------------------------------------- HaloRank
def halo_levels():
    return rows('SELECT * FROM halo_levels ORDER BY series_order, level_order, id')


def clean_halo(d, old=None):
    """Validate a HaloRank level. Ratings are all nine (0-5) or none at all (= unrated)."""
    errs, out = {}, {}
    level = str(d.get('level') or '').strip()
    if not level: errs['level'] = 'Level name is required'
    out['level'] = level
    game = str(d.get('game') or '').strip()
    if not game: errs['game'] = 'Game is required'
    known = rows('SELECT game, MIN(series_order) AS so FROM halo_levels GROUP BY game')
    hit = next((k for k in known if k['game'].lower() == game.lower()), None)
    if hit:
        out['game'], out['series_order'] = hit['game'], hit['so']
    else:
        out['game'] = game
        out['series_order'] = (scalar('SELECT MAX(series_order) FROM halo_levels') or 0) + 1
    if d.get('level_order') in (None, ''):
        out['level_order'] = old['level_order'] if old and old['game'] == out['game'] else             (scalar('SELECT MAX(level_order) FROM halo_levels WHERE game=?', (out['game'],)) or 0) + 1
    else:
        out['level_order'] = _num(d.get('level_order'), 'level_order', errs, 1, 999, True)
    vals = {c: _num(d.get(c), c, errs, halo.RATING_LO, halo.RATING_HI, True) for c in halo.RATING_COLS}
    if not errs and 0 < sum(v is not None for v in vals.values()) < len(vals):
        errs['ratings'] = 'Rate all nine categories, or leave them all blank for an unrated level'
    out.update(vals)
    note = d.get('notes')
    out['notes'] = str(note).strip() or None if note is not None else None
    if not errs and scalar('SELECT 1 FROM halo_levels WHERE game=? AND level=? AND id IS NOT ?', (out['game'], level, old['id'] if old else None)):
        errs['level'] = f'{out["game"]} already has a level called {level}'
    return out, errs


@app.get('/api/halo')
def get_halo():
    weights, tiers = halo.load_scoring(con())
    scored = halo.score_rows(halo_levels(), weights, tiers)
    return jsonify(levels=scored, games=halo.game_summary(scored, tiers), weights=weights, labels=halo.RATING_LABELS,
                   cols=halo.RATING_COLS, tiers=[{'tier': t[0], 'score': t[1], 'upper': t[2]} for t in tiers],
                   range=[halo.RATING_LO, halo.RATING_HI])


@app.post('/api/halo')
def create_halo():
    lvl, errs = clean_halo(request.get_json(force=True))
    raise_if(errs)
    lid = insert_row('halo_levels', lvl, f'Added HaloRank level {lvl["game"]}: {lvl["level"]}')
    return jsonify(id=lid), 201


@app.put('/api/halo/<int:lid>')
def update_halo(lid):
    old = get_row('halo_levels', lid)
    if not old: raise ApiError('Level not found', 404)
    lvl, errs = clean_halo({**old, **request.get_json(force=True)}, old)
    raise_if(errs)
    update_row('halo_levels', lid, lvl, f'Edited HaloRank level {lvl["game"]}: {lvl["level"]}')
    return jsonify(id=lid)


@app.delete('/api/halo/<int:lid>')
def delete_halo(lid):
    old = get_row('halo_levels', lid)
    if not old: raise ApiError('Level not found', 404)
    delete_row('halo_levels', lid, f'Deleted HaloRank level {old["game"]}: {old["level"]}')
    return jsonify(ok=True)


# ----------------------------------------------------------------------------- reviews
# The write-up lives in reviews; its tier is stored on the game (games.tier) but only ever set from here.
def clean_review(d):
    """Validate tier / status / body. Missing figure images block publishing; on a draft they are only warnings."""
    errs, out = {}, {}
    tier = canon(d.get('tier') or '', [t['name'] for t in RV.tiers(con())])
    if tier is None: errs['tier'] = 'Choose a tier'
    status = d.get('status') or 'draft'
    if status not in ('draft', 'published'): errs['status'] = 'Status is draft or published'
    out['status'] = status
    out['body'] = str(d.get('body') or '').replace('\r\n', '\n').strip()
    blocks = RV.parse_body(out['body'])
    missing = [f for f in RV.figure_files(blocks) if not os.path.exists(os.path.join(REVIEW_IMAGES, f))]
    if status == 'published' and not any(b['t'] == 'p' for b in blocks): errs['body'] = 'Write something before publishing'
    if status == 'published' and missing: errs['body'] = 'Missing image file(s): ' + ', '.join(missing)
    return out, tier, errs, [f'Image not found: {f}' for f in missing]


def review_row(rid):
    r = one('''SELECT r.*, g.id AS game_id, g.tier FROM reviews r JOIN games g ON g.title=r.title WHERE r.id=?''', (rid,))
    if not r: raise ApiError('Review not found', 404)
    return r


def _now():
    return dt.datetime.now().isoformat(sep=' ', timespec='seconds')


def tier_list():
    return rows('''SELECT t.id, t.rank, t.name, t.description, (SELECT COUNT(*) FROM games g WHERE g.tier=t.name) AS n_games
                   FROM ref_tier t ORDER BY t.rank, t.id''')


@app.get('/api/tiers')
def get_tiers():
    return jsonify(tier_list())


@app.put('/api/tiers')
def save_tiers():
    """Save the whole tier list, worst to best: [{id|null, name, description}, ...]. The order sent is the new order.
    Ids that are missing are deleted (refused while games are filed under them); null ids are new tiers.
    Renames cascade to games.tier through the foreign key. One audit batch, so one Undo."""
    items = request.get_json(force=True).get('tiers')
    if not isinstance(items, list) or not items: raise ApiError('Keep at least one tier.', 400)
    cur = {t['id']: t for t in tier_list()}
    errs, clean, seen, names = {}, [], set(), set()
    for i, it in enumerate(items):
        name = re.sub(r'\s+', ' ', str(it.get('name') or '')).strip()
        tid = it.get('id')
        if tid is not None:
            if tid not in cur or tid in seen: raise ApiError('The tier list changed since you opened it. Close and reopen the editor.', 409)
            seen.add(tid)
        if not name: errs[f'tiers.{i}.name'] = 'Name is required'
        elif len(name) > 60: errs[f'tiers.{i}.name'] = 'Name is too long (60 characters)'
        elif name.lower() in names: errs[f'tiers.{i}.name'] = 'Another tier already has this name'
        names.add(name.lower())
        clean.append(dict(id=tid, name=name, description=str(it.get('description') or '').strip()))
    gone = [t for tid, t in cur.items() if tid not in seen]
    for t in gone:
        if t['n_games']:
            errs['tiers'] = f'{t["name"]} still has {t["n_games"]} review{"" if t["n_games"] == 1 else "s"} filed under it. Move them to another tier first, or keep the tier.'
    raise_if(errs)
    for t in gone:
        delete_row('ref_tier', t['id'], f'Edited tiers: deleted {t["name"]}')
    renames = {c['id']: cur[c['id']]['name'] for c in clean if c['id'] is not None and c['name'] != cur[c['id']]['name']}
    taken = {cur[c['id']]['name'].lower() for c in clean if c['id'] is not None}
    if any(c['name'].lower() in taken and c['name'].lower() != renames[c['id']].lower() for c in clean if c['id'] in renames):
        for tid, old in renames.items():            # e.g. swapping two names: park them on temporary names first
            update_row('ref_tier', tid, {'name': f'~{tid}'}, f'Edited tiers: renamed {old}')
    for i, c in enumerate(clean, 1):
        if c['id'] is None:
            insert_row('ref_tier', dict(rank=i, name=c['name'], description=c['description']), f'Edited tiers: added {c["name"]}')
            continue
        old = cur[c['id']]
        data = {k: v for k, v in (('name', c['name']), ('description', c['description']), ('rank', i)) if v != old[k]}
        if data:
            what = f'renamed {old["name"]} to {c["name"]}' if 'name' in data else f'changed {old["name"]}'
            update_row('ref_tier', c['id'], data, f'Edited tiers: {what}')
    return jsonify(ok=True, renamed={old: next(c['name'] for c in clean if c['id'] == tid) for tid, old in renames.items()})


@app.get('/api/reviews')
def list_reviews():
    out = rows('''SELECT r.id, r.title, r.status, r.updated, r.body, g.id AS game_id, g.tier, t.rank AS tier_rank, g.my_score
                  FROM reviews r JOIN games g ON g.title=r.title LEFT JOIN ref_tier t ON t.name=g.tier
                  ORDER BY t.rank IS NULL, t.rank, r.title COLLATE NOCASE''')
    for r in out:
        r.update(RV.text_stats(RV.parse_body(r.pop('body'))))
        r['cover'] = cover_url(r['title'])
    return jsonify(out)


@app.get('/api/reviews/<int:rid>')
def get_review(rid):
    r = review_row(rid)
    return jsonify(review=r, cover=cover_url(r['title']), **RV.text_stats(RV.parse_body(r['body'])))


@app.post('/api/reviews')
def create_review():
    d = request.get_json(force=True)
    game = find_game(d.get('title'))
    review, tier, errs, warns = clean_review(d)
    if not game: errs['title'] = 'Choose a game from the list'
    elif scalar('SELECT id FROM reviews WHERE title=?', (game['title'],)):
        errs['title'] = f'{game["title"]} already has a review'
    raise_if(errs)
    rid = insert_row('reviews', {'title': game['title'], **review}, f'Started review of {game["title"]}')
    update_row('games', game['id'], {'tier': tier}, f'Filed {game["title"]} under {tier}')
    return jsonify(id=rid, warnings=warns), 201


@app.put('/api/reviews/<int:rid>')
def update_review(rid):
    old = review_row(rid)
    review, tier, errs, warns = clean_review(request.get_json(force=True))
    raise_if(errs)
    verb = 'Published' if review['status'] == 'published' and old['status'] != 'published' else 'Edited'
    update_row('reviews', rid, {**review, 'updated': _now()}, f'{verb} review of {old["title"]}')
    if tier != old['tier']:
        update_row('games', old['game_id'], {'tier': tier}, f'Filed {old["title"]} under {tier}')
    return jsonify(id=rid, warnings=warns)


@app.delete('/api/reviews/<int:rid>')
def delete_review(rid):
    r = review_row(rid)
    if r['tier'] is not None:
        update_row('games', r['game_id'], {'tier': None}, f'Cleared tier of {r["title"]}')
    delete_row('reviews', rid, f'Deleted review of {r["title"]}')
    return jsonify(ok=True)


@app.post('/api/reviews/<int:rid>/preview')
def preview_review(rid):
    """The review rendered with the reviews-page template, using the editor's unsaved tier/body if sent."""
    review_row(rid)
    d = request.get_json(silent=True) or {}
    payload = RV.gather(con(), COVERS, REVIEW_IMAGES, only=rid, draft={'tier': d.get('tier'), 'body': d.get('body')},
                        embed=False, cover_url=cover_url)
    return Response(RV.render(payload), mimetype='text/html')


@app.post('/api/review-images')
def upload_review_image():
    """Save a screenshot for a review; returns the file name to reference as ![caption](file)."""
    f = request.files.get('file')
    if not f: raise ApiError('Choose an image file', 400)
    raw = f.read()
    try:
        img = Image.open(io.BytesIO(raw)); img.load()
    except Exception:
        raise ApiError('That file is not a readable image (use JPG, PNG or WebP).', 400)
    game = find_game(request.form.get('title'))
    base, _ = RV.safe_image_name(f.filename)
    if game: base = RV.slug(game['title']) + '_' + base
    ext = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}.get(img.format)
    os.makedirs(REVIEW_IMAGES, exist_ok=True)
    name, n = base + (ext or '.png'), 1
    while os.path.exists(os.path.join(REVIEW_IMAGES, name)):
        n += 1; name = f'{base}-{n}{ext or ".png"}'
    path = os.path.join(REVIEW_IMAGES, name)
    if ext: open(path, 'wb').write(raw)                      # keep the original bytes; the page build resizes
    else: img.save(path, 'PNG')
    return jsonify(file=name, width=img.width, height=img.height), 201


# ----------------------------------------------------------------------------- audit / undo
@app.get('/api/audit')
def get_audit():
    out = rows('''SELECT batch, MIN(ts) AS ts, MAX(undone) AS undone, MIN(summary) AS summary, COUNT(*) AS n,
                  GROUP_CONCAT(DISTINCT action) AS actions, MAX(id) AS last_id
                  FROM audit GROUP BY batch ORDER BY last_id DESC LIMIT ?''', (min(int(request.args.get('limit', 40)), 200),))
    return jsonify(out)


@app.post('/api/undo/<batch>')
def undo(batch):
    items = rows('SELECT * FROM audit WHERE batch=? ORDER BY id DESC', (batch,))
    if not items: raise ApiError('Nothing to undo', 404)
    if any(i['undone'] for i in items): raise ApiError('That change was already undone', 409)
    for a in items:
        old = json.loads(a['old']) if a['old'] else None
        tbl = a['tbl']
        if tbl == 'top_rank':
            con().execute('DELETE FROM top_rank')
            con().executemany('INSERT INTO top_rank(rank,title) VALUES (?,?)', [(r['rank'], r['title']) for r in old])
        elif a['action'] == 'insert':
            con().execute(f'DELETE FROM {tbl} WHERE id=?', (a['row_id'],))
        elif a['action'] == 'update':
            # restore only the columns this change touched, so undoing an old edit can't clobber later ones
            # (e.g. undoing a game edit must not wipe a tier its review set afterwards)
            new = json.loads(a['new']) if a['new'] else {}
            data = {k: v for k, v in old.items() if k != 'id' and (k not in new or new[k] != v)}
            if data:
                con().execute(f'UPDATE {tbl} SET {",".join(c + "=?" for c in data)} WHERE id=?', [*data.values(), a['row_id']])
        elif a['action'] == 'delete':
            con().execute(f'INSERT INTO {tbl}({",".join(old)}) VALUES ({",".join("?" * len(old))})', list(old.values()))
    con().execute('UPDATE audit SET undone=1 WHERE batch=?', (batch,))
    return jsonify(ok=True, undone=len(items))


# ----------------------------------------------------------------------------- data checks (the workbook's check columns)
@app.get('/api/checks')
def checks():
    out = []
    add = lambda sev, kind, title, detail, **ids: out.append(dict(severity=sev, kind=kind, title=title, detail=detail, **ids))
    for k, (lo, hi, _) in SCORES.items():
        for r in rows(f'SELECT id, title, {k} AS v FROM games WHERE {k} IS NOT NULL AND ({k} < ? OR {k} > ?)', (lo, hi)):
            add('error', 'score_range', r['title'], f'{k.replace("_", " ")} is {r["v"]:g}, outside {lo}-{hi}', game_id=r['id'])
    for r in rows('SELECT id, title FROM games WHERE NOT EXISTS (SELECT 1 FROM releases r WHERE r.title=games.title)'):
        add('error', 'no_release', r['title'], 'Game has no release (system) entry', game_id=r['id'])
    for r in rows('''SELECT id, title FROM games WHERE COALESCE(my_score,0)+COALESCE(metacritic,0)+COALESCE(pc_gamer,0)+COALESCE(gamespot,0)
                     +COALESCE(ign,0)+COALESCE(destructoid,0)+COALESCE(game_informer,0) < 1'''):
        add('warn', 'no_scores', r['title'], 'No scores entered', game_id=r['id'])
    fp = {r['game']: r for r in rows('SELECT game, MIN(date) AS f, MAX(date) AS l FROM play_log GROUP BY game')}
    for r in rows('''SELECT g.id, g.title, MIN(substr(r.original_release_date,1,4)) AS ry, MIN(substr(r.added_date,1,4)) AS ay
                     FROM games g JOIN releases r ON r.title=g.title GROUP BY g.id'''):
        f = fp.get(r['title'])
        if f and (f['f'][:4] < r['ry'] or f['f'][:4] < r['ay']):
            add('warn', 'year_check', r['title'], f'First played {f["f"]} is before release year {r["ry"]} or added year {r["ay"]}', game_id=r['id'])
    for r in rows('''SELECT r.id, r.title, r.system, r.release, r.version_release_date v, r.added_date a, g.id AS gid,
        (SELECT MIN(date) FROM play_log l WHERE l.game=r.title AND l.system=r.system) AS f
        FROM releases r JOIN games g ON g.title=r.title'''):
        for w in release_warnings(r, r['f']):
            add('warn', 'date_check', f'{r["title"]} ({r["system"]})', w, game_id=r['gid'], release_id=r['id'])
    big = scalar('SELECT COUNT(*) FROM play_log WHERE hours > 24')
    if big: add('info', 'large_hours', f'{big} log entries over 24 hours', 'Likely backfilled totals (e.g. the first of a month); fine if intentional.')
    missing = [r['title'] for r in rows('SELECT title FROM top_rank ORDER BY rank LIMIT 10') if not cover_file(r['title'])]
    if missing: add('info', 'cover_missing', f'{len(missing)} Top 10 game(s) have no cover art', ', '.join(missing))
    for r in rows('SELECT r.id, r.title, r.status, r.body, g.tier, g.id AS gid FROM reviews r JOIN games g ON g.title=r.title'):
        gone = [f for f in RV.figure_files(RV.parse_body(r['body'])) if not os.path.exists(os.path.join(REVIEW_IMAGES, f))]
        if gone: add('error' if r['status'] == 'published' else 'warn', 'review_image', f'{r["title"]} review',
                     'Image file not found: ' + ', '.join(gone), game_id=r['gid'], review_id=r['id'])
        if not r['tier']: add('warn', 'review_tier', f'{r["title"]} review', 'Review has no tier (it is left off the reviews page)',
                              game_id=r['gid'], review_id=r['id'])
    order = {'error': 0, 'warn': 1, 'info': 2}
    out.sort(key=lambda x: order[x['severity']])
    summary = {s: sum(1 for x in out if x['severity'] == s) for s in order}
    return jsonify(summary=summary, items=out)


# ----------------------------------------------------------------------------- covers
@app.post('/api/games/<int:gid>/cover')
def upload_cover(gid):
    game = get_row('games', gid)
    if not game: raise ApiError('Game not found', 404)
    f = request.files.get('file')
    if not f: raise ApiError('Choose an image file', 400)
    try:
        img = Image.open(f.stream); img.load()
    except Exception:
        raise ApiError('That file is not a readable image (use JPG, PNG or WebP).', 400)
    os.makedirs(COVERS, exist_ok=True)
    for ext in COVER_EXTS:
        p = os.path.join(COVERS, cover_base(game['title']) + ext)
        if os.path.exists(p): os.remove(p)
    jpeg = img.format == 'JPEG'
    path = os.path.join(COVERS, cover_base(game['title']) + ('.jpg' if jpeg else '.png'))
    if jpeg: img.convert('RGB').save(path, 'JPEG', quality=95)
    else: img.save(path, 'PNG')
    return jsonify(cover=cover_url(game['title']), width=img.width, height=img.height)


@app.delete('/api/games/<int:gid>/cover')
def delete_cover(gid):
    game = get_row('games', gid)
    if not game: raise ApiError('Game not found', 404)
    f = cover_file(game['title'])
    if f: os.remove(f)
    return jsonify(ok=True)


# ----------------------------------------------------------------------------- backup / export / reports
def make_backup(keep=30):
    os.makedirs(BACKUPS, exist_ok=True)
    path = os.path.join(BACKUPS, f'gamelist-{dt.datetime.now():%Y%m%d-%H%M%S}.db')
    src = sqlite3.connect(DB); dst = sqlite3.connect(path)
    with dst: src.backup(dst)
    src.close(); dst.close()
    for old in sorted(glob.glob(os.path.join(BACKUPS, 'gamelist-*.db')))[:-keep]:
        os.remove(old)
    return path


@app.post('/api/backup')
def backup():
    return jsonify(path=make_backup())


@app.get('/api/export.zip')
def export():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for t in ('games', 'releases', 'play_log', 'top_rank', 'halo_levels', 'reviews', 'ref_tier'):
            cur = con().execute(f'SELECT * FROM {t} ORDER BY 1')
            s = io.StringIO(); w = csv.writer(s); w.writerow([c[0] for c in cur.description]); w.writerows(cur.fetchall())
            z.writestr(f'{t}.csv', s.getvalue())
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=f'games_list_export_{today():%Y%m%d}.zip')


_build_lock = threading.Lock()


@app.post('/api/rebuild')
def rebuild():
    """Rebuild every report, or one of them with ?only=dashboard|pdf|reviews."""
    if not _build_lock.acquire(blocking=False): raise ApiError('A rebuild is already running.', 409)
    try:
        env = dict(os.environ, GAMELIST_DB=DB)
        res = {}
        builds = (('dashboard', [sys.executable, os.path.join(BASE, 'build_html.py'), REPORT_HTML, COVERS]),
                  ('pdf', [sys.executable, os.path.join(BASE, 'build_pdf.py'), COVERS, REPORT_PDF]),
                  ('reviews', [sys.executable, os.path.join(BASE, 'build_reviews.py'), REPORT_REVIEWS, COVERS, REVIEW_IMAGES]))
        only = request.args.get('only')
        if only and only not in dict(builds): raise ApiError('Unknown report', 404)
        for name, cmd in builds:
            if only and name != only: continue
            t0 = dt.datetime.now()
            p = subprocess.run(cmd, cwd=BASE, env=env, capture_output=True, text=True, timeout=600)
            res[name] = dict(ok=p.returncode == 0, seconds=round((dt.datetime.now() - t0).total_seconds(), 1),
                             log=(p.stdout + p.stderr).strip()[-600:])
        status = 200 if all(v['ok'] for v in res.values()) else 500
        return jsonify(res), status
    finally:
        _build_lock.release()


@app.get('/api/reports')
def reports():
    st = lambda p: dict(exists=os.path.exists(p), built=dt.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec='minutes') if os.path.exists(p) else None,
                        ts=dt.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(sep=' ', timespec='seconds') if os.path.exists(p) else None,
                        kb=round(os.path.getsize(p) / 1024) if os.path.exists(p) else None)
    return jsonify(dashboard=st(REPORT_HTML), pdf=st(REPORT_PDF), reviews=st(REPORT_REVIEWS), last_change=scalar('SELECT MAX(ts) FROM audit'),
                   last_review_change=scalar("SELECT MAX(ts) FROM audit WHERE tbl='reviews' OR summary LIKE 'Filed %' OR summary LIKE 'Cleared tier %'"))


# ----------------------------------------------------------------------------- main
def main():
    global DB, COVERS, REVIEW_IMAGES, BACKUPS
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=DB); ap.add_argument('--covers', default=COVERS); ap.add_argument('--review-images', default=REVIEW_IMAGES)
    ap.add_argument('--port', type=int, default=CONFIG.get('port', 8765)); ap.add_argument('--no-browser', action='store_true')
    a = ap.parse_args()
    DB, COVERS, REVIEW_IMAGES = os.path.abspath(a.db), os.path.abspath(a.covers), os.path.abspath(a.review_images)
    os.environ['GAMELIST_DB'] = DB
    os.makedirs(COVERS, exist_ok=True); os.makedirs(REVIEW_IMAGES, exist_ok=True)
    if schema.upgrade(DB): print('Database upgraded to schema v%d' % schema.VERSION)
    if not glob.glob(os.path.join(BACKUPS, f'gamelist-{dt.date.today():%Y%m%d}-*.db')):
        print('Backup:', make_backup())
    url = f'http://127.0.0.1:{a.port}/'
    print(f'Game list app running at {url}  (Ctrl+C to stop)\n  database: {DB}\n  covers:   {COVERS}\n  review images: {REVIEW_IMAGES}')
    if not a.no_browser: threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host='127.0.0.1', port=a.port, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()
