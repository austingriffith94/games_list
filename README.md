# Game list (no Excel required)

## Quick start
    pip install -r requirements.txt
    python app.py                 # opens http://127.0.0.1:8765
Windows: double-click `start_app.bat` (edit the covers path inside if yours differs).
Options: `--covers "D:\Pictures\Game List Covers"` `--db gamelist.db` `--port 8765`

## What the app does  (replaces the Control / TimeControl sheets and all macros)
| Tab | Use it to |
|---|---|
| **Log time** | Date + game + system + hours. System list follows the game; shows the game's running total before/after; if an entry already exists for that date/game/system you choose *Add to* or *Replace* (the workbook's "override" switch). Recent-game chips, Today/Yesterday, per-day summary, edit/delete past entries. |
| **Games** | Search/filter, edit every field, add a new game (with its first release and cover in one form), add/edit/delete releases per system, upload cover art (click, drag-drop or paste), delete with confirmation. |
| **Top list** | Reorder your favourites; the first 10 feed the dashboard and PDF. |
| **Checks** | The workbook's check columns (Data Filled, Year Check, Date Check, duplicates) plus score-range checks, listing anything already wrong in the data. |
| **History** | Every change is recorded; **Undo** any of them. Backup now / CSV export. |
| **Reports** | Rebuild the interactive dashboard and the printable PDF, then open them. |

Every save also offers an **Undo** button in its confirmation.

## Safety
* Rules are enforced by the database, not by formulas: titles unique (any case), a log entry must match a release of that game,
  renaming a game renames it everywhere, and anything still referenced can't be deleted by accident.
* A backup is made each day the app starts (`backups/`, last 30 kept).
* `gamelist.db` is a normal SQLite file; the CSV export (History tab) is a plain-text copy you can keep in git.

## Cover art
Put images in `covers/` (or point `--covers` at your existing folder). File name = title with characters Windows
can't use removed (colons etc.) - the same rule the workbook used, e.g. `Fallout New Vegas.png`.
Covers are cropped to 2:3 and downscaled in the PDF, so large originals are fine and the PDF stays small.

## Reports without the app
    python build_html.py          # games_list_dashboard.html
    python build_pdf.py [covers]  # games_list_report.pdf   (--all includes unplayed games in the collage)

## Data notes
* Two review scores were outside their scale in the workbook: **WRC 8** IGN = 84 and **Overwatch 2** GameSpot = 80
  (probably 8.4 and 8.0). They are flagged on the Checks tab and can't be re-saved until fixed.
* The time log's **Real** column (set on 361 entries from 2001-2018) is carried over as-is.

## Tests
    python test_parity.py   # rebuilt numbers vs the original workbook / PDF
    python test_api.py      # 53 checks on a scratch copy of the data
    python test_e2e.py      # 39 checks driving the real UI in a headless browser (needs playwright)

## One-time import from the workbook
    python migrate.py games_list.xlsm gamelist.db
(Excel ignores letter case in lookups; log rows that differed only by case, e.g. "Dirt Rally" vs "DiRT Rally", are corrected and listed in `data_fixes`.)

## Files
app.py (server + API) · static/app.html (UI) · schema.py (constraints) · data.py (derived metrics) ·
build_html.py / build_pdf.py (reports) · dashboard.template.html · migrate.py · test_*.py
