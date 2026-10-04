"""Migrate games_list.xlsm input tables into SQLite. Usage: python migrate.py <xlsm> <db>"""
import sys, re, sqlite3, datetime, warnings
import openpyxl
from openpyxl.utils import range_boundaries
warnings.filterwarnings('ignore')
src, dbp = sys.argv[1], sys.argv[2]
wb = openpyxl.load_workbook(src, data_only=True)

def table(sheet, name):
    ws = wb[sheet]; t = ws.tables[name]
    c1, r1, c2, r2 = range_boundaries(t.ref)
    hdr = [str(ws.cell(r1, c).value) for c in range(c1, c2 + 1)]
    rows = [[ws.cell(r, c).value for c in range(c1, c2 + 1)] for r in range(r1 + 1, r2 + 1)]
    return hdr, rows

def slug(s): return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')
def norm(v):
    if isinstance(v, datetime.datetime): return v.date().isoformat()
    if isinstance(v, datetime.time): return None
    if isinstance(v, bool): return int(v)
    if isinstance(v, str) and v.strip() == '': return None
    return v

GAME_IN = ['Title','Series','Graphic Style','Camera View','Genre','Sub-Genre','Singleplayer','Local Co-op','Online Co-op','Local Multiplayer','Online Multiplayer','My Score','Metacritic','PC Gamer','GameSpot','IGN','Destructoid','Game Informer','Zero Punctuation','GOTY Votes','Wikipedia GOAT','Soundtrack Owned','Playthroughs','Average Playthrough']
REL_IN = ['Title','Release','System','Ownership','Original Release Date','Version Release Date','Added Date']
LOG_IN = ['Date','Game','System','Hours','Real']

db = sqlite3.connect(dbp)
for t in ['games','releases','play_log']: db.execute(f'DROP TABLE IF EXISTS {t}')
def load(sheet, tname, cols, out, rename=None):
    hdr, rows = table(sheet, tname)
    idx = [hdr.index(c) for c in cols]
    names = [slug((rename or {}).get(c, c)) for c in cols]
    data = [[norm(r[i]) for i in idx] for r in rows]
    data = [d for d in data if d[0] is not None]
    db.execute(f'CREATE TABLE {out} (id INTEGER PRIMARY KEY, ' + ', '.join(names) + ')')
    db.executemany(f'INSERT INTO {out} ({",".join(names)}) VALUES ({",".join("?"*len(names))})', data)
    return len(data)
print('games', load('Game_Table','GameTable',GAME_IN,'games'))
print('releases', load('Year_Table','YearSystemTable',REL_IN,'releases'))
print('play_log', load('TimeLog','TimeLogMaster',LOG_IN,'play_log'))


# --- canonicalize play_log titles/systems to the release table (Excel lookups are case-insensitive) ---
db.execute('DROP TABLE IF EXISTS data_fixes')
db.execute('CREATE TABLE data_fixes (table_name, row_id, column_name, old_value, new_value)')
for col, ref in [('game','title'),('system','system')]:
    rows = db.execute(f"""SELECT l.id, l.{col}, (SELECT r.{ref} FROM releases r WHERE r.{ref}=l.{col} COLLATE NOCASE LIMIT 1)
                          FROM play_log l WHERE l.{col} NOT IN (SELECT {ref} FROM releases)""").fetchall()
    for rid, old, new in rows:
        if new and new != old:
            db.execute(f'UPDATE play_log SET {col}=? WHERE id=?', (new, rid))
            db.execute('INSERT INTO data_fixes VALUES (?,?,?,?,?)', ('play_log', rid, col, old, new))

# lookup tables on List (+ others) copied as-is (cached values)
skip = {'Sheets2Save','CollagePicDimensionTable'}
n = 0
for ws in wb.worksheets:
    for tn, t in ws.tables.items():
        if ws.title != 'List' or tn in skip: continue
        hdr, rows = table('List', tn)
        cols = [slug(h) or f'c{i}' for i, h in enumerate(hdr)]
        seen = {}
        for i, c in enumerate(cols):
            seen[c] = seen.get(c, 0) + 1
            if seen[c] > 1: cols[i] = f'{c}_{seen[c]}'
        name = 'lk_' + slug(tn)
        db.execute(f'DROP TABLE IF EXISTS {name}')
        db.execute(f'CREATE TABLE {name} (' + ','.join(cols) + ')')
        data = [[norm(v) for v in r] for r in rows if any(v is not None for v in r)]
        db.executemany(f'INSERT INTO {name} VALUES ({",".join("?"*len(cols))})', data)
        print(name, len(data)); n += 1
db.commit(); db.close()
import schema
schema.upgrade(dbp)   # constraints, reference tables, audit log
print('schema v%d ready' % schema.VERSION)
