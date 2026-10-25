# Games List Modernization: Context Handoff

Project state and history for picking the work up again (e.g. pasted into a new chat). Architecture and file layout are in `README.md`.

## Goal
Replace my Excel workbook `games_list.xlsm` (personal video-game tracking list with a time log, many charts and a macro-driven PDF export) so Excel is no longer required. I want two outputs:
- an interactive HTML dashboard, and
- a printable letter-size PDF.

They don't need to look identical. The HTML can be more interactive. A reliable process for logging time, adding new games and editing existing entries is a priority.

## Architecture (approved)
SQLite database + Python + generated reports + a local entry app.
- `gamelist.db` is the source of truth (schema v9: v5 added `reviews`, `ref_tier` and `games.tier`; v6 gave `ref_tier` an id so tier edits are audited; v7 added the Total War lord tables). Counts: 656 games, 783 releases (game x system), 2,717 play-log rows, 9,747.5 hours.
- `app.py` is a Flask app on 127.0.0.1. Tabs: Log time, Games, Reviews, Top list, HaloRank, Lords, Gallery, Stats, Checks, History (undo), Reports.
- `build_pdf.py` makes the PDF (matplotlib, Letter, 26 pages including the cover collage).
- `build_html.py` + `dashboard.template.html` make a self-contained dashboard (vanilla JS, inline SVG, no CDN).
- `data.py` replaces about 90K workbook formulas with pandas.
- `gamelist.db` is now the master copy (the one-time workbook import was removed). `schema.py` documents the structure and holds upgrades (v4 dropped `play_log.real`).
- Reviews (Oct 24 2026): write-ups live in `reviews` (one per game, draft/published, plain-text body - format in `reviews.py`).
  The tier is a column on `games` (a `ref_tier` name; 11 tiers, Worstest to Masterpiece, seeded from the old page) but is
  **deliberately only set from a review** - triggers refuse a tier on a game with no review. I don't want every game tiered yet.
  Tiers are edited in the app (Reviews tab > Edit tiers; `PUT /api/tiers` saves the whole ordered list as one undo batch).
  Tiers are an independent judgment, not derived from `my_score` (e.g. Round Peg 4s sit below Forgettable 5-6s).
  `build_reviews.py` + `reviews.template.html` make `games_list_reviews.html` (layout follows my old hand-made reviews page,
  plus a library details panel). The old page's 45 tier-only placements (no write-up) were intentionally not imported.
  Undo now restores only the columns an edit changed, so undoing an old game edit can't wipe a later tier.
- Total War: Warhammer III lord tracker (Oct 24 2026): `tww_lords` (110 legendary lords, 25 races, filled by `tools/fetch_tww_lords.py`
  from the Total War wiki API) and `tww_campaigns` (any number per lord; only lord, mode and status required; the seven 0-5
  ratings are all-or-none). Lookups: `ref_tww_mode`, `ref_tww_status` (editable), `ref_tww_difficulty`, and weights in
  `lk_twwratingweights`. `tww.py` scores like `halo.py` and shares its tier bands. A lord's score is their best rated campaign
  (the dashboard also offers average and recomputes it for the mode filter). `roc_playable` limits Realms of Chaos progress and
  drives a Checks warning. Entry is in the app's Lords tab; the dashboard's Lords tab is read-only. Images are in `lords/`
  (git-ignored cache, served at `/lords/<file>`). The old Old World mod uses the same lords, so it is only a campaign mode.
  Playthroughs are still to be entered by hand.
- Tests: `tests/test_tww.py` covers the scoring. `tests/test_data.py` (derived numbers are internally consistent) and `tests/test_api.py` pass cleanly on Windows. `tests/test_e2e.py` (39 Playwright UI checks) is unresolved on Windows — see **Windows test status** below before touching it.
- `docs/REPORT_LOGIC.md` is a verified spec decoding the workbook's HaloRank, HeatMapScore and Stats sheet formulas (see **Reports decoded** below) — read it before rebuilding any of those reports.
- Run: `pip install -r requirements.txt`, then `python app.py` (or `start_app.bat`).

## Data model notes
- Tables: games, releases (title + system, FK to games), play_log (date, game, system, hours; unique on date+game+system), top_rank, audit (undo), `ref_*` lookup tables.
- Titles and lookups are case-insensitive (`COLLATE NOCASE`), as in Excel. Renaming a game cascades to its releases and log rows.
- Workbook checks ported to the app's Checks tab:
  - Data Filled: system, modes, scores, years.
  - Year Check: first played before release or added year, or after the last.
  - Date Check (non-Demo): first played >= version release; version <= added; added <= first played.
  - Log rows must match a release; no duplicate date/game/system.
- Score ranges: my_score 1-10; metacritic and pc_gamer 0-100; gamespot, ign, destructoid, game_informer 0-10.
- Field provenance:
  - `metacritic`, `pc_gamer`, `gamespot`, `ign`, `destructoid`, `game_informer` — pulled from each
    outlet's own site and from Metacritic's aggregation, not self-scored.
  - `zero_punctuation` (`ref_zp`: Best/Good/Neutral/Bland/Bad/Worst) — Yahtzee's *vibe*, drawn from
    the review itself and his end-of-year list placement, not a numeric score translated into a
    bucket. 209 of 656 games have one; the other 447 were never covered by Zero Punctuation.
  - `average_playthrough` — reference "how long to beat" for the game, not a mean of my own logged
    sessions (561 of 656 games have one; it's populated even where `playthroughs = 0` — see
    `Normalized Playthroughs` in `docs/REPORT_LOGIC.md` §3.1, which depends on this distinction).
- Cover images: filename = game title with `<>:"/\|?*` removed, `.jpg` or `.png`, 2:3 portrait. The covers live in `covers/` in the repo folder (git-ignored local cache; moved there from `D:\Pictures\Game List Covers` in Oct 2026).
- Safety: Undo on every save, History tab, daily backup (30 kept), CSV/zip export.

## Reports decoded (new)
Opus did a formula-by-formula decode of HaloRank, HeatMapScore and the Stats sheet directly
from `old_excel/games_list.xlsm`'s XML, and verified every rule by recomputing it and diffing
against the values Excel itself had cached in the file — **~2,900 cells, zero mismatches**.
Full spec, including the exact tier bands, bin edges, bucket definitions, and several
non-obvious gotchas (upper-inclusive tier bands, a real off-by-one gap in
`LastVsFirstBuckets`, Excel's sample-corrected `SKEW`/`KURT`, `DATEDIF`'s `IFERROR(...,0)`
swallowing data errors) is in **`docs/REPORT_LOGIC.md`**. Re-runnable, dependency-free verification
scripts are archived in `docs/archive/verify/`.

**This also surfaced a real data problem:** the two out-of-range scores (WRC 8 IGN, Overwatch 2
GameSpot) roughly tripled the standard deviation of GameSpot and IGN scores. They were fixed in
commit `eb381be`, so the Stats tables are built on clean inputs.

`TimeHeatComp` is decoded and built too: it is the single-year heat map block repeated for four year
windows (see `docs/archive/ACTION_PLAN_workbook_parity.md` 3.4). Soundtrack stats were part of the Stats sheet.

**Built and verified:** HaloRank (app tab, `halo.py`, `halo_levels` table), HeatMapScore
(`data.heatmap()`) and all fourteen Stats tables (`data.stats_tables()`), plus the Phase 1 and 2
charts. `docs/archive/verify/verify_rebuild.py` diffed them against the workbook's cached values (ALL MATCH).
The workbook-parity plan (including the Phase 4 HTML-only ideas) is finished and archived in
`docs/archive/ACTION_PLAN_workbook_parity.md`. The UI and chart plan that followed is finished and archived in `docs/archive/ACTION_PLAN_ui_charts.md`; its
optional leftovers are listed there.

## Chart colour roles

Used by the dashboard (`--accent`, `--accent2`, `--line`, `--muted` in `dashboard.template.html`) and the PDF
(`ORANGE`, `PURPLE`, `DARK`, `GREY` in `build_pdf.py`). Keep new charts to these roles.

| Role | Colour | Use |
|---|---|---|
| Mine / default | Orange | My score, and every single-series chart (including the weekday and Zero Punctuation bars) |
| Critics / comparison | Purple | Critic average and outlet comparisons only |
| Averages, fits, "everything else" | Ink (`--line` / `DARK`) or grey (`--muted` / `GREY`) | 7-day and 28-day averages, cumulative games, "% of days played", regression lines |
| Ownership classes | Teal (Paid), gold (Free), grey (Friend/Family), shaded by platform | *Games added per year* only |
| My score bands | Single-hue blue, light → dark: 1-2 / 3-4 / 5-6 / 7-8 / 9-10 (`--s1`..`--s5`, `SCORE5`; dark mode has its own lighter set) | Every chart stacked or coloured by my score |
| Counts (heat) | White → report orange `#C55A11`, one hue family | Matrices, heat maps, Statistics tables, calendars |

Red is not used for any data encoding.

Not yet on this scheme: the date-basis series in *Average year per score* (Added year is purple) and the
PDF p7 (the "Flagged Real" overlay is gone). Zero Punctuation always runs Best to Worst.

## Open items
1. ~~`Real` flag~~: resolved. It marked estimated time and was dropped in schema v4 (Oct 12 2026).
   (The two out-of-range scores were corrected in `eb381be`.)
2. ~~Reports not yet rebuilt from the workbook~~ — HaloRank, HeatMapScore, Stats and the Phase 1/2
   charts, the 3.4 heat map comparison and the Phase 4 HTML ideas are built (archived plan in `docs/archive/`).
3. Possible dashboard cover collage/cover tab.
4. **Windows testing — done, but test_e2e.py is unresolved.** See below.

## Windows test status (new)
The app now runs on Windows in a real conda env (`game1`, has pandas/numpy/matplotlib/flask/
openpyxl/pillow/playwright — use this env, not bare `python`/`python3`, which are empty
Microsoft Store stubs on this machine).

- `tests/test_data.py` — **passes.**
- `tests/test_api.py` — **passes**, after one fix already applied: `counts()` left a sqlite
  connection open, which only breaks cleanup on Windows (Windows keeps the file locked for
  `rmtree`; Linux doesn't care). Already fixed in the repo.
- `tests/test_e2e.py` — **unresolved.** Also had three hardcoded cloud-sandbox paths (now fixed: temp
  screenshots dir, `covers/` as upload fixtures, default Playwright chromium instead of
  `/opt/pw-browsers/chromium`), and one genuinely wrong assertion (also fixed: the "recent game"
  chip deterministically re-selects the game you just logged, so that step always produces an
  "Added to" toast, never a fresh "Logged" one — the original assertion only "passed" by
  accident, matching a stale 9-second-lived toast still in the DOM).
  **What's NOT resolved:** individual UI steps that should take milliseconds sometimes take
  10–20+ seconds on this machine — confirmed it's not a bug in `app.py` (the Flask server
  answers in <5ms when driven directly with Python threads, bypassing the browser entirely),
  and confirmed it's not fixed by forcing HTTP/1.1 keep-alive on the dev server. Several
  concurrent-fetch deep dives (documented in this session's transcript, not repeated here)
  didn't land on a clean root cause before the live debugging got contaminated by orphaned
  server processes from earlier aborted attempts, which produced at least one misleading
  "deadlock" reading. **Before attempting this again:** always confirm port 8799 is free
  (`Get-NetTCPConnection -LocalPort 8799`) and no stray `python.exe` with `games_list` in its
  command line is running before AND after any attempt — kill thoroughly, every time, including
  ones bound to port 8799 that don't textually match "games_list" (e.g. a copy run from a temp
  scratch path). Give a real attempt a generous, uninterrupted 10+ minute budget and don't kill
  it mid-run — that's what produced the misleading signals this session.

## Environment notes (for the assistant)
- The cloud sandbox can't reach `D:\Pictures\...`. Covers must be attached or the app run locally.
- pip and npm registries were blocked there. I wrote dependency-free code and didn't work around the block.
- The original xlsm and PDF were attached in the first chat; the migrated DB makes them unnecessary unless re-checking parity.
- I was told Opus may suit the harder remaining report logic — borne out: the formula decode above was Opus, first try, exact match.
- On my actual Windows machine (not the cloud sandbox): use the `game1` conda env
  (`C:\Users\austg\miniconda3\envs\game1\python.exe`), not `python`/`python3` on PATH.

## Suggested next step
1. (done) the `Real` flag was removed.
2. Get one clean, uninterrupted `tests/test_e2e.py` run on Windows to actually know if it passes.
3. (done) the UI and chart plan, archived in `docs/archive/ACTION_PLAN_ui_charts.md`;
   keep re-running `tests/test_data.py` and `tests/test_api.py` after each change.
4. I'll use the app for a week or two after that; tell the assistant which reports I actually
   use, and prioritize those for dashboard/PDF layout work.
