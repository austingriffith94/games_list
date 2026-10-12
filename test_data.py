"""Data sanity tests: internal consistency of the derived numbers. These hold however the data grows, so they
do not break when you add games or log time (the old workbook-parity snapshot lives in docs/archive/verify)."""
import data as D

t = D.load()
g, r, log, scale = D.build(t)
s = D.summary(g, r, log, scale)

# counts agree with each other and with the tables
assert s['games'] == len(r) and s['unique_games'] == len(g) == r['title'].nunique()
assert s['unique_games'] <= s['games']
assert s['games_played'] <= s['games'] and s['unique_played'] <= s['unique_games']
assert s['unique_played'] <= s['games_played']
assert s['backlog'] == s['unique_games'] - s['unique_played']
assert abs(s['total_hours'] - log['hours'].sum()) < 1e-9 and s['total_hours'] > 0
assert (log['hours'] > 0).all()
assert not log.duplicated(['date', 'game', 'system']).any()

# every score average is a plausible 0-100 figure (catches an out-of-scale value like IGN = 84 on a 0-10 scale)
for k, v in s['scores'].items():
    assert 0 < v <= 100, (k, v)
for col in ('my_score', 'metacritic', 'pc_gamer', 'gamespot', 'ign', 'destructoid', 'game_informer'):
    c = t['games'][col].dropna()
    assert (c >= 0).all() and (c <= 100).all(), (col, c.max())

# matrices: row, column and grand totals add up
for dim in ('genre', 'camera_view'):
    m = D.matrix(r, dim, list(t['ref_genre' if dim == 'genre' else 'ref_view']['name']))
    body = m.drop(index='Total', columns='Total')
    assert (body.sum(axis=1) == m['Total'].iloc[:-1]).all() and (body.sum(axis=0) == m.loc['Total'].iloc[:-1]).all()
    assert m.loc['Total', 'Total'] == s['games'] == body.values.sum(), dim

# GOTY vote share: a share exists exactly when the game has votes, and is a percentage. A vote for a year
# missing from lk_goty_yearlyvotes fails here, which is the cue to add that year's total.
v = g[g['goty_votes'].notna()]
assert v['goty_share'].notna().all(), list(v.loc[v['goty_share'].isna(), 'title'])
assert ((v['goty_share'] > 0) & (v['goty_share'] <= 100)).all()
assert g.loc[g['goty_votes'].isna(), 'goty_share'].isna().all()

print('ALL DATA TESTS PASSED')
print(s)
