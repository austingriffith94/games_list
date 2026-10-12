"""Verify the remaining Stats-sheet tables against cached values. Stdlib only."""
import zipfile, math, xml.etree.ElementTree as ET
XLSM = r"C:\Users\austg\git\games_list\old_excel\games_list.xlsm"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
z = zipfile.ZipFile(XLSM)
ss = ["".join(t.text or "" for t in si.iter(NS+"t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]

def cells(sheet):
    out = {}
    for c in ET.fromstring(z.read(sheet)).iter(NS+"c"):
        v = c.find(NS+"v")
        out[c.get("r")] = (ss[int(v.text)] if c.get("t") == "s" else v.text) if v is not None else None
    return out

def col(n):
    s = ""
    while n:
        n, r = divmod(n-1, 26)
        s = chr(65+r) + s
    return s

S13, S11 = cells("xl/worksheets/sheet13.xml"), cells("xl/worksheets/sheet11.xml")
IDX = {"Series":3,"My Score":35,"Metacritic":36,"PC Gamer":37,"GameSpot":38,"IGN":39,"Destructoid":40,
       "Game Informer":41,"Zero Punctuation":42,"Rank":43,"Soundtrack Owned":48,"Playthroughs":49,
       "Hours":51,"Hours Per Series":53,"Hours Per Series Rank":54,"Normalized Playthroughs":55,
       "Release Year":58,"Added Year":60,"First Played Date":61,"First Played":62,
       "Last Played Date":63,"Last Played":64,
       "Release Year vs First Played":65,"First Played vs Last Played":66}

def gcol(name, num=True):
    L = col(IDX[name] + 1)
    out = []
    for row in range(4, 660):
        v = S11.get("%s%d" % (L, row))
        if v in (None, ""):
            out.append(None)
        else:
            out.append(float(v) if num else v)
    return out

SCALE = {"My Score":1,"Metacritic":10,"IGN":1,"Game Informer":1,"GameSpot":1,"Destructoid":1,"PC Gamer":10}

def chk(name, pairs, tol=1e-9):
    bad = 0
    for label, mine, cached in pairs:
        if cached is None:
            continue
        if mine is None:
            ok = False
        elif isinstance(mine, str):
            ok = mine == cached
        else:
            ok = abs(mine - float(cached)) <= tol
        if not ok:
            bad += 1
            if bad <= 6:
                print("  MISMATCH %-40s mine %s cached %s" % (label, mine, cached))
    print("  %-30s compared %3d  mismatches %d" % (name, sum(1 for p in pairs if p[2] is not None), bad))
    return bad

MS, RANK, hrs = gcol("My Score"), gcol("Rank"), gcol("Hours")

def avgif(mask, vals):
    v = [x for m, x in zip(mask, vals) if m and x is not None]
    return sum(v)/len(v) if v else None

# 1. YearsPerScore B17:F28
print("=== YearsPerScore (B17:F28) ===")
P = []
for r in range(18, 29):
    b = S13.get("B%d" % r)
    for c, field in (("C","Release Year"), ("D","Added Year"), ("E","First Played"), ("F","Last Played")):
        cached = S13.get("%s%d" % (c, r))
        if b == "Top 20":
            mask = [x is not None and 1 <= x <= 20 for x in RANK]
        else:
            mask = [x == float(b) for x in MS]
        P.append(("%s %s" % (b, field), avgif(mask, gcol(field)), cached))
chk("YearsPerScore", P)

# 2. SoundtrackStats B32:D42
print("=== SoundtrackStats (B32:D42) ===")
own = gcol("Soundtrack Owned")
P = []
for r in range(34, 43):
    stat = S13.get("B%d" % r)
    for c in ("C", "D"):
        flag = float(S13["%s33" % c])
        cached = S13.get("%s%d" % (c, r))
        mask = [x == flag for x in own]
        if stat == "Hours":
            mine = sum(h for m, h in zip(mask, hrs) if m and h is not None)
        elif stat == "Games":
            mine = float(sum(mask))
        else:
            mine = avgif(mask, gcol(stat)) * 10 / SCALE[stat]
        P.append(("%s owned=%g" % (stat, flag), mine, cached))
chk("SoundtrackStats", P)

# 3. SoundtrackDistributionTable F32:J42
print("=== SoundtrackDistributionTable (F32:J42) ===")
mc, sc = gcol("Metacritic"), SCALE["Metacritic"]
P = []
for r in range(33, 43):
    s = S13.get("F%d" % r)
    if s in (None, ""):
        continue
    s, lo = float(s), float(S13["G%d" % r])
    for c, flag in (("I", 1.0), ("J", 0.0)):
        cached = S13.get("%s%d" % (c, r))
        denom = sum(1 for x in own if x == flag)
        mine = sum(1 for o, v in zip(own, mc)
                   if o == flag and v is not None and sc*lo < v <= s*sc) / denom
        P.append(("MC band %g owned=%g" % (s, flag), mine, cached))
chk("SoundtrackDistribution", P)

# 4. ZeroPunctuationQualityBuckets B46:G52
print("=== ZeroPunctuationQualityBuckets (B46:G52) ===")
zp, fpd = gcol("Zero Punctuation", num=False), gcol("First Played Date")
buckets = [S13.get("B%d" % r) for r in range(47, 53)]

def zpm(b):
    return [x is not None and x.lower() == b.lower() for x in zp]

games  = {b: sum(1 for m, s in zip(zpm(b), MS) if m and s is not None) for b in buckets}
played = {b: sum(1 for m, d in zip(zpm(b), fpd) if m and d is not None and d > 0) for b in buckets}
P = []
for i, r in enumerate(range(47, 53)):
    b = buckets[i]
    m = zpm(b)
    P += [("%s Games" % b,            float(games[b]),                S13.get("C%d" % r)),
          ("%s Frequency" % b,        games[b]/sum(games.values()),   S13.get("D%d" % r)),
          ("%s Games Played" % b,     float(played[b]),               S13.get("E%d" % r)),
          ("%s Frequency Played" % b, played[b]/sum(played.values()), S13.get("F%d" % r)),
          ("%s Hours" % b, sum(h for k, h in zip(m, hrs) if k and h is not None), S13.get("G%d" % r))]
chk("ZPQualityBuckets", P)

# 5. ZeroPunctuationDistribution B56:J61
print("=== ZeroPunctuationDistribution (B56:J61) ===")
P = []
for r in range(57, 62):
    hi, lo = float(S13["B%d" % r]), float(S13["C%d" % r])
    for c in range(5, 11):
        b = S13.get("%s56" % col(c))
        cached = S13.get("%s%d" % (col(c), r))
        mine = float(sum(1 for o, s in zip(zp, MS)
                         if o is not None and b is not None and o.lower() == b.lower()
                         and s is not None and lo <= s <= hi))
        P.append(("band %g-%g %s" % (lo, hi, b), mine, cached))
chk("ZPDistribution", P)

# 6. SeriesRankStats B65:H75 (RANK.EQ walk)
print("=== SeriesRankStats (B65:H75) ===")
series, hps, hpsr = gcol("Series", num=False), gcol("Hours Per Series"), gcol("Hours Per Series Rank")
rank_mine = [None if h is None else 1 + sum(1 for o in hps if o is not None and o > h) for h in hps]
print("  RANK.EQ recomputed vs cached column: mismatches",
      sum(1 for a, b in zip(rank_mine, hpsr) if (a is None) != (b is None) or (a is not None and a != b)))
P, offset = [], 0
for r in range(66, 76):
    cand = [x for x in rank_mine if x is not None and x > offset]
    if not cand:
        break
    req = min(cand)
    i = rank_mine.index(req)
    nm = series[i]
    P += [("rank %d Series" % (r-65),            nm,         S13.get("B%d" % r)),
          ("rank %d Rank Equivalent" % (r-65),   float(req), S13.get("D%d" % r)),
          ("rank %d Games Owned" % (r-65),
           float(sum(1 for s in series if s and s.lower() == nm.lower())), S13.get("F%d" % r)),
          ("rank %d Games Played" % (r-65),
           float(sum(1 for s, h in zip(series, hrs)
                     if s and s.lower() == nm.lower() and h is not None and h > 0)), S13.get("G%d" % r)),
          ("rank %d Hours" % (r-65),             hps[i],     S13.get("H%d" % r))]
    offset = req
chk("SeriesRankStats", P)

# 7. the four bucket cross-tabs
print("=== bucket cross-tabs (O..X = My Score 1..10) ===")
TABS = [("PlaythroughVsScoreBuckets", 25, 32, "Playthroughs"),
        ("NormPlayVsScoreBuckets",    37, 44, "Normalized Playthroughs"),
        ("ReleaseVsFirstBuckets",     49, 56, "Release Year vs First Played"),
        ("LastVsFirstBuckets",        61, 68, "First Played vs Last Played")]
for nm, r0, r1, field in TABS:
    vals = gcol(field)
    P = []
    for r in range(r0, r1+1):
        lo, hi = float(S13["L%d" % r]), float(S13["M%d" % r])
        for c in range(15, 25):
            s = float(S13["%s%d" % (col(c), r0-1)])
            cached = S13.get("%s%d" % (col(c), r))
            mine = float(sum(1 for m, v in zip(MS, vals)
                             if m == s and v is not None and lo <= v < hi))
            P.append(("%s [%g,%g) score %g" % (nm, lo, hi, s), mine, cached))
    chk(nm, P)

# coverage check: the LastVsFirst gap between 6 and 7
vals = gcol("First Played vs Last Played")
print("\nLastVsFirstBuckets coverage: games with gap == 6 (falls between [4,6) and [7,10)):",
      sum(1 for m, v in zip(MS, vals) if v is not None and v == 6))
print("  total non-null gaps:", sum(1 for v in vals if v is not None),
      " counted by the buckets:",
      sum(1 for v in vals if v is not None and any(lo <= v < hi for lo, hi in
          [(float(S13["L%d" % r]), float(S13["M%d" % r])) for r in range(61, 69)])))
