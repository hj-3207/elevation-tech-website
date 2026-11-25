# Draw Odds

Builds the site's big game draw odds pages: `draw-odds.html` (state picker) and `draw-odds-utah.html`. Full context
(logic, decisions, yearly tasks) is in `CLAUDE.md` next to this file.

## Rebuild
```
pip install pdfplumber
python tools/draw-odds/build_utah.py            # uses cached downloads
python tools/draw-odds/build_utah.py --refresh  # re-downloads PDFs and the current year
```
Then commit and push. The build never touches git.

## Species (Utah)
Limited-entry elk, deer and pronghorn; general-season deer; the once-in-a-lifetime species; and, since November 2026, limited-entry **black bear** (grouped by season) and **turkey** (residents and nonresidents draw from one pool).

## Files
- `tools/draw-odds/template.html` — the page: markup, page styles and all the odds math. It uses the site's `style.css` and `nav.js`.
- `tools/draw-odds/build_utah.py` — downloads, parses, builds `draw-odds.html` at the repo root.
- `data/draw-odds/` — the data:
  - the compact JSON the page uses
  - the tags and notes CSVs you edit
  - `raw/` downloads, kept for a rolling 5 years
- `img/drawodds-*.png` — species icons, app icon and screenshot.
- `img/drawodds-og-utah.jpg`, `img/drawodds-og-states.jpg` — link-preview cards (1200×630), made from `tools/draw-odds/og-card.html` with headless Edge.
- `tools/draw-odds/picker.html`, `states.json`, `west-map.json` — the state picker (`draw-odds.html`): the map page, the list of states (set `live` when a state is ready), and the map outlines.

## Pages
- `draw-odds.html` — pick a state on the map. Old Utah links with settings (`?sp=…`) forward to the Utah page.
- `draw-odds-utah.html` — Utah. Each state gets its own `draw-odds-<state>.html`.

## Next year's tag numbers
DWR approves permit numbers in the spring. Until they're loaded, the page projects with last year's tags and says so.
1. Fill in the `res_2027` / `nonres_2027` columns in `data/draw-odds/utah-tags-2027.csv`. Blank cells are skipped.
2. Rebuild, adding `--tags-source <link to DWR's permit document>` if you want it cited.

The bonus/random split is worked out automatically: half rounded up goes to bonus, and a single tag goes random.

Turkey has no resident/nonresident split: put the whole permit number in `res_2027` and leave `nonres_2027` blank. Hunts added to the page later are appended to the sheet automatically, blank.

## After each year's draw
```
python tools/draw-odds/build_utah.py --year 2027 --harvest-year 2026 --harvest-url <newest harvest PDF>
```
- **No `--refresh`.** Keep `data/draw-odds/raw/utah_<year>_*.json`. DWR stopped publishing odds PDFs in 2026 and utahdraws only serves the current year, so those files are the only record of past draws.
- **Automatic:** the build moves the 5-year window and refits the drop-ins.

## Hunters (profiles)
Points for each hunter are saved in the visitor's own browser (localStorage), not in the page:
- they persist across visits in that browser
- each browser and device keeps its own copy
- clearing browser data, or using a private window, loses them

Export / Import on the page backs them up or moves them. The export file (`draw-odds-points.json`) holds the hunters, their points and the starred hunts; importing merges hunters by name and adds stars without removing any.

## Drop-ins (projection calibration)
The plain projection assumes nobody switches hunts, and history shows it runs low. Every year people show up with points who weren't in that hunt's pool before.
- **What's measured:** for each species and residency, the build measures them from the 5-year history as extra applicants at 1, 2, 3 and 4+ points above the projected split, **per bonus tag**.
- **How it's tested:** fit on all years but one, then project the held-out year.
- **Where it's used:** only where it lowers the average error versus the plain projection.

The page adds `rate × bonus tags` people above the split before running next year's draw. "About the projections" on the page shows every species' rates and whether each species uses them.

Splitting the rates by weapon type was tested in 2026 and didn't improve accuracy, so it's one rate per species.
