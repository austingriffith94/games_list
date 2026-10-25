"""Total War: Warhammer III legendary lord scoring (docs/ACTION_PLAN_tww_lords.md). Stdlib only, like halo.py.

A campaign has seven ratings (0-5). All seven NULL means the campaign is *unrated*: it counts as played but has
no score or tier, and is left out of every average. A lord's score is their best rated campaign (or the average).
"""
import halo

GAME = 'Total War: Warhammer III'    # the games / play_log title, for the "h logged on WH3" context figure
RATING_COLS = ['mechanics', 'roster', 'start_position', 'challenge', 'narrative', 'late_game', 'enjoyment']
RATING_LABELS = ['Faction mechanics', 'Roster', 'Start position', 'Challenge', 'Narrative / lore', 'Late game', 'Enjoyment']
# Fallbacks only - the live values come from lk_twwratingweights / lk_tierlistscoring.
DEFAULT_WEIGHTS = [5, 5, 3, 3, 2, 4, 5]
RATING_LO, RATING_HI = halo.RATING_LO, halo.RATING_HI
tier_of = halo.tier_of


def load_scoring(con):
    """(weights, tiers). Weights pair to RATING_COLS by *position* (rowid), like HaloRank; tiers are shared with it."""
    _, tiers = halo.load_scoring(con)
    try:
        w = [float(r[0]) for r in con.execute('SELECT weight FROM lk_twwratingweights ORDER BY rowid')]
    except Exception:
        return DEFAULT_WEIGHTS, tiers
    return (w if len(w) == len(RATING_COLS) else DEFAULT_WEIGHTS), tiers


def is_rated(row):
    return all(row.get(c) is not None for c in RATING_COLS)


def campaign_score(row, weights):
    """SUMPRODUCT(ratings, weights) / SUM(weights); None for an unrated campaign."""
    if not is_rated(row):
        return None
    return sum(row[c] * w for c, w in zip(RATING_COLS, weights)) / sum(weights)


def score_rows(rows, weights, tiers):
    """Adds score, tier and tier_score to each campaign dict (None when unrated)."""
    out = []
    for r in rows:
        s = campaign_score(r, weights)
        tr = tier_of(s, tiers)
        out.append({**r, 'score': s, 'tier': tr[0] if tr else None, 'tier_score': tr[1] if tr else None})
    return out


def lord_scores(scored, tiers, how='best'):
    """{lord_id: {campaigns, rated, score, tier, best_id}} from scored campaign dicts.
    how='best' uses the best rated campaign (ties go to the later id); how='avg' the mean. best_id marks the
    campaign that sets the score in 'best' mode, and is the best campaign either way."""
    by = {}
    for c in scored:
        by.setdefault(c['lord_id'], []).append(c)
    out = {}
    for lid, cs in by.items():
        rated = [c for c in cs if c['score'] is not None]
        best = max(rated, key=lambda c: (c['score'], c['id']), default=None)
        if not rated: s = None
        elif how == 'avg': s = sum(c['score'] for c in rated) / len(rated)
        else: s = best['score']
        tr = tier_of(s, tiers)
        out[lid] = dict(campaigns=len(cs), rated=len(rated), score=s, tier=tr[0] if tr else None,
                        best_id=best['id'] if best else None)
    return out


def race_summary(lords, scored):
    """Per race, in race_game / race_order order: lords played / total, campaigns per mode, average of each rating
    over rated campaigns."""
    played = {c['lord_id'] for c in scored}
    by_lord = {}
    for c in scored:
        by_lord.setdefault(c['lord_id'], []).append(c)
    races = {}
    for l in sorted(lords, key=lambda l: (l['race_game'], l['race'].lower(), l['race_order'])):
        races.setdefault(l['race'], []).append(l)
    out = []
    for race, ls in races.items():
        cs = [c for l in ls for c in by_lord.get(l['id'], [])]
        rated = [c for c in cs if c['score'] is not None]
        modes = {}
        for c in cs:
            modes[c['mode']] = modes.get(c['mode'], 0) + 1
        out.append(dict(
            race=race, race_game=ls[0]['race_game'], lords=len(ls), played=sum(1 for l in ls if l['id'] in played),
            campaigns=len(cs), modes=modes, rated=len(rated),
            ratings={k: (sum(c[k] for c in rated) / len(rated) if rated else None) for k in RATING_COLS}))
    return sorted(out, key=lambda r: (r['race_game'], min(l['race_order'] for l in races[r['race']])))
