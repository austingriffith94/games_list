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
    t['holidays'] = set(pd.read_sql('select holidays from lk_holidaystable', con)['holidays'])
    con.close()
    global SYSTEMS
    SYSTEMS = list(t['ref_system']['name'])   # display order comes from the reference table
    for c in ['date']:
        t['play_log'][c] = pd.to_datetime(t['play_log'][c])
    for c in ['original_release_date', 'version_release_date', 'added_date']:
        t['releases'][c] = pd.to_datetime(t['releases'][c])
    return t


def _datedif_years(start, end):
    """Excel DATEDIF(start, end, "y"): complete years elapsed. NaN if either date is missing
    or end precedes start (matches the workbook's IFERROR(...,0) callers handling the latter)."""
    years = end.dt.year - start.dt.year
    before_anniversary = (end.dt.month < start.dt.month) | ((end.dt.month == start.dt.month) & (end.dt.day < start.dt.day))
    out = years - before_anniversary.astype(int)
    out = out.where(start.notna() & end.notna() & (end >= start))
    return out


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
    # case-insensitive, like Excel's SUMIFS: two titles have 'Need for Speed' vs 'Need For Speed' series text
    g['hours_per_series'] = g.groupby(g['series'].str.lower())['hours'].transform('sum')
    g['Hours Per Series Rank'] = g['hours_per_series'].rank(method='min', ascending=False)
    g['Normalized Playthroughs'] = np.where(
        g['hours'] == 0, 0.0,
        np.where(g['average_playthrough'].isna(), g['playthroughs'].fillna(0).clip(lower=1),
                 g['hours'] / g['average_playthrough']))
    g['Release Year vs First Played'] = _datedif_years(g['release_date'], g['first_played']).fillna(0).where(g['played'])
    g['First Played vs Last Played'] = _datedif_years(g['first_played'], g['last_played'])
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


CAL_STAT_NAMES = ['Max', '75%', 'Avg', 'Median', '25%', 'Min']


def calendar_stats(s, include_zero=False):
    """Max / 75% / Avg / Median / 25% / Min of a daily-hours series (the calendar heat map's stats block).
    Played days only by default; include_zero=True counts every day in the window, as the workbook does.
    Percentiles are PERCENTILE.INC (linear interpolation), not the workbook's PERCENTILE.EXC."""
    v = s if include_zero else s[s > 0]
    if len(v) == 0: return dict.fromkeys(CAL_STAT_NAMES, 0.0)
    q = v.quantile
    return {'Max': float(v.max()), '75%': float(q(.75)), 'Avg': float(v.mean()), 'Median': float(v.median()),
            '25%': float(q(.25)), 'Min': float(v.min())}


def calendar_windows(log, end=None, years=4, days=365):
    """The heat map comparison's windows (TimeHeatComp): the last `days` days ending at `end`, then the same
    window shifted back one year at a time. Newest first, each as (start, end, daily-hours Series).
    A window that begins before the first log row is dropped rather than shown part-empty."""
    end = pd.Timestamp(end) if end is not None else log['date'].max()
    out = []
    for k in range(years):
        e = end - pd.DateOffset(years=k)
        s = daily_hours(log, days, end=e)
        if s.index[0] >= log['date'].min(): out.append((s.index[0], e, s))
    return out


def bucket_label(lo, hi, open_end=100):
    if hi - lo == 1: return f'{lo:g}'
    if hi >= open_end: return f'{lo:g}<'
    return f'{lo:g}-{hi - 1:g}'


def bucket_matrix(score, value, edges):
    """Cross-tab: My Score 1-10 (rows) x bucketed value (cols), counted Start <= v < End
    (REPORT_LOGIC.md §3.4). `edges` is a list of n+1 boundaries for n buckets."""
    iv = pd.IntervalIndex.from_breaks(edges, closed='left')
    bins = pd.cut(value, edges, right=False)
    m = pd.crosstab(score, bins).reindex(index=range(1, 11), columns=iv, fill_value=0)
    m.columns = [bucket_label(lo, hi) for lo, hi in zip(edges[:-1], edges[1:])]
    return m


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


# ----------------------------------------------------------------------------- HeatMapScore (REPORT_LOGIC.md section 2)
def heatmap(g, y_name='Game Informer', x_name='My Score', y_int=0.25, x_int=1.0, scale=None, vmax=10.0, vmin=0.0, display=1.0):
    """2-D binned count of one score source (Y) against another (X) plus the least-squares line of Y on X.
    Bins step in *raw* units (interval x scale) so a 0-100 source rescales automatically; a cell counts
    low <= v < high, except the top bin on each axis, which is the exact maximum (the workbook's low*1000 trick).
    Rows run from the top score down to `vmin` (so there is one more row than Max/interval), columns left to right."""
    sc = scale or {'My Score': 1, 'Metacritic': 10, 'IGN': 1, 'Game Informer': 1, 'GameSpot': 1, 'Destructoid': 1, 'PC Gamer': 10}
    xs_, ys_ = float(sc[x_name]), float(sc[y_name])
    xc, yc = SCORE_COLS[x_name], SCORE_COLS[y_name]
    d = g[[xc, yc]].dropna().astype(float)
    x, y = d[xc].values, d[yc].values
    nx, ny = int(round((vmax - vmin) / x_int)) + 1, int(round((vmax - vmin) / y_int)) + 1
    x_lows = np.round(vmin * xs_ + np.arange(nx) * x_int * xs_, 9)                 # ascending, left to right
    y_lows = np.round(vmax * ys_ - np.arange(ny) * y_int * ys_, 9)                 # descending, top to bottom
    xi = np.searchsorted(x_lows, np.round(x, 9), side='right') - 1
    yi = ny - 1 - (np.searchsorted(y_lows[::-1], np.round(y, 9), side='right') - 1)
    ok = (xi >= 0) & (np.round(y, 9) >= y_lows[-1]) & (yi >= 0)
    grid = np.zeros((ny, nx), dtype=int)
    np.add.at(grid, (yi[ok], xi[ok]), 1)
    if len(x) > 1 and x.std() > 0:
        slope, intercept = np.polyfit(x, y, 1)
        rsq = float(np.corrcoef(x, y)[0, 1] ** 2)
    else:
        slope = intercept = rsq = float('nan')
    stride_x, stride_y = display * xs_, display * ys_
    return dict(grid=grid, x_lows=x_lows, y_lows=y_lows, n=len(d), rsq=rsq, slope=float(slope), intercept=float(intercept),
                x_name=x_name, y_name=y_name, x_int=x_int, y_int=y_int, x_scale=xs_, y_scale=ys_,
                x_labels=[(f'{v / xs_:g}' if abs(v % stride_x) < 1e-9 else '') for v in x_lows],
                y_labels=[(f'{v / ys_:g}' if abs(v % stride_y) < 1e-9 else '') for v in y_lows],
                placed=int(grid.sum()))


# ----------------------------------------------------------------------------- Stats sheet tables (REPORT_LOGIC.md section 3)
PT_EDGES = [0, 1, 2, 3, 4, 5, 10, 15, 100]                 # Playthroughs and Normalized Playthroughs
REL_EDGES = [0, 1, 2, 3, 4, 6, 10, 20, 100]                # Release Year vs First Played
# The workbook's own last bucket edges are [.. 4,6) [7,10), which drops a gap of exactly 6 (5 games). Closed here.
LAST_EDGES = [0, 1, 2, 4, 6, 10, 15, 20, 100]              # First Played vs Last Played
STAT_SOURCES = ['My Score', 'Metacritic', 'GameSpot', 'Game Informer', 'IGN', 'Destructoid', 'PC Gamer']   # workbook order
ZP_ORDER = ['Best', 'Good', 'Neutral', 'Bland', 'Bad', 'Worst']


def stats_tables(t, g, scale=None):
    """The fourteen tables of the workbook's Stats sheet, as DataFrames keyed by their workbook names.
    Scores are in each source's own raw units (Metacritic/PC Gamer 0-100, the rest 0-10)."""
    sc = scale or dict(zip(t['lk_scorescale']['type'], t['lk_scorescale']['scale']))
    raw = {n: g[SCORE_COLS[n]].astype(float) for n in STAT_SOURCES}
    out = {}
    # StatTable: pandas' var/skew/kurt are the sample-corrected forms Excel's VAR.S/SKEW/KURT use
    out['StatTable'] = pd.DataFrame({n: {'Variance': s.var(), 'Std. Deviation': s.std(), 'Mean': s.mean(), 'Median': s.median(),
                                         'Excess Kurtosis': s.kurt(), 'Skewness': s.skew()} for n, s in raw.items()})
    out['CorrelationMatrix'] = pd.DataFrame(raw).corr()
    # ScoreDistributionTable: share of games with scale*(s-1) < v <= scale*s
    sd = {}
    for n in ['My Score', 'GameSpot', 'IGN', 'Game Informer']:
        v = raw[n].dropna()
        sd[n] = [float(((v > sc[n] * (k - 1)) & (v <= sc[n] * k)).sum() / len(v)) for k in range(1, 11)]
    out['ScoreDistributionTable'] = pd.DataFrame(sd, index=range(1, 11))
    # YearsPerScore: mean year per My Score 1-10, plus the Top 20 by personal rank
    top20 = g['title'].isin(set(t['top_rank'].loc[t['top_rank']['rank'] <= 20, 'title']))
    yc = {'Release Year': 'release_year', 'Added Year': 'added_year', 'First Played': 'first_year', 'Last Played': 'last_year'}
    yps = {k: [g.loc[g['my_score'] == s, c].mean() for s in range(1, 11)] + [g.loc[top20, c].mean()] for k, c in yc.items()}
    out['YearsPerScore'] = pd.DataFrame(yps, index=[str(i) for i in range(1, 11)] + ['Top 20'])
    # SoundtrackStats / SoundtrackDistributionTable
    st = {}
    for flag, label in ((1, 'Owned'), (0, 'Not Owned')):
        s = g[g['soundtrack_owned'] == flag]
        col = {'Hours': float(s['hours'].sum()), 'Games': float(len(s))}
        for n in ['My Score', 'Metacritic', 'IGN', 'Game Informer', 'GameSpot', 'Destructoid', 'PC Gamer']:
            col[n] = float(s[SCORE_COLS[n]].mean() * 10 / sc[n])
        st[label] = col
    out['SoundtrackStats'] = pd.DataFrame(st)
    sdist = {}
    for flag, label in ((1, 'Owned'), (0, 'Not Owned')):
        mc = g.loc[g['soundtrack_owned'] == flag, 'metacritic'].dropna()
        sdist[label] = [float(((mc > sc['Metacritic'] * (k - 1)) & (mc <= sc['Metacritic'] * k)).sum() / len(mc)) for k in range(1, 11)]
    out['SoundtrackDistributionTable'] = pd.DataFrame(sdist, index=range(1, 11))
    # ZeroPunctuationQualityBuckets: two different denominators on purpose (all rated games vs games actually played)
    zp = g['zero_punctuation'].str.lower()
    zq = pd.DataFrame(index=ZP_ORDER)
    zq['Games'] = [int(((zp == b.lower()) & g['my_score'].notna()).sum()) for b in ZP_ORDER]
    zq['Frequency'] = zq['Games'] / zq['Games'].sum()
    zq['Games Played'] = [int(((zp == b.lower()) & g['first_played'].notna()).sum()) for b in ZP_ORDER]
    zq['Frequency Played'] = zq['Games Played'] / zq['Games Played'].sum()
    zq['Hours'] = [float(g.loc[zp == b.lower(), 'hours'].sum()) for b in ZP_ORDER]
    out['ZeroPunctuationQualityBuckets'] = zq
    # ZeroPunctuationDistribution: bands are inclusive at both ends: [1,2] [3,4] [5,6] [7,8] [9,10]
    zd = pd.DataFrame({b: [int(((zp == b.lower()) & (g['my_score'] >= hi - 1) & (g['my_score'] <= hi)).sum()) for hi in (2, 4, 6, 8, 10)]
                       for b in ZP_ORDER}, index=['1-2', '3-4', '5-6', '7-8', '9-10'])
    out['ZeroPunctuationDistribution'] = zd
    # SeriesRankStats / SeriesRankTotalStats. Series text compares case-insensitively (SUMIFS/COUNTIF), so group on lower().
    key = g['series'].str.lower()
    sr = g.assign(_k=key).groupby('_k', sort=False).agg(
        Series=('series', 'first'), Hours=('hours', 'sum'), **{'Games Owned': ('title', 'count'), 'Games Played': ('played', 'sum'),
                                                              'Rank Equivalent': ('Hours Per Series Rank', 'min')})
    sr = sr.sort_values('Hours', ascending=False, kind='stable').head(10).reset_index(drop=True)
    sr.index = range(1, len(sr) + 1); sr.index.name = 'Rank'
    sr['Games Played'] = sr['Games Played'].astype(int); sr['Rank Equivalent'] = sr['Rank Equivalent'].astype(int)
    out['SeriesRankStats'] = sr[['Series', 'Rank Equivalent', 'Games Owned', 'Games Played', 'Hours']]
    tot_g, tot_p, tot_h = len(g), int(g['played'].sum()), float(g['hours'].sum())
    top_g, top_p, top_h = int(sr['Games Owned'].sum()), int(sr['Games Played'].sum()), float(sr['Hours'].sum())
    out['SeriesRankTotalStats'] = pd.DataFrame({'Games Owned': [top_g, tot_g - top_g], 'Games Played': [top_p, tot_p - top_p],
                                                'Hours': [top_h, tot_h - top_h]}, index=['Top 10 Series', 'Other'])
    # the four cross-tabs: bucket (rows) x My Score 1-10 (columns), counted Start <= v < End
    for name, col, edges in (('PlaythroughVsScoreBuckets', 'playthroughs', PT_EDGES), ('NormPlayVsScoreBuckets', 'Normalized Playthroughs', PT_EDGES),
                             ('ReleaseVsFirstBuckets', 'Release Year vs First Played', REL_EDGES), ('LastVsFirstBuckets', 'First Played vs Last Played', LAST_EDGES)):
        m = bucket_matrix(g['my_score'], g[col], edges).T
        m['Total'] = m.sum(axis=1)
        out[name] = m
    return out


if __name__ == '__main__':
    t = load()
    g, r, log, scale = build(t)
    s = summary(g, r, log, scale)
    print(s)
