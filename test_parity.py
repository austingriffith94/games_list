"""Parity tests: the rebuilt numbers must match the workbook / PDF figures."""
import data as D

t = D.load()
g, r, log, scale = D.build(t)
s = D.summary(g, r, log, scale)

# Summary sheet (cached values in the workbook)
assert s['games'] == 783 and s['games_played'] == 445 and s['unique_games'] == 656
assert s['unique_played'] == 405 and s['backlog'] == 251
assert abs(s['total_hours'] - 9747.5) < 1e-9
for k, v in {'My Score': 67, 'Metacritic': 80, 'GameSpot': 80, 'Destructoid': 81, 'Game Informer': 83,
             'PC Gamer': 81, 'IGN': 84}.items():
    assert round(s['scores'][k]) == v, (k, s['scores'][k])

# Genre x System matrix totals printed on PDF page 2
gm = D.matrix(r, 'genre', list(t['ref_genre']['name']))
pdf_genre_totals = [35, 152, 56, 25, 50, 14, 41, 7, 120, 175, 18, 38, 52]
assert list(gm.loc['Total'].iloc[:-1]) == pdf_genre_totals, list(gm.loc['Total'])
assert gm.loc['Total', 'Total'] == 783
pdf_sys = {'PS1': 3, 'PS2': 60, 'PCSX2': 34, 'PS4': 6, 'PS5': 2, 'Xbox': 26, 'Xbox 360': 92, 'Xbox One': 21,
           'Nintendo 64': 5, 'Nintendo Gamecube': 2, 'Nintendo Switch': 2, 'Wii': 12, 'Steam': 147, 'GOG': 108,
           'Origin': 16, 'EPIC': 130, 'Battle.net': 5, 'Prime Gaming': 6, 'Windows': 37, 'Gameboy': 20, 'PSP': 16,
           'Mobile': 33}
for k, v in pdf_sys.items():
    assert gm.loc[k, 'Total'] == v, (k, gm.loc[k, 'Total'], v)

# Camera view x System matrix
vm = D.matrix(r, 'camera_view', list(t['ref_view']['name']))
assert list(vm.loc['Total'].iloc[:-1]) == [175, 34, 107, 258, 78, 54, 77], list(vm.loc['Total'])
print('ALL PARITY TESTS PASSED')
print(s)
