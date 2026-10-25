# Game list (no Excel required)

## Quick start
    pip install -r requirements.txt
    python app.py                 # opens http://127.0.0.1:8765
Windows: double-click `start_app.bat`.
Options: `--covers covers` `--db gamelist.db` `--port 8765` (or set them in `config.json`; see `config.example.json`)

## What the app does  (replaces the Control / TimeControl sheets and all macros)
| Tab | Use it to |
|---|---|
| **Log time** | Date + game + system + hours. System list follows the game; shows the game's running total before/after; if an entry already exists for that date/game/system you choose *Add to* or *Replace* (the workbook's "override" switch). Recent-game chips, Today/Yesterday, per-day summary, edit/delete past entries. |
| **Games** | Search/filter, edit every field, add a new game (with its first release and cover in one form), add/edit/delete releases per system, upload cover art (click, drag-drop or paste), delete with confirmation. |
| **Top list** | Reorder your favourites; the first 10 feed the dashboard and PDF. |
| **Checks** | The workbook's check columns (Data Filled, Year Check, Date Check, duplicates) plus score-range checks, listing anything already wrong in the data. |
| **History** | Every change is recorded; **Undo** any of them. Backup now / CSV export. |
| **Reviews** | Write a review of any game in the library: pick its tier (worst to best), write paragraphs, add screenshots (button, paste or drop), see a live preview, publish. The tier is stored on the game and only set here. **Edit tiers** renames, reorders, adds and removes tiers and edits their descriptions (one Undo covers the whole edit; a tier can't be removed while a review is filed under it). **Build reviews page** makes the shareable `games_list_reviews.html`, which pulls each game's scores, hours, systems and so on into a details panel. |
| **Lords** | Total War: Warhammer III legendary lords, one section per race. Click a lord to see their campaigns and add a **+ Playthrough**: mode (Realms of Chaos / Immortal Empires / Old World) and status are required; difficulty, dates, turns, hours, patch, mods, co-op partner, notes and seven 0-5 ratings are optional (all seven ratings or none). A lord's score is their best rated campaign (HaloRank-style weighted score and S-F tier). Lord details can be edited by hand. |
| **Reports** | Rebuild the interactive dashboard, the printable PDF and the reviews page, then open them. |

Every save also offers an **Undo** button in its confirmation.

## Safety
* Rules are enforced by the database, not by formulas: titles unique (any case), a log entry must match a release of that game,
  renaming a game renames it everywhere, and anything still referenced can't be deleted by accident.
* A backup is made each day the app starts (`backups/`, last 30 kept).
* `gamelist.db` is a normal SQLite file; the CSV export (History tab) is a plain-text copy you can keep in git.

## Cover art
Images live in `covers/` next to `app.py`, which acts as the local cache (git-ignored, about 450 MB; the app writes new covers there). To keep them elsewhere, point `--covers` or `config.json` at that folder. File name = title with characters Windows
can't use removed (colons etc.) - the same rule the workbook used, e.g. `Fallout New Vegas.png`.
Lord images live in `lords/` (git-ignored local cache, like `covers/`). `python tools/fetch_tww_lords.py` fills the lord list from the Total War wiki and downloads each lord's unit card, portrait and faction icon. Run it again when new DLC lords come out; it only adds new lords and missing images, and never touches campaigns or fields you edited.

Covers are cropped to 2:3 and downscaled in the PDF, so large originals are fine and the PDF stays small.

## Review text format
Plain text. A blank line starts a new paragraph. A figure is a line of its own: `![caption](file.jpg)`, or `![caption](file.jpg){small}`
for a narrow in-column image. Images live in `review_images/` (git-ignored; `--review-images` or `review_images` in `config.json` to move it).
The old standalone reviews page was imported once with `python tools/import_reviews.py "<file>.html"` (re-running skips games that already have a review).

## Reports without the app
    python build_html.py          # games_list_dashboard.html
    python build_reviews.py       # games_list_reviews.html   (published reviews only)
    python build_pdf.py [covers]  # games_list_report.pdf   (--all includes unplayed games in the collage)

## Data notes
* Two review scores were outside their scale in the workbook: **WRC 8** IGN = 84 and **Overwatch 2** GameSpot = 80
  (probably 8.4 and 8.0). They are flagged on the Checks tab and can't be re-saved until fixed.
* The old workbook's time-log "Real" flag (estimated vs save-file time) was dropped in schema v4.

## Tests
    python tests/test_data.py     # internal consistency of the derived numbers
    python tests/test_api.py      # API checks on a scratch copy of the data
    python tests/test_tww.py      # lord campaign scoring
    python tests/test_e2e.py      # browser-driven UI checks in a headless browser (needs playwright)

(Excel ignores letter case in lookups; log rows that differed only by case, e.g. "Dirt Rally" vs "DiRT Rally", are corrected and listed in `data_fixes`.)

## Files
app.py (server + API) · static/app.html (UI) · schema.py (constraints, upgrades) · data.py (derived metrics) ·
halo.py (HaloRank scoring) · tww.py (lord campaign scoring) · tools/fetch_tww_lords.py (lord list + images) · reviews.py (review text format + reviews page data) · build_html.py / build_pdf.py / build_reviews.py (reports) ·
dashboard.template.html (includes the read-only Lords tab) · reviews.template.html · tools/import_reviews.py (one-time import of the old reviews page) · tests/ · tools/screenshot.py (review screenshots) ·
docs/ (REPORT_LOGIC.md = formula spec; archive/ = finished plans and one-time verify scripts) · PROJECT_CONTEXT.md (project state)
