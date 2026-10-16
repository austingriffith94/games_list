# Action plan: closing the gap with the old workbook PDF

> **Archived Oct 12 2026.** Every phase below is built. The two leftovers (the dashboard half of 1.3
> and the optional Phase 2b residuals) moved to the current [`ACTION_PLAN_ui_charts.md`](ACTION_PLAN_ui_charts.md).
> Kept as the record of what was built and why.

Derived from a page-by-page review of `old_excel/games_list.pdf` (30 pages, exported Aug 9 2026)
against the current `build_pdf.py` (9 content pages + collage) and `dashboard.template.html`.

Read with [`PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md) (project state) and `docs/REPORT_LOGIC.md` (decoded workbook formulas).
This file is the backlog; the other two are the spec.

## Status (Oct 12 2026)

**Phases 1, 2 and 3 are built** in `build_pdf.py` / `dashboard.template.html` and checked: the
regenerated PDF is 24 pages, `test_parity.py` and `test_api.py` (68 checks) pass, and
`tools/verify_rebuild.py` reports ALL MATCH against the workbook's cached values. The remaining
work is the **Phase 4 HTML-only ideas** (none built; only a static mosaic tab exists) and a few
small cleanups. Everything marked DONE below is kept as a record of the
spec, not as work.

| Item | State |
|---|---|
| 1.1-1.11 Phase 1 charts | DONE (PDF + dashboard); 1.3 has one dashboard gap, see there |
| 2.1 Playthrough charts, 2.2 Year-gap bars | DONE |
| 2.3 Calendar heat map furniture | DONE (PDF page 7c, dashboard Time played tab) |
| 3.1 HaloRank, 3.2 HeatMapScore, 3.3 Stats tables | DONE |
| 3.4 Calendar heat map comparison | DONE (PDF page 12, dashboard Time played tab, checked by `tools/verify_rebuild.py`) |
| Phase 4 (4.1-4.7) | **Done** (Oct 2026) |

---

## 0. Corrections to existing notes — read before planning anything

These were verified during the review. Three of them change effort estimates.

1. **Total time is correct, not a regression.** The old PDF shows `406d 18h`; current output shows
   `406d 3.5h`. The workbook's own `TimeLog` column D sums to exactly **9747.5 h** = 406d 3.5h, and
   `gamelist.db` matches it exactly (2,717 rows). The migration is clean; the ~14.5 h delta is
   editing done in the workbook between the Aug 2026 PDF export and the Sep 20 2026 state. **No action.**

2. **GameSpot 80→79 and IGN 84→83 are the fix landing,** not drift. Commit `eb381be` corrected the
   two out-of-range scores (WRC 8 IGN, Overwatch 2 GameSpot). **No action.**

3. **`PROJECT_CONTEXT.md` is half right on HaloRank.** It says the level ratings, `TierListScoring`
   and section weights "were never migrated into `gamelist.db`". The **lookups were** migrated:
   - `lk_tierlistscoring` — 6 rows (`rank`, `score`, `upper`)
   - `lk_haloranksectionweights` — 10 rows (`variable`, `weight`, `percent`)
   - `lk_goty_yearlyvotes` — 22 rows (`year`, `total_goty_votes`)
   - `games.goty_votes`, `games.wikipedia_goat`

   But the **85 level rows of `HaloRankMaster` (9 ratings each) are genuinely absent** — no table
   holds them. HaloRank still needs a schema addition and a migration step, just a smaller one than
   `PROJECT_CONTEXT.md` implies: the weights and tier bands are already in place.

   **Resolved:** the `halo_levels` table and migration landed in 3.1.

4. **Resolved:** the PDF and dashboard were regenerated on Oct 12 2026 (23 pages, includes
   Soundtrack). Both are gitignored build outputs, so regenerate after any change to judge it.

5. **Weekday quartiles and Weekday Range are both done** (boxplot with mean dots plus the ±1 SD
   band, `build_pdf.py` page 7).

6. **Unused data already in the DB:** `games.graphic_style` is now a dashboard category option, and
   `lk_holidaystable`, `playthroughs` and `average_playthrough` are used. Still displayed nowhere: the
   five multiplayer-mode flags, `games.wikipedia_goat`, `games.goty_votes`.

---

## Phase 1 — No blockers, every input already exists

**All DONE** (Oct 2026), PDF and dashboard. The notes below are the original spec.

### 1.1 Six critic scatter plots with regression (old p26) — DONE
My Score vs each of Game Informer, GameSpot, IGN, Metacritic, PC Gamer, Destructoid, each with
trendline and R². `data.py:regression()` already exists and is already used for score-vs-hours.
Workbook's cached R²: GI 0.29, GameSpot 0.24, IGN 0.30, Metacritic 0.37, PC Gamer 0.17, Destructoid 0.10.
→ New PDF page; dashboard section.

### 1.2 Fix the score-distribution axes (old p22 vs current page 4) — DONE
**This is a readability regression, not an omission.** The workbook plotted all six outlets as
*% frequency on a shared 1–10 axis*, so they were directly comparable. Current code plots raw
counts with a different y-scale per panel, which makes cross-outlet comparison impossible by eye.
→ Switch to percentage-of-games and a shared y-axis in `build_pdf.py:137` and the dashboard's
`#dist` / `#distsrc` section.

### 1.3 Restore per-outlet lines and sample size on category charts (old p11–13 vs current page 5) — DONE (PDF); dashboard partial
Current "Scores by category" (`build_pdf.py:156`) averages all critics into one "Critics" value
and drops the Games Played bar. The workbook drew Metacritic, Game Informer and IGN as separate
lines over a Games Played bar, for genre / system / camera view.
→ Without the sample-size bar a 2-game system reads the same as a 147-game one. Restore both.

**Status:** the PDF has the Games Played bar and three outlet dots per row. The dashboard shows the
sample size only as `(n)` in the row label and lets you pick one critic source at a time. For parity,
add the faint sample-size bar behind each row (`drawCat`, `dashboard.template.html`).

### 1.4 Average Year per Score (old p14) — DONE
x = my score 1–10 plus a "Top 20" column; y = year; four lines: release year, added year,
first played, last played.

### 1.5 Frequency of Hours Played (old p10) — DONE
Two curves over "up to X hours per day" (1–10): % of all days, and % of days played.

### 1.6 Scores per Year Played and per Last Year Played (old p15, p18) — DONE
Current output has first-played year and release year only (`build_pdf.py:172`). Add the other two
year bases. The dashboard already has a `#yrbasis` selector — extend it rather than adding sections.

### 1.7 Weekday Range band (old p9 bottom) — DONE
Average ±1 standard deviation band per weekday. Sits next to the existing boxplot.

### 1.8 Top series: restore the lost dimensions (old p23 vs current page 8) — DONE
Current chart is hours bars only (`build_pdf.py:224`). Add:
- Games Owned and Games Played lines on a secondary axis.
- The two share pies: Top 10 series = **63 of 656 games but 5,136 of 9,747 hours**.
  That ratio is the single most striking stat in the whole data set and is currently displayed nowhere.

### 1.9 Zero Punctuation score distribution (old p25 vs current pages 4/8) — DONE
Current output has a count bar and an hours bar. Missing: my-score-band distribution grouped by ZP
rank (bands 1-2 / 3-4 / 5-6 / 7-8 / 9-10), which is the part that shows whether you *agree* with the
reviewer. Optionally the two pies.

### 1.10 Games added per year: restore the platform split (old p19 vs current page 6) — DONE
Current stack is 3-way (Paid / Free / Friend-Family). The workbook stacked **8 series**:
ownership × platform class (PC / Console / Handheld). The dropped dimension is what makes the chart
readable — it shows the console→PC migration around 2015.

### 1.11 Hours-per-day and cumulative detail (old p8 vs current page 7) — DONE
- Old had **7-day and 28-day** moving averages; current has a single 14-day (`build_pdf.py:197`).
- Old plotted **cumulative games** on a secondary axis alongside cumulative hours; current drops it
  (`build_pdf.py:200`).

---

## Phase 2 — Needs the derived columns from `docs/REPORT_LOGIC.md` §3.1 — DONE

The four derived columns are in `data.build()`: `Hours Per Series Rank`, `Normalized Playthroughs`,
and the two `DATEDIF` gap columns. 2.1-2.3 are built on them.

### 2.1 Playthrough charts (old p28, p29, p30)
- My Score vs Normalized Playthroughs, scatter with exponential fit (workbook: `y = 0.14e^0.29x`, R² = 0.28).
- My Score vs Playthroughs, stacked bars over buckets `0 1 2 3 4 5-9 10-14 15<`.
- My Score vs Normalized Playthroughs, same bucket treatment.

### 2.2 Year-gap stacked bars (old p20, p21)
- My Score vs (First Played − Release Year), buckets `0 1 2 3 4-5 6-9 10-19 20<`.
- My Score vs (Last Played − First Played), buckets `0 1 2-3 4-5 7-9 10-14 15-19 20<`.

Both stack by my score 1–10 on a red→green ramp.
**Decided:** the workbook's `LastVsFirstBuckets` has a real off-by-one gap (no bucket for a gap of
exactly `6`, which drops 5 games). The rebuild **fixes it deliberately**: the gap is closed in
`data.py` (`LAST_EDGES`), with a comment in `build_pdf.py`. The labels above are the workbook's,
not the rebuild's.

### 2.3 Calendar heat map furniture (old p6 vs current page 7) — DONE
Current heat map (`build_pdf.py:207`) is bare. The workbook's carried:
- A stats block: Max / 75% / Avg / Median / 25% / Min.
- A rolling-7-day-average sparkline.
- Day-of-week average mini-bars across the top.
- A weekly-average bar column down the right.
- Holiday marking (dashed cell borders) — `lk_holidaystable` has 349 rows already migrated.
- Month-boundary stair-step rules.

---

## Phase 2b — Demo / pre-release plays: the model is already correct

**Owner's policy (Oct 2026):** *"I still count demos as playing the game, just not giving them a
full playthrough count."*

**The existing data model already implements this. Do not change it.** This section exists so a
future session does not "fix" it into something wrong — an earlier draft of this plan proposed
excluding demo plays from `first_played`, which **contradicts the policy and should not be done.**

### Why it already works

Two independent measures, each doing its own job:

| Measure | What it does with a demo play |
|---|---|
| `play_log.hours` → Games Played | Counts. A demo play means you played the game. **445 stands.** |
| `games.playthroughs` | Manual integer count of completions — `0` for 21 of the 26 demo-only games |
| `Normalized Playthroughs` = `Hours / Average Playthrough` (§3.1) | Yields a *fraction*, automatically |

The third row is the elegant part: Kingdoms of Amalur was demoed for 2.25 h against a 31.5 h
average playthrough, so it scores **0.07 normalized playthroughs** — "played it, nowhere near
finished it" — with no special-casing anywhere.

> **`average_playthrough` is a reference length, not a mean of your own sessions.** It is populated
> even where `playthroughs = 0` (Kingdoms of Amalur: `playthroughs=0`, `average_playthrough=31.5`).
> It means "how long a full playthrough of this game takes". Do not redefine it as an average of
> logged sessions — that would break `Normalized Playthroughs` in exactly the case it handles best.

### Consequences for the rest of the plan

- **2.2 (year-gap charts)** use `first_played` / `last_played` **as-is, demos included**. ARK's
  2015 demo → 2020 retail span is a *true* statement about engagement under this policy, not an
  artifact. No `first_played_owned` variant is needed.
- **2.1 (playthrough charts)** must implement `Normalized Playthroughs` exactly as §3.1 specifies.
  That formula is what keeps demos honest; do not add a demo filter on top of it.
- **Games Played / backlog KPIs** need no change.

### Residual items (small, optional)

1. **Baldur's Gate 3 trips the Date Check as a false positive.** Played 2020-10-08 against a
   2023-08-03 release — that is **Early Access**, i.e. the real game, legitimately played early.
   The check at `app.py:277` flags it as an error. Note also §3.1's `IFERROR(..., 0)` on
   `Release Year vs First Played` silently reports this as a gap of `0`.
2. **Ratchet & Clank: Up Your Arsenal (PS2)** — played 2004-07-01, retail released 2004-11-02. A
   PS2 demo-disc play on the same system as the owned retail copy, which `UNIQUE(title, system)`
   cannot represent as a separate release row.
   Both cases would be solved by a nullable `play_log.version TEXT` (`NULL` = the release you own,
   else `'Demo'` / `'Beta'` / `'Early Access'`), mirroring the existing `real` flag. **3 rows to
   backfill.** Worth doing only if the false-positive check becomes annoying — it changes no report.
3. **Five demo-only games carry a playthrough count ≥ 1:** Geometry Wars: Touch (2), Death Worm,
   Devolverland Expo, Geometry Wars: Retro Evolved, Quake III Arena. These look **correct, not
   broken** — they are free or complete titles (Devolverland Expo is a whole promotional game;
   Quake III's shareware release is substantial) that happen to be tagged `Demo`. Worth one glance
   to confirm, not a cleanup task.

**Do not** relax `UNIQUE(title, system)` and repoint the `play_log` FK at `releases.id`. It is the
theoretically correct model, but it cascades through `migrate.py`, `app.py`, `data.py` and the Checks
tab for the sake of 3 rows.

---

## Phase 3 — Blocked or larger

### 3.1 HaloRank — DONE (HaloRank tab in app.py; `halo.py`, `halo_levels` table, schema v3; all-zero rows imported as unrated)
**Scope decision (owner, Oct 2026):** HaloRank is a personal write-up the owner maintains by hand,
not an analytical report. Build it as an **editable tab in `app.py` with a tier-list visualisation**,
rather than a static page in `build_pdf.py`.

Work:
1. **Schema + migration.** Add a table for the 85 `HaloRankMaster` rows — game, level name, level
   order, and the nine rating columns (`Enemy`, `Weapon/Vehicle`, `Design/Set Piece`,
   `Replayability/Pacing`, `Difficulty`, `Visual`, `Music`, `Story`, `Enjoyment`). Read them out of
   `old_excel/games_list.xlsm` in `migrate.py`. The weights and tier bands already exist as
   `lk_haloranksectionweights` / `lk_tierlistscoring`.
2. **Editable grid tab.** 85 rows x 9 ratings, same save/undo/audit path as the other tabs.
   Recompute `Variable Score`, `Rank` and `Score` live on edit — do **not** store them.
3. **Tier-list visualisation.** Classic S/A/B/C/D/F rows with each level as a chip, grouped or
   filtered by game. This is the part the owner actually wants to look at.
4. Optional: per-game summary (`HaloRankLetterScore` / `HaloRankNumberScore`) as a side panel.

Formula rules from `docs/REPORT_LOGIC.md` §1 that must survive the rebuild:
- `SUMPRODUCT` pairs weights to columns **by position, not by name** — the weight labels and the
  master column names deliberately do not match. Never join on the label.
- Tier bands are **upper-inclusive** (`(4.5,5] = S` ... `<=1 = F`). Naive `floor` binning gets
  boundary scores wrong.
- Scores above 5 yield `#N/A` in the workbook — decide what the tab shows instead.

**Decided and shipped:** all-zero rows are imported as unrated and excluded from averages. The
original open question (../REPORT_LOGIC.md §1 "Data note"): Halo 5 (12 levels) and Halo Infinite (14 levels)
have all nine ratings set to `0` — 26 of 85 rows are unrated placeholders that currently score 0.0
and land in tier F, indistinguishable from "rated terrible". An editable tab makes this worth fixing
properly: treat all-zero as **unrated**, render it as an empty/"—" tier, and exclude it from the
per-game averages. That also turns the tab into the thing that lets the owner fill them in.

### 3.2 HeatMapScore — DONE (`data.heatmap()`, PDF p19, interactive Statistics tab in the dashboard)
`docs/REPORT_LOGIC.md` §2 (parameters, bin edges, counts and fit). All inputs already in the DB.

### 3.3 Stats sheet — fourteen tables — DONE (`data.stats_tables()`, PDF p20-22, dashboard Statistics tab; checked by `tools/verify_rebuild.py`)
`docs/REPORT_LOGIC.md` §3.2. Needs the §3.1 derived columns from Phase 2. Note §4: the two out-of-range
scores that distorted `StatTable` are already fixed, so these can now be built against clean inputs.

### 3.4 Calendar Heat Map Comparison (old p7) — DONE
Four years side by side, each with its own From/To/Total and Max/75%/Avg/Med/25%/Min block.

**Decode (Oct 2026).** `TimeHeatComp` (`sheet19.xml`) is the `TimeHeat1Y` block four times over,
with each copy's date window moved back one year. There is no new logic:
- Window 1 = `HeatMapEndDateComp` → `HeatMapStartDateComp` (`TimeControl!N16` = `N15 − 365`, `N15` is
  the input). Windows 2–4 = the same month/day in `HeatMapCompYear1..3` (`N17..N19` =
  `YEAR(N15) − 1, −2, −3`).
- Per panel: daily `SUMIFS` grid (blank outside the window), Total = `SUM`, stats = `MAX`,
  `PERCENTILE.EXC(HeatMapPercPlus)`, `AVERAGE`, `MEDIAN`, `PERCENTILE.EXC(HeatMapPercMinus)`, `MIN`,
  plus a weekday-average row, a weekly-average column (`0` for a week with any blank day) and holiday
  flags from `HolidaysTable`.

Every one of those pieces already exists on the single-year page (2.3, `build_pdf.py` page 7c).

**Built (Oct 12 2026):**
- `data.calendar_stats(s, include_zero=False)` and `data.calendar_windows(log, end)` (the last 365 days
  and the same window shifted back 1, 2 and 3 years; a window that starts before the first log row is
  dropped).
- `build_pdf.py`: `draw_calendar_grid()` is shared by page 7c (single year) and the new page 7d
  (four stacked panels, PDF page 12). All panels use **one colour scale and one weekday-bar scale**; a
  light year no longer looks as busy as a heavy one.
- Dashboard (Time played tab): a "Calendar heat map comparison" card, with the same four panels, and an
  "Include zero-hour days in stats" checkbox on both heat map cards (the two stay in sync).
- `tools/verify_rebuild.py` checks Total / Max / Avg / Median / Min for all four panels against the
  workbook's cached `TimeHeatComp` values, with zero-hour days counted: 20 values, 0 mismatches.

**Where the rebuild deliberately differs from the workbook:**
- Windows are exactly 365 days ending on the report's end date (today), as on page 7. The workbook's
  are inclusive `From..To` dates (366-367 days) anchored on the last log date. The verifier feeds the
  workbook's own dates through the same stats code so the numbers can still be compared.
- Percentiles are `PERCENTILE.INC`, not `.EXC`, so 75% / 25% are not compared against the workbook.
  (The dashboard's old single-year view picked percentiles by floor index; it now interpolates, like the PDF.)
- A partial week at a window edge shows the average of its in-window days. The workbook shows `0`.

**Stats basis (decided Oct 2026, proposed by the owner for the dashboard):**
- **Days in the stats:** the workbook includes zero-hour days; page 7c counts played days only
  (`s365 > 0`), which raises Avg/Median/Min. The **PDF uses played days only** and prints the basis in
  the caption. The **dashboard gets an "Include zero-hour days" toggle**, default off so it matches the
  PDF, applied to all four comparison panels at once so the years stay comparable.
- **Percentiles:** use `PERCENTILE.INC` (pandas default) everywhere. The workbook's `.EXC` is not worth
  reproducing; note the deliberate difference next to `LAST_EDGES`-style fixes.
- Implement the toggle once in `data.calendar_stats(s, include_zero=False)` and the JS equivalent, so
  the single-year heat map (2.3) and the comparison page share it.

**This is not replaced by 4.6.** A scrubber makes the reader compare a frame against their memory of
the last one. Side-by-side panels let the eye do the comparison directly.

---

## Phase 4 — HTML-only ideas (things paper can't do)

The dashboard currently mirrors the PDF page for page. These are its actual advantage.

### 4.1 Make the collection mosaic the spine
405 covers is a lot of pixels doing nothing (`#mosaic`). Let it re-sort and re-tint live by score,
hours, year, genre or system, so the grid physically rearranges and each cover is tinted by the
active metric. It becomes a heat map made of box art.

**Done (Oct 2026):** the Mosaic tab has Order (series, my score, critics, hours, release year, first played,
genre, system, title) and Tint by (my score, critics, hours, release year) selectors. Covers persist and slide to
their new slots (FLIP animation, skipped under reduced motion); games missing the metric go grey; a legend shows
the range. Only 6 covers exist in `covers/` locally, so the full 405-cover grid has not been eyeballed.

### 4.2 Global cross-filter
Click a genre in any chart, every other chart filters to it. 656 games is small enough to do
entirely client-side, and it collapses a dozen static pages into one explorable view.

**Done (Oct 2026):** a filter bar under the tabs shows the active filters as removable chips, with a count of the games
that pass. Filters combine with AND, and clicking the same bar again removes that filter.
- **Filter sources:** Average score by category (genre / system / view / style), the Systems matrix row and column
  headers (system, genre, view, style, ownership, release type), the ZP bars on Scores and Hours, the My Score bins in
  Score distribution, Games per year (on whichever year basis is selected), and Top series by hours. Every underlined
  value in a game's detail panel and in the All games table is a filter too.
- **Highlighting:** a chart that sets a filter is drawn without its own filter, so the chosen bar stays highlighted
  among faded siblings instead of collapsing to one bar.
- **Recomputed under a filter:** the KPIs, the Top 10 (the best-ranked games that pass, numbered by their overall
  rank), Score averages and Soundtrack are recomputed client-side. Unfiltered, they still use the Python values; the
  JS matches them exactly.
- **Time tab:** keeps its date windows from the full log, so only the hours change.
- **Not filtered:** the Statistics tables stay precomputed for the whole collection and say so when a filter is on.
  The score heat map does follow the filter.
- **Empty results:** a combination that would match no games is refused, with a message.

### 4.3 "Who do I agree with" summary
Instead of six scatter panels (1.1), lead with one ranked bar of R² across outlets and let the
reader expand any one into its scatter. Answers the question in a glance.

**Done (Oct 2026):** Scores tab "Who do I agree with?": ranked bars of R² per outlet (n shown), click a bar to open that
scatter with its fit. "Show all six scatters" restores the old grid. Follows the global filter.

### 4.4 Biggest disagreements table
Games ranked by `my_score * 10 - metacritic`, both directions. Data is already there; appears nowhere.

**Done (Oct 2026):** Scores tab "Biggest disagreements": two tables (I rated higher / lower), gap = my score ×10 minus the
outlet, against any single outlet or the critics average, top 10 / 15 / 25. Click a title for the game card. Follows the
global filter.

### 4.5 Per-game playtime timeline
2,717 dated rows → a horizontal strip per game, first-to-last span with density. Shows which games
were binged versus returned to for years. The Last−First bucket chart (2.2) is a lossy summary of
exactly this.

**Done (Oct 2026):** Time tab "Per-game playtime timeline": a strip per game (first to last log entry, a mark per day
played, darker = more hours), sortable by first played / longest span / most hours / most days, Top 40 / 100 / all.
Click a strip for the game card. Follows the global filter; the axis stays on the full log's date range.

### 4.6 Year scrubber on the calendar heat map
Step or animate through 2022→2026 in place. This adds to 3.4; it does not replace it. A scrubber is
good for browsing a single year but weak for comparing years (see 3.4). The dashboard's `calGrid()`
already draws any date window on a shared `vmax`, so the scrubber only needs to re-call it.

**Done (Oct 2026):** the calendar heat map has a year slider, prev/next arrows and Play (steps every 1.3 s, stops at the
last year or when you leave the tab), kept in sync with the Year select. "Same colour scale for all years" colours every
year against the busiest day of any year; off by default, which keeps the old per-year scale.

### 4.7 Flip the Top 10 cards
Reveal per-game stats (hours, playthroughs, every critic score, ZP rank) on the card itself instead
of a separate table.

**Done (Oct 2026):** click (or Enter/Space on) a Top 10 card to flip it: hours, playthroughs (raw and normalized), first
and last played, systems, my score, all six critic scores and the ZP opinion, plus a Details button for the game card.
The flip is skipped under reduced motion.

---

## Suggested order

1. **Phase 4**, highest value per hour first: 4.4 (disagreements table, data already there), 4.3
   (R² ranked bar as the lead view), 4.1 (re-sortable mosaic), 4.6 (year scrubber), then
   4.2 / 4.5 / 4.7. Phase 4 only touches `dashboard.template.html` and `build_html.py`, so it does not
   conflict with PDF work.
2. Small cleanups: the dashboard half of 1.3, and the Phase 2b residual items if the Date Check
   false positives become annoying.
3. Re-run the tests and `tools/verify_*.py` after each step.

## Open questions for the owner

- What does the `Real` flag on log rows mean? 361 of 2,717 rows have it set; the PDF currently
  labels it "Flagged Real" (`build_pdf.py:196`).
- Should the multiplayer-mode flags, `wikipedia_goat` and `goty_votes` be surfaced anywhere, or are
  they input-only fields for Checks and HaloRank? (`graphic_style` now is.)

*Resolved since the last revision:* the `LastVsFirstBuckets` gap is fixed (2.2); Halo 5 / Infinite
all-zero rows are unrated (3.1).
