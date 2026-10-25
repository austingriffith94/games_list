"""One-time import of the old "Game Reviews" page (a self-contained HTML file with a JSON data block) into the app.

Usage: python tools/import_reviews.py "Austin's Game Reviews.html" [--db gamelist.db] [--images review_images] [--dry-run]

* every game that had a full write-up becomes a published review, filed under its tier
* figures are written to the review images folder and referenced as ![caption](file){small}
* games that only had a tier placement (no write-up) are listed but not imported - tiers arrive with reviews
* the import is one audit batch, so it can be undone from the History tab
Re-running skips games that already have a review.
"""
import argparse, base64, json, os, re, sqlite3, sys, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import schema

ap = argparse.ArgumentParser()
ap.add_argument('html'); ap.add_argument('--db', default=os.path.join(ROOT, 'gamelist.db'))
ap.add_argument('--images', default=os.path.join(ROOT, 'review_images')); ap.add_argument('--dry-run', action='store_true')
a = ap.parse_args()
sys.stdout.reconfigure(encoding='utf-8')

src = open(a.html, encoding='utf-8').read()
m = re.search(r'<script type="application/json" id="data">(.*?)</script>', src, re.S)
if not m: sys.exit('No <script id="data"> JSON block found - is this the reviews page?')
D = json.loads(m.group(1))

if schema.upgrade(a.db): print('database upgraded to schema v%d' % schema.VERSION)
con = schema.connect(a.db)
batch = uuid.uuid4().hex
known_tiers = {r['name'].lower(): r['name'] for r in con.execute('SELECT name FROM ref_tier')}


def audit(action, tbl, rid, old, new, summary):
    con.execute('INSERT INTO audit(batch,action,tbl,row_id,old,new,summary) VALUES (?,?,?,?,?,?,?)',
                (batch, action, tbl, rid, None if old is None else json.dumps(old), None if new is None else json.dumps(new), summary))


def row(tbl, rid):
    return dict(con.execute(f'SELECT * FROM {tbl} WHERE id=?', (rid,)).fetchone())


def find_game(title):
    t = title.replace('&amp;', '&')
    for cand in (t, t.replace('’', "'")):
        r = con.execute('SELECT id, title FROM games WHERE title=?', (cand,)).fetchone()
        if r: return r
    return None


images, imported, skipped, tier_only = {}, [], [], []
for tier in D['tiers']:
    tname = known_tiers.get(tier['name'].lower())
    if not tname: sys.exit(f'Tier {tier["name"]!r} is not in ref_tier')
    for g in tier['games']:
        if not g.get('review'):
            tier_only.append(f'{g["title"]} ({tname})'); continue
        game = find_game(g['title'])
        if not game: skipped.append(f'{g["title"]}: no game with that title'); continue
        if con.execute('SELECT 1 FROM reviews WHERE title=?', (game['title'],)).fetchone():
            skipped.append(f'{game["title"]}: already has a review'); continue
        parts = []
        for b in g['blocks']:
            if b['t'] == 'p':
                parts.append(re.sub(r'\s+', ' ', b['h']).strip())
            else:
                uri = D['imgs'][b['img']]
                mime, data = re.match(r'data:image/(\w+);base64,(.*)', uri, re.S).groups()
                fname = b['img'] + ('.jpg' if mime == 'jpeg' else '.' + mime)
                images[fname] = base64.b64decode(data)
                cap = (b.get('cap') or '').replace('[', '(').replace(']', ')')
                parts.append(f'![{cap}]({fname})' + ('{small}' if b.get('small') else ''))
        body = '\n\n'.join(parts)
        cur = con.execute("INSERT INTO reviews(title, status, body) VALUES (?, 'published', ?)", (game['title'], body))
        audit('insert', 'reviews', cur.lastrowid, None, row('reviews', cur.lastrowid), f'Imported review of {game["title"]}')
        old = row('games', game['id'])
        con.execute('UPDATE games SET tier=? WHERE id=?', (tname, game['id']))
        audit('update', 'games', game['id'], old, row('games', game['id']), f'Filed {game["title"]} under {tname}')
        imported.append(f'{game["title"]} -> {tname} ({len(body.split())} words, {sum(1 for p in parts if p.startswith("!["))} figures)')

print(f'Imported {len(imported)} review(s):'); [print('  ' + x) for x in imported]
if skipped: print('Skipped:'); [print('  ' + x) for x in skipped]
if tier_only: print(f'Not imported - {len(tier_only)} tier placement(s) without a write-up (still in the source file):\n  ' + ', '.join(tier_only))
if a.dry_run:
    con.rollback(); print('dry run: nothing saved')
else:
    os.makedirs(a.images, exist_ok=True)
    for fname, raw in images.items():
        p = os.path.join(a.images, fname)
        if not os.path.exists(p): open(p, 'wb').write(raw)
    con.commit(); print(f'Saved. {len(images)} image(s) in {a.images}. Undo from the History tab if needed.')
con.close()
