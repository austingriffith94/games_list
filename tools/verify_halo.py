"""Verify the decoded HaloRank logic against the workbook's own cached values. Stdlib only."""
import zipfile, re, xml.etree.ElementTree as ET
from collections import defaultdict

XLSM = r"C:\Users\austg\git\games_list\old_excel\games_list.xlsm"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

z = zipfile.ZipFile(XLSM)
ss = [ "".join(t.text or "" for t in si.iter(NS+"t"))
       for si in ET.fromstring(z.read("xl/sharedStrings.xml")) ]

def cells(sheet):
    out = {}
    for c in ET.fromstring(z.read(sheet)).iter(NS+"c"):
        r = c.get("r"); v = c.find(NS+"v"); t = c.get("t")
        val = None
        if v is not None:
            val = ss[int(v.text)] if t == "s" else v.text
        out[r] = val
    return out

S4 = cells("xl/worksheets/sheet4.xml")

def col(n):            # 1 -> A
    s = ""
    while n: n, r = divmod(n-1, 26); s = chr(65+r) + s
    return s

# --- decoded constants -------------------------------------------------------
WEIGHTS = [5, 5, 5, 5, 2, 3, 2, 2, 5]          # List!X12:X20, positional
TOTAL   = sum(WEIGHTS)                          # 34
TIERS   = [("S",5,5.0), ("A",4,4.5), ("B",3,4.0), ("C",2,3.0), ("D",1,2.0), ("F",0,1.0)]

def tier(vs):
    """INDEX(TierListScoring[Rank], MATCH(vs, TierListScoring[Upper], -1))

    MATCH over a descending column with match_type -1 returns the row holding the
    smallest Upper that is still >= the lookup value, so bands are upper-inclusive.
    """
    cand = [t for t in TIERS if t[2] >= vs]
    if not cand: return None                       # #N/A above the top bound
    name, score, _ = min(cand, key=lambda t: t[2])
    return name, score

# --- HaloRankMaster: B24:R109 -----------------------------------------------
# B Series Order, C Game, D Order, E Level, F Rank, G Score, H Variable Score,
# I..Q the nine ratings, R Notes
bad_vs = bad_rank = bad_score = rows = 0
per_game = defaultdict(list)
for row in range(25, 110):                      # 24 is the header
    game = S4.get("C%d" % row)
    if not game: continue
    ratings = [S4.get("%s%d" % (col(i), row)) for i in range(9, 18)]   # I..Q
    if any(x is None for x in ratings): continue
    ratings = [float(x) for x in ratings]
    rows += 1
    vs = sum(r*w for r, w in zip(ratings, WEIGHTS)) / TOTAL
    letter, tscore = tier(vs)
    cvs   = float(S4["H%d" % row])
    crank = S4["F%d" % row]
    cscore= float(S4["G%d" % row])
    if abs(vs - cvs)   > 1e-9: bad_vs += 1
    if letter != crank:        bad_rank += 1; print("  rank mismatch row", row, game, vs, letter, crank)
    if tscore != cscore:       bad_score += 1
    per_game[game].append((vs, tscore, letter))

print("HaloRankMaster level rows checked:", rows)
print("  Variable Score  mismatches:", bad_vs)
print("  Rank letter     mismatches:", bad_rank)
print("  Tier Score      mismatches:", bad_score)

# --- HaloRankLetterScore: B2:L10 --------------------------------------------
print("\nHaloRankLetterScore (per game):")
hdr = [S4.get("%s2" % col(i)) for i in range(7, 13)]     # G..L = S A B C D F
bad = 0
for row in range(3, 11):
    game = S4.get("C%d" % row)
    if not game: continue
    v = per_game[game]
    avg_vs = sum(x[0] for x in v)/len(v)
    avg_sc = sum(x[1] for x in v)/len(v)
    cnt = {h: sum(1 for x in v if x[2] == h) for h in hdr}
    c_avg_vs = float(S4["D%d" % row]); c_avg_sc = float(S4["E%d" % row])
    c_levels = int(float(S4["F%d" % row]))
    c_cnt = {h: int(float(S4["%s%d" % (col(i), row)])) for i, h in zip(range(7, 13), hdr)}
    ok = abs(avg_vs-c_avg_vs) < 1e-9 and abs(avg_sc-c_avg_sc) < 1e-9 \
         and len(v) == c_levels and cnt == c_cnt
    bad += not ok
    print("  %-22s levels %2d/%2d  avgVS %.4f/%.4f  avgRank %.4f/%.4f  tiers %s  %s"
          % (game, len(v), c_levels, avg_vs, c_avg_vs, avg_sc, c_avg_sc,
             "".join("%s%d" % (h, cnt[h]) for h in hdr), "OK" if ok else "MISMATCH"))
print("\nper-game mismatches:", bad)
