"""Derived data layer: replaces the ~90K workbook formulas with pandas over the SQLite tables."""
import os, sqlite3
import numpy as np
import pandas as pd

DB = os.environ.get('GAMELIST_DB', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gamelist.db'))
# Display order used by the workbook's summary matrices
SYSTEMS = ['PS1', 'PS2', 'PCSX2', 'PS4', 'PS5', 'Xbox', 'Xbox 360', 'Xbox One', 'Nintendo 64', 'Nintendo Gamecube',
           'Nintendo Switch', 'Wii', 'Steam', 'GOG', 'Origin', 'EPIC', 'Battle.net', 'Prime Gaming', 'Windows',
           'Gameboy', 'PSP', 'Mobile']
SCORE_COLS = {'My Score': 'my_score', 'Metacritic': 'metacritic', 'GameSpot': 'gamespot', 'Destructoid': 'destructoid',
              'Game Informer': 'game_informer', 'PC Gamer': 'pc_gamer', 'IGN': 'ign'}


def load(db=DB):
    con = sqlite3.connect(db)
    t = {n: pd.read_sql(f'select * from {n} order by rowid', con) for n in
         ['games', 'releases', 'play_log', 'lk_scorescale', 'lk_goty_yearlyvotes', 'ref_genre', 'ref_view', 'ref_style',
          'ref_system', 'ref_ownership', 'ref_release_type', 'ref_zp']}
    t['top_rank'] = pd.read_sql('select title, rank from top_rank order by rank', con)
    con.close()
    global SYSTEMS
    SYSTEMS = list(t['ref_system']['name'])   # display order comes from the reference table
    for c in ['date']:
        t['play_log'][c] = pd.to_datetime(t['play_log'][c])
    for c in ['original_release_date', 'version_release_date', 'added_date']:
        t['releases'][c] = pd.to_datetime(t['releases'][c])
    return t


def build(t):
    g, r, log = t['games'].copy(), t['releases'].copy(), t['play_log'].copy()
    scale = dict(zip(t['lk_scorescale']['type'], t['lk_scorescale']['scale']))

    # --- release level (title x system): what Year_Table's calc columns did
    agg = log.groupby(['game', 'system']).agg(hours=('hours', 'sum'), first_played=('date', 'min'),
                                              last_played=('date', 'max')).reset_index()
    r = r.merge(agg, left_on=['title', 'system'], right_on=['game', 'system'], how='left').drop(columns='game')
    r['hours'] = r['hours'].fillna(0.0)
    r['played'] = r['first_played'].notna()
    r['system_type'] = r['system'].map(dict(zip(t['ref_system']['name'], t['ref_system']['type'])))
    r['added_year'] = r['added_date'].dt.year
    r['first_year'] = r['first_played'].dt.year
    r['last_year'] = r['last_played'].dt.year
    r = r.merge(g[['title', 'genre', 'camera_view', 'graphic_style', 'series']], on='title', how='left')

    # --- game level: what GameTable's calc columns did
    gh = r.groupby('title').agg(hours=('hours', 'sum'), first_played=('first_played', 'min'),
                                last_played=('last_played', 'max'), release_date=('original_release_date', 'min'),
                                added_date=('added_date', 'min'), n_releases=('system', 'count')).reset_index()
    g = g.merge(gh, on='title', how='left')
    g['played'] = g['first_played'].notna()
    g['release_year'] = g['release_date'].dt.year
    g['first_year'] = g['first_played'].dt.year
    g['last_year'] = g['last_played'].dt.year
    g['added_year'] = g['added_date'].dt.year
    g['hours_per_series'] = g.groupby('series')['hours'].transform('sum')
    # score columns on a common 0-100 scale, as the Summary sheet does (value*10/scale)
    for name, col in SCORE_COLS.items():
        g[col + '_100'] = g[col] * 10 / scale[name]

    log = log.merge(r[['title', 'system', 'system_type']], left_on=['game', 'system'], right_on=['title', 'system'],
                    how='left').drop(columns='title')
    log = log.merge(g[['title', 'genre', 'my_score']], left_on='game', right_on='title', how='left').drop(columns='title')
    return g, r, log, scale


def summary(g, r, log, scale):
    total_h = float(log['hours'].sum())
    days = total_h / 24
    d, h = int(days), (days - int(days)) * 24
    out = {
        'games': len(r), 'games_played': int(r['played'].sum()), 'unique_games': len(g),
        'unique_played': int(g['played'].sum()), 'total_hours': total_h,
        'total_time': f'{d}d {h:.1f}h',
        'scores': {n: round(float(g[c + '_100'].mean()), 1) for n, c in SCORE_COLS.items()},
    }
    out['backlog'] = out['unique_games'] - out['unique_played']
    return out


def soundtrack(g):
    """Stats split by Soundtrack Owned (REPORT_LOGIC.md SoundtrackStats / SoundtrackDistributionTable).
    Returns {1: {...}, 0: {...}}: games, hours, mean of each score source on 0-100, and the share of
    Metacritic scores in each 10-point band (lo < v <= hi, upper-inclusive)."""
    out = {}
    for flag in (1, 0):
        s = g[g['soundtrack_owned'] == flag]
        mc = (s['metacritic_100']).dropna()
        out[flag] = dict(games=len(s), hours=float(s['hours'].sum()),
                         scores={n: (round(float(s[c + '_100'].mean()), 1) if s[c + '_100'].notna().any() else None)
                                 for n, c in SCORE_COLS.items()},
                         mc_dist=[float(((mc > 10 * k) & (mc <= 10 * (k + 1))).sum() / len(mc)) if len(mc) else 0.0 for k in range(10)])
    return out


def matrix(r, col, cols):
    """System x category count matrix of releases, with totals (the Summary sheet cross-tabs)."""
    m = pd.crosstab(r['system'], r[col]).reindex(index=SYSTEMS, columns=cols, fill_value=0)
    m['Total'] = m.sum(axis=1)
    m.loc['Total'] = m.sum()
    return m


def top10(t, n=10):
    return t['top_rank'].sort_values('rank').head(n)


def daily_hours(log, days=365, end=None):
    end = pd.Timestamp(end) if end is not None else log['date'].max()
    idx = pd.date_range(end - pd.Timedelta(days=days - 1), end)
    s = log.groupby('date')['hours'].sum().reindex(idx, fill_value=0.0)
    return s


def regression(x, y, log_y=False):
    m = x.notna() & y.notna() & (y > 0 if log_y else True)
    xs, ys = x[m].astype(float).values, y[m].astype(float).values
    if log_y:
        b, a = np.polyfit(xs, np.log(ys), 1)
        pred = np.exp(a + b * xs)
        ss = 1 - ((np.log(ys) - (a + b * xs)) ** 2).sum() / ((np.log(ys) - np.log(ys).mean()) ** 2).sum()
        return a, b, ss, xs, ys
    b, a = np.polyfit(xs, ys, 1)
    r2 = np.corrcoef(xs, ys)[0, 1] ** 2
    return a, b, r2, xs, ys


if __name__ == '__main__':
    t = load()
    g, r, log, scale = build(t)
    s = summary(g, r, log, scale)
    print(s)
