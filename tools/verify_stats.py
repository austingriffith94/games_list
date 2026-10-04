"""Verify decoded Stats-sheet logic against the workbook's cached values. Stdlib only."""
import zipfile, math, datetime, xml.etree.ElementTree as ET
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
    while n: n, r = divmod(n-1, 26); s = chr(65+r) + s
    return s
S13, S11 = cells("xl/worksheets/sheet13.xml"), cells("xl/worksheets/sheet11.xml")

# Game_Table index (1 = Title at column B) -> sheet column letter
IDX = {"My Score":35,"Metacritic":36,"PC Gamer":37,"GameSpot":38,"IGN":39,"Destructoid":40,"Game Informer":41,
       "Playthroughs":49,"Average Playthrough":50,"Hours":51,"Normalized Playthroughs":55,
       "Release Date":57,"First Played Date":61,"Last Played Date":63,
       "Release Year vs First Played":65,"First Played vs Last Played":66}
def gcol(name, cast=float):
    L = col(IDX[name] + 1)
    out = []
    for row in range(4, 660):
        v = S11.get("%s%d" % (L, row))
        out.append(None if v in (None, "") else cast(v))
    return out
SCALE = {"My Score":1,"Metacritic":10,"IGN":1,"Game Informer":1,"GameSpot":1,"Destructoid":1,"PC Gamer":10}

# ---------- StatTable L3:S9 -------------------------------------------------
def mean(v): return sum(v)/len(v)
def var_s(v):
    m = mean(v); return sum((x-m)**2 for x in v)/(len(v)-1)
def median(v):
    s = sorted(v); n = len(s); return s[n//2] if n % 2 else (s[n//2-1]+s[n//2])/2
def skew_excel(v):                    # SKEW: n/((n-1)(n-2)) * sum(((x-m)/s)^3)
    n = len(v); m = mean(v); s = math.sqrt(var_s(v))
    return n/((n-1)*(n-2)) * sum(((x-m)/s)**3 for x in v)
def kurt_excel(v):                    # KURT: excess kurtosis, sample-corrected
    n = len(v); m = mean(v); s = math.sqrt(var_s(v))
    return (n*(n+1)/((n-1)*(n-2)*(n-3))) * sum(((x-m)/s)**4 for x in v) \
           - 3*(n-1)**2/((n-2)*(n-3))
STATFN = {"Variance":var_s, "Std. Deviation":lambda v: math.sqrt(var_s(v)),
          "Mean":mean, "Median":median, "Excess Kurtosis":kurt_excel, "Skewness":skew_excel}
print("=== StatTable (L3:S9) ===")
bad = tot = 0
for r in range(4, 10):
    label = S13.get("L%d" % r)
    for c in range(13, 20):                      # M..S
        src = S13.get("%s3" % col(c))
        if not src or not label: continue
        cached = S13.get("%s%d" % (col(c), r))
        if cached in (None, ""): continue
        vals = [x for x in gcol(src) if x is not None]
        mine = STATFN[label](vals)
        tot += 1
        if abs(mine - float(cached)) > 1e-9:
            bad += 1
            if bad <= 8: print("  MISMATCH %-16s %-14s mine %.10f cached %.10f" % (label, src, mine, float(cached)))
print("  compared %d  mismatches %d" % (tot, bad))

# ---------- CorrelationMatrix L13:S20 --------------------------------------
def correl(a, b):
    p = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    n = len(p); sx = sum(q[0] for q in p); sy = sum(q[1] for q in p)
    sxy = sum(q[0]*q[1] for q in p); sxx = sum(q[0]**2 for q in p); syy = sum(q[1]**2 for q in p)
    return (n*sxy - sx*sy)/math.sqrt((n*sxx - sx*sx)*(n*syy - sy*sy))
print("=== CorrelationMatrix (L13:S20) ===")
bad = tot = 0
for r in range(14, 21):
    a = S13.get("L%d" % r)
    for c in range(13, 20):
        b = S13.get("%s13" % col(c))
        cached = S13.get("%s%d" % (col(c), r))
        if cached in (None, "") or not a or not b: continue
        mine = correl(gcol(a), gcol(b)); tot += 1
        if abs(mine - float(cached)) > 1e-9:
            bad += 1
            if bad <= 8: print("  MISMATCH %s vs %s mine %.10f cached %.10f" % (a, b, mine, float(cached)))
print("  compared %d  mismatches %d" % (tot, bad))

# ---------- ScoreDistributionTable B3:G13 ----------------------------------
print("=== ScoreDistributionTable (B3:G13) ===")
bad = tot = 0
for r in range(4, 14):
    score = float(S13["B%d" % r])
    for c in range(4, 8):                        # D..G
        src = S13.get("%s3" % col(c))
        cached = S13.get("%s%d" % (col(c), r))
        if cached in (None, "") or not src: continue
        sc = SCALE[src]; vals = [x for x in gcol(src) if x is not None]
        mine = sum(1 for v in vals if sc*(score-1) < v <= score*sc) / len(vals)
        tot += 1
        if abs(mine - float(cached)) > 1e-9:
            bad += 1
            if bad <= 8: print("  MISMATCH score %g %-14s mine %.10f cached %.10f" % (score, src, mine, float(cached)))
print("  compared %d  mismatches %d" % (tot, bad))

# ---------- derived Game_Table columns -------------------------------------
EPOCH = datetime.date(1899, 12, 30)
def ser(v): return None if v is None else EPOCH + datetime.timedelta(days=int(v))
def datedif_y(a, b):
    """Excel DATEDIF(a,b,'y'): complete years; errors (#NUM!) when b < a."""
    if b < a: return "ERR"
    y = b.year - a.year - ((b.month, b.day) < (a.month, a.day))
    return y
print("=== Normalized Playthroughs (BD) ===")
hours, pt, apt, cached_np = gcol("Hours"), gcol("Playthroughs"), gcol("Average Playthrough"), gcol("Normalized Playthroughs")
bad = tot = 0
for i in range(656):
    if cached_np[i] is None: continue
    h = hours[i] or 0
    mine = 0 if h == 0 else (max(pt[i] or 0, 1) if apt[i] is None else h/apt[i])
    tot += 1
    if abs(mine - cached_np[i]) > 1e-9:
        bad += 1
        if bad <= 8: print("  MISMATCH row %d h=%s pt=%s apt=%s mine %.6f cached %.6f" % (i+4, h, pt[i], apt[i], mine, cached_np[i]))
print("  compared %d  mismatches %d" % (tot, bad))

print("=== DATEDIF gap columns (BN, BO) ===")
rel, fpd, lpd = gcol("Release Date"), gcol("First Played Date"), gcol("Last Played Date")
cBN, cBO = gcol("Release Year vs First Played"), gcol("First Played vs Last Played")
bad = tot = 0
for i in range(656):
    if fpd[i] is None: continue
    d = datedif_y(ser(rel[i]), ser(fpd[i]))
    mine_bn = 0 if d == "ERR" else d                     # IFERROR(...,0)
    mine_bo = datedif_y(ser(fpd[i]), ser(lpd[i]))
    for mine, cached, nm in ((mine_bn, cBN[i], "BN"), (mine_bo, cBO[i], "BO")):
        if cached is None: continue
        tot += 1
        if mine == "ERR" or abs(mine - cached) > 1e-9:
            bad += 1
            if bad <= 8: print("  MISMATCH %s row %d mine %s cached %s" % (nm, i+4, mine, cached))
print("  compared %d  mismatches %d" % (tot, bad))
