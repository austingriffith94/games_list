"""Verify the decoded HeatMapScore bin math against the workbook's cached grid. Stdlib only."""
import zipfile, xml.etree.ElementTree as ET
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

S5, S11 = cells("xl/worksheets/sheet5.xml"), cells("xl/worksheets/sheet11.xml")

# Game_Table: header row 3, data 4..659.  My Score -> AJ, Game Informer -> AP
def column_vals(letter):
    out = []
    for row in range(4, 660):
        v = S11.get("%s%d" % (letter, row))
        out.append(None if v in (None, "") else float(v))
    return out
X = column_vals("AJ")   # My Score      (x axis, F5)
Y = column_vals("AP")   # Game Informer (y axis, C5)
pairs = [(x, y) for x, y in zip(X, Y) if x is not None and y is not None]
print("Game_Table rows with both scores:", len(pairs))

# decoded parameters: C2 Max, C3 Min, C6 Y-interval, C7 Y-scale, F6 X-interval, F7 X-scale
MAX, MIN = float(S5["C2"]), float(S5["C3"])
YI, YS = float(S5["C6"]), float(S5["C7"])
XI, XS = float(S5["F6"]), float(S5["F7"])
print("Max %g Min %g | Y interval %g scale %g | X interval %g scale %g" % (MAX, MIN, YI, YS, XI, XS))

TOP = 1000          # the "*1000" open-ended top bin

def x_edges():
    lows, e = [], MIN
    while True:
        lows.append(e)
        if e >= MAX*XS: break
        e += XI*XS
    return [(lo, (lo*TOP if lo == MAX*XS else lows[i+1])) for i, lo in enumerate(lows)]
def y_edges():
    # K24 = Max*scale; a row exists while the PREVIOUS low was still > Min, so Min itself is emitted
    lows, e = [], MAX*YS
    while True:
        lows.append(e)
        if e <= MIN: break
        e -= YI*YS
    return [(lo, (lo*TOP if i == 0 else lows[i-1])) for i, lo in enumerate(lows)]

XE, YE = x_edges(), y_edges()
print("X bins %d (expect %s)  Y bins %d (expect %s)"
      % (len(XE), S5.get("F10"), len(YE), S5.get("C10")))

bad = tot = 0
for i, (ylo, yhi) in enumerate(YE):            # grid starts at row 24, descending
    row = 24 + i
    for j, (xlo, xhi) in enumerate(XE):        # grid starts at column Q (17)
        c = "%s%d" % (col(17+j), row)
        cached = S5.get(c)
        if cached is None or cached == "": continue
        cached = int(float(cached))
        mine = sum(1 for x, y in pairs if xlo <= x < xhi and ylo <= y < yhi)
        tot += 1
        if mine != cached:
            bad += 1
            if bad <= 10: print("  %s mismatch x[%g,%g) y[%g,%g): mine %d cached %d" % (c, xlo, xhi, ylo, yhi, mine, cached))
print("grid cells compared: %d   mismatches: %d" % (tot, bad))
print("sum of cached grid: %d   pairs: %d" %
      (sum(int(float(S5[c])) for i in range(len(YE)) for j in range(len(XE))
           if (c := "%s%d" % (col(17+j), 24+i)) in S5 and S5[c] not in (None, "")), len(pairs)))

# regression, I5:I7 = RSQ, SLOPE, INTERCEPT with known_y = Y axis, known_x = X axis
n = len(pairs); sx = sum(p[0] for p in pairs); sy = sum(p[1] for p in pairs)
sxx = sum(p[0]**2 for p in pairs); syy = sum(p[1]**2 for p in pairs); sxy = sum(p[0]*p[1] for p in pairs)
slope = (n*sxy - sx*sy)/(n*sxx - sx*sx); inter = (sy - slope*sx)/n
rsq = (n*sxy - sx*sy)**2/((n*sxx - sx*sx)*(n*syy - sy*sy))
print("\nRSQ  mine %.10f  cached %.10f" % (rsq,   float(S5["I5"])))
print("SLOPE mine %.10f cached %.10f" % (slope, float(S5["I6"])))
print("INTER mine %.10f cached %.10f" % (inter, float(S5["I7"])))
