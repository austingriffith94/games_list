"""Interactive dashboard: one self-contained HTML file.  Usage: python build_html.py [out.html] [covers_dir] [lords_dir]"""
import sys, os, io, json, math, datetime, base64, sqlite3
import pandas as pd
from PIL import Image
import data as D
import tww

_a = [x for x in sys.argv[1:] if not x.startswith('--')]
_here = os.path.dirname(os.path.abspath(__file__))
OUT = _a[0] if _a else 'games_list_dashboard.html'
COVERS = _a[1] if len(_a) > 1 else os.path.join(_here, 'covers')
LORDS_DIR = _a[2] if len(_a) > 2 else os.environ.get('GAMELIST_LORDS') or os.path.join(_here, 'lords')
TW, TH = 80, 120          # mosaic thumbnail size; JPEG q55 keeps each to ~2-3 KB so ~650 covers add ~2 MB
CW, CH = 85, 115          # lord unit card size (the in-game card's own size)
PW, PH = 240, 320         # lord portrait, drawer only; JPEG q70 is ~10-15 KB each
Image.MAX_IMAGE_PIXELS = None   # lords/ is a local cache, and a wiki portrait can be a 12000 px wallpaper
t = D.load(); g, r, log, scale = D.build(t); S = D.summary(g, r, log, scale)

def clean(v):
    if v is None: return None
    if isinstance(v, float) and math.isnan(v): return None
    if isinstance(v, pd.Timestamp): return None if pd.isna(v) else v.strftime('%Y-%m-%d')
    if pd.isna(v) if not isinstance(v, (list, str)) else False: return None
    if hasattr(v, 'item'): v = v.item()
    return v
def num(v):
    v = clean(v); return None if v is None else (int(v) if float(v).is_integer() else round(float(v), 3))

def thumb(title):
    base = os.path.join(COVERS, title.translate({ord(c): None for c in '<>:"/\\|?*'}))
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        if os.path.exists(base + ext):
            im = Image.open(base + ext).convert('RGB'); want = TW / TH
            if im.width / im.height > want: w = int(im.height * want); x = (im.width - w) // 2; im = im.crop((x, 0, x + w, im.height))
            else: h = int(im.width / want); im = im.crop((0, 0, im.width, h))      # keep the top of tall art (title lettering)
            buf = io.BytesIO(); im.resize((TW, TH), Image.LANCZOS).save(buf, 'JPEG', quality=55, optimize=True)
            return base64.b64encode(buf.getvalue()).decode()
    return None
THUMBS = {x.title: b for x in g.itertuples() if (b := thumb(x.title))}

sysmap = r.groupby('title')['system'].apply(lambda s: [x for x in D.SYSTEMS if x in set(s)]).to_dict()
rank_of = dict(zip(t['top_rank']['title'], t['top_rank']['rank']))
npt_of = dict(zip(g['title'], g['Normalized Playthroughs']))
rgap_of = dict(zip(g['title'], g['Release Year vs First Played']))
# one player-mode bucket per game: any versus mode wins, then any co-op, else single-player
def mode(x):
    on = lambda *k: any(num(getattr(x, c)) == 1 for c in k)
    return 'Multiplayer' if on('local_multiplayer', 'online_multiplayer') else 'Co-op' if on('local_co_op', 'online_co_op') else 'Single-player'
lgap_of = dict(zip(g['title'], g['First Played vs Last Played']))
G = [dict(t=x.title, s=clean(x.series), genre=clean(x.genre), view=clean(x.camera_view), style=clean(x.graphic_style),
          so=int(x.soundtrack_owned or 0), ms=num(x.my_score), mc=num(x.metacritic), pg=num(x.pc_gamer), gs=num(x.gamespot), ign=num(x.ign),
          des=num(x.destructoid), gi=num(x.game_informer), zp=clean(x.zero_punctuation), hrs=num(x.hours),
          rel=num(x.release_year), ay=num(x.added_year), fp=clean(x.first_played), lp=clean(x.last_played),
          goat=int(x.wikipedia_goat or 0), gv=num(x.goty_votes), vs=num(x.goty_share),
          rank=rank_of.get(x.title), sys=sysmap.get(x.title, []), mode=mode(x),
          plt=num(x.playthroughs), npt=num(npt_of.get(x.title)), rgap=num(rgap_of.get(x.title)), lgap=num(lgap_of.get(x.title)))
     for x in g.itertuples()]
R = [dict(t=x.title, sys=x.system, own=clean(x.ownership), rt=clean(x.release), hrs=num(x.hours), ay=num(x.added_year),
          pt=clean(x.system_type), genre=clean(x.genre), view=clean(x.camera_view), style=clean(x.graphic_style)) for x in r.itertuples()]
L = [[x.date.strftime('%Y-%m-%d'), x.game, x.system, num(x.hours)] for x in log.itertuples()]
top = list(D.top10(t)['title'])


def table_payload(df):
    """DataFrame -> {index, columns, values} with NaN as null, for the dashboard's Statistics tab."""
    cell = lambda v: None if (not isinstance(v, str) and pd.isna(v)) else (v if isinstance(v, str) else float(v))
    return dict(index=[str(i) for i in df.index], columns=[str(c) for c in df.columns], values=[[cell(v) for v in row] for row in df.itertuples(index=False)])
STATS = {k: table_payload(v) for k, v in D.stats_tables(t, g, scale).items()}


def lord_img(name, kind):
    """base64 of a lords/ image: 'card' and 'portrait' as JPEG q70, 'icon' as a 32 px PNG. None when missing."""
    p = os.path.join(LORDS_DIR, name) if name else None
    if not p or not os.path.exists(p): return None
    buf = io.BytesIO()
    try:                                     # PIL decodes lazily, so a truncated file only fails at convert/resize
        im = Image.open(p)
        if kind == 'icon':
            im = im.convert('RGBA'); im.thumbnail((32, 32), Image.LANCZOS); im.save(buf, 'PNG', optimize=True)
        else:
            w, h = (CW, CH) if kind == 'card' else (PW, PH)
            im.draft('RGB', (w * 2, h * 2))                                  # JPEG: decode a big file at a reduced size
            if im.mode in ('RGBA', 'LA', 'P'):                               # flatten transparency onto a dark neutral
                im = im.convert('RGBA'); bg = Image.new('RGB', im.size, (43, 43, 43)); bg.paste(im, mask=im.getchannel('A')); im = bg
            im = im.convert('RGB'); want = w / h
            if im.width / im.height > want: cw = int(im.height * want); x = (im.width - cw) // 2; im = im.crop((x, 0, x + cw, im.height))
            else: im = im.crop((0, 0, im.width, int(im.width / want)))      # keep the top: the face
            im.resize((w, h), Image.LANCZOS).save(buf, 'JPEG', quality=70, optimize=True)
    except (OSError, ValueError) as e:
        print(f'skipped lord image {name}: {e}'); return None
    return base64.b64encode(buf.getvalue()).decode()


def lords_payload():
    """The dashboard Lords tab: lords, scored campaigns, scoring tables and embedded images. None before schema v7."""
    con = sqlite3.connect(D.DB); con.row_factory = sqlite3.Row
    try:
        lords = [dict(r) for r in con.execute('SELECT * FROM tww_lords ORDER BY race_game, race_order, race COLLATE NOCASE, lord COLLATE NOCASE')]
        camps = [dict(r) for r in con.execute("SELECT * FROM tww_campaigns ORDER BY COALESCE(started, finished, '') DESC, id DESC")]
        modes = [r[0] for r in con.execute('SELECT name FROM ref_tww_mode ORDER BY rowid')]
        weights, tiers = tww.load_scoring(con)
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()
    camps = [{k: v for k, v in c.items() if v is not None} | {'score': c['score'], 'tier': c['tier']}
             for c in tww.score_rows(camps, weights, tiers)]
    pl = t['play_log']
    return dict(
        lords=[{k: l[k] for k in ('id', 'lord', 'race', 'race_game', 'race_order', 'faction', 'start_location', 'dlc',
                                  'roc_playable', 'faction_icon')} for l in lords],
        campaigns=camps, races=[r['race'] for r in tww.race_summary(lords, camps)], modes=modes,
        weights=weights, labels=tww.RATING_LABELS, cols=tww.RATING_COLS,
        tiers=[{'tier': x[0], 'upper': x[2]} for x in tiers],
        wh3_hours=num(pl.loc[pl['game'] == tww.GAME, 'hours'].sum()) or 0,
        cards={l['id']: b for l in lords if (b := lord_img(l['card'], 'card'))},
        portraits={l['id']: b for l in lords if (b := lord_img(l['portrait'], 'portrait'))},
        icons={f: b for f in {l['faction_icon'] for l in lords} if (b := lord_img(f, 'icon'))})
LORDS = lords_payload()
payload = dict(G=G, R=R, L=L, SYSTEMS=D.SYSTEMS, GENRES=list(t['ref_genre']['name']), VIEWS=list(t['ref_view']['name']),
               STYLES=list(t['ref_style']['name']), OWN=list(t['ref_ownership']['name']), RELT=list(t['ref_release_type']['name']),
               TOP=top, SUMMARY=dict(S, total_time=f"{int(S['total_hours']//24)}d {S['total_hours']%24:.1f}h"),
               SCORES=S['scores'], SOUND=D.soundtrack(g), THUMBS=THUMBS,
               SERIES_ORDER=list(g.sort_values(['series', 'release_date'])['title']), ASOF=log['date'].max().strftime('%b %d, %Y'), END=datetime.date.today().isoformat(),
               HOLIDAYS=sorted(t['holidays']), STATS=STATS, LORDS=LORDS)
html = open('dashboard.template.html', encoding='utf-8').read().replace('/*DATA*/', json.dumps(payload, separators=(',', ':'), allow_nan=False).replace('</', '<\\/'))
open(OUT, 'w', encoding='utf-8').write(html)
print('wrote', OUT, f'{len(html)/1024:.0f} KB')
