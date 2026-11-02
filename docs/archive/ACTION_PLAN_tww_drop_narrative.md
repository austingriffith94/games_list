# Action plan: remove "Narrative / lore" from the Warhammer III lord ratings

Status: **finished and archived** (schema v10 applied Nov 1 2026; the Open question was real: `_v10` also strips `narrative` from past `audit` rows).

## Goal
Narrative / lore does not tell campaigns apart (there is little narrative for any faction), so it should not be a
rating or count towards a campaign's score. The lord tracker goes from seven ratings to six:
Faction mechanics, Roster, Start position, Challenge, Late game, Enjoyment.

## Decisions
- **Weights** become 5, 5, 3, 3, 4, 5 (sum 25). The other six keep their current weights; only narrative's 2 goes.
- **Existing data**: all 15 campaigns currently have narrative = 3 (a neutral placeholder I entered because the app
  needs all seven ratings or none), so nothing real is lost.
- **Ratings stay all-or-none**, now across the six.

## 1. Schema v10 (`schema.py`)
- `_v10`: rebuild `tww_campaigns` without `narrative` (same approach as `_v8`: rename, create from the updated DDL,
  copy with the same ids so History still points at the right rows, drop the old table). A rebuild is needed because
  the all-or-none `CHECK` mentions `narrative`, which stops `DROP COLUMN`. Also recreate `ix_tww_camp_lord`.
- Delete the `narrative` row from `lk_twwratingweights`.
- Remove `narrative` from `_TWW_RATINGS` and `TWW_SEEDS`, so a fresh database is created with six ratings.
- Bump `VERSION` to 10, add to `STEPS` and the `upgrade()` docstring.
- Open question to check before building: whether audit/History rows recorded before the migration store a
  `narrative` value that Undo would then try to write back. If so, `_v10` also strips that key from old
  `tww_campaigns` audit entries (or Undo skips unknown columns).

## 2. Code
- `tww.py`: remove `narrative` from `RATING_COLS`, `RATING_LABELS` and `DEFAULT_WEIGHTS`; update the docstring ("seven" -> "six").
- `app.py`: validation message "Rate all seven categories" -> "six", and its docstring. Everything else reads the
  columns from `tww.RATING_COLS`, so the API needs no other change.
- `static/app.html` and `dashboard.template.html`: the rating inputs, race averages and ratings chart are driven by
  `cols` / `labels`, so they follow automatically. Only the text "all seven" -> "all six" (and the drawer comment) changes.
- `README.md`, `PROJECT_CONTEXT.md`: "seven" -> "six".
- The archived plan `docs/archive/ACTION_PLAN_tww_lords.md` stays as it is (history).

## 3. Tests
- `tests/test_tww.py`: the hand-worked example uses weights 5,5,3,3,2,4,5 and ratings 5,4,3,2,1,0,5. Re-work it for six
  (weights 5,5,3,3,4,5; sum 25), and drop `narrative=1` from the update on line 104.
- Add a check that a migrated v9 copy has no `narrative` column, no narrative weight row, the same campaign ids and
  an unchanged `COUNT(*)`, and that running `upgrade` again does nothing (same pattern as the v6 -> v7 test).
- Run the full suite (`test_tww`, `test_api`, `test_e2e`).

## 4. Rollout
1. Back up `gamelist.db` to `backups/` before the migration runs on the real database.
2. Run the migration, then re-read `/api/lords` and confirm 15 campaigns, all still rated, with the new scores and tiers.
3. Rebuild the reports (Reports tab -> Rebuild reports) so `games_list_dashboard.html` drops the Narrative column.

## Expected effect
Scores move a little (narrative was pulling every campaign towards 3). The order is unlikely to change much, but a
couple of campaigns near a tier line (Taurox at 4.00, Boris Ursus at 3.30) could move, and I will list any tier
changes after the migration.
