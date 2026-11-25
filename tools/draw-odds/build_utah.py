"""
Build draw-odds-utah.html, the website's Utah draw odds page, and draw-odds.html,
the state picker (map) in front of every state's page.

1. Downloads the per-point draw results for each big game hunt type from
   utahdraws.com (the same JSON the official "Draw Odds" page uses), plus the
   four earlier draws from DWR's PDF reports and the DWR harvest report.
2. Compacts it all into data/draw-odds/utah-<year>.json and injects it into
   tools/draw-odds/template.html -> draw-odds-utah.html at the repo root, and
   builds tools/draw-odds/picker.html -> draw-odds.html (states.json, west-map.json).
3. Keeps data/draw-odds/raw/ to a rolling 5 years of draws.

Run from anywhere in the repo:
    python tools/draw-odds/build_utah.py              # use cached downloads when present
    python tools/draw-odds/build_utah.py --refresh    # re-download (current year + PDFs)
    python tools/draw-odds/build_utah.py --year 2027 --harvest-url <pdf url> --harvest-year 2026

Never runs git. Commit and push the results like any other change.
Requires: pdfplumber  (pip install pdfplumber)
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

TOOL = Path(__file__).resolve().parent          # tools/draw-odds
ROOT = TOOL.parent.parent                         # website repo root
DATA = ROOT / "data" / "draw-odds"                # compact data, CSVs you edit
RAW = DATA / "raw"                                # downloads and parsed caches

ODDS_URL = "https://www.utahdraws.com/internetsales/Home/DrawOddsData?drawName={draw}&licenseYear={year}&masterHuntTypeID={id}"
DEFAULT_HARVEST_URL = "https://wildlife.utah.gov/pdf/bg/2025/2025_gs_buck_deer_hr-preliminary.pdf"
DEFAULT_HARVEST_YEAR = 2025

# masterHuntTypeID -> (species key, label, short label for the buttons, draw system)
HUNT_TYPES = {
    9:  ("le-elk",    "Limited-Entry Bull Elk",      "LE Elk",       "bonus"),
    8:  ("le-deer",   "Limited-Entry Buck Deer",     "LE Deer",      "bonus"),
    5:  ("gs-deer",   "General-Season Buck Deer",    "General Deer", "preference"),
    10: ("pronghorn", "Limited-Entry Pronghorn",     "Pronghorn",    "bonus"),
    11: ("moose",     "Bull Moose (Once-in-a-lifetime)",           "Moose",        "bonus"),
    13: ("desert-bighorn", "Desert Bighorn Sheep (Once-in-a-lifetime)", "Desert Sheep", "bonus"),
    14: ("rocky-bighorn",  "Rocky Mtn Bighorn Sheep (Once-in-a-lifetime)", "Rocky Sheep", "bonus"),
    12: ("bison",     "Bison (Once-in-a-lifetime)",                "Bison",        "bonus"),
    15: ("goat",      "Mountain Goat (Once-in-a-lifetime)",        "Mtn Goat",     "bonus"),
    1:  ("bear",      "Limited-Entry Black Bear",    "Bear",         "bonus"),
    3:  ("turkey",    "Limited-Entry Turkey",        "Turkey",       "bonus"),
}
# Draws outside "Big Game" on utahdraws.com (its DrawOddsSupplementData lists them all).
DRAW_NAME = {1: "Black Bear", 3: "Turkey"}
# Turkey: residents and nonresidents (and youth, after their 15% youth round) draw from
# one pool, so its tables merge everyone and both residency views show the same thing.
POOLED = {3}
# Bear and turkey hunts are labelled by season, not weapon (DWR lists every one as
# "Any Legal Weapon"); their season windows keep DWR's wording rather than "Rifle".
SEASON_LABELS = {1, 3}
# Species button icons: img/drawodds-*.png (white PNGs from the Rack Scorer app
# assets, cropped and resized to 64px tall). Types without an icon show text only.
ICONS = {
    "le-elk": "img/drawodds-elk.png",
    "le-deer": "img/drawodds-deer.png",
    "gs-deer": "img/drawodds-deer.png",
    "pronghorn": "img/drawodds-pronghorn.png",
    "desert-bighorn": "img/drawodds-bighorn.png",
    "rocky-bighorn": "img/drawodds-bighorn.png",
    "moose": "img/drawodds-moose.png",
    "bison": "img/drawodds-bison.png",
    "goat": "img/drawodds-goat.png",
    "bear": "img/drawodds-bear.png",      # Rack Scorer's BearPawWhite128.png
    "turkey": "img/drawodds-turkey.png",  # Rack Scorer's turkeyFan512.png
}


def weapon_type(weapon):
    """Bucket DWR's weapon names into the filter buttons at the top of the page."""
    w = weapon.lower()
    if "multi" in w:
        return "Multi-Season"
    if "h.a.m.s.s" in w or "hamss" in w:
        return "HAMSS"
    if "archery" in w:
        return "Archery"
    if "muzzleloader" in w:
        return "Muzzleloader"
    if "rifle" in w or "any legal weapon" in w:
        return "Rifle"
    return "Other"


def auto_notes(h, weapon):
    """Short badges for hunts with special rules, from DWR's own hunt labels.
    Sources: R657-5-45 (management buck), R657-5-48 (restricted weapons)."""
    sub = (h.get("SpeciesSubtypeName") or "").lower()
    cat = (h.get("HuntCategoryName") or "").lower()
    w = weapon.lower()
    notes = []
    if "management" in sub or cat == "management":
        notes.append(["Management buck", "Management buck: 3 points or less on at least one antler, counting from the first fork. Eye guards don't count."])
    if "cactus" in sub:
        notes.append(["Cactus buck", "Cactus buck hunt: bucks whose antlers stay in velvet. Check the guidebook for the exact definition."])
    if "premium" in sub or cat == "premium":
        notes.append(["Premium", "Premium limited-entry hunt."])
    if "cow only" in sub:
        notes.append(["Cow only", "Cow bison only."])
    if "hunter's choice" in sub:
        notes.append(["Hunter's choice", "Bull or cow."])
    if "h.a.m.s.s" in w:
        notes.append(["HAMSS", "H.A.M.S.S.: handgun, archery, muzzleloader, shotgun or straight-walled cartridge rifle only. Check the guidebook for the exact equipment rules."])
    if "restricted rifle" in w:
        notes.append(["Restricted", "Restricted rifle: open or peep sights only, no semi-automatic."])
    elif "restricted" in w:
        notes.append(["Restricted", "Restricted weapon hunt: limited equipment. Check the guidebook."])
    return notes
def bear_notes(season):
    """Hounds/bait badges for limited-entry bear, from DWR's black bear guidebook (2025
    pp. 42-47; unchanged in the 2026 edition, pp. 73-80; R657-33): spring and fall allow dogs but no bait; summer allows bait
    (bait station COR required, no early baiting) but no dogs; multi-season follows the
    rules of whichever season you hunt in. "The only bear season that allows bait is the
    summer limited-entry season." Max 16 dogs in spring and fall."""
    s = season.lower()
    if s in ("spring", "fall"):
        return [["Hounds", f"{season} bear: dogs allowed (up to 16 in a pursuit), no bait. Some units close to dogs at times; check the guidebook."]]
    if s == "summer":
        return [["Bait", "Summer bear: bait allowed where permitted (a bait station registration from DWR is required first, no early baiting); no dogs."]]
    if s == "multi-season":
        return [["Hounds or bait", "Multi-season bear: each season's rules apply while you hunt it, so dogs in spring and fall, bait (with a bait station registration) in summer."]]
    if "spot" in s:
        return [["No hounds or bait", "Spot-and-stalk bear: no dogs and no bait."]]
    return []


SKIP_CATEGORIES = {"CWMU", "Bonus Point", "Preference Point"}
RES = {1: "R", 2: "N"}  # ResidencyTypeID


def fetch(url, dest, refresh):
    if dest.exists() and not refresh:
        return dest.read_bytes()
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (draw-odds builder)",
        "Accept": "application/json, application/pdf, */*",
        "X-Requested-With": "XMLHttpRequest",
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return body


def plain_weapon(name):
    """DWR says "Any Legal Weapon"; hunters say "Rifle". The owner asked for the common
    term everywhere on the page ("Early Any Legal Weapon" -> "Early Rifle")."""
    return re.sub(r"(?i)any legal weapon", "Rifle", name or "")


def season_label(h):
    """Bear/turkey: "Bear Spring" -> "Spring", "Bear Multi-season" -> "Multi-Season".
    Goes by DWR's season name, not IsMultiseasonHunt: fall bear hunts have two windows
    and are flagged multi-season, but DWR calls them "Bear Fall"."""
    if "multi" in (h.get("SpeciesSubtypeName") or "").lower():
        return "Multi-Season"
    sub = re.sub(r"(?i)^(bear|le bearded turkey)\s*", "", (h.get("SpeciesSubtypeName") or "").strip())
    if sub:
        return sub[0].upper() + sub[1:].lower()
    start = ((h.get("SeasonWeapons") or [{}])[0].get("SeasonStartDate") or "")[5:7]
    return {"03": "Spring", "04": "Spring", "05": "Spring"}.get(start, "Spring" if "turkey" in (h.get("SpeciesSubtypeName") or "").lower() else "Other")


def weapon_label(h, tid=None):
    if tid in SEASON_LABELS:
        return season_label(h)
    if h.get("IsMultiseasonHunt") or len(h.get("SeasonWeapons") or []) > 1:
        return "Multi-Season"
    sw = (h.get("SeasonWeapons") or [{}])[0]
    return plain_weapon((sw.get("WeaponName") or "").strip()) or "—"


def seasons(h, tid=None):
    keep = tid in SEASON_LABELS   # bear/turkey: DWR's own wording ("Any Legal Weapon")
    out = []
    for s in h.get("SeasonWeapons") or []:
        w = s.get("WeaponName", "")
        out.append([w if keep else plain_weapon(w), (s.get("SeasonStartDate") or "")[:10], (s.get("SeasonEndDate") or "")[:10]])
    return out


def merge_rows(*tables):
    """Add up [points, applicants, drew, drew_in_bonus] rows from several tables by point level."""
    m = {}
    for t in tables:
        for p, a, d, b in t:
            r = m.setdefault(p, [p, 0, 0, 0])
            r[1] += a; r[2] += d; r[3] += b
    return sorted(m.values(), key=lambda r: -r[0])


def compact_hunt(h, system, tid=None):
    pooled = tid in POOLED
    rows = {"R": {}, "N": {}}
    for o in h.get("OddsList") or []:
        res = RES.get(o.get("ResidencyTypeID"))
        if res is None or (o.get("IsYouth") and not pooled):
            continue
        pts = int(round(o.get("Point") or 0))
        r = rows[res].setdefault(pts, [pts, 0, 0, 0])
        r[1] += o.get("ParticipantCount") or 0
        r[2] += o.get("SuccessfulCount") or 0
        r[3] += o.get("SuccessfulByMaxPointRoundCount") or 0

    def q(prefix):
        tot = h.get(f"{prefix}QuotaQuantity") or 0
        mx = h.get(f"{prefix}MaxPointRoundQuota")
        rg = h.get(f"{prefix}RegularRoundQuota")
        if system == "preference" or mx is None:
            mx, rg = tot, 0
        return [tot, mx or 0, rg or 0]

    rows = {k: sorted(v.values(), key=lambda r: -r[0]) for k, v in rows.items()}
    if pooled:
        # One pool: everyone's rows together, and the whole quota split by Utah's rule
        # (checked: 2026 bonus-round draws match half rounded up within a tag or two,
        # the youth round accounting for the difference).
        both = merge_rows(rows["R"], rows["N"])
        rows = {"R": both, "N": both}
        quota = split_quota(h.get("QuotaQuantity") or 0, system)
        quota = {"R": quota, "N": quota}
    else:
        quota = {"R": q("Resident"), "N": q("NonResident")}
    wl = weapon_label(h, tid)
    return {
        "code": h["HuntCode"],
        "unit": h["HuntName"].strip(),
        "weapon": wl,
        "seasons": seasons(h, tid),
        "wtype": wl if tid in SEASON_LABELS else weapon_type(wl),
        "notes": auto_notes(h, wl) + (bear_notes(wl) if tid == 1 else []),
        "map": h.get("HuntMapURL") or "",
        "quota": quota,
        "rows": rows,
    }


HARVEST_LINE = re.compile(
    r"^([A-Z]{2}\d{4})\s.*?\s(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$"
)


def parse_harvest(pdf_bytes, dest):
    import pdfplumber
    dest.write_bytes(pdf_bytes)
    out = {}
    with pdfplumber.open(dest) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                m = HARVEST_LINE.match(line.strip())
                if not m:
                    continue
                code, permits, hunters, harvest, pct = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), float(m.group(5))
                out[code] = [permits, hunters, harvest, pct]
    return out


# Bear and turkey harvest are in their own DWR reports (wildlife.utah.gov/hunting/reports
# and /uplandgame/reports), one table row per hunt number:
#  - bear: annual black bear report, "Hunt number, Hunt name, Permits sold, Male, Female,
#    Total harvest, % permits filled" (no hunters-afield count, so success = permits filled).
#  - turkey: upland game annual report <yyyy-1>-<yy>, "Spring wild turkey harvest statistics
#    by hunt": Hunt, name, Permits, n (surveyed), Hunters, Harvest, Days afield, Percent
#    success. Its spring season is the one right after that year's draw.
SPECIES_HARVEST = {
    "bear": {"year": 2025, "url": "https://wildlife.utah.gov/pdf/annual-reports/bear/{yy}_black_bear_report.pdf",
             "line": re.compile(r"^(BR\d{4})\s+.+?\s(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$")},
    "turkey": {"year": 2026, "url": "https://wildlife.utah.gov/pdf/annual-reports/upland/{prev}-{yy}.pdf",
               "line": re.compile(r"^(TK\d{4})\s+.+?\s(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$")},
}


def parse_species_harvest(key, pdf_path):
    """{hunt_code: [permits, hunters afield or None, harvested, percent]}."""
    import pdfplumber
    line_re = SPECIES_HARVEST[key]["line"]
    out = {}
    table = ""   # title of the table the rows belong to ("Table 7. ... multi-season limited-entry ...")
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                if re.match(r"^\s*T\s?able\s*\d+", line):
                    table = line.lower()
                m = line_re.match(line.strip())
                if not m:
                    continue
                # The bear report's conservation-permit table (Table 8) reuses limited-entry
                # hunt numbers; only the drawn limited-entry permits belong on this page.
                if key == "bear" and "conservation" in table:
                    continue
                v = [int(x) for x in m.groups()[1:]]
                if key == "bear":     # permits, male, female, total, % filled
                    out[m.group(1)] = [v[0], None, v[3], float(v[4])]
                else:                 # permits, n surveyed, hunters, harvest, days, % success
                    out[m.group(1)] = [v[0], v[2], v[3], float(v[5])]
    return out


def apply_species_harvest(species, refresh):
    for sp in species:
        cfg = SPECIES_HARVEST.get(sp["key"])
        if not cfg:
            continue
        y = cfg["year"]
        url = cfg["url"].format(yy=str(y)[2:], prev=y - 1)
        pdf = RAW / f"utah_{sp['key']}_harvest_{y}.pdf"
        try:
            fetch(url, pdf, refresh)
            hv = parse_species_harvest(sp["key"], pdf)
        except Exception as e:
            print(f"  ! {sp['key']} harvest report not available ({e})", file=sys.stderr)
            continue
        n = 0
        for h in sp["hunts"]:
            if h["code"] in hv:
                h["harvest"] = hv[h["code"]]
                n += 1
        sp["harvestYear"], sp["harvestSource"] = y, url
        print(f"  {sp['short']} {y} harvest: {n}/{len(sp['hunts'])} hunts")


# Bear harvest-objective (over-the-counter) hunts: a permit bought without drawing, good on
# a unit until its quota is met. Listed in DWR's black bear guidebook hunt tables
# ("Harvest-objective hunts": unit, harvest quota, season dates, hunting method). The
# guidebook URL has no year in it; the cached copy is named for the year on its cover.
BEAR_GUIDEBOOK_URL = "https://wildlife.utah.gov/guidebooks/black-bear-cougar-furbearer-guidebook.pdf"
# DWR's live list: each harvest-objective unit's quota, harvest to date, remaining, open or
# closed, and method. (The guidebook's "wildlife.utah.gov/bearharvest" link was a 404 in Nov 2026.)
BEAR_HO_STATUS_URL = "https://wildlife.utah.gov/bear/harvest"
_MON = r"(?:Jan|Feb|March|April|May|June|July|Aug|Sept|Oct|Nov|Dec)\.?"
_DATES = rf"{_MON} \d+[–-]{_MON} \d+"
HO_ROW = re.compile(rf"^(.+?) (\d+)(?: ({_DATES}))? (No bait(?:/no dogs)?)$")
HO_DATES = re.compile(rf"^({_DATES})$")


def parse_bear_ho(pdf_path):
    """{"year", "fee": [res, nonres], "sale": "March 10", "units": {unit: [[quota, [dates...], method]]}}.
    In the table a unit with two seasons prints its dates on the lines above and below the row."""
    import pdfplumber
    out = {"year": None, "fee": None, "sale": None, "units": {}}
    with pdfplumber.open(pdf_path) as pdf:
        cover = " ".join((pdf.pages[0].extract_text() or "").split())
        m = re.search(r"GUIDEBOOK (20\d\d)", cover)
        out["year"] = int(m.group(1)) if m else None
        for page in pdf.pages:
            text = page.extract_text() or ""
            flat = " ".join(text.split())
            if out["fee"] is None:
                m = re.search(r"Harvest-objective hunts Permit fee: Resident \$(\d+), Nonresident \$(\d+)", flat)
                if m:
                    out["fee"] = [int(m.group(1)), int(m.group(2))]
            if out["sale"] is None:
                m = re.search(r"harvest-objective permits will be available to residents and nonresidents, begin- ?ning (\w+ \d+)", flat, re.I)
                if m:
                    out["sale"] = m.group(1)
            if "Harvest-objective hunts" not in text:
                continue
            lines = [l.strip() for l in text.splitlines()]
            start = next((i for i, l in enumerate(lines) if l.startswith("Unit name quota Season dates method")), None)
            if start is None:
                continue
            body = lines[start + 1:]
            for i, l in enumerate(body):
                m = HO_ROW.match(l)
                if not m:
                    continue
                unit, quota, dates, method = m.group(1), int(m.group(2)), m.group(3), m.group(4)
                if dates:
                    windows = [dates]
                else:  # two seasons: one date line above the row, one below
                    windows = [x.group(1) for x in (HO_DATES.match(body[i - 1]) if i else None,
                                                     HO_DATES.match(body[i + 1]) if i + 1 < len(body) else None) if x]
                out["units"].setdefault(unit, []).append([quota, [w.replace("-", "–") for w in windows], method])
    return out


def apply_bear_ho(species, refresh):
    """Badge every limited-entry bear hunt whose unit also has a harvest-objective hunt."""
    sp = next((s for s in species if s["key"] == "bear"), None)
    if not sp:
        return
    # Reuse the newest saved copy unless --refresh; otherwise download and save it under
    # the year printed on its cover.
    saved = sorted(RAW.glob("utah_bear_guidebook_*.pdf"))
    try:
        if saved and not refresh:
            ho = parse_bear_ho(saved[-1])
        else:
            tmp = RAW / "utah_bear_guidebook.pdf"
            fetch(BEAR_GUIDEBOOK_URL, tmp, True)
            ho = parse_bear_ho(tmp)
            dated = RAW / f"utah_bear_guidebook_{ho['year'] or 'unknown'}.pdf"
            tmp.replace(dated)
    except Exception as e:
        print(f"  ! bear guidebook not available ({e})", file=sys.stderr)
        return
    # The owner first had a badge on every unit with an OTC hunt, then (same day) asked for
    # one note at the bottom instead, since most units have one. The page builds that note
    # from this summary and links DWR's live unit list and the guidebook.
    sp["ho"] = {"year": ho["year"], "units": len(ho["units"]), "fee": ho["fee"], "sale": ho["sale"],
                "status": BEAR_HO_STATUS_URL, "guide": BEAR_GUIDEBOOK_URL}
    print(f"  bear harvest-objective ({ho['year']} guidebook): {len(ho['units'])} units with an OTC hunt")


def split_quota(total, system):
    """Utah's split, checked against every 2026 hunt: the bonus round gets half
    the tags rounded up, the random round the rest; a single tag goes random."""
    if system == "preference":
        return [total, total, 0]
    bonus = 0 if total <= 1 else -(-total // 2)
    return [total, bonus, total - bonus]


def apply_next_tags(species, path, next_year):
    """Merge next year's tag numbers from a CSV. Writes a fill-in template if the
    file doesn't exist yet. Blank cells mean "not released" and are skipped."""
    import csv
    cols = ["hunt_code", "species", "unit", "weapon", "res_prev", "nonres_prev", f"res_{next_year}", f"nonres_{next_year}"]
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for sp in species:
                for h in sp["hunts"]:
                    w.writerow([h["code"], sp["short"], h["unit"], h["weapon"], h["quota"]["R"][0], h["quota"]["N"][0], "", ""])
        print(f"  wrote tag template {path} (fill in the {next_year} columns when DWR releases them)")
        return 0
    rows, listed = {}, set()
    with path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            code = (r.get("hunt_code") or "").strip().upper()
            listed.add(code)
            res, non = (r.get(f"res_{next_year}") or "").strip(), (r.get(f"nonres_{next_year}") or "").strip()
            if code and (res or non):
                rows[code] = (int(float(res or 0)), int(float(non or 0)))
    # Hunts added to the page after the sheet was made (e.g. bear and turkey, Nov 2026):
    # append them blank so they can be filled in too. Pooled species (turkey) list their
    # whole quota under res_prev; fill the total into res_<year> and leave nonres blank.
    extra = [(sp, h) for sp in species for h in sp["hunts"] if h["code"] not in listed]
    if extra:
        with path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for sp, h in extra:
                pooled = sp.get("pooled")
                w.writerow([h["code"], sp["short"], h["unit"], h["weapon"], h["quota"]["R"][0], "" if pooled else h["quota"]["N"][0], "", ""])
        print(f"  added {len(extra)} new hunts to {path.name} (blank, to fill in)")
    n = 0
    known = set()
    for sp in species:
        for h in sp["hunts"]:
            known.add(h["code"])
            if h["code"] in rows:
                r, nr = rows[h["code"]]
                if sp.get("pooled"):   # one pool: the sheet's total covers everyone
                    both = split_quota(r + nr, sp["system"])
                    h["next"] = {"R": both, "N": both}
                else:
                    h["next"] = {"R": split_quota(r, sp["system"]), "N": split_quota(nr, sp["system"])}
                n += 1
    missing = sorted(set(rows) - known)
    print(f"  {next_year} tags loaded for {n} hunts" + (f"; not in draw data (new hunt #s?): {', '.join(missing[:12])}" if missing else ""))
    return n


# Earlier draws exist only as DWR PDFs: one for limited-entry / once-in-a-lifetime
# (bonus points) and one for general-season deer (preference points). Both print
# one table per hunt with residents and nonresidents side by side.
HIST_YEARS = 4  # earlier draws to keep: with the current year, a rolling 5 years


def hist_pdfs(draw_year):
    """The PDF links for the HIST_YEARS draws before draw_year (DWR's naming)."""
    out = {}
    for y in range(draw_year - HIST_YEARS, draw_year):
        yy = str(y)[2:]
        out[y] = [f"https://wildlife.utah.gov/pdf/bg/{y}/{yy}_bg-odds.pdf",
                  f"https://wildlife.utah.gov/pdf/bg/{y}/{yy}_deer_odds.pdf"]
    return out
# Bear and turkey have their own DWR odds reports, in the same layout as the big game
# ones (parse_hist_pdf reads them unchanged). Each is cached on its own:
# raw/utah_<name>_odds_<year>.pdf and .parsed.json. Listed at wildlife.utah.gov/odds.
EXTRA_HIST = {
    "bear":   "https://wildlife.utah.gov/pdf/bear/{yy}_drawing_odds.pdf",
    "turkey": "https://wildlife.utah.gov/pdf/uplandgame/turkey/{yyyy}_turkey_bonus_points_draw_results.pdf",
}
HIST_ROW = re.compile(r"^(\d+) (\d+) (\d+) (\d+) (\d+) (?:N/A|1 in [\d.,]+) (\d+) (\d+) (\d+) (\d+) (\d+) (?:N/A|1 in [\d.,]+)$")
HIST_HUNT = re.compile(r"^Hunt: (\w+) ")


def parse_hist_pdf(pdf_path):
    """{hunt_code: {"R": rows, "N": rows}} with rows as [points, applicants, drew, drew_in_bonus_round]."""
    import pdfplumber
    out = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            lines = (page.extract_text() or "").splitlines()
            code = next((m.group(1) for m in map(HIST_HUNT.match, lines) if m), None)
            if not code:
                continue  # species summary pages
            hunt = out.setdefault(code, {"R": [], "N": []})
            for line in lines:
                m = HIST_ROW.match(line)
                if not m:
                    continue
                v = [int(x) for x in m.groups()]
                for res, (pts, apps, bonus, reg, tot) in (("R", v[0:5]), ("N", v[5:10])):
                    if apps:
                        hunt[res].append([pts, apps, tot, bonus])
    return out


def history_from_json(year):
    """Since 2026, DWR publishes odds only on utahdraws.com (no PDF), and that
    site serves only the current year. So a year's cached utahdraws JSON
    (data/draw-odds/raw/utah_<year>_<typeId>.json, saved when it was the current year) is
    the history source for that year. Keep those files."""
    files = [RAW / f"utah_{year}_{tid}.json" for tid in HUNT_TYPES]
    if not all(f.exists() for f in files):
        return None
    out = {}
    for f, (tid, (key, label, short, system)) in zip(files, HUNT_TYPES.items()):
        for h in json.loads(f.read_bytes()).get("Data") or []:
            if h.get("HuntCategoryName") in SKIP_CATEGORIES:
                continue
            out[h["HuntCode"]] = compact_hunt(h, system, tid)["rows"]
    return out


def load_history(refresh, draw_year):
    """Parse each year's PDFs once and cache the result next to them."""
    hist = {}
    for year, urls in hist_pdfs(draw_year).items():
        from_json = history_from_json(year)
        if from_json is not None:
            hist[year] = from_json
            print(f"  {year} history from cached utahdraws JSON: {len(from_json)} hunts")
            continue
        cache = RAW / f"utah_odds_{year}.parsed.json"
        if cache.exists() and not refresh:
            merged = json.loads(cache.read_text(encoding="utf-8"))
        else:
            merged = {}
            for i, url in enumerate(urls):
                pdf = RAW / f"utah_odds_{year}_{i}.pdf"
                fetch(url, pdf, refresh)
                merged.update(parse_hist_pdf(pdf))
            cache.write_text(json.dumps(merged, separators=(",", ":")), encoding="utf-8")
            print(f"  parsed {year} draw PDFs: {len(merged)} hunts")
        for name, pattern in EXTRA_HIST.items():
            extra_cache = RAW / f"utah_{name}_odds_{year}.parsed.json"
            if extra_cache.exists() and not refresh:
                extra = json.loads(extra_cache.read_text(encoding="utf-8"))
            else:
                pdf = RAW / f"utah_{name}_odds_{year}.pdf"
                try:
                    fetch(pattern.format(yy=str(year)[2:], yyyy=year), pdf, refresh)
                except Exception as e:  # a missing year shouldn't stop the build
                    print(f"  ! {name} {year} odds PDF not available ({e})", file=sys.stderr)
                    continue
                extra = parse_hist_pdf(pdf)
                extra_cache.write_text(json.dumps(extra, separators=(",", ":")), encoding="utf-8")
                print(f"  parsed {year} {name} odds PDF: {len(extra)} hunts")
            merged = {**merged, **extra}
        hist[year] = merged
    return hist


def apply_history(species, hist):
    """Attach earlier years' tables to hunts by hunt number."""
    for year, by_code in sorted(hist.items()):
        n = 0
        for sp in species:
            for h in sp["hunts"]:
                t = by_code.get(h["code"])
                if t and (t["R"] or t["N"]):
                    if sp.get("pooled") and t["R"] is not t["N"]:
                        both = merge_rows(t["R"], t["N"])   # the PDFs split residents and nonresidents
                        t = {"R": both, "N": both}
                    h.setdefault("hist", {})[str(year)] = t
                    n += 1
        print(f"  {year} draw results matched to {n} current hunts")


# ---------------------------------------------------------------------------
# Drop-ins: applicants who show up with high points that last year's pool can't
# account for (people switching from other hunts, point-only buyers coming back).
# Measured from the history as extra applicants at 1, 2, 3 and 4+ points above
# the projected split, per bonus tag. Backtested by fitting on all but one year
# and projecting that year; used only where it beats the plain projection.
# The page's JS mirrors next_pool / the bonus round exactly.
# ---------------------------------------------------------------------------
def _next_pool(rows):
    pool = {}
    for p, a, d, b in rows:
        if a - d > 0:
            pool[p + 1] = pool.get(p + 1, 0) + (a - d)
    zero = next((r for r in rows if r[0] == 0), None)
    if zero:
        pool[0] = pool.get(0, 0) + zero[1]
    return pool


def _bonus_round(pool, bonus):
    """(guaranteed points, split level) for handing `bonus` tags out top-down."""
    left, guar = bonus, None
    for p in sorted(pool, reverse=True):
        c = pool[p]
        if c <= 0:
            continue
        if left > 0 and c <= left + 1e-9:
            left -= c; guar = p; continue
        return (guar if guar is not None else p + 1), p
    return (guar if guar is not None else 0), None


def _actual_guar(rows, system):
    rows = sorted([r for r in rows if r[1] > 0], key=lambda r: -r[0])
    if not rows:
        return None
    if system == "bonus":
        idx = max([i for i, r in enumerate(rows) if r[3] > 0], default=-1)
        if idx < 0:
            return None
        low = rows[idx]
        if low[3] < low[1]:
            return rows[idx - 1][0] if idx > 0 else low[0] + 1
        return low[0]
    i = len(rows) - 1
    while i >= 0 and rows[i][2] / rows[i][1] < 0.9:
        i -= 1
    if i == len(rows) - 1:
        return rows[i][0]
    return rows[i][0] if i >= 0 else rows[i + 1][0] + 1


def _with_dropins(pool, bonus, d):
    _, split = _bonus_round(pool, bonus)
    if split is None:
        return pool
    out = dict(pool)
    for k, rate in enumerate(d, start=1):
        if rate > 0:
            out[split + k] = out.get(split + k, 0) + rate * bonus
    return out


def fit_dropins(species, draw_year):
    for sp in species:
        sp["dropin"] = {}
        for res in ("R", "N"):
            by_year = {}
            for h in sp["hunts"]:
                years = {int(y): t[res] for y, t in (h.get("hist") or {}).items()}
                years[draw_year] = h["rows"][res]
                for y in sorted(years):
                    prev, cur = years.get(y - 1), years[y]
                    if not prev or not cur:
                        continue
                    prev = sorted([r for r in prev if r[1] > 0], key=lambda r: -r[0])
                    cur = [r for r in cur if r[1] > 0]
                    bonus = sum(r[3] for r in cur) if sp["system"] == "bonus" else sum(r[2] for r in cur)
                    act = _actual_guar(cur, sp["system"])
                    if bonus > 0 and act is not None:
                        by_year.setdefault(y, []).append((prev, cur, bonus, act))

            def fit(samples):
                extra, tags = [0.0] * 4, 0.0
                for prev, cur, bonus, _ in samples:
                    pool = _next_pool(prev)
                    _, split = _bonus_round(pool, bonus)
                    if split is None:
                        continue
                    tags += bonus
                    act = {r[0]: r[1] for r in cur}
                    for p in set(pool) | set(act):
                        if p > split:
                            extra[min(p - split, 4) - 1] += act.get(p, 0) - pool.get(p, 0)
                return [max(0.0, e / tags) if tags else 0.0 for e in extra]

            plain, adj = [], []
            for y, test in by_year.items():
                d = fit([s for yy, ss in by_year.items() if yy != y for s in ss])
                for prev, cur, bonus, act in test:
                    pool = _next_pool(prev)
                    plain.append(act - _bonus_round(pool, bonus)[0])
                    adj.append(act - _bonus_round(_with_dropins(pool, bonus, d), bonus)[0])
            if not plain:
                continue
            stat = lambda v: {"avg": round(sum(v) / len(v), 2), "mae": round(sum(abs(x) for x in v) / len(v), 2),
                              "within1": sum(abs(x) <= 1 for x in v), "exact": sum(x == 0 for x in v), "n": len(v)}
            sp_, sa = stat(plain), stat(adj)
            use = sa["mae"] < sp_["mae"]
            d_all = fit([s for ss in by_year.values() for s in ss])
            sp["dropin"][res] = {"d": [round(x, 4) for x in d_all], "use": use, "plain": sp_, "adjusted": sa,
                                 "years": f"{min(by_year)}–{max(by_year)}"}
            if res == "R":
                print(f"  drop-ins {sp['short']:<13} per 10 bonus tags: " + " ".join(f"+{k}:{x * 10:.2f}" for k, x in enumerate(d_all, 1))
                      + f" | exact {sp_["exact"]}->{sa["exact"]}/{sa['n']}, mae {sp_["mae"]}->{sa["mae"]} -> {'use' if use else 'plain'}")


def apply_user_notes(species, path):
    """Your own badges, e.g. "Stag hunt". One row per note; a row with the same
    badge as an automatic note replaces that note's text."""
    import csv
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["hunt_code", "badge", "note"])
        print(f"  wrote empty {path.name} (add your own hunt notes there)")
        return
    by_code = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            code = (r.get("hunt_code") or "").strip().upper()
            badge = (r.get("badge") or "").strip()
            if code and badge:
                by_code.setdefault(code, []).append([badge, (r.get("note") or "").strip() or badge])
    n = 0
    for sp in species:
        for h in sp["hunts"]:
            for badge, note in by_code.get(h["code"], []):
                h["notes"] = [x for x in h["notes"] if x[0].lower() != badge.lower()] + [[badge, note]]
                n += 1
    print(f"  your hunt notes applied: {n}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026, help="draw year to pull from utahdraws.com")
    ap.add_argument("--harvest-url", default=DEFAULT_HARVEST_URL)
    ap.add_argument("--harvest-year", type=int, default=DEFAULT_HARVEST_YEAR)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--tags-csv", help="next year's tag numbers (default data/draw-odds/utah-tags-<year+1>.csv)")
    ap.add_argument("--tags-source", default="", help="link to DWR's document the new tag numbers came from")
    a = ap.parse_args()

    species = []
    for type_id, (key, label, short, system) in HUNT_TYPES.items():
        url = ODDS_URL.format(draw=urllib.parse.quote(DRAW_NAME.get(type_id, "Big Game")), year=a.year, id=type_id)
        body = fetch(url, RAW / f"utah_{a.year}_{type_id}.json", a.refresh)
        payload = json.loads(body)
        hunts = [compact_hunt(h, system, type_id) for h in payload.get("Data") or []
                 if h.get("HuntCategoryName") not in SKIP_CATEGORIES]
        if not hunts:
            print(f"  ! no data for {label} {a.year}", file=sys.stderr)
            continue
        hunts.sort(key=lambda h: (h["unit"], h["weapon"], h["code"]))
        sp = {"key": key, "label": label, "short": short, "icon": ICONS.get(key, ""), "system": system, "hunts": hunts}
        if type_id in POOLED:
            sp["pooled"] = True
        species.append(sp)
        print(f"  {label}: {len(hunts)} hunts")

    harvest_pdf = fetch(a.harvest_url, RAW / f"utah_harvest_{a.harvest_year}.pdf", a.refresh)
    harvest = parse_harvest(harvest_pdf, RAW / f"utah_harvest_{a.harvest_year}.pdf")
    print(f"  harvest rows parsed: {len(harvest)}")
    matched = 0
    for sp in species:
        for h in sp["hunts"]:
            hv = harvest.get(h["code"])
            if hv:
                h["harvest"] = hv
                matched += 1
    total = sum(len(s["hunts"]) for s in species)
    print(f"  hunts with harvest data: {matched}/{total}")
    apply_species_harvest(species, a.refresh)
    apply_bear_ho(species, a.refresh)

    apply_history(species, load_history(a.refresh, a.year))
    fit_dropins(species, a.year)
    apply_user_notes(species, DATA / "utah-hunt-notes.csv")
    next_year = a.year + 1
    tags_csv = Path(a.tags_csv) if a.tags_csv else DATA / f"utah-tags-{next_year}.csv"
    loaded = apply_next_tags(species, tags_csv, next_year)

    state = {
        "state": "UT",
        "name": "Utah",
        "drawYear": a.year,
        "nextYear": next_year,
        "nextTags": loaded > 0,
        "harvestYear": a.harvest_year,
        "sources": {
            "odds": "https://utahdraws.com/drawodds",
            "harvest": a.harvest_url,
            "tags": a.tags_source,
        },
        "species": species,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / f"utah-{a.year}.json").write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    build_page()
    prune_raw(a.year)


NOTICE = """<!-- GENERATED FILE - do not edit. Source: tools/draw-odds/template.html,
     built by tools/draw-odds/build_utah.py (see tools/draw-odds/CLAUDE.md).
     Edits made here are overwritten on the next build. -->
"""


def build_page():
    """One page per live state, plus the state picker.

    - draw-odds-<state>.html: the template with that state's latest
      data/draw-odds/<state>-<year>.json inlined (so the page also opens straight from
      disk; browsers block fetch() over file://) and the state list for the switcher.
    - draw-odds.html: the map picker (tools/draw-odds/picker.html), with the map, the
      state list, and the nav and footer copied from the template so they stay in sync.
    The state list (names, pages, which are live) is tools/draw-odds/states.json."""
    states = json.loads((TOOL / "states.json").read_text(encoding="utf-8"))
    latest = {}
    for f in sorted(DATA.glob("*-*.json")):
        st = json.loads(f.read_text(encoding="utf-8"))
        if st["state"] not in latest or st["drawYear"] > latest[st["state"]]["drawYear"]:
            latest[st["state"]] = st
    template = (TOOL / "template.html").read_text(encoding="utf-8")
    slist = json.dumps(states, separators=(",", ":")).replace("</", "<\\/")
    for s in states:
        if not s["live"]:
            continue
        st = latest.get(s["code"])
        if not st:
            raise SystemExit(f"states.json marks {s['name']} live but there is no data/draw-odds/{s['code'].lower()}-<year>.json")
        blob = json.dumps([st], separators=(",", ":")).replace("</", "<\\/")
        page = (template.replace("/*__DATA__*/[]", blob).replace("/*__STATELIST__*/[]", slist)
                .replace("__PAGE__", s["page"]).replace("__STATENAME__", s["name"])
                .replace("__OGIMAGE__", f"drawodds-og-{s['page'][len('draw-odds-'):-len('.html')]}.jpg")
                .replace("<!DOCTYPE html>\n", "<!DOCTYPE html>\n" + NOTICE, 1))
        out = ROOT / s["page"]
        out.write_text(page, encoding="utf-8")
        print(f"  wrote {out.name} ({out.stat().st_size // 1024} KB)")
    build_picker(states, template)


def build_picker(states, template):
    """draw-odds.html: the Western states map (tools/draw-odds/west-map.json) and list."""
    from html import escape
    m = json.loads((TOOL / "west-map.json").read_text(encoding="utf-8"))
    by_code = {s["code"]: s for s in states}
    # Label nudges where the bounding-box centre sits badly (Idaho's panhandle, etc.).
    nudge = {"ID": (6, 38), "CA": (-14, 8), "MT": (0, -4), "NV": (-4, -14), "WA": (0, 4), "AZ": (0, 6)}
    parts = []
    for code, g in m["states"].items():
        s = by_code.get(code)
        dx, dy = nudge.get(code, (0, 0))
        x, y = g["cx"] + dx, g["cy"] + dy
        if not s:   # context only (on the map but not in states.json, e.g. WA, CA): outline, no label
            parts.append(f'<g class="ctx"><path d="{g["d"]}"/></g>')
            continue
        status = "Open" if s["live"] else "Under construction" if s.get("building") else "Coming later"
        label = (f'<text class="code" x="{x}" y="{y}">{code}</text>'
                 f'<text class="sub" x="{x}" y="{y + 12}">{status}</text>')
        title = f'<title>{escape(s["name"])}: {status.lower()}</title>'
        if s["live"]:
            parts.append(f'<a class="live" href="{s["page"]}" aria-label="{escape(s["name"])} draw odds">{title}<path d="{g["d"]}"/>{label}</a>')
        elif s.get("building"):
            # Under construction: clickable, but it opens the notice on this page.
            parts.append(f'<a class="building" href="#{s["code"].lower()}" data-building="{s["code"]}" aria-label="{escape(s["name"])}: under construction">{title}<path d="{g["d"]}"/>{label}</a>')
        else:
            parts.append(f'<g class="soon">{title}<path d="{g["d"]}"/>{label}</g>')
    svg = (f'<svg viewBox="{m["viewBox"]}" role="img" aria-label="Map of the Western states and Kansas. '
           f'{", ".join(s["name"] for s in states if s["live"])} ready; the others are coming later.">' + "".join(parts) + "</svg>")
    items, notices = [], []
    for s in sorted(states, key=lambda s: (not s["live"], not s.get("building"), s["name"])):
        go = "Open →" if s["live"] else "Under construction" if s.get("building") else "Coming later"
        inner = (f'<span class="nm">{escape(s["name"])}</span><span class="sys">{escape(s["system"])}</span>'
                 f'<span class="go">{go}</span>')
        if s["live"]:
            items.append(f'<li><a class="st live" data-code="{s["code"]}" href="{s["page"]}">{inner}</a></li>')
        elif s.get("building"):
            items.append(f'<li><a class="st building" data-code="{s["code"]}" data-building="{s["code"]}" href="#{s["code"].lower()}">{inner}</a></li>')
            notices.append(f'<div class="notice" id="notice-{s["code"].lower()}" role="status" hidden>'
                           f'<b>{escape(s["name"])} is under construction.</b> {escape(s.get("notice", "")).replace(escape(s["name"]) + " is under construction. ", "")}</div>')
        else:
            items.append(f'<li><div class="st soon" data-code="{s["code"]}">{inner}</div></li>')
    nav = re.search(r"<nav>.*?</nav>", template, re.S).group(0)
    footer = re.search(r"<footer>.*?</footer>", template, re.S).group(0)
    page = ((TOOL / "picker.html").read_text(encoding="utf-8")
            .replace("<!--__MAP__-->", svg).replace("<!--__LIST__-->", "".join(notices) + "<ul>" + "".join(items) + "</ul>")
            .replace("<!--__NAV__-->", nav).replace("<!--__FOOTER__-->", footer)
            .replace("<!DOCTYPE html>\n", "<!DOCTYPE html>\n" + NOTICE.replace("template.html", "picker.html"), 1))
    out = ROOT / "draw-odds.html"
    out.write_text(page, encoding="utf-8")
    print(f"  wrote {out.name} ({out.stat().st_size // 1024} KB, state picker)")


def prune_raw(draw_year):
    """Rolling 5 years: delete downloads and caches for draws older than the window.
    (They stay in git history.) Also refreshes data/draw-odds/README.md."""
    first = draw_year - HIST_YEARS
    year_of = lambda name: int(re.search(r"_(\d{4})", name).group(1))
    pruned = [f for f in RAW.iterdir() if f.is_file() and re.search(r"_(\d{4})", f.name) and year_of(f.name) < first]
    for f in pruned:
        f.unlink()
    if pruned:
        print(f"  removed {len(pruned)} files for draws before {first} from data/draw-odds/raw/")
    (DATA / "README.md").write_text(
        "# Draw Odds data\n\n"
        "Read and written by `tools/draw-odds/build_utah.py` (see `tools/draw-odds/CLAUDE.md`).\n\n"
        "- `utah-<year>.json` - the compact data inlined into draw-odds.html\n"
        "- `utah-tags-<year>.csv`, `utah-hunt-notes.csv` - hand-entered tag numbers and hunt notes\n"
        "- `raw/utah_<year>_<typeId>.json` - utahdraws.com draw results. utahdraws only serves the\n"
        "  current year, so once a year passes these files are the only copy. Keep them.\n"
        "- `raw/utah_odds_<year>_0.pdf` / `_1.pdf` - DWR's draw odds reports (limited-entry and\n"
        "  once-in-a-lifetime / general-season deer), kept in case DWR stops publishing them\n"
        "- `raw/utah_odds_<year>.parsed.json` - those reports parsed into tables\n"
        "- `raw/utah_harvest_<year>.pdf` - DWR harvest report used for harvest success\n\n"
        "Rolling 5 years: the build deletes files for draws older than that.\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
