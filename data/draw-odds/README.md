# Draw Odds data backup

Copied here by `tools/build_utah.py --site` from the Draw Odds project
(OneDrive\Documents\Hunting\DrawOdds). That project is the source; this is a backup.

- `utah-<year>.json` - the compact data inlined into draw-odds.html
- `utah-tags-<year>.csv`, `utah-hunt-notes.csv` - hand-entered tag numbers and hunt notes
- `raw/utah_<year>_<typeId>.json` - utahdraws.com draw results. utahdraws only serves the
  current year, so once a year passes these files are the only copy. Keep them.
- `raw/utah_odds_<year>_0.pdf` / `_1.pdf` - DWR's draw odds reports (limited-entry and
  once-in-a-lifetime / general-season deer), kept in case DWR stops publishing them
- `raw/utah_odds_<year>.parsed.json` - those reports parsed into tables
- `raw/utah_harvest_<year>.pdf` - DWR harvest report used for harvest success

Rolling 5 years: files for draws older than that are removed from this backup on
each build. The Draw Odds project in OneDrive keeps its own copies.
