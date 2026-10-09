# Action plan: closing the gap with the old workbook PDF

Derived from a page-by-page review of `old_excel/games_list.pdf` (30 pages, exported Aug 9 2026)
against the current `build_pdf.py` (9 content pages + collage) and `dashboard.template.html`.

Read with `PROJECT_CONTEXT.md` (project state) and `REPORT_LOGIC.md` (decoded workbook formulas).
This file is the backlog; the other two are the spec.

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

4. **The committed `games_list_report.pdf` is stale.** The working tree already adds a Soundtrack
   ownership page (`build_pdf.py:239`) and `data.py:soundtrack()`, but the checked-in PDF predates
   them. **Regenerate before judging current state.** Don't re-report soundtrack as missing.

5. **Weekday quartiles are already done.** `build_pdf.py:203` is a real boxplot with mean dots,
   covering old p9 top. Only the second chart on that page (Weekday Range, ±1 SD band) is missing.

6. **Unused data already in the DB:** `lk_holidaystable` (349 rows), `games.graphic_style`, the five
   multiplayer-mode flags, `games.wikipedia_goat`, `games.goty_votes`, `games.playthroughs`,
   `games.average_playthrough`. All migrated, none displayed anywhere.

---

## Phase 1 — No blockers, every input already exists

Pure plotting work against current `data.py`. Highest value per hour.

### 1.1 Six critic scatter plots with regression (old p26)
My Score vs each of Game Informer, GameSpot, IGN, Metacritic, PC Gamer, Destructoid, each with
trendline and R². `data.py:regression()` already exists and is already used for score-vs-hours.
Workbook's cached R²: GI 0.29, GameSpot 0.24, IGN 0.30, Metacritic 0.37, PC Gamer 0.17, Destructoid 0.10.
→ New PDF page; dashboard section.

### 1.2 Fix the score-distribution axes (old p22 vs current page 4)
**This is a readability regression, not an omission.** The workbook plotted all six outlets as
*% frequency on a shared 1–10 axis*, so they were directly comparable. Current code plots raw
counts with a different y-scale per panel, which makes cross-outlet comparison impossible by eye.
→ Switch to percentage-of-games and a shared y-axis in `build_pdf.py:137` and the dashboard's
`#dist` / `#distsrc` section.

### 1.3 Restore per-outlet lines and sample size on category charts (old p11–13 vs current page 5)
Current "Scores by category" (`build_pdf.py:156`) averages all critics into one "Critics" value
and drops the Games Played bar. The workbook drew Metacritic, Game Informer and IGN as separate
lines over a Games Played bar, for genre / system / camera view.
→ Without the sample-size bar a 2-game system reads the same as a 147-game one. Restore both.

### 1.4 Average Year per Score (old p14)
x = my score 1–10 plus a "Top 20" column; y = year; four lines: release year, added year,
first played, last played.

### 1.5 Frequency of Hours Played (old p10)
Two curves over "up to X hours per day" (1–10): % of all days, and % of days played.

### 1.6 Scores per Year Played and per Last Year Played (old p15, p18)
Current output has first-played year and release year only (`build_pdf.py:172`). Add the other two
year bases. The dashboard already has a `#yrbasis` selector — extend it rather than adding sections.

### 1.7 Weekday Range band (old p9 bottom)
Average ±1 standard deviation band per weekday. Sits next to the existing boxplot.

### 1.8 Top series: restore the lost dimensions (old p23 vs current page 8)
Current chart is hours bars only (`build_pdf.py:224`). Add:
- Games Owned and Games Played lines on a secondary axis.
- The two share pies: Top 10 series = **63 of 656 games but 5,136 of 9,747 hours**.
  That ratio is the single most striking stat in the whole data set and is currently displayed nowhere.

### 1.9 Zero Punctuation score distribution (old p25 vs current pages 4/8)
Current output has a count bar and an hours bar. Missing: my-score-band distribution grouped by ZP
rank (bands 1-2 / 3-4 / 5-6 / 7-8 / 9-10), which is the part that shows whether you *agree* with the
reviewer. Optionally the two pies.

### 1.10 Games added per year: restore the platform split (old p19 vs current page 6)
Current stack is 3-way (Paid / Free / Friend-Family). The workbook stacked **8 series**:
ownership × platform class (PC / Console / Handheld). The dropped dimension is what makes the chart
readable — it shows the console→PC migration around 2015.

### 1.11 Hours-per-day and cumulative detail (old p8 vs current page 7)
- Old had **7-day and 28-day** moving averages; current has a single 14-day (`build_pdf.py:197`).
- Old plotted **cumulative games** on a secondary axis alongside cumulative hours; current drops it
  (`build_pdf.py:200`).

---

## Phase 2 — Needs the derived columns from `REPORT_LOGIC.md` §3.1

Add these four `Game_Table` columns to `data.py` first: `Hours Per Series Rank`,
`Normalized Playthroughs`, and the two `DATEDIF` gap columns. Then:

### 2.1 Playthrough charts (old p28, p29, p30)
- My Score vs Normalized Playthroughs, scatter with exponential fit (workbook: `y = 0.14e^0.29x`, R² = 0.28).
- My Score vs Playthroughs, stacked bars over buckets `0 1 2 3 4 5-9 10-14 15<`.
- My Score vs Normalized Playthroughs, same bucket treatment.

### 2.2 Year-gap stacked bars (old p20, p21)
- My Score vs (First Played − Release Year), buckets `0 1 2 3 4-5 6-9 10-19 20<`.
- My Score vs (Last Played − First Played), buckets `0 1 2-3 4-5 7-9 10-14 15-19 20<`.

Both stack by my score 1–10 on a red→green ramp.
**Use `REPORT_LOGIC.md` §3.4 for the exact edges** — it documents a real off-by-one gap in
`LastVsFirstBuckets` (note the missing `6` in the bucket labels above; that is the workbook's own
behaviour, reproduce it deliberately or fix it deliberately, but decide which).

### 2.3 Calendar heat map furniture (old p6 vs current page 7)
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

### 3.1 HaloRank — build as an editable app tab, not a generated report
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

Formula rules from `REPORT_LOGIC.md` §1 that must survive the rebuild:
- `SUMPRODUCT` pairs weights to columns **by position, not by name** — the weight labels and the
  master column names deliberately do not match. Never join on the label.
- Tier bands are **upper-inclusive** (`(4.5,5] = S` ... `<=1 = F`). Naive `floor` binning gets
  boundary scores wrong.
- Scores above 5 yield `#N/A` in the workbook — decide what the tab shows instead.

**Open decision (REPORT_LOGIC.md §1 "Data note"):** Halo 5 (12 levels) and Halo Infinite (14 levels)
have all nine ratings set to `0` — 26 of 85 rows are unrated placeholders that currently score 0.0
and land in tier F, indistinguishable from "rated terrible". An editable tab makes this worth fixing
properly: treat all-zero as **unrated**, render it as an empty/"—" tier, and exclude it from the
per-game averages. That also turns the tab into the thing that lets the owner fill them in.

### 3.2 HeatMapScore
`REPORT_LOGIC.md` §2 (parameters, bin edges, counts and fit). All inputs already in the DB.

### 3.3 Stats sheet — fourteen tables
`REPORT_LOGIC.md` §3.2. Needs the §3.1 derived columns from Phase 2. Note §4: the two out-of-range
scores that distorted `StatTable` are already fixed, so these can now be built against clean inputs.

### 3.4 Calendar Heat Map Comparison (old p7) — **still undecoded**
Four years side by side, each with its own From/To/Total and Max/75%/Avg/Med/25%/Min block.
`TimeHeatComp` has not been decoded from the workbook yet. Either decode it the way §1–3 were
decoded, or **skip it for the PDF and solve it in HTML instead** with a year scrubber on the single
heat map (see 4.6), which gets the same insight without the decode.

---

## Phase 4 — HTML-only ideas (things paper can't do)

The dashboard currently mirrors the PDF page for page. These are its actual advantage.

### 4.1 Make the collection mosaic the spine
405 covers is a lot of pixels doing nothing (`#mosaic`). Let it re-sort and re-tint live by score,
hours, year, genre or system, so the grid physically rearranges and each cover is tinted by the
active metric. It becomes a heat map made of box art.

### 4.2 Global cross-filter
Click a genre in any chart, every other chart filters to it. 656 games is small enough to do
entirely client-side, and it collapses a dozen static pages into one explorable view.

### 4.3 "Who do I agree with" summary
Instead of six scatter panels (1.1), lead with one ranked bar of R² across outlets and let the
reader expand any one into its scatter. Answers the question in a glance.

### 4.4 Biggest disagreements table
Games ranked by `my_score * 10 - metacritic`, both directions. Data is already there; appears nowhere.

### 4.5 Per-game playtime timeline
2,717 dated rows → a horizontal strip per game, first-to-last span with density. Shows which games
were binged versus returned to for years. The Last−First bucket chart (2.2) is a lossy summary of
exactly this.

### 4.6 Year scrubber on the calendar heat map
Step or animate through 2022→2026 in place. **This is the cheap answer to 3.4** — same insight as
the four-up comparison, no decode needed.

### 4.7 Flip the Top 10 cards
Reveal per-game stats (hours, playthroughs, every critic score, ZP rank) on the card itself instead
of a separate table.

---

## Suggested order

1. Regenerate both artifacts so current state is visible (correction #4).
2. **1.2 and 1.3** first — both actively mislead rather than merely omit.
3. The rest of Phase 1, cheapest-first: 1.1, 1.4, 1.5, 1.8, 1.11.
4. Phase 2's derived columns in one pass, then 2.1 / 2.2 / 2.3 together. **Read Phase 2b first** —
   it is a "do not change this" note, not a work item.
5. Phase 3 reports, re-running `tools/verify_*.py` after each. HaloRank (3.1) is now an app-tab
   feature and can be done at any point — it shares no code with the rest of Phase 3.
6. Phase 4 as a separate track — it touches `dashboard.template.html` and `build_html.py` only,
   so it can proceed in parallel without conflicting with the PDF work.

## Open questions for the owner

- What does the `Real` flag on log rows mean? 361 of 2,717 rows have it set; the PDF currently
  labels it "Flagged Real" (`build_pdf.py:196`).
- `LastVsFirstBuckets` off-by-one (2.2): reproduce the workbook's behaviour, or fix it? The 5
  affected games are Halo: CE Anniversary, Halo: MCC, Robot Unicorn Attack 2, Star Wars:
  Battlefront II and Skyrim — **none involve a demo**, so this is unrelated to Phase 2b.
- Halo 5 and Halo Infinite's 26 all-zero rating rows: unrated, or genuinely F? (3.1)
- Should `graphic_style`, the multiplayer-mode flags, `wikipedia_goat` and `goty_votes` be surfaced
  anywhere, or are they input-only fields for Checks and HaloRank?
