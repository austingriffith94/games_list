# Games List Modernization: Context Handoff

Paste this into a new chat (or attach it with `games_list_project.zip`) to continue the work.

## Goal
Replace my Excel workbook `games_list.xlsm` (personal video-game tracking list with a time log, many charts and a macro-driven PDF export) so Excel is no longer required. I want two outputs:
- an interactive HTML dashboard, and
- a printable letter-size PDF.

They don't need to look identical. The HTML can be more interactive. A reliable process for logging time, adding new games and editing existing entries is a priority.

## Architecture (approved)
SQLite database + Python + generated reports + a local entry app.
- `gamelist.db` is the source of truth (schema v2). Counts: 656 games, 783 releases (game x system), 2,717 play-log rows, 9,747.5 hours.
- `app.py` is a Flask app on 127.0.0.1. Tabs: Log time, Games, Top list, Checks, History (undo), Reports.
- `build_pdf.py` makes the PDF (matplotlib, Letter, 8 pages plus a cover collage).
- `build_html.py` + `dashboard.template.html` make a self-contained dashboard (vanilla JS, inline SVG, no CDN).
- `data.py` replaces about 90K workbook formulas with pandas.
- `migrate.py` converted the xlsm to SQLite. `schema.py` holds the DDL and upgrade.
- Tests: `test_parity.py` (numbers match the workbook) and `test_api.py` (53 checks) pass cleanly on Windows. `test_e2e.py` (39 Playwright UI checks) is unresolved on Windows — see **Windows test status** below before touching it.
- `REPORT_LOGIC.md` is a verified spec decoding the workbook's HaloRank, HeatMapScore and Stats sheet formulas (see **Reports decoded** below) — read it before rebuilding any of those reports.
- Run: `pip install -r requirements.txt`, then `python app.py --covers "D:\Pictures\Game List Covers"` (or `start_app.bat`).

## Data model notes
- Tables: games, releases (title + system, FK to games), play_log (date, game, system, hours, real; unique on date+game+system), top_rank, audit (undo), `ref_*` lookup tables.
- Titles and lookups are case-insensitive (`COLLATE NOCASE`), as in Excel. Renaming a game cascades to its releases and log rows.
- Workbook checks ported to the app's Checks tab:
  - Data Filled: system, modes, scores, years.
  - Year Check: first played before release or added year, or after the last.
  - Date Check (non-Demo): first played >= version release; version <= added; added <= first played.
  - Log rows must match a release; no duplicate date/game/system.
- Score ranges: my_score 1-10; metacritic and pc_gamer 0-100; gamespot, ign, destructoid, game_informer 0-10.
- Cover images: filename = game title with `<>:"/\|?*` removed, `.jpg` or `.png`, 2:3 portrait. The covers live in `D:\Pictures\Game List Covers` on my PC.
- Safety: Undo on every save, History tab, daily backup (30 kept), CSV/zip export.

## Reports decoded (new)
Opus did a formula-by-formula decode of HaloRank, HeatMapScore and the Stats sheet directly
from `old_excel/games_list.xlsm`'s XML, and verified every rule by recomputing it and diffing
against the values Excel itself had cached in the file — **~2,900 cells, zero mismatches**.
Full spec, including the exact tier bands, bin edges, bucket definitions, and several
non-obvious gotchas (upper-inclusive tier bands, a real off-by-one gap in
`LastVsFirstBuckets`, Excel's sample-corrected `SKEW`/`KURT`, `DATEDIF`'s `IFERROR(...,0)`
swallowing data errors) is in **`REPORT_LOGIC.md`**. Re-runnable, dependency-free verification
scripts are in `tools/verify_*.py`.

**This also surfaces a real data problem, not just a reporting one:** the two out-of-range
scores below (item 1) aren't cosmetic — they roughly triple the standard deviation of
GameSpot and IGN scores and corrupt `ScoreDistributionTable`, `StatTable` and
`CorrelationMatrix`. Fix them before rebuilding `StatTable`.

Still not decoded: `TimeHeatComp` (heat-map comparison sheets) and a few smaller charts.
Soundtrack stats *are* now covered — they turned out to be part of the Stats sheet.

**What's left to build, concretely:**
- **HaloRank** needs a schema/migration addition first — the level ratings, `TierListScoring`
  and the section weights were never migrated into `gamelist.db` (`schema.py` has no table for
  them, `migrate.py` never reads that sheet).
- **HeatMapScore** and all fourteen **Stats** tables need only derived columns in `data.py` —
  every input already exists in the DB. `REPORT_LOGIC.md` §3.1 lists the four derived
  `Game_Table` columns to add (`Hours Per Series Rank`, `Normalized Playthroughs`, and the two
  `DATEDIF` gap columns).

## Open items
1. **Data questions for me — now with evidence, still need my answer:**
   - WRC 8's IGN = 84 and Overwatch 2's GameSpot = 80 are outside the 0–10 scale, and they're
     the *only* two out-of-range values in the whole workbook (confirmed exhaustively). They
     need fixing, but I still need to say what the correct values should be.
   - What the `Real` flag on log rows means: 15 of the 23 entries over 24 hours have it set.
     The reports currently label it "Flagged Real".
2. ~~Reports not yet rebuilt from the workbook~~ — decoded now, see **Reports decoded** above.
   `TimeHeatComp` and a few smaller charts are still undecoded.
3. Possible dashboard cover collage/cover tab.
4. **Windows testing — done, but test_e2e.py is unresolved.** See below.

## Windows test status (new)
The app now runs on Windows in a real conda env (`game1`, has pandas/numpy/matplotlib/flask/
openpyxl/pillow/playwright — use this env, not bare `python`/`python3`, which are empty
Microsoft Store stubs on this machine).

- `test_parity.py` — **passes.**
- `test_api.py` — **passes, 53/53**, after one fix already applied: `counts()` left a sqlite
  connection open, which only breaks cleanup on Windows (Windows keeps the file locked for
  `rmtree`; Linux doesn't care). Already fixed in the repo.
- `test_e2e.py` — **unresolved.** Also had three hardcoded cloud-sandbox paths (now fixed: temp
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
1. Give me the correct WRC 8 IGN score and Overwatch 2 GameSpot score (item 1).
2. Get one clean, uninterrupted `test_e2e.py` run on Windows to actually know if it passes.
3. Rebuild HaloRank (needs the schema/migration work first), HeatMapScore and Stats using
   `REPORT_LOGIC.md` as the spec — then re-run `tools/verify_*.py` to confirm `data.py` still
   agrees with the workbook.
4. I'll use the app for a week or two after that; tell the assistant which reports I actually
   use, and prioritize those for dashboard/PDF layout work.
