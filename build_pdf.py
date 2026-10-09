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
r = r.merge(g[['title', 'my_score_100', 'critic_100', 'metacritic_100', 'game_informer_100', 'ign_100']], on='title', how='left')
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
    if key not in _cache and len(_cache) > 2000: _cache.clear()
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
    header(fig, 'Score distributions', '% of games per score, 1–10 scale shared across outlets for direct comparison')
    srcs = [('My Score', 'my_score_100'), ('Metacritic', 'metacritic_100'), ('PC Gamer', 'pc_gamer_100'),
            ('GameSpot', 'gamespot_100'), ('IGN', 'ign_100'), ('Game Informer', 'game_informer_100'),
            ('Destructoid', 'destructoid_100')]
    dists = []
    for name, col in srcs:
        v10 = (g[col] / 10).dropna()
        cnt = v10.round().clip(1, 10).astype(int).value_counts().reindex(range(1, 11), fill_value=0)
        dists.append((name, v10, cnt))
    ymax = max((cnt / len(v10) * 100).max() for _, v10, cnt in dists if len(v10))
    for i, (name, v10, cnt) in enumerate(dists):
        ax = fig.add_subplot(3, 3, i + 1)
        pct = cnt / len(v10) * 100
        ax.bar(cnt.index, pct.values, color=ORANGE, edgecolor='white', width=.8)
        ax.set_ylim(0, ymax * 1.08); ax.set_xlim(0.5, 10.5); ax.set_xticks(range(1, 11))
        if i % 3 == 0: ax.set_ylabel('% of games')
        ax.set_title(f'{name}  (n={len(v10)}, avg {v10.mean():.1f})', loc='left')
    ax = fig.add_subplot(3, 3, 8)
    zp = g['zero_punctuation'].value_counts().reindex(['Best', 'Good', 'Neutral', 'Bland', 'Bad', 'Worst']).fillna(0)
    ax.bar(zp.index, zp.values, color=[PURPLE] * 6, edgecolor='white'); ax.set_title('Zero Punctuation opinions', loc='left')
    plt.setp(ax.get_xticklabels(), fontsize=7)
    fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.91]); footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 5: scores by genre / system / view
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Scores by category', 'My score vs. Metacritic / Game Informer / IGN (0–100); pale bar = games played, ordered by my score')
    OUTLETS = [('Metacritic', 'metacritic_100', PURPLE), ('Game Informer', 'game_informer_100', '#4F9DE8'), ('IGN', 'ign_100', '#5BBF6A')]
    for i, (title, col, order) in enumerate([('Genre', 'genre', genres), ('System', 'system', D.SYSTEMS), ('Camera view', 'camera_view', views)]):
        ax = fig.add_subplot(1, 3, i + 1)
        src = r if col == 'system' else g
        agg = dict(me=('my_score_100', 'mean'), n=('title', 'count'), **{o: (c, 'mean') for o, c, _ in OUTLETS})
        grp = src.groupby(col).agg(**agg).reindex(order)
        grp = grp.dropna(subset=['me'] + [o for o, _, _ in OUTLETS], how='all').sort_values('me')
        y = np.arange(len(grp))
        axn = ax.twiny()
        axn.barh(y, grp['n'], color='#ECECEC', height=.8, zorder=1); axn.set_xlim(0, max(1, grp['n'].max()) * 1.15)
        axn.tick_params(axis='x', labelsize=6, colors=GREY); axn.set_xlabel('Games played', fontsize=6.5, color=GREY)
        ax.patch.set_visible(False); ax.set_zorder(axn.get_zorder() + 1)
        ax.barh(y, grp['me'], color=ORANGE, height=.3, zorder=3, label='My score')
        for oname, _, color in OUTLETS: ax.scatter(grp[oname], y, color=color, zorder=4, s=13, label=oname)
        ax.set_yticks(y); ax.set_yticklabels([f'{k} ({int(v)})' for k, v in zip(grp.index, grp['n'])], fontsize=7)
        ax.set_xlim(40, 100); ax.set_title(title, loc='left')
        if i == 0: ax.legend(frameon=False, fontsize=6, loc='lower right', ncol=2)
    fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.91]); footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 5b: my score vs. each critic, with regression
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'My score vs. each critic', 'Linear fit and R² per outlet')
    CRIT_SRC = [('Game Informer', 'game_informer_100'), ('GameSpot', 'gamespot_100'), ('IGN', 'ign_100'),
                ('Metacritic', 'metacritic_100'), ('PC Gamer', 'pc_gamer_100'), ('Destructoid', 'destructoid_100')]
    for i, (name, col) in enumerate(CRIT_SRC):
        ax = fig.add_subplot(2, 3, i + 1)
        d = g[['my_score_100', col]].dropna()
        a, b, r2, xs, ys = D.regression(d['my_score_100'], d[col])
        ax.scatter(xs + np.random.default_rng(i).uniform(-1.2, 1.2, len(xs)), ys, s=10, color=DARK, alpha=.5)
        xx = np.linspace(10, 100, 50); ax.plot(xx, a + b * xx, color=ORANGE, lw=2)
        ax.set_xlim(0, 100); ax.set_ylim(0, 100)
        ax.set_title(f'{name}  ·  R² = {r2:.2f}  (n={len(d)})', loc='left')
        if i % 3 == 0: ax.set_ylabel('Critic score')
        if i >= 3: ax.set_xlabel('My score')
    fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.91]); footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 5c: average year per score
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Average year per score', 'Mean release / added / first played / last played year, by my score (plus Top 20)')
    top20 = set(t['top_rank'].loc[t['top_rank']['rank'] <= 20, 'title'])
    cats = [str(i) for i in range(1, 11)] + ['Top 20']
    ax = fig.add_axes([0.08, 0.14, 0.86, 0.68])
    for name, col, color in [('Release year', 'release_year', ORANGE), ('Added year', 'added_year', PURPLE),
                              ('First played', 'first_year', DARK), ('Last played', 'last_year', '#4F9DE8')]:
        ys = [g.loc[g['my_score'] == i, col].mean() for i in range(1, 11)]
        ys.append(g.loc[g['title'].isin(top20), col].mean())
        ax.plot(np.arange(len(cats)), ys, marker='o', ms=4, lw=1.6, color=color, label=name)
    ax.set_xticks(np.arange(len(cats))); ax.set_xticklabels(cats); ax.set_xlabel('My score')
    ax.set_ylabel('Year'); ax.legend(frameon=False, fontsize=8, ncol=2, loc='upper left')
    footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 6: games by year, four bases
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Games by year', 'Count of games per year (bars) and average score (lines), four year bases')
    bases = [('First played', 'first_year', True), ('Released', 'release_year', False),
             ('Last played', 'last_year', True), ('Added', 'added_year', False)]
    for i, (title, col, need_played) in enumerate(bases):
        ax = fig.add_subplot(2, 2, i + 1)
        d = g.dropna(subset=[col]); d = d[d['played']] if need_played else d
        cnt = d.groupby(col).size(); ax.bar(cnt.index, cnt.values, color=ORANGE, width=.7)
        ax.set_ylabel('Games'); ax2 = ax.twinx(); ax2.spines['right'].set_visible(True)
        sc_ = d.groupby(col).agg(me=('my_score_100', 'mean'), cr=('critic_100', 'mean'))
        ax2.plot(sc_.index, sc_['me'], color=DARK, marker='o', ms=3, lw=1, label='My score'); ax2.plot(sc_.index, sc_['cr'], color=PURPLE, lw=1.2, label='Critics')
        ax2.set_ylim(40, 100); ax.set_title(f'By {title.lower()} year', loc='left')
        if i == 0: ax2.legend(frameon=False, fontsize=7, loc='upper left')
    fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.91]); footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 6b: games added per year, by ownership x platform class
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Games added per year', 'Stacked by ownership × platform class')
    ax = fig.add_axes([0.06, 0.14, 0.88, 0.68])
    combo = r.copy(); combo['combo'] = combo['ownership'] + ' · ' + combo['system_type']
    order_combo = [f'{o} · {s}' for o in ['Paid', 'Free', 'Friend/Family'] for s in ['PC', 'Console', 'Handheld']]
    palette = {'Paid · PC': '#C55A11', 'Paid · Console': '#E8914A', 'Paid · Handheld': '#F4B183',
               'Free · PC': '#8E5BD0', 'Free · Console': '#B18CF0', 'Free · Handheld': '#D4C2F5',
               'Friend/Family · PC': '#4C4C4C', 'Friend/Family · Console': '#8C8C8C', 'Friend/Family · Handheld': '#C4C4C4'}
    add = combo.groupby(['added_year', 'combo']).size().unstack(fill_value=0)
    add = add.reindex(columns=[c for c in order_combo if c in add.columns])
    bottom = np.zeros(len(add))
    for c in add.columns:
        ax.bar(add.index, add[c], bottom=bottom, color=palette.get(c, '#999'), label=c, width=.7); bottom += add[c].values
    ax.legend(frameon=False, fontsize=6.5, ncol=4, loc='upper left'); ax.set_ylabel('Games added')
    footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 7: time played (last 365 days)
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    s365 = D.daily_hours(log, 365, end=max(today, pd.Timestamp(datetime.date.today()))); start = s365.index[0]
    header(fig, 'Time played', f'{start:%b %d, %Y} – {s365.index[-1]:%b %d, %Y}')
    ax = fig.add_axes([0.06, 0.66, 0.90, 0.22])
    real = log[log['real'] == 1].groupby('date')['hours'].sum().reindex(s365.index, fill_value=0)
    ax.bar(s365.index, s365.values, color=ORANGE, width=1, label='All logged'); (ax.bar(real.index, real.values, color=PURPLE, width=1, label='Flagged Real') if real.sum() > 0 else None)
    ax.plot(s365.index, s365.rolling(7, min_periods=1).mean(), color=DARK, lw=1.2, label='7-day average')
    ax.plot(s365.index, s365.rolling(28, min_periods=1).mean(), color='#4F9DE8', lw=1.4, label='28-day average')
    ax.legend(frameon=False, fontsize=7, ncol=4); ax.set_title('Hours per day', loc='left'); ax.set_ylabel('Hours')
    ax = fig.add_axes([0.06, 0.38, 0.90, 0.21])
    ax.plot(s365.index, s365.cumsum(), color=DARK); ax.set_title('Cumulative hours and games played', loc='left'); ax.set_ylabel('Hours')
    fp_all = np.sort(log.groupby('game')['date'].min().dropna().values)
    cum_games = np.searchsorted(fp_all, s365.index.values, side='right')
    ax2 = ax.twinx(); ax2.spines['right'].set_visible(True)
    ax2.plot(s365.index, cum_games, color=PURPLE, lw=1.2); ax2.set_ylabel('Games (cumulative)', color=PURPLE); ax2.tick_params(axis='y', colors=PURPLE)
    # weekday box + range + calendar
    wd = s365.groupby(s365.index.weekday)
    ax = fig.add_axes([0.06, 0.07, 0.19, 0.22])
    ax.boxplot([v.values for _, v in wd], tick_labels=['M', 'T', 'W', 'T', 'F', 'S', 'S'], showfliers=False, patch_artist=True,
               boxprops=dict(facecolor='#F4B183', color=ORANGE), medianprops=dict(color=DARK))
    ax.plot(range(1, 8), [v.mean() for _, v in wd], 'o', color=PURPLE, ms=4); ax.set_title('Hours by weekday (dot = mean)', loc='left')
    ax = fig.add_axes([0.29, 0.07, 0.19, 0.22])
    wmeans = np.array([v.mean() for _, v in wd]); wstds = np.array([v.std() for _, v in wd])
    xs_wd = range(1, 8)
    ax.plot(xs_wd, wmeans, color=PURPLE, marker='o', ms=4)
    ax.fill_between(xs_wd, np.maximum(0, wmeans - wstds), wmeans + wstds, color=PURPLE, alpha=.22)
    ax.set_xticks(xs_wd); ax.set_xticklabels(['M', 'T', 'W', 'T', 'F', 'S', 'S']); ax.set_title('Weekday range (±1 SD)', loc='left')
    ax = fig.add_axes([0.52, 0.07, 0.44, 0.22])
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

    # ---------------- Page 7b: frequency of hours played
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    full_idx = pd.date_range(log['date'].min(), log['date'].max())
    daily_all = log.groupby('date')['hours'].sum().reindex(full_idx, fill_value=0.0)
    played_days = daily_all[daily_all > 0]
    xs_h = list(range(1, 11))
    pct_all = [float((daily_all <= x).mean() * 100) for x in xs_h]
    pct_played = [float((played_days <= x).mean() * 100) for x in xs_h]
    header(fig, 'Frequency of hours played', 'Cumulative % of days at or under X hours played')
    ax = fig.add_axes([0.08, 0.14, 0.86, 0.68])
    ax.plot(xs_h, pct_all, marker='o', color=ORANGE, label='% of all days')
    ax.plot(xs_h, pct_played, marker='o', color=PURPLE, label='% of days played')
    ax.set_xticks(xs_h); ax.set_xlabel('Up to X hours per day'); ax.set_ylabel('% of days'); ax.set_ylim(0, 100)
    ax.legend(frameon=False, fontsize=8)
    footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 8: hours by ZP opinion & score vs hours
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Hours played', 'Hours by Zero Punctuation opinion, and how hours relate to score')
    ax = fig.add_subplot(2, 1, 1)
    zh = g.groupby('zero_punctuation').agg(hours=('hours', 'sum')).reindex(['Best', 'Good', 'Neutral', 'Bland', 'Bad', 'Worst']).fillna(0)
    ax.bar(zh.index, zh['hours'], color=PURPLE); ax.set_title('Hours by Zero Punctuation opinion', loc='left'); ax.set_ylabel('Hours')
    ax = fig.add_subplot(2, 1, 2)
    p = g[g['hours'] > 0]
    a, b, r2, xs, ys = D.regression(p['my_score'] * 10, p['hours'], log_y=True)
    ax.scatter(p['my_score'] * 10 + np.random.default_rng(1).uniform(-1.5, 1.5, len(p)), p['hours'], s=9, color=DARK, alpha=.6)
    xx = np.linspace(10, 100, 50); ax.plot(xx, np.exp(a + b * xx), color=ORANGE, lw=2)
    ax.set_yscale('log'); ax.set_xlabel('My score'); ax.set_ylabel('Hours (log)'); ax.set_title(f'My score vs. hours played · exponential fit R² = {r2:.2f}', loc='left')
    fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.91]); footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 8b: top series detail
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Top series', 'Hours, games owned and played per series; how concentrated hours are in the top 10')
    hours_by_series = g.groupby('series')['hours'].sum()
    owned_by_series = g.groupby('series')['title'].count()
    played_by_series = g.groupby('series')['played'].sum()
    top_s = hours_by_series.sort_values().tail(10)
    ax = fig.add_axes([0.14, 0.12, 0.50, 0.72])
    y = np.arange(len(top_s))
    ax.barh(y, top_s.values, color=ORANGE, height=.6)
    ax.set_yticks(y); ax.set_yticklabels(top_s.index, fontsize=8); ax.set_xlabel('Hours')
    axn = ax.twiny()
    axn.plot(owned_by_series.reindex(top_s.index), y, 'o-', color=PURPLE, ms=5, lw=1, label='Games owned')
    axn.plot(played_by_series.reindex(top_s.index), y, 'o-', color=DARK, ms=5, lw=1, label='Games played')
    axn.set_xlabel('Games', fontsize=8); axn.legend(frameon=False, fontsize=7, loc='lower right')
    top10_set = set(top_s.index)
    g_top, g_all = len(g[g['series'].isin(top10_set)]), len(g)
    h_top, h_all = float(top_s.sum()), float(g['hours'].sum())
    for i, (lbl, a_, b_, fmt_) in enumerate([('Games', g_top, g_all - g_top, '{:.0f}'), ('Hours', h_top, h_all - h_top, '{:,.0f}')]):
        ax2 = fig.add_axes([0.68 + i * 0.16, 0.5, 0.14, 0.3])
        ax2.pie([a_, b_], colors=[ORANGE, GREY], startangle=90, counterclock=False, wedgeprops=dict(width=.45, edgecolor='white'))
        ax2.text(0, 0, f'{fmt_.format(a_)}\n{fmt_.format(b_)}', ha='center', va='center', fontsize=8, fontweight='bold')
        ax2.set_title(lbl, fontsize=9)
    fig.text(0.68, 0.42, f'Top 10 series = {g_top} of {g_all} games ({g_top / g_all * 100:.0f}%)\n'
                          f'but {h_top:,.0f} of {h_all:,.0f} hours ({h_top / h_all * 100:.0f}%)', fontsize=9, color=DARK)
    fig.text(0.68, 0.15, 'Orange = top 10 series   ·   Grey = everything else', fontsize=7, color=GREY)
    footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 8c: Zero Punctuation vs. my score
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Zero Punctuation vs. my score', 'My score band, grouped by ZP opinion — do I agree with the reviewer?')
    zp_order = ['Worst', 'Bad', 'Bland', 'Neutral', 'Good', 'Best']
    bands = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]
    zp_cmap = LinearSegmentedColormap.from_list('rg', ['#C0392B', '#F4B183', '#FFE699', '#A9D18E', '#538135'])
    ax = fig.add_axes([0.1, 0.14, 0.8, 0.66])
    bottom = np.zeros(len(zp_order))
    for i, (lo, hi) in enumerate(bands):
        vals = []
        for zp in zp_order:
            sub = g.loc[g['zero_punctuation'] == zp, 'my_score'].dropna()
            vals.append(float(((sub >= lo) & (sub <= hi)).sum() / len(sub) * 100) if len(sub) else 0.0)
        ax.bar(zp_order, vals, bottom=bottom, color=zp_cmap(i / (len(bands) - 1)), label=f'{lo}-{hi}')
        bottom += np.array(vals)
    ax.set_ylabel('% of games'); ax.legend(title='My score', frameon=False, fontsize=7, ncol=5, loc='upper center', bbox_to_anchor=(0.5, 1.14))
    footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Page 9: soundtrack ownership (the old workbook's "Game Statistics by Soundtrack Ownership")
    ST = D.soundtrack(g); OWN_C, NOT_C = ORANGE, GREY
    fig = plt.figure(figsize=(11, 8.5)); n += 1
    header(fig, 'Soundtrack ownership', f"{ST[1]['games']} games with a soundtrack owned vs. {ST[0]['games']} without")
    ax = fig.add_subplot(2, 2, 1); xs = np.arange(10); w = .38
    ax.bar(xs - w / 2, [v * 100 for v in ST[1]['mc_dist']], w, color=OWN_C, label='Owned')
    ax.bar(xs + w / 2, [v * 100 for v in ST[0]['mc_dist']], w, color=NOT_C, label='Not owned')
    ax.set_xticks(xs); ax.set_xticklabels([f'{10 * k + 1}-{10 * k + 10}' if k else '0-10' for k in range(10)], fontsize=6.5)
    ax.set_ylabel('% of games'); ax.set_title('Metacritic distribution', loc='left'); ax.legend(frameon=False, fontsize=7)
    ax = fig.add_subplot(2, 2, 2); names = list(D.SCORE_COLS); xs = np.arange(len(names))
    for off, key, c_, lab in [(-w / 2, 1, OWN_C, 'Owned'), (w / 2, 0, NOT_C, 'Not owned')]:
        vals = [ST[key]['scores'][k_] or 0 for k_ in names]
        ax.bar(xs + off, vals, w, color=c_, label=lab)
        for x_, v_ in zip(xs + off, vals): ax.text(x_, v_ + 1, f'{v_:.0f}', ha='center', fontsize=6.5)
    ax.set_xticks(xs); ax.set_xticklabels(names, rotation=25, ha='right', fontsize=7); ax.set_ylim(0, 118)
    ax.set_title('Average scores (0-100)', loc='left'); ax.legend(frameon=False, fontsize=7, ncol=2, loc='upper right')
    for k_, (title, key, fmt_) in enumerate([('Games', 'games', '{:.0f}'), ('Hours played', 'hours', '{:,.0f}')]):
        ax = fig.add_subplot(2, 4, 5 + 2 * k_ if k_ == 0 else 7)
        vals = [ST[1][key], ST[0][key]]
        ax.pie(vals, colors=[OWN_C, NOT_C], startangle=90, counterclock=False, wedgeprops=dict(width=.45, edgecolor='white'))
        ax.text(0, 0, '\n'.join(fmt_.format(v) for v in vals), ha='center', va='center', fontsize=8, fontweight='bold')
        ax.set_title(title, loc='center', fontsize=9)
    fig.text(0.5, 0.06, 'Orange = soundtrack owned   ·   Grey = not owned', ha='center', fontsize=8, color=GREY)
    fig.tight_layout(rect=[0.02, 0.08, 0.98, 0.91]); footer(fig, n); pdf.savefig(fig); plt.close(fig)

    # ---------------- Collage pages (only if covers present): landscape, 20 x 9 per page like the workbook.
    # Each page is composited into ONE small image first (PIL) - far smaller/faster than 180 separate figure images.
    ordered = g.sort_values(['series', 'release_date'])
    if '--all' not in sys.argv: ordered = ordered[ordered['played']]
    paths = [p for p in (cover_path(x) for x in ordered['title']) if p]
    COLS, ROWS, TW, TH = 20, 9, 72, 108
    for pg in range(0, len(paths), COLS * ROWS):
        sheet = np.full((ROWS * TH, COLS * TW, 3), 255, np.uint8)
        for k, p in enumerate(paths[pg:pg + COLS * ROWS]):
            r_, c_ = divmod(k, COLS); sheet[r_ * TH:(r_ + 1) * TH, c_ * TW:(c_ + 1) * TW] = load_cover(p, TW, TH)
        sheet &= 0xF8                       # 5 bits/channel: invisible at this size, compresses much better in the PDF
        fig = plt.figure(figsize=(11, 8.5)); n += 1
        ax = fig.add_axes([1 / 22, 1 - 0.103 - 0.75 / 8.5 * ROWS, 0.5 / 11 * COLS, 0.75 / 8.5 * ROWS]); ax.axis('off')
        ax.imshow(sheet, aspect='auto', interpolation='lanczos')
        fig.text(0.5, 0.045, f'Collection · {len(paths)} covers', ha='center', fontsize=8, color=GREY); footer(fig, n); pdf.savefig(fig); plt.close(fig)
print('wrote', OUT)
