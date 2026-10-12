# Action plan: UI and chart presentation

Derived from a rendered review on Oct 12 2026: every dashboard tab in light, dark and phone width
(390 px), all 26 PDF pages, and every entry-app tab. Line numbers are as of commit `c19376f`.

Read with `PROJECT_CONTEXT.md` (project state) and `REPORT_LOGIC.md` (decoded workbook formulas).
The workbook-parity plan that came before this one is finished and archived in
[`docs/archive/ACTION_PLAN_workbook_parity.md`](docs/archive/ACTION_PLAN_workbook_parity.md).

## Status (Oct 12 2026)

| Item | State |
|---|---|
| Phase 0: render-and-screenshot tool | Done |
| Phase 1 (1.1-1.10): rendering, layout and contrast bugs | Done (1.1-1.10) |
| Phase 2 (2.1-2.8): chart form and encoding | Done (2.1-2.8) |
| Gate (G1-G3): finish the review before Phase 3 | Not started |
| Phase 3 (3.1-3.7): layout, polish, hygiene | Done (before the Gate; G1-G3 still open) |
| Phase 4 (4.1-4.2): carried over from the parity plan | Not started |

**Scope.** The entry app (`static/app.html`) is in good shape and only gets small items (3.4). Most
of the work is in `dashboard.template.html`, plus a few real bugs in `build_pdf.py`.

**Guard rails.** No item changes a value in the database or a number in a Statistics table, so
`test_parity.py` and `tools/verify_rebuild.py` should keep passing unchanged. One thing can still
trip them: `data.ZP_ORDER`, which the verifier uses to line up workbook rows (see 2.3), so leave it
alone. The report window end date (see Decisions) does not affect the verifier, which feeds the
workbook's own From/To dates into the same code (`tools/verify_rebuild.py:157`), but it does change
what the Time played pages show.

A review coverage note is at the bottom: what was looked at and what was not.

---

## Phase 0: Make reviews repeatable

### 0.1 Add `tools/screenshot.py`
Both reports are git-ignored build outputs, so the only way to judge a change is to rebuild and
look. Add a script that rebuilds, rasterizes each PDF page (PyMuPDF is already in the `game1` env),
and screenshots each dashboard tab in light, dark and 390 px, writing PNGs to a git-ignored
`screenshots/` folder. Optionally it also starts `app.py` on a **copy** of the database, on a spare
port with `--no-browser` and `GAMELIST_BACKUPS` pointed at a temp folder, and screenshots each tab.
Use it after every item below.
- Add `screenshots/` to `.gitignore` (it is not there yet).
- Dependencies: PyMuPDF and Playwright are installed in the `game1` env but are not in
  `requirements.txt` (and the dashboard and PDF do not need them). Add a `requirements-dev.txt`
  (`pymupdf`, `playwright`, then `playwright install chromium`) so the tool, and `test_e2e.py`, can
  be set up on a fresh machine.
- Run it from the `game1` env, not bare `python` (see `PROJECT_CONTEXT.md`).

---

## Phase 1: Rendering bugs. These are wrong, not just unpolished.

### 1.1 Bars and lines run past the top of the plot
`niceTicks` (`dashboard.template.html:235`) never returns a tick above the data maximum, and every
chart uses its last tick as the top of the y-axis. A bar of 32 on an axis ending at 30 runs out of
the plot.
- **Visible in:** Games per year, Games added per year, Hours per day (the tallest bars pass the "8"
  gridline), all four score-stacked bucket charts (they run into their own subtitles), Cumulative
  hours (the line crosses 200), and the Weekday range band (its top is clipped flat).
- **Callers that derive the axis top from the last tick, and so need the fix:** `vbars` (244),
  `scoreStack` (284), the `#add` chart (520), `#daily` (542), `vbarsLine` (554, 557), `rangeBand`
  (565) and `#sdist` (785).
- **Callers that must NOT change:** `niceTicks` is also used for axes with a fixed domain: the
  secondary-axis labels in `vbars` (255, `lineRange`), `#yps` (505, `yLo`..`yHi`), the 0-100 and 1-10
  score axes (447, 583, 730-731, 747), and `hbars` (268). Raising the last tick there would draw
  gridlines and labels outside the plot.
- **Fix:** do not change the default behaviour of `niceTicks`. Add an option (for example
  `niceTicks(a, b, n, {ceil:true})`, or a small `niceCeil(b, n)` helper) that extends the last tick to
  at or above `b`, and call it from the listed callers only. For `hbars` (the R² and series bars)
  also set `m` to that top tick so the longest bar does not touch the right edge.
- **Order with 2.1:** `vbars`' `lines` option (253-260) and `vbarsLine`' second axis (557-559) are
  removed by 2.1, so do not spend time patching those lines here.

### 1.2 PDF heat tables shade the highest values white
`draw_table` (`build_pdf.py:118`) computes `HEAT(min(1, v / (hi * .55)))`. When the ratio passes 1,
`min` returns the **integer** `1`, and a matplotlib colormap reads an integer as a lookup-table index
(near white), not as the top of the scale.
- **Visible in:** p21 *Share of games per score band* (22.0%, 28.5%, 36.1%, 38.5% are white) and
  *Metacritic band share* (52.1%, 30.1%). Also p23's largest playthrough and gap counts.
- **Fix:** `min(1.0, …)`.

### 1.3 Years print with thousands separators
`fmt()` (`dashboard.template.html:225`) uses `toLocaleString`, so the Average year per score axis
reads "2,018" and the Statistics tab's *Average year per my score* table reads "2,005.3".
- **Fix:** add a year formatter with no grouping (`useGrouping:false`) and use it for every
  year-valued axis and cell.

### 1.4 Chart text size depends on the card width
`canvas()` (`dashboard.template.html:233`) draws each chart in a fixed `viewBox` (560 to 1000 units
wide) and lets the SVG scale like an image. The 11 px text scales with it:
- A 560-wide chart in a full-width card renders at about 22 px (Cumulative hours, the R² bars).
- A 1000-wide chart in a half-width card renders at about 6 px (Score distribution, the year-gap
  stacks, the Playthroughs stacks).
- At phone width all chart text is about 3 px.

**Fix:** size each chart's `viewBox` width to its container's `clientWidth` at draw time, and redraw
on resize (debounced). Text then renders at its real 11 px everywhere. Do this before Phase 2, since
it changes how every chart looks.
- **Resize path:** redraw through the same route `applyFilter` uses (clear `built`, rebuild the open
  tab), so filters, selects and the open tab survive a resize. Do not redraw on every pixel.
- **Hidden tabs:** a chart in a `display:none` tab has a width of 0. Charts are built lazily when their
  tab opens, so this works today, but do not pre-build hidden tabs.
- **Fixed pixel widths in layout units:** calls pass layout constants such as `labelW:190`, `l:44`
  and `w:560`. Once the unit is real pixels, `labelW:190` leaves about 150 px of plot in a half-width
  card. Give `hbars` a label width that scales (or truncates long labels with a tooltip).
- **Leave alone:** the calendar grids and the timeline, which size from their own week counts and
  scroll horizontally.

### 1.5 All games: the sticky header is offset 34 px and hides a row
`table.gt th{position:sticky;top:34px}` (`dashboard.template.html:59`) is inside `.tablewrap`
(`max-height:70vh;overflow:auto`), which is the scroll container, so `top` is measured from the top of
that box, not the page. Measured: the header sits 34 px below the box top, so rows scroll visibly above
it, and even at scroll 0 it is pushed down over the second row (the first game, 2XKO, shows above the
header and the second, A Plague Tale: Innocence, is hidden behind it). The 34 looks like an old guess at the sticky nav's height; the nav is
72 px at desktop width and 119 px at 390 px, and it does not apply here anyway.
- **Fix:** `top:0`. Leave `table.mx th{top:0}` alone.

### 1.6 Contrast: white text on the dashboard's accent colour
Measured WCAG contrast ratios (4.5 is the AA minimum for body text):

| Pair | Ratio |
|---|---|
| White on `--accent` `#ee8a45` (dark mode active tab) | **2.51** (fails) |
| White on `--accent` `#c55a11` (light mode active tab) | 4.33 (just under) |
| `#c55a11` text on white card (KPI numbers, h1) | 4.33 (just under; the 22 px h1 passes as large text) |
| `--muted` `#757575` on white | 4.61 (passes) |
| `--muted` `#9a9a9a` on dark card | 5.53 (passes) |

The entry app already solves the dark case with an `--accent-t` token (`#fff` in light, `#1a1a1a` in
dark, `static/app.html:8-10`); the dashboard hard-codes `#fff` (`nav button.on`, line 19).
- **Fix:** add `--accent-t` to the dashboard and use it on every accent-filled element. For the
  light-mode shortfall, either darken the text-on-white accent a step (for example `#b3500e`) or keep
  the brand colour for fills and use the darker value for small accent text. Check any new value
  against both card backgrounds.
- **PDF:** `ORANGE #C55A11` on white is fine in print; leave it.

### 1.7 Printing the dashboard is broken
`@media print` (`dashboard.template.html:87`) hides the nav and shows every tab
(`.tab{display:block!important}`), but tabs are built lazily when first opened. Printing straight
from the Overview gave 6 pages: the Overview in full, and the other seven tabs as headings and notes
with no charts (Scores has 783 characters of text against the Overview's 4,376). The Top 10 card
backs also print, mirrored (the `backface-visibility` trick does not apply in print), and tables and
cards split across pages.
- **Fix (recommended):** print the open tab only: drop the show-all-tabs rule, hide `.t10 .bk`, add
  `break-inside:avoid` on `.card`, and `print-color-adjust:exact` so heat cells keep their colour.
- **Decided (Oct 12 2026): the PDF is the printable output.** So there is no need to build every tab
  for print; the dashboard only has to print the open tab cleanly (the fix above). Do not spend more
  effort on dashboard print layout than that.

### 1.8 Pages scroll sideways at 390 px
Measured page width at 390 px: dashboard Years **491**, dashboard Statistics **511**, app Games
**554**. Every other tab fits.
- **Dashboard Years:** `.legend` (line 83) is a non-wrapping flex row, so the nine-item ownership
  legend in *Games added per year* is wider than the card. Add `flex-wrap:wrap`.
- **Dashboard Statistics:** the playthroughs and year-gap grid has an inline
  `grid-template-columns:repeat(auto-fit,minmax(480px,1fr))` (line 194). Use
  `minmax(min(480px,100%),1fr)`.
- **App Games:** the search box and "+ New" row (`#gsearch`, `#gnew`) are wider than the viewport. Let
  the row wrap, or shrink the input.

### 1.9 Statistics tables hide columns behind an invisible scroll
At 1280 px the Statistics tab shows three cards per row. *Distribution of each score source* and
*Correlation* have eight columns each, so they scroll sideways inside `.mxscroll`: IGN is cut in
half, and Destructoid and PC Gamer are not visible at all, with no scroll bar or fade to say there is
more (light and dark).
- **Fix:** make those two cards span the full grid width (`grid-column:1/-1`), and add a right-edge
  fade or shadow on `.mxscroll` so any remaining overflow can be found.

### 1.10 "Hours by month" is a solid block for short games
In the entry app's game detail dialog (`static/app.html:629`) each month is a bar with
`flex:1 0 8px` (line 89), so a game played in one month draws one bar the full width of the dialog.
A Short Hike shows as a solid orange rectangle. Cap the bar width (about 14 px), left-align the bars,
and label the first and last month. The Stats tab's "Hours per month" (line 647) uses the same class
and is fine with many months.

---

## Phase 2: Chart form and encoding

### 2.1 Replace the dual-axis charts
Two y-scales on one plot suggest a relationship that depends only on how the axes happen to line up.
In *Cumulative hours and games played*, the games line is nearly flat, and neither axis says which
series it belongs to.

| Chart | Where | Replace with |
|---|---|---|
| Games per year (bars + score lines) | dashboard `vbars` `lines` option (253-260), `#yr` (491); PDF p8 (`build_pdf.py:336`) | Two stacked panels sharing the year axis: games (bars) above, my score and critic average (lines, 0-100) below |
| Cumulative hours and games | dashboard `vbarsLine` (553-559), `#cum` (546); PDF p10 (`build_pdf.py:374`) | Two small stacked panels, or drop the games line (it barely moves inside a 365-day window) |
| Top series bars + games-owned/played lines | PDF p15 (`build_pdf.py:469`) | Games owned / played as a second small bar chart beside the hours bars, sharing the series rows. A line between categorical rows implies an order that isn't there. |
| Scores by category, secondary "Games played" axis | PDF p5 (`build_pdf.py:284`) | Keep the faint sample-size bar but drop its top axis; print `n` in the row label (the dashboard already does) |

### 2.2 One colour for single-series charts
Single-series bars are orange almost everywhere, but *Zero Punctuation opinions*, *Hours by ZP
opinion* and *Average hours by weekday* are purple (`color:css('accent2')` at 427, 549 and 714; PDF
p4 and p14). Make every single-series chart orange.

Purple currently has several unrelated jobs, so "purple = critics" is not true today: critic average
(*Average score by category*, *Games per year*), 28-day average, cumulative games, "% of days played",
the weekday range band, and the "Free" ownership class in *Games added per year*. Write down a short
colour-role table and apply it everywhere (dashboard CSS tokens and the PDF constants):
- **Orange:** "mine" and the default single series.
- **Purple:** critics / comparison series only.
- **Neutral grey or ink:** averages, fits and "everything else".
- **Ownership classes in *Games added per year*:** a separate palette, not orange or purple, so they
  do not read as "mine" or "critics".

### 2.3 One Zero Punctuation order everywhere
*ZP opinions* and *Hours by ZP* run Best→Worst (426, 713), but *ZP vs. my score* runs Worst→Best
(474). The PDF repeats the split (`build_pdf.py:268` and `:448` vs. `:489`; p4/p14 vs. p16).

**Use Best→Worst everywhere.** The Statistics tables and `data.ZP_ORDER` (`data.py:229`) already use
it, it matches the workbook, and `tools/verify_rebuild.py` (lines 97 and 101) indexes workbook rows by
that order, so changing `ZP_ORDER` would break verification for no visual gain. So the fix is two
charts only: reverse `zpOrder` in the dashboard (474) and `zp_order` in the PDF (489). Do not touch
`data.py`.

### 2.4 Score colour scale
The 10-step red→green ramp (`RG` at `dashboard.template.html:280`; `RG` at `build_pdf.py:17`) is hard
to read for red-green colour-blind viewers, and 10 adjacent classes blur together. The 5-band legend
on *ZP vs. my score* (1-2 / 3-4 / 5-6 / 7-8 / 9-10) is easier to read.
- **Fix:** use the 5 bands in every score-stacked chart, on a palette that is colour-blind safe
  (a single-hue light→dark ramp, or a diverging pair such as orange↔blue with a grey middle).
- Check the chosen colours with a CVD simulator against both the light and dark card backgrounds
  before shipping.
- **The PDF is the printed output, so also check the palette in greyscale** (a monochrome laser
  printer): the 5 score bands, and orange against purple, must still be told apart by lightness
  alone. Convert a page to greyscale (PyMuPDF `csGRAY`) in the 0.1 tool to check.
- **The count heat ramp has the same problem.** `HEAT` (`build_pdf.py:16`) and the dashboard's matrix
  and calendar cells run white→yellow→orange→**red**, so on the same page a red cell means "many" in a
  matrix and "score 1-2" in a score chart. Once the score palette is chosen, end the heat ramp in a
  dark orange or brown (one hue family) so red is reserved for "bad".

### 2.5 Replace the two-number donuts
The four donuts show a pair of unlabelled numbers in the middle: *Soundtrack ownership* Games and
Hours (`donut()` at 771, calls at 791; PDF p19) and *Top 10 series concentration* (721-722; PDF p15).
Show the point as one labelled figure: a stat tile or a single 100% bar reading
**"Top 10 series: 10% of games, 53% of hours"**. The existing subtitle already says this in words.

**p15 is touched by 2.1 (series bars), this item (donuts) and 2.2 (colour).** Do them as one change
to that page, not three, or the layout will be redone twice.

Donut size is also inconsistent: the soundtrack donuts are capped at 240 px by CSS
(`#sgames svg,#shours svg`, line 63) but the Top 10 concentration donuts are not, so they are about
270 px across at desktop and the full card width at 390 px. If any donut stays, cap them all.

### 2.6 Score averages as tiles, not bars
On the dashboard Overview, *Score averages* spends a full card on seven nearly equal bars (67-83 on
0-100, `#avgs` at 409). PDF p1 shows the same data as a row of stat tiles, which reads better. Reuse
the tiles on the dashboard, or use a dot plot on a 50-100 axis if a chart is wanted.

### 2.7 "Top 20" on *Average year per score*
The line runs through scores 1-10 and then carries on to "Top 20" as if it were score 11 (dashboard
`#yps` at 499; PDF p7). Break the line before it and draw Top 20 as separate markers with a gap or
divider.

### 2.8 Missing labels and units
- **R² bars:** the axis runs 0-40 with no unit. Label it "R² (%)" or show 0.00-0.40.
- **Critic scatter (`#critone`):** no y-axis label. Name the outlet.
- **Hours per day:** three series (daily bars plus 7-day and 28-day averages) identified only by a
  legend. Direct-label the two average lines at their right ends so the legend becomes optional.
- **Score heat map (PDF p20):** the axes are on 0-10, but the Metacritic equation is in raw 0-100
  units (`y = 3.47x + 57.32`). State the units or convert.

---

## Gate: finish the review before Phase 3

Phase 3 changes layout and phone width, so the checks below should be done first; otherwise their
findings land after the work they affect. Run them once Phase 2 is finished, using the 0.1 tool
extended with the states listed. Add what turns up to Phase 1 (if it is a bug) or Phase 3 (if it is
polish). Each check is static, so one script run covers it.

### G1 Tablet widths (768 and 1024 px)
Everything so far was at 1280 px or 390 px. The dashboard has no width media queries at all (only
dark mode, reduced motion and print); it relies on `auto-fit` grids with 340-480 px minimums, so the
in-between widths are where odd column counts and clipped tables are most likely. The app has
breakpoints at 900 and 560 px only. Screenshot every dashboard tab and every app tab at both widths,
and look for:
- grids that settle on an awkward column count (Statistics at 1024 px, the Top 10 grid, the paired
  charts in `.grid2`);
- tables clipped inside `.mxscroll`, and the 1.9 fix at these widths;
- charts after the 1.4 resize change, which has never been seen at an in-between width;
- the sticky nav height, and the app header wrapping.

### G2 The remaining dark and phone views
Capture and look at the ones not yet viewed:
- Dashboard dark: Mosaic, All games, and the game detail panel.
- App dark: Games, Gallery, Checks, History, Reports.
- App at 390 px: History, Reports.
- Dashboard at 390 px: Time played, Mosaic, All games (so far only measured for sideways overflow).

### G3 Long titles and empty records
Pick the worst cases from the database (a read-only query on a copy): the 5 longest titles, and games
with no score, no cover, no playtime or no release row. View them in Gallery, All games, Top 10, the
game detail dialog and panel, the Log time game picker and Recent entries. Look for overflow, ugly
truncation (the Gallery already ends titles in "…" with no tooltip), and "NaN", "undefined" or blank
values.

### Checked as each item lands, not here
- **Calendar Play, the card flip, keyboard focus and touch tooltips:** check with 3.1 and 3.7, when the
  code behind them changes.
- **Firefox and Safari:** check the 3D card flip once, with 3.1. Nothing else is likely to differ.
- **PDF viewers:** only if a printed page looks wrong.

---

## Phase 3: Layout and polish

### 3.1 Top 10 cards are mostly empty
The front and back faces share one grid cell (`.t10 .fr,.t10 .bk{grid-area:1/1}`, line 42), so the
taller back face sets the card height and about 80% of each front face is blank. Size the card to the
front face (cover + caption) and let the back face scroll or use smaller type.

### 3.2 PDF whitespace
- **p9 Games added per year:** the plot uses the bottom two-thirds, with the legend floating in a
  large empty band above it. Move the legend into the plot and give the plot the page.
- **p20 Score heat map:** rows 0-4 are almost empty. Start the y-axis at the lowest occupied bin.
- **p26 collage:** three rows of covers sit in a full-page grey panel. Size the panel to the rows
  actually used, or reflow the 405 covers evenly across the collage pages.
- **p3 Table summary (camera view):** only 7 columns, so the matrix fills about two-thirds of the
  page width. Widen the cells to fill the page.

### 3.3 Consistent number formatting
- **Statistics tables:** hours show 735.5 next to 688.25 and 1,129.8 next to 1,502. Correlations show
  0.4 next to 0.45. Fix decimals per column: hours 1 dp, correlations 2 dp, percentages 1 dp.
- **App Stats tab:** shows "9,748" next to "2156". Group thousands everywhere.
- **Overview KPIs:** "783 Games" counts releases (game × system), while "656 Unique games" counts
  games, so relabel the first "Releases" (dashboard Overview and PDF p1 tile). Keep "406d 3.5h": it is
  the figure `PROJECT_CONTEXT.md` and the archived plan verified against the workbook. Add the plain
  hours ("9,748 h") as the tile's caption instead of replacing it.

### 3.4 Entry app (small)
- **Log time → Recent entries:** every row has a red-outlined Delete button, so the table reads as a
  column of warnings. Make Delete a neutral (grey) button that turns red on hover and focus. Do not
  hide it until row hover: touch screens have no hover, and `test_e2e.py:61` clicks
  `#logtable button[data-del]` directly. Keep the `data-del` attribute and the confirm dialog.
- **Phone width (390 px):** in *Recent entries* the Delete button is clipped at the right edge ("Delet")
  and dates wrap onto two lines. Let the table scroll inside its card, or stack each row, and keep the
  date on one line. The header also wraps awkwardly (title on the left, tabs centred and split over
  three rows); put the tabs on their own full-width row, or scroll them horizontally.
- **Top list:** rows are tall with most of the width empty, and the ↑ ↓ ✕ controls are small and far
  from the title. Tighten the rows and enlarge the controls (24 px minimum target).
- **Reports tab:** the build timestamps are styled as headline KPI numbers. Make them ordinary text
  ("Dashboard: built 11:47, 2,668 KB").
- **Theme toggle:** the header button is the bare glyph "◐" (it has a tooltip but no visible label).
  Add the visible "Theme" text the dashboard uses.
- **HaloRank edit grid:** the level-name and notes inputs clip their text ("The Truth and
  Reconciliatio", "Assault on the Control Roo"). Widen those two columns, or show a tooltip.
- **Everything else in the app held up** in dark mode and at 390 px (Log time, Stats, Top list,
  HaloRank, Gallery, Checks), and the game edit form, new-game form and delete dialog need no change.

### 3.5 Phone width
After 1.4, re-check 390 px:
- Wide matrices (*Systems by category*, the Statistics tables) need horizontal scroll inside their
  card. Several already have it (`.mxscroll`); make it consistent.
- The Top 10 grid would fit better as two narrower columns, or a horizontal scroller, than as two
  very tall cards per row.
- The sticky nav is 119 px tall at 390 px (tabs wrap, plus the filter bar lives inside it), which is a
  large share of a phone screen. Let the tabs scroll horizontally on one row, and keep the filter bar
  out of the sticky area unless a filter is active.

### 3.6 Repo hygiene
- Three screenshots from the unresolved `test_e2e.py` debugging are tracked in the repo root:
  `debug_after_click.png`, `debug_before_click.png`, `debug_timeout.png`. Delete them (`git rm`); the
  test already writes new screenshots to a temp folder.
- Add `screenshots/` to `.gitignore` (see 0.1).

### 3.7 Accessibility (lower priority for a personal tool, but part of "professional")
- **Tooltips:** `tip()` (`dashboard.template.html:238`) only listens for `mousemove`, so chart values
  cannot be read by keyboard or touch. Use pointer events, and show the same text on focus.
- **Clickable marks:** bars, rows and column headers that set filters are `<rect>`/`<td>` elements with
  click handlers and no `tabindex` or role, so the cross-filter cannot be used from the keyboard.
- **Chart summaries:** SVG charts have no `role="img"` or `aria-label`, and the template has only 2
  `aria-` / `role` / `tabindex` attributes in total. Add a one-line label per chart (its title plus the
  headline value).
- **Colour-only encoding:** see 2.4. Heat cells carry their numbers, which is good; the stacked score
  charts do not.

---

## Phase 4: Carried over from the parity plan

### 4.1 Sample-size bar on the dashboard's category chart (was 1.3, dashboard half)
The PDF draws a faint Games Played bar behind each category row. The dashboard shows sample size only
as `(n)` in the label, so a 2-game system reads the same as a 147-game one. Add the faint bar in
`drawCat` (`dashboard.template.html:429`), and fold it into 2.1's no-second-axis rule.

### 4.2 Date Check false positives (was Phase 2b residuals, optional)
Baldur's Gate 3 (Early Access) and Ratchet & Clank: Up Your Arsenal (demo disc) trip the Date Check.
A nullable `play_log.version` would fix both; see the archived plan for the full reasoning and the
"do not relax `UNIQUE(title, system)`" warning. Do this only if the Checks tab warning becomes
annoying.

---

## Suggested order

1. **0.1** first, so every later step can be checked by eye.
2. **1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 1.9, 1.10:** small, contained fixes with the most visible payoff.
   Skip the `vbars` `lines` and `vbarsLine` second-axis lines in 1.1 (2.1 deletes them). Do 1.7
   (print the open tab only) alongside them.
3. **1.4**, since it changes the look of every dashboard chart; doing Phase 2 first would mean judging
   charts at the wrong size.
4. **2.1, 2.2, 2.5 together for each page**, taking p15 as one change, then 2.3 and 2.4 (2.4 also fixes
   the heat ramp, so decide the palette first).
5. The rest of Phase 2, then the **Gate** (G1-G3), then Phase 3, then Phase 4.
6. After each step: rebuild both reports, screenshot, run `test_parity.py`, `test_api.py` and
   `tools/verify_*.py` (use the `game1` env). `test_e2e.py` is still unresolved on Windows (see
   `PROJECT_CONTEXT.md`), so check the entry-app changes in 3.4 by hand until it is.

## Decisions for the owner

- **Window end date.** "Last 365 days" ends on today's date, not the last log date
  (`build_pdf.py:362`, `build_html.py:62` `END`). So right now the PDF's Time played pages cover
  Oct 13 2025 – Oct 12 2026 while the footer says "data through Sep 20, 2026", and the last three
  weeks show as empty days. That is correct if you stopped playing; it looks stale if you just haven't
  logged yet. Options:
  - **(a)** keep ending on today and say so in the subtitle;
  - **(b)** end on the last log date;
  - **(c)** end on today but grey out the days after the last log.
- **Resolved, score palette (2.4):** single-hue blue, light (1-2) to dark (9-10), in 5 bands. Chosen over
  diverging because it also stays ordered on a greyscale printout.
- **Resolved, printing (1.7):** the PDF is the printable output; the dashboard only prints the open tab.
- **Overview labels (3.3):** relabel "Games" to "Releases" and keep "406d 3.5h" (recommended), or leave
  the labels as they are.
- **Still open from before:** what the `Real` flag on log rows means, and whether the multiplayer-mode
  flags, `wikipedia_goat` and `goty_votes` should be shown anywhere.

## Review coverage

Two passes on Oct 12 2026, all from rendered output (Playwright for the dashboard and the app, PyMuPDF
for the PDF), plus measured values where a number mattered (contrast, page width, header offsets).

**Looked at:**
- **PDF:** all 26 pages.
- **Dashboard, desktop:** every tab in light mode; Overview, Scores, Years, Time played, Hours and
  Statistics in dark mode.
- **Dashboard, 390 px:** Overview, Scores, Years, Hours and Statistics viewed; the other tabs measured
  for sideways overflow only (none).
- **Dashboard states:** the Top 10 flip, an active filter chip with faded siblings, a hover tooltip,
  the game detail panel, and print output.
- **Entry app, desktop:** every tab in light mode; Log time, Stats, Top list and HaloRank in dark mode;
  the game edit and new-game forms, the delete dialog, the HaloRank edit grid and the gallery detail.
- **Entry app, 390 px:** Log time, Games, Gallery, Stats, Top list, HaloRank and Checks.

**Not reviewed yet** (the Gate section schedules these):
- Dashboard dark mode on Mosaic and All games; app dark mode on Games, Gallery, Checks, History and
  Reports; app 390 px on History and Reports (G2).
- Tablet widths of 768-1024 px (G1). Browser zoom and large system fonts are not scheduled.
- Very long titles and games with missing data (G3).
- Calendar Play, the card flip transition, touch tooltips, keyboard focus, and the app's toasts and
  undo: checked as items 3.1 and 3.7 land.
- Firefox and Safari (everything was Chromium): the card flip, once, with 3.1.
- PDF viewers: only rasterized, not opened in a viewer.

Add items to this file as they turn up.
