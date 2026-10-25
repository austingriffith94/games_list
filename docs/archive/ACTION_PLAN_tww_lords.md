# Action plan: Total War: Warhammer III legendary lord tracker

Status: **finished and archived** (all steps done; playthroughs are entered in the app). Original build order below.

## Goal
A tracker of every legendary lord in Total War: Warhammer III, grouped by race, showing which lords I've
played, in which campaign, and how good each campaign was. It works like HaloRank: 0-5 ratings, a
weighted score, S-F tiers.

- **Dashboard**: a new **Lords** tab in `dashboard.template.html`. This is the main place to view it.
  It is read-only.
- **Entry app**: a **Lords** tab in `app.py` / `static/app.html`. This is where playthroughs are added and
  edited, with the same Undo/History safety as every other table.

## Decisions (agreed Oct 24 2026)
- **Rating categories**: the seven below. Weights live in a lookup table, so they can change later
  without touching code.
- **Images**: the in-game **unit card** on the grid; the **portrait art** in the detail drawer; the
  **faction icon** as a corner badge and in race headers.
- **Campaign modes**: Realms of Chaos, Immortal Empires, Old World (mod). The Old World mod has the same
  lords on a different map, so the mode is just a field on each campaign. It does not need its own
  list of lords.
- **Workflow**: playthroughs are entered in the app. The dashboard Lords tab is part of
  `games_list_dashboard.html`, which the Reports tab's *Rebuild reports* (`build_html.py`) generates.
- **Many playthroughs per lord**: a lord can have any number of campaigns, including several in the same
  mode. `tww_campaigns` has no uniqueness rule on lord or lord + mode. The drawer lists them newest first.
- **Lord score**: the best rated campaign by default.
- **Race grouping**: one section per race, matching the game's faction-select screen. Khorne, Nurgle,
  Slaanesh, Tzeentch, Warriors of Chaos and Daemons of Chaos are six separate sections. Chaos Dwarfs,
  Norsca, Beastmen and Ogre Kingdoms each get their own section too.
- **Section order**: by the game the race came from (WH1 → WH2 → WH3, with DLC races placed by the game
  they were added to), then A–Z within each game. Stored as `race_game` + `race_order`, so it can be
  changed by hand.
- **Realms of Chaos availability**: each lord has a `roc_playable` flag. Many WH1/WH2 lords can only be
  played in Immortal Empires (or Old World). The Checks tab warns about a RoC campaign for a lord who
  isn't RoC-playable. The dashboard shows RoC progress counted only over lords who are.
- **Difficulty**: two separate optional dropdowns, `campaign_difficulty` and `battle_difficulty` (Easy /
  Normal / Hard / Very Hard / Legendary, from `ref_tww_difficulty`).
- **Co-op**: optional free-text `coop_with` (who I played with). Empty means a single-player campaign.
- **Backfilling old campaigns**: only lord, mode and status are required. Dates, turns, hours, patch,
  difficulty and ratings are all optional. A campaign with no ratings counts as played but has no
  score or tier.
- **Statuses**: stored in the editable `ref_tww_status` table, not hard-coded. Starting values: In progress
  / Short victory / Long victory / Abandoned / Lost. More (e.g. Domination, Forge of Souls completed) can
  be added without code changes.
- **Patch**: optional free text (e.g. "6.3"), because factions are reworked between patches.

## 1. Schema v7
The schema was already at v6 when this started, so this is a 6 → 7 step (`_v7` in `schema.py`), run in the
same transaction as the other upgrades. `TWW_DDL` and `TWW_SEEDS` sit beside `HALO_DDL`; the seed rows for
the four lookup tables come from `TWW_SEEDS`.

```sql
CREATE TABLE ref_tww_mode(name TEXT PRIMARY KEY COLLATE NOCASE);          -- Realms of Chaos / Immortal Empires / Old World
CREATE TABLE ref_tww_status(name TEXT PRIMARY KEY COLLATE NOCASE);        -- In progress / Short victory / Long victory / Abandoned / Lost (editable)
CREATE TABLE ref_tww_difficulty(name TEXT PRIMARY KEY COLLATE NOCASE, sort INTEGER NOT NULL);  -- Easy .. Legendary
CREATE TABLE lk_twwratingweights(col TEXT PRIMARY KEY, label TEXT NOT NULL, weight NUMERIC NOT NULL);

CREATE TABLE tww_lords(
  id INTEGER PRIMARY KEY,
  race TEXT NOT NULL COLLATE NOCASE,
  race_game INTEGER NOT NULL CHECK(race_game IN (1,2,3)),                -- game the race came from (section order)
  race_order INTEGER NOT NULL,                                            -- A-Z within race_game by default; editable
  lord TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK(length(trim(lord)) > 0),
  faction TEXT, start_location TEXT, dlc TEXT, wiki_page TEXT,
  roc_playable INTEGER NOT NULL DEFAULT 0 CHECK(roc_playable IN (0,1)),
  card TEXT, portrait TEXT, faction_icon TEXT                             -- filenames in lords/
);

CREATE TABLE tww_campaigns(
  id INTEGER PRIMARY KEY,
  lord_id INTEGER NOT NULL REFERENCES tww_lords(id) ON DELETE RESTRICT,
  mode TEXT NOT NULL REFERENCES ref_tww_mode(name) ON UPDATE CASCADE,
  status TEXT NOT NULL REFERENCES ref_tww_status(name) ON UPDATE CASCADE,
  campaign_difficulty TEXT REFERENCES ref_tww_difficulty(name) ON UPDATE CASCADE,
  battle_difficulty TEXT REFERENCES ref_tww_difficulty(name) ON UPDATE CASCADE,
  started TEXT, finished TEXT, turns INTEGER CHECK(turns IS NULL OR turns > 0),
  hours NUMERIC CHECK(hours IS NULL OR hours > 0), patch TEXT, mods TEXT, coop_with TEXT, notes TEXT,
  mechanics INTEGER CHECK(mechanics BETWEEN 0 AND 5),
  roster INTEGER CHECK(roster BETWEEN 0 AND 5),
  start_position INTEGER CHECK(start_position BETWEEN 0 AND 5),
  challenge INTEGER CHECK(challenge BETWEEN 0 AND 5),
  narrative INTEGER CHECK(narrative BETWEEN 0 AND 5),
  late_game INTEGER CHECK(late_game BETWEEN 0 AND 5),
  enjoyment INTEGER CHECK(enjoyment BETWEEN 0 AND 5),
  CHECK(-- all seven ratings NULL, or none NULL (same rule as halo_levels)
    ...)
);
CREATE INDEX ix_tww_camp_lord ON tww_campaigns(lord_id);
```

- Only `lord_id`, `mode` and `status` are required. Every other campaign column can be NULL, so old
  campaigns can be filled in from memory.
- No UNIQUE rule on `lord_id` or `(lord_id, mode)`, so a lord can have any number of campaigns.
- `started` / `finished` use the same `YYYY-MM-DD` GLOB check as the other date columns, when filled in.
- `start_location` holds the Immortal Empires start. It differs by map, and IE is the one that covers
  every lord.
- Campaign `hours` is optional and separate from `play_log`. The play log is per game, so it can't be
  split by lord. The tab shows "589 h logged on WH3" as context next to the sum of campaign hours.

## 2. Scoring: `tww.py`
Standard library only, laid out like `halo.py`, and reusing its tier logic:

| Column | Label | What it judges | Weight |
|---|---|---|---|
| `mechanics` | Faction mechanics | How fun and deep the unique mechanics are | 5 |
| `roster` | Roster | Army variety; how strong late-game units are | 5 |
| `start_position` | Start position | Neighbours, room to expand, early pacing | 3 |
| `challenge` | Challenge | Difficulty curve, threats that matter | 3 |
| `narrative` | Narrative / lore | Quest battles, story, feeling of character | 2 |
| `late_game` | Late game | Whether it holds up after turn 80 or becomes a slog | 4 |
| `enjoyment` | Enjoyment | Overall fun | 5 |

- `load_scoring(con)` reads `lk_twwratingweights` (by `rowid`, like HaloRank) and `lk_tierlistscoring`
  (shared with HaloRank, so the tier bands match).
- `campaign_score` = SUMPRODUCT / SUM(weights). Its tier comes from `halo.tier_of`.
- **Lord score = their best rated campaign.** The tab has a toggle to show the average instead.
  Unrated campaigns count as "played" but have no score.
- `race_summary` gives, per race: lords played / total, campaigns per mode, and the average of each
  rating.

## 3. Lord list and images: `tools/fetch_tww_lords.py`
Run once to fill `tww_lords`, and again when new DLC lords come out. It inserts new lords and fills in
missing image filenames. It never edits `tww_campaigns` and never overwrites fields I have changed by
hand.

- **Source**: the Total War wiki's MediaWiki API, `https://totalwarwarhammer.fandom.com/api.php`. The
  normal wiki pages return 403/402 to scripts; the API answers when sent a browser User-Agent.
  - Lord list: the *Legendary lords* page (parse its tables by race), with `Category:Legendary lord
    units` as a cross-check.
  - Per lord: `prop=pageimages&piprop=original` gives the **portrait** (e.g. `Karl_Franz_3.png`, 600×830).
    `prop=images` lists the **unit card** (`<race>_ch_<name>_0.png`, e.g. `Emp ch karl 0.png`) and the
    **faction icon** (e.g. `Reikland.png`). `imageinfo&iiprop=url` turns a file name into its download URL.
  - Infobox wikitext (`prop=revisions&rvprop=content`) gives race, faction, start location and DLC.
  - `race_game` comes from a small race → game map in the script (e.g. Empire = 1, Skaven = 2, Kislev = 3,
    Chaos Dwarfs = 3). `race_order` is A–Z within each game.
  - `roc_playable` comes from the wiki's Realms of Chaos playable-factions list when the script can find
    it. Otherwise it is left as 0 and the script prints a reminder to set it by hand in the app. The
    script prints the lords it marks RoC-playable so they can be checked.
- **Output**: images go in `lords/` (git-ignored local cache, like `covers/`), named
  `<lord> - card.png`, `<lord> - portrait.png` and `<faction>.png`, with the same character-stripping
  rule as covers.
- The script prints every lord where it couldn't find a card, portrait or faction icon. Missing images
  fall back to a race-coloured tile with the lord's initials. Old World mod lords need nothing extra,
  because the mod uses the same lords.
- Lords for WH1/WH2 who are playable in WH3's Immortal Empires are included; they are part of the WH3
  roster.
- Manual check after the first run: compare the lord count per race with the wiki, and look through
  `lords/` for wrong matches (e.g. a mount icon picked up as the unit card).

## 4. App API and the app's Lords tab (for entering playthroughs)
`app.py`, following the HaloRank section:

- `GET /api/lords` returns lords, campaigns (scored), race summaries, weights/labels/cols, modes,
  statuses and tiers.
- `POST/PUT/DELETE /api/lords/campaigns[/<id>]` go through `insert_row`/`update_row`/`delete_row`, so
  Undo and History work automatically. A `clean_campaign()` validator checks that ratings are all seven
  or none, dates and turns are valid, and mode/status come from the ref tables.
- `POST/PUT /api/lords[/<id>]` add or edit a lord by hand (for anything the wiki script misses).
- `GET /lords/<file>` serves images from `lords/`.
- Add `tww_lords` and `tww_campaigns` to the CSV/zip export list.
- **Checks tab**: `finished` before `started`; a Realms of Chaos campaign for a lord with
  `roc_playable = 0`; a lord with no card image. Missing dates are **not** flagged, since old campaigns
  are allowed to leave them out.
- **UI** (`static/app.html`): race sections with lord cards (same look as the dashboard, smaller). Clicking
  a card opens a drawer with that lord's campaigns (newest first, each one editable or deletable) and a
  **+ Playthrough** form: mode and status (required); campaign and battle difficulty, dates, turns,
  hours, patch, mods, co-op with, seven rating sliders (0-5) and notes (all optional; the ratings are
  all seven or none). A live score/tier preview uses the same calculation as `tww.py`, like `haloVS`
  does for HaloRank. The lord edit form includes `roc_playable`, `race_game` and `race_order`.

## 5. Dashboard tab
`build_html.py` adds a `LORDS` payload: lords, scored campaigns, race summaries, weights/labels, and images
embedded as base64:

- Unit card: cropped/resized to one fixed size, JPEG ~q70.
- Portrait: ~240 px wide, JPEG ~q70, embedded for every lord, about 1.5 MB in total. (If that is too
  heavy: embed portraits only for played lords.)
- Faction icon: 32 px PNG.

The layout in `dashboard.template.html` (vanilla JS, inline SVG, no CDN, same as the other tabs):

- **Header**: tiles for "N / total lords played", campaigns, hours, campaigns per mode, and RoC progress
  ("RoC: 5 / 12 available played", counted over `roc_playable` lords only). Filter
  buttons: mode (All / RoC / IE / OW), played (All / Played / Unplayed), race dropdown. A Gallery / Tier
  list view toggle and a Best / Average score toggle.
- **Gallery view**: one section per race, in `race_order`. Each has a header strip with the race's faction
  icon, its name and a progress bar ("Dwarfs 3 / 8"), and can be collapsed. Inside is a grid of lord
  cards: unit card image, lord name, faction icon in a corner, tier badge, and RoC / IE / OW chips for
  the modes played. Unplayed lords are desaturated and dimmed.
- **Detail drawer** (click a card): portrait, faction, start location, DLC, then every campaign as a row,
  newest first (mode, status, campaign/battle difficulty, turns, dates, co-op partner, patch,
  score + tier pill). The best rated campaign is marked as the one setting the lord's score. Below
  that: a seven-bar rating chart for the selected campaign, and notes.
- **Tier list view**: S-F rows with lord card thumbnails, like HaloRank's tier view, colour-coded by
  race.
- **Summary table**: per race, lords played, campaign count, and the average of each rating, using the
  white → orange heat scale already used for counts.
- **Colours**: tiers reuse the existing tier colours. Race colours mark which race something belongs to
  (headers and tier-chip borders), they don't encode data, and they are kept muted so the
  tier colours stay the strongest. Red is not used for data, as in the rest of the dashboard.

## 6. Tests
- `tests/test_api.py`: create, edit, delete and undo a campaign; ratings must be all-or-none (400, like every
  other validation error, when only some are given); bad mode/status/difficulty is refused; deleting a lord that has campaigns is
  refused; a campaign with only lord + mode + status saves; two campaigns for the same lord and mode
  both save, and the lord's score is the better one.
- `tests/test_data.py` (or a new `tests/test_tww.py`): `tww.campaign_score` and tiers match a
  hand-worked example, and the band edges match `halo.tier_of`.
- The schema upgrade from v6 to v7 runs on a copy of the DB, and running it again does nothing.

## Build order
1. Schema v7 + `tww.py` + tests. **Done.**
2. `tools/fetch_tww_lords.py`. **Done.**
3. App API + Lords tab + checks. **Done.** I then enter my playthroughs.
4. Dashboard Lords tab, then a look at it in light and dark mode at phone width. **Done.** A lord's score is
   recomputed in the page so it follows the mode filter; under the RoC filter only RoC-playable lords are listed.
5. Update `README.md` / `PROJECT_CONTEXT.md` and archive this plan. **Done.**

## Out of scope for now
- PDF pages for the lords.
- Splitting the WH3 `play_log` hours by lord.
- Notes on each lord in general (separate from notes on each campaign).
