# Draw Odds — project context

`draw-odds.html` (live at https://elevationtechsolutions.net/draw-odds.html) is a Utah big
game draw odds tool. It replaces the spreadsheets the owner kept by hand for years
(`OneDrive\Documents\Hunting\DrawOdds2025.xlsx`, `ElkDrawOdds2026.xlsx` and older).
- **Scope:** Utah only for now. Other states (the owner also tracks Colorado and Wyoming points) will likely get **their own page**, not a state dropdown on this one.
- **History:** built Nov 2026 in `OneDrive\Documents\Hunting\DrawOdds`, then **moved into this repo on 2026-11-24** so it lives in one place. That OneDrive folder is now only an archive; don't build from it.

## Build and run

```
pip install pdfplumber pillow                   # pillow only needed for icon work
python tools/draw-odds/build_utah.py            # rebuild from cached downloads (~10 s)
python tools/draw-odds/build_utah.py --refresh  # re-download PDFs and current-year JSON (~5 min). Cached JSON
                                                # for PAST years (e.g. utah_2026_*.json once 2027 is current)
                                                # is never re-fetched; utahdraws only serves the current year.
```

- **What it writes:**
  - `draw-odds.html` at the repo root: the template with the data inlined (~900 KB).
  - `data/draw-odds/utah-<year>.json`.
  - It also prunes `data/draw-odds/raw/` to a **rolling 5 years** and refreshes `data/draw-odds/README.md`.
- **No git:** it never runs git. Commit and push like any other change; pushing `main` publishes (see the root `CLAUDE.md`).
- **Inline data:** the draw data is inlined because browsers block `fetch()` over `file://`. The same file works opened from disk and on the site. All paths are relative.
- **Windows console:** build output must stay ASCII (no `→`), or Python's cp1252 console crashes. Or set `PYTHONIOENCODING=utf-8`.
- **Never hand-edit `draw-odds.html`.** Edit `tools/draw-odds/template.html` (markup, CSS and all the JS odds math) or `build_utah.py` (data), then rebuild.
- **Template rules:** the page links the site's `style.css` and `nav.js`, so its nav and footer match every other page. Avoid `<section>` and `.container` in the template, which `style.css` restyles; the page uses `div.panel` and `.do-container`. Its page styles are inline and come after `style.css`.

## Files

| Path | What |
|---|---|
| `tools/draw-odds/template.html` | The page: styling, markup, all JS (analysis, projection, drop-ins, rendering). `/*__DATA__*/[]` is replaced with the data at build. |
| `tools/draw-odds/build_utah.py` | Downloads and parses everything, fits drop-ins, writes the data JSON, builds the page, prunes old years. |
| `tools/draw-odds/README.md` | Shorter how-to notes. Keep in sync with this file. |
| `draw-odds.html` | **Generated.** The published page. |
| `data/draw-odds/utah-2026.json` | Compact data the page uses (what `build_page()` injects). |
| `data/draw-odds/utah-tags-2027.csv` | **Fill in each spring** with next year's tag numbers (blank = not released). Auto-generated template. |
| `data/draw-odds/utah-hunt-notes.csv` | Owner's own hunt badges (`hunt_code,badge,note`), e.g. "Stag". Empty so far. |
| `data/draw-odds/raw/` | Downloads and caches, rolling 5 years: `utah_<year>_<typeId>.json` (utahdraws), `utah_odds_<year>_{0,1}.pdf` plus `.parsed.json`, `utah_harvest_<year>.pdf`. About 36 MB, committed on purpose as the backup. |
| `img/drawodds-*.png` | Species button icons: white PNGs from `C:\Users\hayden.j\Desktop\RackScore\rackscoreflutter\assets`, cropped and resized to 64 px tall. |
| `img/drawodds-icon.png`, `img/drawodds-screenshot.jpg` | App icon (a dice placeholder) and screenshot used on `apps.html` and `index.html`. |

## Data sources

- **Current draw (2026):** JSON endpoint behind utahdraws.com's official Draw Odds page:
  `https://www.utahdraws.com/internetsales/Home/DrawOddsData?drawName=Big%20Game&licenseYear=2026&masterHuntTypeID=N`.
  Only the current year is served (2025 returns empty).
  - **Type IDs:** 9 LE elk, 8 LE deer, 5 general-season deer (preference), 10 pronghorn, 11 moose, 13 desert bighorn, 14 Rocky bighorn, 12 bison, 15 goat.
  - **Skipped:** CWMU, Bonus Point and Preference Point categories, plus youth rows.
  - **Residency:** `ResidencyTypeID` 1 = resident, 2 = nonresident.
  - **Fields used:** `SuccessfulCount` (first choice) and `SuccessfulByMaxPointRoundCount` (bonus round).
  - **Hunt labels:** `SpeciesSubtypeName` / `HuntCategoryName` drive the automatic badges.
- **Earlier draws:** a rolling 5 years total. `HIST_YEARS = 4`, currently 2022–2025.
  - **Files:** DWR PDFs `https://wildlife.utah.gov/pdf/bg/<yyyy>/<yy>_bg-odds.pdf` (limited-entry and once-in-a-lifetime) and `<yy>_deer_odds.pdf` (general-season deer). The owner said 5 years is enough; don't add more.
  - **Layout:** one page per hunt (`Hunt: CODE ...`), with resident and nonresident tables side by side, parsed by regex.
  - **What they give:** permits *drawn*, not quota.
  - **From 2026 on,** a year's history comes from its cached utahdraws JSON (`history_from_json`), not a PDF.
- **Harvest:** `2025_gs_buck_deer_hr-preliminary.pdf`. Despite its name it covers all big game, by hunt number, and gives percent success of hunters afield. It's the newest available; DWR lists reports at wildlife.utah.gov/biggame/reports.
- **Hunt codes** are stable across years and are how everything joins.
- **Next year's tags:** DWR approves permit numbers in the spring. They're entered by hand in the CSV; the bonus/random split is derived automatically.

## Odds logic (all in `template.html`; the build mirrors the parts it needs)

Data rows are `[points, applicants, drew (all rounds), drew in bonus round]`. Quotas are `[total, bonus, random]`.

- **Utah bonus draw:** half the tags, rounded up, go to the bonus round. A single tag goes to the random round. This rule matched all 646 hunts in 2026.
- **Random round:** each applicant holds **points + 1 entries**, drawn without replacement.
  - **Evidence:** fitting this against 2026 random winners beat unweighted and squared weighting by far, and the model reproduced 6,566 vs 6,567 actual resident tags drawn.
  - **Odds formula:** P = 1 − e^(−w·τ), with τ solved so expected winners = tags.
- **Guaranteed (2026 column):** bonus hunts use the lowest point level that drew a bonus tag outright. If no one sat above the split group, guaranteed = split + 1.
  - This is the owner's rule: 10 people at 25 points with 8 bonus tags → 26.
  - Preference hunts (general deer) use the highest level where fewer than 90% drew as the split.
  - The owner's sheet sometimes used the stricter "everyone at that level drew". Example: Manti archery 2025, sheet 10 vs page 9, because 34 of 35 drew at 9. The page's rule was kept.
- **Next-year projection (2027):**
  1. Everyone who missed comes back with +1 point.
  2. Winners are removed.
  3. New applicants at 0 points = last year's 0-point count.
  4. Add drop-ins (below).
  5. Run the bonus round, then the random round with weights.
  6. Use 2027 tags if loaded, else 2026.
- **Drop-ins:** high-point applicants who appear each year and weren't in that hunt's pool before (switching hunts, point-only buyers returning).
  - **How they're measured:** from the 5-year history, as extra applicants at +1, +2, +3 and +4+ points above the projected split, **per bonus tag**.
  - **Example:** LE elk is about 0.66 per bonus tag, so Manti archery's 73 bonus tags get ~48.
  - **Which method won:** fitted and **backtested leave-one-year-out**. Per bonus tag beat per-applicant, a flat +1 bump, and no adjustment. LE elk exact hits: 206 of 510 per bonus tag, 158 plain, 152 for the bump.
  - **Where it's used:** only where it lowers mean absolute error. In 2026 that was LE elk, LE deer, desert sheep, bison and goat. Pronghorn, general deer, moose and Rocky sheep stay plain. The build prints the rates and backtest.
  - **Matching code:** JS `withDropins` and Python `_with_dropins` must stay identical; they were cross-checked with 0 mismatches over 140 elk hunts.
- **"2026 vs projected" column:** the owner's old spreadsheet check, where blue meant people jumped in and yellow meant people left.
  - **How it's computed:** project 2026 from 2025 the same way as 2027 (with drop-ins), using 2026's actual bonus/random split, then take actual − projected.
  - **Labels:** 0 = as projected, +1 or more = jumped in, −1 or less = left. The tooltip gives projected (including drop-ins), actual and why.
  - The drop-in rates include 2026, so this check isn't fully independent.
- **Trend columns:**
  - **Tag change** compares permits drawn, because the PDFs have no quotas. Undersubscribed hunts can show drops that aren't quota changes. Once 2027 tags are loaded, it compares quota to quota.
  - **Point creep** is guaranteed points 2026 − 2025, with 2026 − 2024 shown underneath.
- **Your odds:** the 2027 modelled odds at the active hunter's points. The small line shows "15 of 21,453 entries"; the owner asked for this instead of "1 in N". Small odds show real values (0.07%), never "<1%".

## UI decisions the owner made (keep these)

- **Styled like the website** because it *is* a site page: it uses `style.css`, `nav.js`, the shared nav and footer, and the title `<State> Draw Odds | Elevation Technology`. Dark only, with no light theme.
- **Top of the page:**
  - Species are **buttons with icons**, not a dropdown. Labels spell out "(Once-in-a-lifetime)", not OIAL.
  - **No state dropdown** while there's one state.
  - Weapon-type buttons sit at the top: Archery, Muzzleloader, Any Legal Weapon, Multi-Season, HAMSS. They allow more than one.
- **Hunters (profiles):** each has a name and points per species. They're saved in **localStorage** only, separate per browser, device and address, with Export/Import of JSON. No real family data is embedded; the owner's sheets hold private points.
- **Table:**
  - Columns: Hunt · 2026 tags · 2026 applicants · 2026 guaranteed at · 2026 split group · 2025 harvest success · [trend columns] · 2027 projected guaranteed · 2027 projected split · **<Name>'s 2027 odds (far right)**.
  - Every header carries its year.
  - **Trend columns** (Tag change, Point creep, 2026 vs projected) are **hidden by default** behind a "Show trend columns" checkbox. Turning it off clears their filters and sort.
  - Removed at the owner's request: the top group column and the average random-odds column.
  - Units are **grouped** (collapsible) when sorted by Hunt. Weapon buttons, search and the unit picker keep the grouping. Sorting by another column or a number filter makes the list flat.
  - Every column has a **filter button**: min/max for numbers, a unit multi-select for Hunt.
  - The **header row is frozen**: the table scrolls inside its own pane.
  - The table must fit at **1,400 px** width. Check `.tbl-wrap` scrollWidth vs clientWidth after adding anything.
- **Badges** come from DWR labels:
  - Management buck (rule R657-5-45: 3 points or less on at least one antler, eye guards don't count), Cactus buck, Premium, Restricted (restricted rifle: open or peep sights, no semi-auto, per R657-5-48), HAMSS, and bison Cow only / Hunter's choice.
  - The cactus buck and HAMSS wording is plain-language, unconfirmed against DWR, and says to check the guidebook.
- **Hunt detail view:** shows the 2026 table by point level with 2027 estimates, the year-by-year table (5 draws plus the 2027 projection), each hunter's 2027 odds, the random-draw entry count, notes, season dates, harvest and the projection text.
- **Notes at the bottom:**
  - "How the numbers are calculated", which is collapsible.
  - "About the 2027 projections", which covers the assumptions, the guaranteed = split + 1 example, and drop-in applicants with the per-bonus-tag rate table, examples and backtest.
- **On the rest of the site:** Draw Odds is listed as the fifth app, **outside** the Sort → View → Track → Score workflow. See the root `CLAUDE.md`.
- **Advertising the paid apps** (added 2026-11-24). The page is free, and the owner wants it to show off the paid apps without being annoying. The owner chose three placements:
  1. **Maker line** (`.maker-strip`): one quiet line under the intro, "Free from Elevation Technology Solutions, makers of …", with a link to each app and to `apps.html`.
  2. **Hunt detail suggestions** (`promoHtml` / `promoFor`): one or two apps at the bottom of a hunt's right-hand column, worded for that species.
     - The lead line is "Looks like you'll draw this one. Get ready:" when the active hunter's 2027 odds are 90% or better, otherwise "Getting ready for this hunt?".
     - **Only claim what each app supports:** Scorer covers elk, mule deer, whitetail, bighorn, pronghorn, bear and lion; Tracker covers elk, mule deer, whitetail, bighorn and bear; Detector identifies elk and deer.
     - So elk, deer and bighorn get Tracker + Scorer, pronghorn gets Scorer + Viewer, and moose, bison and goat get Viewer only. Recheck this if an app adds species.
  3. **"After the draw" section** (`.after-draw`): four cards in Sort → View → Track → Score order with the `apps.html` verbs, a one-line pitch and the price. **Prices are duplicated here**, so update them when a product page's price changes.
  - **Declined:** a pop-up (annoying, and it lands before the tool has given anything), a sidebar (the table needs the full width), and a "you'll draw" toast (held in reserve).
  - Icons are the 64px `img/menu-*.png` used by the nav dropdown. None of this shows when printing.
- **Copy voice:** plain, concrete, and honest about limitations, like the website.

## Yearly / seasonal tasks

- **Spring (DWR approves permit numbers):** fill in `res_2027` and `nonres_2027` in `data/draw-odds/utah-tags-2027.csv`, then rebuild, optionally with `--tags-source <url>`.
- **After the 2027 draw (late May/June):** run `python tools/draw-odds/build_utah.py --year 2027 --harvest-year 2026 --harvest-url <newest harvest PDF>`, then commit and push.
  - **Don't add `--refresh`**, and don't delete `data/draw-odds/raw/utah_2026_*.json`.
  - **Why:** DWR stopped making odds PDFs in 2026 (there is no `26_bg-odds.pdf`), and utahdraws only serves the current year. So the cached 2026 JSON is the **only** record of the 2026 draw.
  - **How it's used:** `history_from_json()` reads it automatically for that year. Tested: 478 of 478 hunts identical.
  - **Also do the same each year after:** keep each year's `utah_<year>_*.json`.
  - The history window moves to 2023–2026, the drop-ins are refit, and 2022's files are pruned automatically (they stay in git history). To force fresh current-year data, delete just `utah_2027_*.json` instead of using `--refresh`.
  - Also update the "2026"/"2027" wording on `apps.html` / `index.html` if any of it names years. It currently doesn't.

## Testing approach used

There's no test suite. Checks are done by:
- Extracting the JS analysis functions from `template.html` with Node (split on the `// ---------- last year's draw ----------` and `// ---------- columns, sorting, filtering ----------` markers) and running them against `data/draw-odds/utah-2026.json`.
- Headless Edge (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe --headless=new`):
  - `--screenshot` for visuals and `--dump-dom` with an injected script for measurements.
  - Seed localStorage with a `<script>` injected before `const STATES` in a temp copy (e.g. `_t.html` in the repo root, so `style.css` resolves), then delete the temp file.
  - Headless enforces a minimum width of about 490 px.
- The owner's spreadsheets may be open in Excel (file locked). Copy to a scratch folder before reading with openpyxl.

## Backlog / ideas (owner agreed to "later")

- **QUEUED, next up: click counters from Draw Odds to each app.** The owner wants to know how many clicks Draw Odds sends to each paid app's page. Not built yet.
  - **Links to tag:** the maker line, the hunt-detail suggestions, and the After the draw cards.
  - **Suggested approach:** add `?from=draw-odds` (or a per-placement value like `draw-odds-detail`) to those links, then record a row per click.
  - **How it fits the existing counters:** `downloads.js` writes one row per click to a separate Supabase table per app, with insert-only RLS and the publishable key. See "The four download counters" in the root `CLAUDE.md` and never merge those tables.
  - **Two options:**
    - A new table, e.g. `referrals_drawodds(app, placement, created_at)`, written from the Draw Odds page when a promo link is clicked.
    - Or the product pages read `?from=` and record it.
  - **Before building:**
    - Check the privacy policies still describe it accurately. They disclose anonymous, timestamped click counting.
    - The download-log admin page may want a view of these counts.
    - Over `http://localhost` the counters write real rows; test over `file://`.
- Shareable view: species, residency, search and filters in the URL.
- A real Draw Odds app icon to replace the dice placeholder (`img/drawodds-icon.png`).
- Possibly calibrate pronghorn and general deer differently, since drop-ins didn't help there.
- A flat-number-per-hunt drop-in variant was never backtested. The owner asked; it was offered, not done.
- Separate Colorado and Wyoming pages. Colorado uses preference points; Wyoming uses preference plus random.
