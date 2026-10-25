"""Fills tww_lords from the Total War: Warhammer wiki (docs/ACTION_PLAN_tww_lords.md, step 2).

Usage: python tools/fetch_tww_lords.py [--db gamelist.db] [--lords lords] [--dry-run] [--no-images] [--list]

* reads the "Total War: Warhammer III legendary lords" page (it lists the lords from all three games) through the
  MediaWiki API, sent with a browser User-Agent because the normal pages answer scripts with 403
* inserts lords that are not in the table yet; for lords already there it only fills columns that are still empty,
  so anything edited by hand in the app is kept. It never touches tww_campaigns.
* roc_playable is set from the wiki's own "(IE & tRoC)" markers on the start location - check the list it prints
* downloads the unit card, portrait and faction icon into lords/ (skipping files already there)
* the run is one audit batch, so it can be undone from the History tab
"""
import argparse, json, os, re, sqlite3, sys, time, uuid
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import schema

API = 'https://totalwarwarhammer.fandom.com/api.php'
PAGE = 'Total War: Warhammer III legendary lords'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'

# The game each race first appeared in; sections are ordered WH1 -> WH2 -> WH3, then A-Z. An unknown race stops the
# run instead of being guessed, so a new race has to be placed here on purpose.
RACE_GAME = {
    'The Empire': 1, 'Dwarfs': 1, 'Greenskins': 1, 'Vampire Counts': 1, 'Warriors of Chaos': 1,
    'Beastmen': 1, 'Bretonnia': 1, 'Norsca': 1, 'Wood Elves': 1,
    'High Elves': 2, 'Dark Elves': 2, 'Lizardmen': 2, 'Skaven': 2, 'Tomb Kings': 2, 'Vampire Coast': 2,
    'Daemons of Chaos': 3, 'Grand Cathay': 3, 'Khorne': 3, 'Kislev': 3, 'Nurgle': 3, 'Slaanesh': 3, 'Tzeentch': 3,
    'Ogre Kingdoms': 3, 'Chaos Dwarfs': 3, 'Undead Legions': 3,
}

ap = argparse.ArgumentParser()
ap.add_argument('--db', default=os.path.join(ROOT, 'gamelist.db'))
ap.add_argument('--lords', default=os.path.join(ROOT, 'lords'))
ap.add_argument('--dry-run', action='store_true'); ap.add_argument('--no-images', action='store_true')
ap.add_argument('--list', action='store_true', help='name every lord in the per-race counts')
a = ap.parse_args()
sys.stdout.reconfigure(encoding='utf-8')


def get(url, binary=False, tries=3):
    for i in range(tries):
        try:
            with urlopen(Request(url, headers={'User-Agent': UA, 'Referer': 'https://totalwarwarhammer.fandom.com/'}), timeout=30) as r:
                data = r.read()
            return data if binary else json.loads(data)
        except Exception as e:
            if i == tries - 1: raise RuntimeError(f'{url}: {e}')
            time.sleep(1.5 * (i + 1))


def api(**params):
    return get(API + '?format=json&redirects=1&' + '&'.join(f'{k}={quote(str(v))}' for k, v in params.items()))


class Tables(HTMLParser):
    """Every <table> as rows of cells: {tag, rs, cs, text, links, imgs}; <br> becomes a newline in the text."""
    def __init__(s):
        super().__init__(); s.tables = []; s.row = None; s.cell = None; s.href = None

    def handle_starttag(s, tag, at):
        at = dict(at)
        if tag == 'table': s.tables.append([])
        elif tag == 'tr' and s.tables: s.row = []; s.tables[-1].append(s.row)
        elif tag in ('td', 'th') and s.row is not None:
            s.cell = dict(tag=tag, rs=int(at.get('rowspan', 1)), cs=int(at.get('colspan', 1)), text='', links=[], imgs=[])
            s.row.append(s.cell)
        elif s.cell is not None and tag == 'br': s.cell['text'] += '\n'
        elif s.cell is not None and tag == 'a': s.href = at
        elif s.cell is not None and tag == 'img':
            src = at.get('data-src') or at.get('src') or ''
            s.cell['imgs'].append(dict(alt=at.get('alt', ''), file=at.get('data-image-name', ''),
                                       url=re.sub(r'/scale-to-width-down/\d+', '', src),
                                       page=(s.href or {}).get('title', '') if 'mw-file-description' not in (s.href or {}).get('class', '') else ''))

    def handle_endtag(s, tag):
        if tag in ('td', 'th'): s.cell = None
        elif tag == 'a': s.href = None

    def handle_data(s, d):
        if s.cell is not None:
            s.cell['text'] += d
            if s.href and s.href.get('title'): s.cell['links'].append(s.href['title'])


def grid(rows):
    """Expands rowspans/colspans so every row has a value at every column index."""
    out, carry = [], {}
    for r in rows:
        line, col, it = [], 0, iter(r)
        while True:
            if col in carry:
                cell, left = carry[col]
                line.append(cell)
                if left > 1: carry[col] = (cell, left - 1)
                else: del carry[col]
                col += 1; continue
            cell = next(it, None)
            if cell is None: break
            for _ in range(cell['cs']):
                line.append(cell)
                if cell['rs'] > 1: carry[col] = (cell, cell['rs'] - 1)
                col += 1
        out.append(line)
    return out


def clean(s):
    return re.sub(r'[ \t]+', ' ', s).strip()


def start_and_roc(text):
    """('Uzkulak, Zorn Uzkul', True): the Immortal Empires start, and whether the wiki marks a Realm of Chaos start."""
    segs = []
    for line in text.split('\n'):
        line = clean(line)
        if not line: continue
        m = re.match(r'(.*?)\s*\(([^)]*)\)\s*$', line)
        segs.append((clean(m.group(1)), m.group(2)) if m else (line, ''))
    if not segs: return None, False
    ie = next((s for s in segs if 'IE' in s[1]), segs[0])
    return ie[0] or None, any('tRoC' in s[1] for s in segs)


def parse(html):
    p = Tables(); p.feed(html)
    lords, seen = [], set()
    for t in p.tables:
        for row in grid(t):
            if len(row) != 5 or row[0]['tag'] != 'th' or row[2]['tag'] != 'td' or not row[2]['imgs']: continue
            race, fac, lordc, loc, dlc = row
            start, roc = start_and_roc(loc['text'])
            dlc_name = ', '.join(dict.fromkeys(dlc['links'])) or clean(dlc['text']) or None
            fimg = fac['imgs'][0] if fac['imgs'] else None
            for im in lordc['imgs']:
                name = clean(im['alt'])
                if not name or name in seen: continue
                seen.add(name)
                lords.append(dict(race=clean(race['text']), faction=clean(fac['text']) or None, lord=name, start_location=start,
                                  roc=roc, dlc=dlc_name, wiki_page=im['page'] or name, card_url=im['url'], icon_url=fimg['url'] if fimg else None))
    return lords


def safe(name):
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()          # same rule as the covers


def ext_of(url):
    m = re.search(r'\.(png|jpe?g|gif|webp)(?:/|$)', urlparse(url).path, re.I)
    return '.' + m.group(1).lower() if m else '.png'


def portraits(pages):
    """page title -> original image URL, 40 titles per API call."""
    out = {}
    pages = list(pages)
    for i in range(0, len(pages), 40):
        d = api(action='query', prop='pageimages', piprop='original', titles='|'.join(pages[i:i + 40]))['query']
        norm = {n['to']: n['from'] for n in d.get('normalized', [])}
        redir = {r['to']: r['from'] for r in d.get('redirects', [])}
        for pg in d['pages'].values():
            src = pg.get('original', {}).get('source')
            if not src: continue
            title = pg['title']
            title = redir.get(title, title); title = norm.get(title, title)
            out[title] = src
    return out


print('Reading the wiki...')
lords = parse(api(action='parse', page=PAGE, prop='text')['parse']['text']['*'])
if not lords: sys.exit('No lords found - has the wiki page layout changed?')
unknown = sorted({l['race'] for l in lords} - set(RACE_GAME))
if unknown: sys.exit('Races missing from RACE_GAME (add the game each came from): ' + ', '.join(unknown))
print(f'{len(lords)} lords across {len({l["race"] for l in lords})} races')

pmap = portraits({l['wiki_page'] for l in lords})
for l in lords:
    l['portrait_url'] = pmap.get(l['wiki_page']) or pmap.get(l['wiki_page'].replace('_', ' '))

# file names + downloads
for l in lords:
    base = safe(l['lord'])
    l['card'] = f'{base} - card{ext_of(l["card_url"])}' if l['card_url'] else None
    l['portrait'] = f'{base} - portrait{ext_of(l["portrait_url"])}' if l['portrait_url'] else None
    l['faction_icon'] = f'{safe(l["faction"])}{ext_of(l["icon_url"])}' if l['faction'] and l['icon_url'] else None
want = {}
for l in lords:
    for col, url in (('card', 'card_url'), ('portrait', 'portrait_url'), ('faction_icon', 'icon_url')):
        if l[col]: want[l[col]] = l[url]
got = 0
if not a.no_images and not a.dry_run:
    os.makedirs(a.lords, exist_ok=True)
    for fname, url in want.items():
        path = os.path.join(a.lords, fname)
        if os.path.exists(path) and os.path.getsize(path) > 0: continue
        try:
            data = get(url, binary=True)                # fetched in full before the file is created
            if not data: raise RuntimeError('empty response')
            open(path, 'wb').write(data); got += 1; time.sleep(0.1)
        except Exception as e:
            print('  download failed:', fname, e)
    for l in lords:                                     # a file that failed to download is not recorded
        for col in ('card', 'portrait', 'faction_icon'):
            p = os.path.join(a.lords, l[col]) if l[col] else None
            if p and (not os.path.exists(p) or os.path.getsize(p) == 0): l[col] = None

# database
if not a.dry_run and schema.upgrade(a.db): print('database upgraded to schema v%d' % schema.VERSION)
con = schema.connect(a.db) if not a.dry_run else None
inserted, filled = [], []
if con:
    batch = uuid.uuid4().hex

    def audit(action, rid, old, new, summary):
        con.execute('INSERT INTO audit(batch,action,tbl,row_id,old,new,summary) VALUES (?,?,?,?,?,?,?)',
                    (batch, action, 'tww_lords', rid, None if old is None else json.dumps(old), json.dumps(new), summary))

    def row(rid):
        return dict(con.execute('SELECT * FROM tww_lords WHERE id=?', (rid,)).fetchone())

    races = {r['race'].lower(): (r['race_game'], r['race_order']) for r in con.execute('SELECT DISTINCT race, race_game, race_order FROM tww_lords')}
    new_races = sorted({l['race'] for l in lords if l['race'].lower() not in races}, key=lambda r: (RACE_GAME[r], r.lower()))
    for g in (1, 2, 3):                                 # A-Z within each game, after any races already there
        start = max([o for gm, o in races.values() if gm == g] + [0])
        for i, r in enumerate([x for x in new_races if RACE_GAME[x] == g], start + 1):
            races[r.lower()] = (g, i)
    fill_cols = ['faction', 'start_location', 'dlc', 'wiki_page', 'card', 'portrait', 'faction_icon']
    for l in lords:
        ex = con.execute('SELECT * FROM tww_lords WHERE lord=?', (l['lord'],)).fetchone()
        if ex is None:
            game, order = races[l['race'].lower()]
            cur = con.execute('INSERT INTO tww_lords(race,race_game,race_order,lord,faction,start_location,dlc,wiki_page,roc_playable,card,portrait,faction_icon)'
                              ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                              (l['race'], game, order, l['lord'], l['faction'], l['start_location'], l['dlc'], l['wiki_page'],
                               int(l['roc']), l['card'], l['portrait'], l['faction_icon']))
            audit('insert', cur.lastrowid, None, row(cur.lastrowid), f'Added lord {l["lord"]}')
            inserted.append(l['lord'])
        else:
            todo = {c: l[c] for c in fill_cols if ex[c] is None and l[c] is not None}
            if todo:
                old = dict(ex)
                con.execute(f'UPDATE tww_lords SET {", ".join(c + "=?" for c in todo)} WHERE id=?', (*todo.values(), ex['id']))
                audit('update', ex['id'], old, row(ex['id']), f'Filled {", ".join(todo)} for {l["lord"]}')
                filled.append(f'{l["lord"]} ({", ".join(todo)})')

# report
by_race = {}
for l in lords: by_race.setdefault((RACE_GAME[l['race']], l['race']), []).append(l)
print('\nLords per race (compare with the wiki):')
for (g, race), ls in sorted(by_race.items(), key=lambda kv: (kv[0][0], kv[0][1].lower())):
    print(f'  WH{g}  {race}: {len(ls)}' + (' - ' + '; '.join(l['lord'] for l in ls) if a.list else ''))
print('\nMarked Realms of Chaos playable (check this list):')
for l in lords:
    if l['roc']: print(f'  {l["race"]}: {l["lord"]}')
print(f'  = {sum(l["roc"] for l in lords)} of {len(lords)}')
for col, what in (('card', 'unit card'), ('portrait', 'portrait'), ('faction_icon', 'faction icon')):
    miss = [l['lord'] for l in lords if not l[col]]       # after a real download this also covers failed downloads
    if miss: print(f'\nNo {what} for {len(miss)}: ' + ', '.join(miss))
if a.dry_run:
    print('\ndry run: nothing downloaded or saved')
else:
    con.commit(); con.close()
    print(f'\nSaved. Added {len(inserted)} lord(s), filled gaps on {len(filled)}, downloaded {got} image(s) into {a.lords}. Undo from the History tab if needed.')
    if inserted: print('Set roc_playable by hand in the app for anything the check above got wrong.')
