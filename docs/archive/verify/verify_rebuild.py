"""Check the rebuilt reports (data.py heatmap()/stats_tables(), halo.py) against the values Excel cached in the
workbook.  Needs pandas (run it in the project env):  python docs/archive/verify/verify_rebuild.py

Two things legitimately differ from the workbook and are handled explicitly, not ignored:
  * WRC 8's IGN (84) and Overwatch 2's GameSpot (80) were out of range in the workbook and are fixed in
    gamelist.db.  The comparison puts the two bad values back before computing, so every GameSpot/IGN cell
    can still be checked against the cached number.
  * LastVsFirstBuckets: the workbook's edges skip a gap of exactly 6 years (5 games); data.LAST_EDGES closes it.
    That table is compared with the 6-year games added back to the "6-9" row.
"""
import os, sys, zipfile, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
import numpy as np
import pandas as pd
import data as D, halo

XLSM = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'old_excel', 'games_list.xlsm')
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
z = zipfile.ZipFile(XLSM)
ss = [''.join(t.text or '' for t in si.iter(NS + 't')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]


def cells(sheet):
    out = {}
    for c in ET.fromstring(z.read(sheet)).iter(NS + 'c'):
        v = c.find(NS + 'v')
        out[c.get('r')] = (ss[int(v.text)] if c.get('t') == 's' else v.text) if v is not None else None
    return out


def col(n):
    s = ''
    while n:
        n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s


S4, S5, S13 = cells('xl/worksheets/sheet4.xml'), cells('xl/worksheets/sheet5.xml'), cells('xl/worksheets/sheet13.xml')
t = D.load(); g, r, log, scale = D.build(t)
g = g.copy()
g.loc[g['title'] == 'WRC 8', 'ign'] = 84.0                  # put the two out-of-range cells back, as the workbook had them
g.loc[g['title'] == 'Overwatch 2', 'gamespot'] = 80.0
T = D.stats_tables(t, g)
total_bad = 0


def report(name, pairs, tol=1e-9):
    """pairs: (label, mine, cached). Prints a summary line and the first few mismatches."""
    global total_bad
    bad = 0
    n = 0
    for label, mine, cached in pairs:
        if cached in (None, ''):
            continue
        n += 1
        ok = (mine == cached) if isinstance(mine, str) else (mine is not None and abs(float(mine) - float(cached)) <= tol)
        if not ok:
            bad += 1
            if bad <= 5: print(f'    MISMATCH {label}: mine {mine} cached {cached}')
    total_bad += bad
    print(f'  {name:34s} compared {n:4d}   mismatches {bad}')


print('HeatMapScore')
ysrc, xsrc = S5['C5'], S5['F5']
h = D.heatmap(g, ysrc, xsrc, float(S5['C6']), float(S5['F6']), scale=None, vmax=float(S5['C2']), vmin=float(S5['C3']))
pairs = []
for i in range(h['grid'].shape[0]):
    for j in range(h['grid'].shape[1]):
        pairs.append((f'{col(17 + j)}{24 + i}', h['grid'][i, j], S5.get(f'{col(17 + j)}{24 + i}')))
report(f'grid {ysrc} (Y) vs {xsrc} (X), {h["grid"].shape[0]}x{h["grid"].shape[1]}', pairs, 0)
report('RSQ / SLOPE / INTERCEPT', [('RSQ', h['rsq'], S5['I5']), ('SLOPE', h['slope'], S5['I6']), ('INTERCEPT', h['intercept'], S5['I7'])], 1e-9)

print('Stats sheet')
P = []
for ri, label in enumerate(['Variance', 'Std. Deviation', 'Mean', 'Median', 'Excess Kurtosis', 'Skewness']):
    for c in range(13, 20):
        P.append((f'{label} {S13[col(c) + "3"]}', T['StatTable'].loc[label, S13[col(c) + '3']], S13.get(f'{col(c)}{4 + ri}')))
report('StatTable', P)
P = []
for ri in range(14, 21):
    for c in range(13, 20):
        P.append((f'{S13["L%d" % ri]} x {S13[col(c) + "13"]}', T['CorrelationMatrix'].loc[S13['L%d' % ri], S13[col(c) + '13']], S13.get(f'{col(c)}{ri}')))
report('CorrelationMatrix', P)
P = [(f'band {k} {n}', T['ScoreDistributionTable'].loc[k, n], S13.get(f'{col(c)}{3 + k}'))
     for k in range(1, 11) for c, n in ((4, 'My Score'), (5, 'GameSpot'), (6, 'IGN'), (7, 'Game Informer'))]
report('ScoreDistributionTable', P)
P = [(f'{S13["B%d" % ri]} {S13[col(c) + "17"]}', T['YearsPerScore'].loc[S13['B%d' % ri], S13[col(c) + '17']], S13.get(f'{col(c)}{ri}'))
     for ri in range(18, 29) for c in range(3, 7)]
report('YearsPerScore', P)
P = [(f'{S13["B%d" % ri]} {lab}', T['SoundtrackStats'].loc[S13['B%d' % ri], lab], S13.get(f'{c}{ri}'))
     for ri in range(34, 43) for c, lab in (('C', 'Owned'), ('D', 'Not Owned'))]
P += [(f'MC band {k} {lab}', T['SoundtrackDistributionTable'].loc[k, lab], S13.get(f'{c}{32 + k}'))
      for k in range(1, 11) for c, lab in (('I', 'Owned'), ('J', 'Not Owned'))]
report('SoundtrackStats + Distribution', P)
P = [(f'{b} {lab}', T['ZeroPunctuationQualityBuckets'].loc[b, lab], S13.get(f'{c}{47 + i}'))
     for i, b in enumerate(D.ZP_ORDER) for c, lab in (('C', 'Games'), ('D', 'Frequency'), ('E', 'Games Played'), ('F', 'Frequency Played'), ('G', 'Hours'))]
report('ZeroPunctuationQualityBuckets', P)
bands = ['1-2', '3-4', '5-6', '7-8', '9-10']
P = [(f'{bands[i]} {b}', T['ZeroPunctuationDistribution'].loc[bands[i], b], S13.get(f'{col(5 + j)}{57 + i}'))
     for i in range(5) for j, b in enumerate(D.ZP_ORDER)]
report('ZeroPunctuationDistribution', P)
sr = T['SeriesRankStats']
P = []
for i in range(1, 11):
    ri = 65 + i
    P += [(f'#{i} Series', sr.loc[i, 'Series'], S13.get(f'B{ri}')), (f'#{i} Rank Equivalent', sr.loc[i, 'Rank Equivalent'], S13.get(f'D{ri}')),
          (f'#{i} Games Owned', sr.loc[i, 'Games Owned'], S13.get(f'F{ri}')), (f'#{i} Games Played', sr.loc[i, 'Games Played'], S13.get(f'G{ri}')),
          (f'#{i} Hours', sr.loc[i, 'Hours'], S13.get(f'H{ri}'))]
report('SeriesRankStats', P)
tot = T['SeriesRankTotalStats']
P = [(f'{lab} {c}', tot.loc[lab, c], S13.get(f'{cc}{79 + i}')) for i, lab in enumerate(['Top 10 Series', 'Other'])
     for cc, c in (('C', 'Games Owned'), ('D', 'Games Played'), ('E', 'Hours'))]
report('SeriesRankTotalStats', P)
for name, r0 in (('PlaythroughVsScoreBuckets', 25), ('NormPlayVsScoreBuckets', 37), ('ReleaseVsFirstBuckets', 49), ('LastVsFirstBuckets', 61)):
    m = T[name]
    P = []
    for i in range(8):
        for s in range(1, 11):
            mine = m.iloc[i][s]
            if name == 'LastVsFirstBuckets' and i == 4:          # the closed gap: add the gap==6 games back to "6-9"
                mine -= int(((g['my_score'] == s) & (g['First Played vs Last Played'] == 6)).sum())
            P.append((f'{name} row {i + 1} score {s}', mine, S13.get(f'{col(14 + s)}{r0 + i}')))
    report(name, P, 0)
print(f'  (gap == 6 years, the workbook\'s dropped bucket: {int((g["First Played vs Last Played"] == 6).sum())} games)')

print('HaloRank (rated levels only: the workbook scores the 26 all-zero Halo 5 / Infinite rows as F, this rebuild leaves them unrated)')
import sqlite3
con = sqlite3.connect(D.DB); con.row_factory = sqlite3.Row
w, tiers = halo.load_scoring(con)
lv = {(x['game'], x['level']): x for x in halo.score_rows([dict(r_) for r_ in con.execute('SELECT * FROM halo_levels')], w, tiers)}
P = []
for ri in range(25, 110):
    game, level = S4.get(f'C{ri}'), S4.get(f'E{ri}')
    mine = lv[(game, level)]
    if mine['variable_score'] is None:
        continue
    P += [(f'{level} Variable Score', mine['variable_score'], S4.get(f'H{ri}')), (f'{level} Rank', mine['tier'], S4.get(f'F{ri}')),
          (f'{level} Score', mine['tier_score'], S4.get(f'G{ri}'))]
report('HaloRankMaster', P)
P = []
for gm in halo.game_summary(list(lv.values()), tiers):
    if not gm['rated']:
        continue
    ri = next(i for i in range(3, 11) if S4.get(f'C{i}') == gm['game'])
    P += [(f'{gm["game"]} avg score', gm['avg_score'], S4.get(f'D{ri}')), (f'{gm["game"]} avg tier score', gm['avg_tier_score'], S4.get(f'E{ri}')),
          (f'{gm["game"]} levels', gm['levels'], S4.get(f'F{ri}'))]
    P += [(f'{gm["game"]} {tt}', gm['tiers'][tt], S4.get(f'{col(7 + k)}{ri}')) for k, tt in enumerate('SABCDF')]
report('HaloRankLetterScore', P)

print('TimeHeatComp (calendar heat map comparison; every day counted, as the workbook does)')
S19 = cells('xl/worksheets/sheet19.xml')
xl_date = lambda n: pd.Timestamp('1899-12-30') + pd.Timedelta(days=int(float(n)))
P = []
for k, c0 in enumerate(('L', 'AD', 'AV', 'BN')):                 # the four panels; each one's value column follows its label column
    f, to = xl_date(S19[f'{c0}3']), xl_date(S19[f'{c0}4'])
    s = D.daily_hours(log, (to - f).days + 1, end=to)               # the workbook's window is From..To inclusive (366-367 days)
    st = D.calendar_stats(s, include_zero=True)
    P += [(f'panel {k + 1} total', s.sum(), S19[f'{c0}5']), (f'panel {k + 1} max', st['Max'], S19[f'{c0}7']),
          (f'panel {k + 1} avg', st['Avg'], S19[f'{c0}9']), (f'panel {k + 1} median', st['Median'], S19[f'{c0}10']),
          (f'panel {k + 1} min', st['Min'], S19[f'{c0}12'])]
report('TimeHeatComp', P, tol=1e-9)
print('  (75% / 25% are not compared: the workbook uses PERCENTILE.EXC, data.calendar_stats uses PERCENTILE.INC on purpose)')

con.close()

print('\nALL MATCH' if not total_bad else f'\n{total_bad} MISMATCHES')
sys.exit(1 if total_bad else 0)
