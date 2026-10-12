"""HaloRank scoring (REPORT_LOGIC.md section 1). Stdlib only, so app.py can use it without pandas.

A level has nine ratings (0-5). All nine NULL means the level is *unrated*: it has no score and no
tier, and is left out of every average (the workbook scored these 0.0 and filed them under F).
"""
RATING_COLS = ['enemy', 'weapon_vehicle', 'design_set_piece', 'replayability_pacing', 'difficulty', 'visual',
               'music', 'story', 'enjoyment']
RATING_LABELS = ['Enemy', 'Weapon/Vehicle', 'Design/Set Piece', 'Replayability/Pacing', 'Difficulty', 'Visual',
                 'Music', 'Story', 'Enjoyment']
RATING_LO, RATING_HI = 0, 5
# Fallbacks only - the live values come from lk_haloranksectionweights / lk_tierlistscoring.
DEFAULT_WEIGHTS = [5, 5, 5, 5, 2, 3, 2, 2, 5]
DEFAULT_TIERS = [('S', 5, 5.0), ('A', 4, 4.5), ('B', 3, 4.0), ('C', 2, 3.0), ('D', 1, 2.0), ('F', 0, 1.0)]   # rank, score, upper


def load_scoring(con):
    """(weights, tiers) from the lookup tables. Weights pair to RATING_COLS by *position* - the label
    text in the weights table deliberately differs from the column names, so never join on it."""
    try:
        w = [float(r[0]) for r in con.execute('SELECT weight FROM lk_haloranksectionweights ORDER BY rowid')][:9]
        t = [(r[0], r[1], float(r[2])) for r in con.execute('SELECT rank, score, upper FROM lk_tierlistscoring ORDER BY rowid')]
    except Exception:
        return DEFAULT_WEIGHTS, DEFAULT_TIERS
    return (w if len(w) == 9 else DEFAULT_WEIGHTS), (t or DEFAULT_TIERS)


def is_rated(row):
    return all(row.get(c) is not None for c in RATING_COLS)


def variable_score(row, weights):
    """SUMPRODUCT(ratings, weights) / SUM(weights); None for an unrated level."""
    if not is_rated(row):
        return None
    return sum(row[c] * w for c, w in zip(RATING_COLS, weights)) / sum(weights)


def tier_of(vs, tiers):
    """Upper-inclusive bands: (4.5,5]=S ... <=1=F. Returns (letter, tier score) or None above the top band
    (impossible with ratings capped at 5)."""
    if vs is None:
        return None
    cand = [t for t in tiers if t[2] >= vs - 1e-12]
    if not cand:
        return None
    letter, score, _ = min(cand, key=lambda t: t[2])
    return letter, score


def score_rows(rows, weights, tiers):
    """Adds variable_score, tier and tier_score to each level dict (None when unrated)."""
    out = []
    for r in rows:
        vs = variable_score(r, weights)
        tr = tier_of(vs, tiers)
        out.append({**r, 'variable_score': vs, 'tier': tr[0] if tr else None, 'tier_score': tr[1] if tr else None})
    return out


def game_summary(scored, tiers):
    """Per-game HaloRankLetterScore + HaloRankNumberScore, over *rated* levels only."""
    letters = [t[0] for t in tiers]
    games = {}
    for r in scored:
        games.setdefault(r['game'], []).append(r)
    out = []
    for name, lv in games.items():
        rated = [x for x in lv if x['variable_score'] is not None]
        n = len(rated)
        out.append(dict(
            game=name, series_order=lv[0]['series_order'], levels=len(lv), rated=n,
            avg_score=sum(x['variable_score'] for x in rated) / n if n else None,
            avg_tier_score=sum(x['tier_score'] for x in rated) / n if n else None,
            tiers={l: sum(1 for x in rated if x['tier'] == l) for l in letters},
            ratings={c: (sum(x[c] for x in rated) / n if n else None) for c in RATING_COLS}))
    return sorted(out, key=lambda g: g['series_order'])
