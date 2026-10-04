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
- Tests: `test_parity.py` (numbers match the workbook), `test_api.py` (53 checks), `test_e2e.py` (39 Playwright UI checks). All pass.
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

## Open items
1. **Data questions for me:**
   - WRC 8 has IGN = 84 (outside the 0-10 scale).
   - Overwatch 2 has GameSpot = 80 (outside the 0-10 scale).
   - What the `Real` flag on log rows means: 15 of the 23 entries over 24 hours have it set. The reports currently label it "Flagged Real".
2. **Reports not yet rebuilt from the workbook:**
   - HaloRank, HeatMapScore and Stats logic
   - heat-map comparison sheets (TimeHeatComp)
   - soundtrack stats
   - a few smaller charts
3. Possible dashboard cover collage/cover tab.
4. The app was only tested on Linux, not yet on my Windows machine.

## Environment notes (for the assistant)
- The cloud sandbox can't reach `D:\Pictures\...`. Covers must be attached or the app run locally.
- pip and npm registries were blocked there. I wrote dependency-free code and didn't work around the block.
- The original xlsm and PDF were attached in the first chat; the migrated DB makes them unnecessary unless re-checking parity.
- I was told Opus may suit the harder remaining report logic.

## Suggested next step
I'll use the app for a week or two. After that, tell the assistant which of the remaining reports I actually use, and rebuild those first.
