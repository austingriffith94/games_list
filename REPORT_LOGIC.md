# Workbook report logic: HaloRank, HeatMapScore, Stats

Decoded from `old_excel/games_list.xlsm` and verified against the workbook's own cached
results. Every rule below was checked numerically — see [Verification](#verification).

Sheet / table locations are given so the original can be re-checked:
`HaloRank` = `xl/worksheets/sheet4.xml`, `HeatMapScore` = `sheet5.xml`,
`Stats` = `sheet13.xml`, `List` = `sheet6.xml`, `Game_Table` = `sheet11.xml`.

Two workbook-wide names matter:

- `MainName` = `Game_Table!$B$2`, a cell holding the string `GameTable`. Formulas that
  read a user-chosen column do `INDIRECT(MainName & "[" & <column name> & "]")`. In the
  rebuild this is just a column lookup by name.
- `ScoreScale` (`List!L33:M40`) is a **divisor** that maps a raw score onto 0–10:

  | Type | My Score | Metacritic | IGN | Game Informer | GameSpot | Destructoid | PC Gamer |
  |---|---|---|---|---|---|---|---|
  | Scale | 1 | 10 | 1 | 1 | 1 | 1 | 10 |

  So a 0–10 source has scale 1 and a 0–100 source has scale 10. Anywhere the workbook
  compares against a band edge it multiplies the edge *by* the scale rather than dividing
  the value, which keeps the comparison in the column's own raw units.

---

## 1. HaloRank

A per-level tier list for eight Halo games. Three tables, all on `HaloRank`:

| Table | Range | What it is |
|---|---|---|
| `HaloRankMaster` | `B24:R109` | 85 level rows: 9 ratings each, plus derived score/tier |
| `HaloRankLetterScore` | `B2:L10` | per game: averages, level count, tier histogram |
| `HaloRankNumberScore` | `B13:O21` | per game: mean of each of the 9 ratings |

### Weights

`HaloRankSectionWeights` (`List!W11:Y21`). `Percent` = `Weight / 34`.

| Variable | Enemy | Weapon | Vehicle/Set Piece | Replayability/Structure | Difficulty | Visual | Music | Story | Enjoyment |
|---|---|---|---|---|---|---|---|---|---|
| Weight | 5 | 5 | 5 | 5 | 2 | 3 | 2 | 2 | 5 |

> **The weight names do not match the master-table column names.** The master columns are
> `Enemy, Weapon/Vehicle, Design/Set Piece, Replayability/Pacing, Difficulty, Visual,
> Music, Story, Enjoyment`. `SUMPRODUCT` pairs them **by position**, not by name, so the
> rebuild must preserve this order and must not join on the label.

### Tiers

`TierListScoring` (`List!W2:Y8`):

| Rank | S | A | B | C | D | F |
|---|---|---|---|---|---|---|
| Score | 5 | 4 | 3 | 2 | 1 | 0 |
| Upper | 5 | 4.5 | 4 | 3 | 2 | 1 |

### The three derived columns

```
Variable Score  = sum(rating[i] * weight[i]) / 34            # SUMPRODUCT, positional
Rank  (letter)  = INDEX(TierListScoring[Rank],
                        MATCH(Variable Score, TierListScoring[Upper], -1))
Score (numeric) = INDEX(TierListScoring[Score], MATCH(Rank, TierListScoring[Rank], 0))
```

`MATCH(..., -1)` over a descending `Upper` column returns the row with the **smallest
`Upper` that is still >= the value**, so the bands are **upper-inclusive**:

| Variable Score | (4.5, 5] | (4, 4.5] | (3, 4] | (2, 3] | (1, 2] | <= 1 |
|---|---|---|---|---|---|---|
| Tier | S | A | B | C | D | F |

A value above 5 yields `#N/A`. Use `>` on the lower edge and `<=` on the upper edge; a
naive `floor`-style binning gets the boundary scores wrong.

### Per-game aggregates

```
Average Score      = mean(Variable Score) over that game's levels     # AVERAGEIFS
Average Rank Score = mean(Score)          over that game's levels
Levels             = S + A + B + C + D + F
S..F               = count of levels at each tier                     # COUNTIFS
```

`HaloRankNumberScore` is the same shape but averages each of the nine raw ratings.

### Data note

Halo 5: Guardians (12 levels) and Halo: Infinite (14 levels) have **all nine ratings set
to 0** — 26 of the 85 rows are unrated placeholders. They therefore score 0.0 and land in
tier F, which is indistinguishable from "rated as terrible". Decide whether the rebuild
should treat an all-zero row as *unrated* and exclude it, rather than reproducing the
workbook's F.

---

## 2. HeatMapScore

A 2-D binned count of one score source against another, with a least-squares line. The
axes are chosen by dropdown, which is why the sheet is built out of `INDIRECT`.

### Parameters

| Cell | Name | Value as saved |
|---|---|---|
| `C2` | Max | 10 |
| `C3` | Min | 0 |
| `C5` / `F5` | Y-axis / X-axis source | Game Informer / My Score |
| `C6` / `F6` | Y-interval / X-interval | 0.25 / 1 |
| `C7` / `F7` | Y-scale / X-scale | from `ScoreScale` |
| `C8` / `F8` | Y-display / X-display | 1 (axis-label stride) |
| `C10` / `F10` | Y-cells / X-cells | `Max/interval + 1` → 41 / 11 |

### Bin edges

Both axes step in **raw units** (`interval * scale`), so switching to Metacritic or PC
Gamer rescales the grid automatically:

```
X lows: Min, Min + XI*XS, ...  up to and including Max*XS      # left to right, column Q onward
Y lows: Max*YS, Max*YS - YI*YS, ...  down to and including Min  # top to bottom, row 24 onward
```

Each bin's upper edge is the **next** low edge, and a cell is counted with
`low <= v < high`.

> **The final bin on each axis uses `low * 1000` as its upper edge.** That is the
> workbook's trick for making the maximum value inclusive: the top bin is the exact
> maximum (`[Max*scale, Max*scale*1000)`) and the bin below it is `[Max*scale - step,
> Max*scale)`. Miss this and every perfect score vanishes from the grid.

Note the Y axis emits a row for `Min` itself (the blank-out test looks at the *previous*
low), which is why there are 41 rows for a 0–10 range at 0.25 — not 40.

### Counts and fit

```
cell(x_bin, y_bin) = COUNTIFS(x_col >= x_low, x_col < x_high,
                              y_col >= y_low, y_col < y_high)
I5 = RSQ(y_col, x_col)        I6 = SLOPE(y_col, x_col)        I7 = INTERCEPT(y_col, x_col)
```

Excel's `RSQ`/`SLOPE`/`INTERCEPT` take **known_y first**, so the Y-axis source is the
dependent variable. Rows missing either score are excluded pairwise.

Axis tick labels (`row 22`, `column O`) print an edge only when
`MOD(edge, display * scale) == 0`.

---

## 3. Stats

Fourteen independent tables. `GameTable` columns are referenced throughout; all of them
already exist in `gamelist.db` except the four derived ones in §3.1.

### 3.1 Derived `Game_Table` columns to add to `data.py`

```
Hours Per Series             = SUMIFS(Hours by Series)          # data.py already has this
Hours Per Series Rank        = RANK.EQ(Hours Per Series, all rows, 0)
                             = 1 + count(values strictly greater)   # descending, ties share the low rank
Normalized Playthroughs      = 0                        if Hours == 0
                               max(Playthroughs, 1)     if Average Playthrough is blank
                               Hours / Average Playthrough  otherwise
Release Year vs First Played = IFERROR(DATEDIF(Release Date, First Played Date, "y"), 0)
First Played vs Last Played  = DATEDIF(First Played Date, Last Played Date, "y")
```

Both gap columns are blank when the game was never played.

> `DATEDIF(..., "y")` is **complete years elapsed**, not a subtraction of year numbers:
> `b.year - a.year - ((b.month, b.day) < (a.month, a.day))`.
>
> `DATEDIF` raises `#NUM!` when the end date precedes the start date, and
> `Release Year vs First Played` wraps that in `IFERROR(..., 0)`. So a game first played
> **before** its recorded release date reports a gap of **0**, not a negative number.
> This silently absorbs the data errors the `Date Check` rule is meant to catch.

### 3.2 The tables

| Table | Range | Rule |
|---|---|---|
| `StatTable` | `L3:S9` | 6 stats × 7 sources: `Variance` (`STDEV.S²`), `Std. Deviation`, `Mean`, `Median`, `Excess Kurtosis` (`KURT`), `Skewness` (`SKEW`) |
| `CorrelationMatrix` | `L13:S20` | `CORREL` for every source pair; the upper triangle is hidden by a conditional-format flag, not by the formula |
| `ScoreDistributionTable` | `B3:G13` | share of games per integer band, for My Score / GameSpot / IGN / Game Informer: `count(scale*(s-1) < v <= s*scale) / count(v)` |
| `YearsPerScore` | `B17:F28` | mean Release Year / Added Year / First Played / Last Played per My Score 1–10, plus a `Top 20` row using `Rank` between 1 and 20 |
| `SoundtrackStats` | `B32:D42` | Hours, Games, and each score source's mean (`× 10 / scale`), split by `Soundtrack Owned` = 1 / 0. Row 33 holds the 1/0 criteria |
| `SoundtrackDistributionTable` | `F32:J42` | Metacritic band share within each soundtrack-owned group |
| `ZeroPunctuationQualityBuckets` | `B46:G52` | per ZP opinion: Games (requires a non-blank My Score), Frequency, Games Played (requires a First Played date), Frequency Played, Hours. **The two frequencies use different denominators** |
| `ZeroPunctuationDistribution` | `B56:J61` | My Score × ZP opinion. Bands are `Score-1 <= v <= Score` over scores 2,4,6,8,10 → `[1,2] [3,4] [5,6] [7,8] [9,10]`, **inclusive at both ends** |
| `SeriesRankStats` | `B65:H75` | top 10 series by hours — see §3.3 |
| `SeriesRankTotalStats` | `B78:E80` | totals plus an `Other` remainder row = `ABS(grand total − sum of the top 10)` |
| `PlaythroughVsScoreBuckets` | `L24:X32` | My Score 1–10 × bucketed `Playthroughs` |
| `NormPlayVsScoreBuckets` | `L36:X44` | My Score × bucketed `Normalized Playthroughs` |
| `ReleaseVsFirstBuckets` | `L48:X56` | My Score × bucketed `Release Year vs First Played` |
| `LastVsFirstBuckets` | `L60:X68` | My Score × bucketed `First Played vs Last Played` |

All four cross-tabs count with `Start <= v < End`.

Excel's `SKEW` and `KURT` are the **sample-corrected** forms, not raw moments:

```
SKEW = n/((n-1)(n-2)) * Σ((x-m)/s)³
KURT = n(n+1)/((n-1)(n-2)(n-3)) * Σ((x-m)/s)⁴ − 3(n-1)²/((n-2)(n-3))     # excess
```

`pandas.Series.skew()` and `.kurt()` already match these, so use them rather than SciPy's
defaults (`scipy.stats.skew`/`kurtosis` are the biased forms unless `bias=False`).

### 3.3 Series ranking

The workbook cannot just sort: `Hours Per Series` is a per-*game* column, so every game in
a series repeats the same total and `RANK.EQ` repeats the same rank. It walks the rank
gaps instead:

```
Rank Offset[1]     = 0
Rank Equivalent[i] = MINIFS(Hours Per Series Rank, Hours Per Series Rank > Rank Offset[i])
Rank Offset[i]     = Rank Equivalent[i-1]
Series[i]          = INDEX(Series,          MATCH(Rank Equivalent[i], Hours Per Series Rank, 0))
Hours[i]           = INDEX(Hours Per Series, MATCH(Rank Equivalent[i], Hours Per Series Rank, 0))
Games Owned[i]     = COUNTIF(Series, Series[i])
Games Played[i]    = COUNTIFS(Series, Series[i], Hours, "> 0")
```

In pandas this collapses to grouping by series, summing hours, and taking the 10 largest.
The walk is a spreadsheet workaround, not business logic — don't port it literally.

### 3.4 Bucket edges

| | Start / End |
|---|---|
| Playthrough, NormPlay | `[0,1) [1,2) [2,3) [3,4) [4,5) [5,10) [10,15) [15,100)` |
| ReleaseVsFirst | `[0,1) [1,2) [2,3) [3,4) [4,6) [6,10) [10,20) [20,100)` |
| LastVsFirst | `[0,1) [1,2) [2,4) [4,6) [7,10) [10,15) [15,20) [20,100)` |

> **`LastVsFirstBuckets` has a gap.** The fourth bucket ends at 6 and the fifth starts at
> **7**, so a gap of exactly 6 years falls into no bucket. **5 games are affected**: the
> cross-tab totals 400 where 405 games have a value. Almost certainly a typo for 6.
> Decide whether to reproduce it or fix it; the rebuild should not reproduce it silently.

---

## 4. Out-of-range scores distort the Stats sheet

The two open data questions in `PROJECT_CONTEXT.md` are the **only** out-of-range values
in the workbook, and they are not cosmetic:

| | value | effect |
|---|---|---|
| Overwatch 2 — GameSpot | 80 (scale is 0–10) | — |
| WRC 8 — IGN | 84 (scale is 0–10) | — |

| Source | n | mean | sd | skew | excess kurtosis |
|---|---|---|---|---|---|
| GameSpot, as recorded | 565 | 8.016 | **3.272** | **18.87** | **416.8** |
| GameSpot, outlier removed | 564 | 7.889 | 1.227 | −1.02 | 1.06 |
| IGN, as recorded | 591 | 8.417 | **3.307** | **20.23** | **464.1** |
| IGN, outlier removed | 590 | 8.288 | 1.114 | −1.33 | 3.09 |

Two cells nearly triple both standard deviations and make skew and kurtosis meaningless.
They also drop out of `ScoreDistributionTable` entirely (its GameSpot and IGN columns sum
to 0.998, not 1.000) because no band covers them. `CORREL` is unaffected only by luck —
neither game has a My Score, so both are already excluded pairwise.

**Fix these two values before rebuilding `StatTable`**, or the rebuilt numbers will match
a broken original.

---

## Verification

Decode checked against the values Excel itself last computed and stored in the workbook.
All comparisons at a tolerance of 1e-9; **zero mismatches**.

| Area | Cells compared |
|---|---|
| HaloRank — Variable Score, tier letter, tier score (85 level rows) | 255 |
| HaloRank — per-game averages, level counts, tier histograms | 8 games |
| HeatMapScore — grid counts (41 × 11) | 451 |
| HeatMapScore — RSQ / SLOPE / INTERCEPT | 3 (to 10 dp) |
| Stats — StatTable | 42 |
| Stats — CorrelationMatrix | 49 |
| Stats — ScoreDistributionTable | 40 |
| Stats — YearsPerScore | 44 |
| Stats — SoundtrackStats + SoundtrackDistributionTable | 38 |
| Stats — both Zero Punctuation tables | 60 |
| Stats — SeriesRankStats (incl. RANK.EQ over all 656 rows) | 50 |
| Stats — the four bucket cross-tabs | 320 |
| Derived — Normalized Playthroughs (all rows) | 656 |
| Derived — both DATEDIF gap columns | 810 |

Scripts are in `tools/` and need **no third-party packages** — they read the `.xlsm` with
`zipfile` + `ElementTree`, so they run on a bare Python:

```
python tools/verify_halo.py
python tools/verify_heat.py
python tools/verify_stats.py
python tools/verify_stats2.py
```

Re-run them after the rebuild to confirm `data.py` still agrees with the workbook.
