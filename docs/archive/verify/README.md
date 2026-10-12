# Workbook verification scripts (archived)

One-time proofs that the rebuilt reports match the numbers Excel cached in `old_excel/games_list.xlsm`.
They compare the *current* database to that frozen workbook, so they only pass while the data is unchanged
from the day the workbook was retired (Oct 12 2026). Adding or editing a game will make them differ, which is
expected, not a bug. Run them only against a copy of the database from that date (see `backups/`), using the
`game1` env, e.g. `python docs/archive/verify/verify_rebuild.py`.
