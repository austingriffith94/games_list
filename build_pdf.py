"""Printable report: Letter-size PDF via matplotlib.  Usage: python build_pdf.py [covers_dir] [out.pdf]"""
import sys, os, datetime
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LinearSegmentedColormap
import data as D

_a = [x for x in sys.argv[1:] if not x.startswith('--')]
COVERS = _a[0] if len(_a) > 0 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'covers')
OUT = _a[1] if len(_a) > 1 else 'games_list_report.pdf'
ORANGE, PURPLE, GREY, DARK = '#C55A11', '#8E5BD0', '#8C8C8C', '#222222'
HEAT = LinearSegmentedColormap.from_list('h', ['#FFFFFF', '#FFE699', '#F4B183', '#E8584F'])
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8, 'axes.spines.top': False,
                     'axes.spines.right': False, 'axes.edgecolor': '#999', 'axes.titleweight': 'bold',
                     'axes.titlesize': 9.5, 'pdf.fonttype': 42})

t = D.load()
g, r, log, scale = D.build(t)
S = D.summary(g, r, log, scale)
genres = list(t['ref_genre']['name']); views = list(t['ref_view']['name'])
CRIT = ['metacritic_100', 'gamespot_100', 'destructoid_100', 'game_informer_100', 'pc_gamer_100', 'ign_100']
g['critic_100'] = g[CRIT].mean(axis=1)
r = r.merge(g[['title', 'my_score_100', 'critic_100']], on='title', how='left')
today = log['date'].max()


def cover_path(title):
    base = os.path.join(COVERS, title.replace(':', ''))
    for ext in ('.jpg', '.png', '.jpeg'):
        if os.path.exists(base + ext): return base + ext
    return None


from PIL import Image
_cache = {}
def load_cover(path, w, h):
    """Centre-crop to w:h (never stretch) and downscale to w x h pixels - keeps the PDF small."""
    key = (path, w, h)
    if key not in _cache:
        im = Image.open(path).convert('RGB'); want, have = w / h, im.width / im.height
        if have > want: nw = int(im.height * want); x = (im.width - nw) // 2; im = im.crop((x, 0, x + nw, im.height))
        else: nh = int(im.width / want); y = (im.height - nh) // 2; im = im.crop((0, y, im.width, y + nh))
        _cache[key] = np.asarray(im.resize((w, h), Image.LANCZOS))
    return _cache[key]


def header(fig, title, sub=None):
    fig.text(0.04, 0.965, title, fontsize=15, fontweight='bold', color=ORANGE, va='top')
    if sub: fig.text(0.04, 0.935, sub, fontsize=8, color=GREY, va='top')


def footer(fig, n):
    fig.text(0.04, 0.02, f'Game list report · data through {today:%b %d, %Y}', fontsize=7, color=GREY)
    fig.text(0.96, 0.02, str(n), fontsize=7, color=GREY, ha='right')


def heat_matrix(ax, m, title):
    body = m.iloc[:-1, :-1]
    ax.imshow(body.values, cmap=HEAT, vmin=0, vmax=max(1, body.values.max() * 0.55), aspect='auto')
    ax.set_xticks(range(body.shape[1])); ax.set_xticklabels(body.columns, rotation=40, ha='right', fontsize=7)
    ax.set_yticks(range(body.shape[0])); ax.set_yticklabels(body.index, fontsize=7)
    ax.xaxis.tick_top(); ax.tick_params(length=0)
    plt.setp(ax.get_xticklabels(), rotation=40, ha='left')
    for i in range(body.shape[0]):
        for j in range(body.shape[1]):
            v = body.iat[i, j]
            if v: ax.text(j, i, int(v), ha='center', va='center', fontsize=6.5)
    ax.set_xticks(np.arange(-.5, body.shape[1]), minor=True); ax.set_yticks(np.arange(-.5, body.shape[0]), minor=True)
    ax.grid(which='minor', color='white', lw=1); ax.tick_params(which='minor', length=0)
    for s in ax.spines.values(): s.set_visible(False)
    # totals
    for j, v in enumerate(m.iloc[-1, :-1]): ax.text(j, body.shape[0] + .15, int(v), ha='center', va='top', fontsize=7, fontweight='bold', color=DARK)
    for i, v in enumerate(m.iloc[:-1, -1]): ax.text(body.shape[1] - .35, i, int(v), ha='left', va='center', fontsize=7, fontweight='bold', color=DARK)
    ax.text(body.shape[1] - .35, body.shape[0] + .15, int(m.iloc[-1, -1]), ha='left', va='top', fontsize=7.5, fontweight='bold', color=ORANGE)
    pass


with PdfPages(OUT) as pdf:
    n = 0
    # ---------------- Page 1: Top 10 + totals (portrait)
    fig = plt.figure(figsize=(8.5, 11)); n += 1
    header(fig, 'Personal Top 10', 'Ranked favorites, with game totals')
    kp = [('Games', S['games']), ('Games played', S['games_played']), ('Unique games', S['unique_games']),
          ('Unique played', S['unique_played']), ('Backlog', S['backlog']), ('Total time', S['total_time'])]
    for i, (k, v) in enumerate(kp):
        x = 0.04 + i * 0.158
        fig.patches.append(plt.Rectangle((x, 0.855), 0.145, 0.055, transform=fig.transFigure, fc='#FBE5D6', ec=ORANGE, lw=.8))
        fig.text(x + .0725, 0.895, str(v), ha='center', va='center', fontsize=12, fontweight='bold', color=ORANGE)
        fig.text(x + .0725, 0.866, k, ha='center', va='center', fontsize=7, color=DARK)
    top = D.top10(t).merge(g[['title', 'my_score', 'metacritic', 'hours', 'genre', 'release_year']], on='title', how='left')
    ax = fig.add_axes([0.04, 0.605, 0.92, 0.235]); ax.axis('off')
    ax.set_xlim(0, 1); ax.set_ylim(0, 11)
    for j, (h, x) in enumerate(zip(['#', 'Title', 'Genre', 'Year', 'My score', 'Metacritic', 'Hours'], [0.0, .05, .52, .68, .77, .87, .97])):
        ax.text(x, 10.55, h, fontweight='bold', color='white', ha='right' if j >= 3 else 'left', va='center')
    ax.add_patch(plt.Rectangle((0, 10.2), 1, .7, fc=ORANGE, zorder=0))
    for i, row in top.reset_index(drop=True).iterrows():
        y = 9.55 - i
        if i % 2 == 0: ax.add_patch(plt.Rectangle((0, y - .5), 1, 1, fc='#F5F5F5', zorder=0))
        ax.text(0.01, y, str(i + 1), fontweight='bold', color=ORANGE, va='center')
        ax.text(.05, y, row['title'], va='center'); ax.text(.52, y, str(row['genre']), va='center')
        ax.text(.68, y, f"{row['release_year']:.0f}", ha='right', va='center')
        ax.text(.77, y, f"{row['my_score']:.0f}/10" if pd.notna(row['my_score']) else '–', ha='right', va='center')
        ax.text(.87, y, f"{row['metacritic']:.0f}" if pd.notna(row['metacritic']) else '–', ha='right', va='center')
        ax.text(.97, y, f"{row['hours']:.0f}", ha='right', va='center')
    # covers: 2 rows x 5, portrait 2:3, cropped to fill (only drawn for games that have a cover file)
    found = [(row['title'], cover_path(row['title'])) for _, row in top.iterrows()]
    cw, ch = 0.176, 0.2045
    for i, (title, p) in enumerate(found):
        x0, y0 = 0.04 + (i % 5) * 0.186, 0.375 - (i // 5) * 0.215
        ax2 = fig.add_axes([x0, y0, cw, ch]); ax2.axis('off')
        if p: ax2.imshow(load_cover(p, 300, 450), aspect='auto')
        else:
            ax2.add_patch(plt.Rectangle((0, 0), 1, 1, fc='#F3EDE7', ec='#DDD')); ax2.text(.5, .5, f'#{i + 1}\n' + '\n'.join(__import__('textwrap').wrap(title, 16)), ha='center', va='center', color=GREY, fontsize=8)
            ax2.set_xlim(0, 1); ax2.set_ylim(0, 1)
    ax = fig.add_axes([0.04, 0.05, 0.92, 0.075]); ax.axis('off'); ax.set_xlim(0, 7); ax.set_ylim(0, 1)
    for i, (k, v) in enumerate(S['scores'].items()):
        ax.add_patch(plt.Rectangle((i + .03, .08), .94, .84, fc='#F5F5F5', ec='#DDD'))
        ax.text(i + .5, .62, f'{v:.0f}', ha='center', va='center', fontsize=13, fontweight='bold', color=ORANGE); ax.text(i + .5, .27, k, ha='center', va='center', fontsize=7)
    fig.text(0.04, 0.135, 'Score averages (0–100)', fontsize=9, fontweight='bold', color=ORANGE)
    footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Pages 2-3: matrices (landscape)
    for title, col, cols in [('Systems by genre', 'genre', genres), ('Systems by camera view', 'camera_view', views)]:
        fig = plt.figure(figsize=(11, 8.5)); n += 1
        header(fig, 'Table summary', f'{title} · count of games per system')
        ax = fig.add_axes([0.13, 0.08, 0.80 if col == 'genre' else 0.55, 0.72])
        heat_matrix(ax, D.matrix(r, col, cols), title)
        footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 4: score distributions
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Score distributions', 'Games per score bucket · critic sources shown on a 0–100 scale')
    srcs = [('My Score', 'my_score', 1, 1), ('Metacritic', 'metacritic', 10, 5), ('PC Gamer', 'pc_gamer', 10, 5),
            ('GameSpot', 'gamespot', 1, 0.5), ('IGN', 'ign', 1, 0.5), ('Game Informer', 'game_informer', 1, 0.5),
            ('Destructoid', 'destructoid', 1, 0.5)]
    for i, (name, col, sc_, step) in enumerate(srcs):
        ax = fig.add_subplot(3, 3, i + 1)
        v = (g[col] * 10 / sc_).dropna()
        if name == 'My Score': bins = np.arange(5, 105, 10); lab = 'My Score'
        else: bins = np.arange(0, 105, 10)
        ax.hist(v, bins=np.arange(0, 110, 10), color=ORANGE, edgecolor='white', rwidth=.9)
        ax.set_title(f'{name}  (n={len(v)}, avg {v.mean():.0f})', loc='left'); ax.set_xlim(0, 100)
    ax = fig.add_subplot(3, 3, 8)
    zp = g['zero_punctuation'].value_counts().reindex(['Best', 'Good', 'Neutral', 'Bland', 'Bad', 'Worst']).fillna(0)
    ax.bar(zp.index, zp.values, color=[PURPLE] * 6, edgecolor='white'); ax.set_title('Zero Punctuation opinions', loc='left')
    plt.setp(ax.get_xticklabels(), fontsize=7)
    fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.91]); footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 5: scores by genre / system / view
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Scores by category', 'My score vs. average of critic outlets (0–100), ordered by my score')
    for i, (title, col, order) in enumerate([('Genre', 'genre', genres), ('System', 'system', D.SYSTEMS), ('Camera view', 'camera_view', views)]):
        ax = fig.add_subplot(1, 3, i + 1)
        src = r if col == 'system' else g
        grp = src.groupby(col).agg(me=('my_score_100' if col == 'system' else 'my_score_100', 'mean'),
                                   cr=('critic_100', 'mean'), n=('title', 'count')).reindex(order).dropna(subset=['me', 'cr'], how='all')
        grp = grp.sort_values('me')
        y = np.arange(len(grp))
        ax.barh(y, grp['me'], color=ORANGE, height=.6, label='My score'); ax.scatter(grp['cr'], y, color=PURPLE, zorder=3, s=14, label='Critics')
        ax.set_yticks(y); ax.set_yticklabels([f'{k} ({int(v)})' for k, v in zip(grp.index, grp['n'])], fontsize=7)
        ax.set_xlim(40, 100); ax.set_title(title, loc='left')
        if i == 0: ax.legend(frameon=False, fontsize=7, loc='lower right')
    fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.91]); footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 6: years
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Games by year', 'First-played year, release year, and games added by ownership')
    for i, (title, col) in enumerate([('First played', 'first_year'), ('Released', 'release_year')]):
        ax = fig.add_subplot(3, 1, i + 1)
        d = g.dropna(subset=[col] if col == 'release_year' else [col]); d = d[d['played']] if col == 'first_year' else d
        cnt = d.groupby(col).size(); ax.bar(cnt.index, cnt.values, color=ORANGE, width=.7)
        ax.set_ylabel('Games'); ax2 = ax.twinx(); ax2.spines['right'].set_visible(True)
        sc_ = d.groupby(col).agg(me=('my_score_100', 'mean'), cr=('critic_100', 'mean'))
        ax2.plot(sc_.index, sc_['me'], color=DARK, marker='o', ms=3, lw=1, label='My score'); ax2.plot(sc_.index, sc_['cr'], color=PURPLE, lw=1.2, label='Critics')
        ax2.set_ylim(40, 100); ax.set_title(f'Games by {title.lower()} year (bars) and average score (lines)', loc='left')
        if i == 0: ax2.legend(frameon=False, fontsize=7, loc='upper left')
    ax = fig.add_subplot(3, 1, 3)
    add = r.groupby(['added_year', 'ownership']).size().unstack(fill_value=0)
    bottom = np.zeros(len(add))
    for c, colr in zip(['Paid', 'Free', 'Friend/Family'], [ORANGE, PURPLE, GREY]):
        if c in add: ax.bar(add.index, add[c], bottom=bottom, color=colr, label=c, width=.7); bottom += add[c].values
    ax.legend(frameon=False, fontsize=7, ncol=3, loc='upper left'); ax.set_title('Games added per year by ownership', loc='left')
    fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.91]); footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 7: time played (last 365 days)
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    s365 = D.daily_hours(log, 365, end=max(today, pd.Timestamp(datetime.date.today()))); start = s365.index[0]
    header(fig, 'Time played', f'{start:%b %d, %Y} – {s365.index[-1]:%b %d, %Y}')
    ax = fig.add_axes([0.06, 0.66, 0.90, 0.22])
    real = log[log['real'] == 1].groupby('date')['hours'].sum().reindex(s365.index, fill_value=0)
    ax.bar(s365.index, s365.values, color=ORANGE, width=1, label='All logged'); (ax.bar(real.index, real.values, color=PURPLE, width=1, label='Flagged Real') if real.sum() > 0 else None)
    ax.plot(s365.index, s365.rolling(14, min_periods=1).mean(), color=DARK, lw=1.2, label='14-day average')
    ax.legend(frameon=False, fontsize=7, ncol=3); ax.set_title('Hours per day', loc='left'); ax.set_ylabel('Hours')
    ax = fig.add_axes([0.06, 0.38, 0.90, 0.21])
    ax.plot(s365.index, s365.cumsum(), color=DARK); ax.set_title('Cumulative hours', loc='left'); ax.set_ylabel('Hours')
    # weekday box + calendar
    wd = s365.groupby(s365.index.weekday)
    ax = fig.add_axes([0.06, 0.07, 0.30, 0.22])
    ax.boxplot([v.values for _, v in wd], tick_labels=['M', 'T', 'W', 'T', 'F', 'S', 'S'], showfliers=False, patch_artist=True,
               boxprops=dict(facecolor='#F4B183', color=ORANGE), medianprops=dict(color=DARK))
    ax.plot(range(1, 8), [v.mean() for _, v in wd], 'o', color=PURPLE, ms=4); ax.set_title('Hours by weekday (dot = mean)', loc='left')
    ax = fig.add_axes([0.42, 0.07, 0.54, 0.22])
    first_monday = start - pd.Timedelta(days=start.weekday())
    grid = np.full((7, ((s365.index[-1] - first_monday).days // 7) + 1), np.nan)
    for d_, v in s365.items(): grid[d_.weekday(), (d_ - first_monday).days // 7] = v
    ax.imshow(grid, cmap=HEAT, aspect='auto', vmin=0, vmax=max(4, np.nanpercentile(grid, 95)))
    ax.set_yticks(range(7)); ax.set_yticklabels(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], fontsize=6.5)
    ticks = [i for i in range(grid.shape[1]) if (first_monday + pd.Timedelta(weeks=i)).day <= 7]
    ax.set_xticks(ticks); ax.set_xticklabels([(first_monday + pd.Timedelta(weeks=i)).strftime('%b') for i in ticks], fontsize=6.5)
    ax.set_title('Calendar heat map', loc='left'); ax.tick_params(length=0)
    for s_ in ax.spines.values(): s_.set_visible(False)
    footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 8: series & score vs hours
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Hours played', 'Top series and how hours relate to score')
    ax = fig.add_subplot(2, 2, 1)
    ts = g[g['hours'] > 0].groupby('series')['hours'].sum().sort_values().tail(10)
    ax.barh(ts.index, ts.values, color=ORANGE); ax.set_title('Top 10 series by hours', loc='left'); plt.setp(ax.get_yticklabels(), fontsize=7)
    ax = fig.add_subplot(2, 2, 2)
    zh = g.groupby('zero_punctuation').agg(hours=('hours', 'sum')).reindex(['Best', 'Good', 'Neutral', 'Bland', 'Bad', 'Worst']).fillna(0)
    ax.bar(zh.index, zh['hours'], color=PURPLE); ax.set_title('Hours by Zero Punctuation opinion', loc='left'); ax.set_ylabel('Hours')
    ax = fig.add_subplot(2, 1, 2)
    p = g[g['hours'] > 0]
    a, b, r2, xs, ys = D.regression(p['my_score'] * 10, p['hours'], log_y=True)
    ax.scatter(p['my_score'] * 10 + np.random.default_rng(1).uniform(-1.5, 1.5, len(p)), p['hours'], s=9, color=DARK, alpha=.6)
    xx = np.linspace(10, 100, 50); ax.plot(xx, np.exp(a + b * xx), color=ORANGE, lw=2)
    ax.set_yscale('log'); ax.set_xlabel('My score'); ax.set_ylabel('Hours (log)'); ax.set_title(f'My score vs. hours played · exponential fit R² = {r2:.2f}', loc='left')
    fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.91]); footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Collage pages (only if covers present): landscape, 20 x 9 per page like the workbook
    ordered = g.sort_values(['series', 'release_date'])
    if '--all' not in sys.argv: ordered = ordered[ordered['played']]
    paths = [p for p in (cover_path(x) for x in ordered['title']) if p]
    COLS, ROWS, CELLW, CELLH = 20, 9, 0.5 / 11, 0.75 / 8.5
    for pg in range(0, len(paths), COLS * ROWS):
        fig = plt.figure(figsize=(11, 8.5)); n += 1
        for k, p in enumerate(paths[pg:pg + COLS * ROWS]):
            ax = fig.add_axes([(1 / 22) + (k % COLS) * CELLW, 1 - 0.103 - (k // COLS + 1) * CELLH, CELLW, CELLH]); ax.axis('off')
            ax.imshow(load_cover(p, 140, 210), aspect='auto')
        fig.text(0.5, 0.045, f'Collection · {len(paths)} covers', ha='center', fontsize=8, color=GREY); footer(fig, n); pdf.savefig(fig); plt.close(fig)
print('wrote', OUT)
