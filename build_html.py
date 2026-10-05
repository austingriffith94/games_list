"""Interactive dashboard: one self-contained HTML file.  Usage: python build_html.py [out.html]"""
import sys, json, math, datetime
import pandas as pd
import data as D

OUT = sys.argv[1] if len(sys.argv) > 1 else 'games_list_dashboard.html'
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

sysmap = r.groupby('title')['system'].apply(lambda s: [x for x in D.SYSTEMS if x in set(s)]).to_dict()
G = [dict(t=x.title, s=clean(x.series), genre=clean(x.genre), view=clean(x.camera_view), style=clean(x.graphic_style),
          ms=num(x.my_score), mc=num(x.metacritic), pg=num(x.pc_gamer), gs=num(x.gamespot), ign=num(x.ign),
          des=num(x.destructoid), gi=num(x.game_informer), zp=clean(x.zero_punctuation), hrs=num(x.hours),
          rel=num(x.release_year), fp=clean(x.first_played), lp=clean(x.last_played), sys=sysmap.get(x.title, []))
     for x in g.itertuples()]
R = [dict(t=x.title, sys=x.system, own=clean(x.ownership), rt=clean(x.release), hrs=num(x.hours), ay=num(x.added_year),
          genre=clean(x.genre), view=clean(x.camera_view), style=clean(x.graphic_style)) for x in r.itertuples()]
L = [[x.date.strftime('%Y-%m-%d'), x.game, x.system, num(x.hours), int(x.real) if pd.notna(x.real) else 0] for x in log.itertuples()]
top = list(D.top10(t)['title'])
payload = dict(G=G, R=R, L=L, SYSTEMS=D.SYSTEMS, GENRES=list(t['ref_genre']['name']), VIEWS=list(t['ref_view']['name']),
               STYLES=list(t['ref_style']['name']), OWN=list(t['ref_ownership']['name']), RELT=list(t['ref_release_type']['name']),
               TOP=top, SUMMARY=dict(S, total_time=f"{int(S['total_hours']//24)}d {S['total_hours']%24:.1f}h"),
               SCORES=S['scores'], ASOF=log['date'].max().strftime('%b %d, %Y'), END=datetime.date.today().isoformat())
html = open('dashboard.template.html', encoding='utf-8').read().replace('/*DATA*/', json.dumps(payload, separators=(',', ':'), allow_nan=False).replace('</', '<\\/'))
open(OUT, 'w', encoding='utf-8').write(html)
print('wrote', OUT, f'{len(html)/1024:.0f} KB')
