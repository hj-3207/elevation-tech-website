"""
Colorado data for the Draw Odds pages (stage 1: download and parse).

Colorado Parks and Wildlife publishes, per species and year, a "Draw Recap" PDF (every
hunt code: quota, how many residents/nonresidents/youth/landowners drew, and the
applicants and successful draws at every preference point level for choices 1-4) and a
"Drawn Out At" report. The species statistics pages link them on CPW's file host
(cpw.widen.net). Valid units per hunt code come from CPW's Chapter W-2 regulation.

The PDFs are large (the 2026 elk recap is 1,282 pages / 29 MB), so they are kept OUTSIDE
the repo, in the owner's OneDrive (PDF_DIR). The repo keeps only the parsed tables:
    data/draw-odds/raw/colorado_<species>_<year>_recap.json
    data/draw-odds/raw/colorado_<species>_<year>_drawnout.json   (2024: the only record)
    data/draw-odds/raw/colorado_w2_units_<year>.json
    data/draw-odds/raw/colorado_sources.json                      (where each file came from)

Run:
    python -P tools/draw-odds/build_colorado.py            # download what's missing, parse what's new
    python -P tools/draw-odds/build_colorado.py --reparse  # re-parse every PDF (after a parser change)
Parsing takes ~3 minutes per large recap; parsed JSON is cached, so reruns are quick.
See tools/draw-odds/CLAUDE.md.
"""
import argparse, json, re, sys, urllib.request
from pathlib import Path

TOOL = Path(__file__).resolve().parent
ROOT = TOOL.parent.parent
RAW = ROOT / "data" / "draw-odds" / "raw"
PDF_DIR = Path(r"C:\Users\hayden.j\OneDrive\Documents\Hunting\DrawOddsData\colorado")

STATS = "https://cpw.state.co.us/hunting/big-game/{slug}/statistics"
# page slug -> [(species key, test on the link's file name)]
PAGES = {
    "elk": [("elk", lambda n: True)],
    "deer": [("deer", lambda n: True)],
    "pronghorn": [("pronghorn", lambda n: True)],
    "moose": [("moose", lambda n: True)],
    "bear": [("bear", lambda n: True)],
    "mountain-goat": [("goat", lambda n: True)],
    "bighorn-sheep": [("desert-bighorn", lambda n: "deser" in n),
                      ("rocky-bighorn", lambda n: "deser" not in n)],
}
YEARS = range(2022, 2027)          # rolling 5 draws, like Utah
W2_URL = "https://cpw.state.co.us/sites/default/files/dam/ykldhjuxtt/chw02-as-approved-may-2026.pdf"
W2_YEAR = 2026
UA = {"User-Agent": "Mozilla/5.0 (draw-odds builder)"}


def get(url, tries=4):
    """Fetch with retries: CPW's file host occasionally drops a request or a DNS lookup."""
    import time
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"  ! {e}; retrying in {10 * (i + 1)} s", file=sys.stderr)
            time.sleep(10 * (i + 1))


def link_year(name):
    m = re.search(r"(20\d\d)", name)
    if m:
        return int(m.group(1))
    m = re.search(r"-(\d\d)_\d{8}", name)      # postdrawrecapreport_elk-26_05142026_1426
    return 2000 + int(m.group(1)) if m else None


def discover():
    """{(species, year, kind): share_url} from CPW's statistics pages (kind: recap | drawnout)."""
    found = {}
    for slug, variants in PAGES.items():
        html = get(STATS.format(slug=slug)).decode("utf-8", "ignore")
        for url, name in re.findall(r'href="(https://cpw\.widen\.net/s/[a-z0-9]+/([^"]+))"', html):
            n = name.lower()
            if "secondary" in n:
                continue
            # 2024's recaps are named "2024-primary-elk-post-draw-report" (no "recap").
            kind = ("drawnout" if ("drawnout" in n or "drawn-out" in n)
                    else "recap" if ("recap" in n or "post-draw-report" in n) else None)
            year = link_year(n)
            if not kind or year not in YEARS:
                continue
            for key, test in variants:
                if test(n):
                    found.setdefault((key, year, kind), url)
    return found


def download_share(share_url, dest):
    """cpw.widen.net share page -> the original PDF."""
    page = get(share_url).decode("utf-8", "ignore")
    m = re.search(r'"(/content/[a-z0-9]+/original/[^"]+?download=true)"', page)
    if not m:
        raise RuntimeError(f"no download link on {share_url}")
    body = get("https://cpw.widen.net" + m.group(1).replace("&amp;", "&"))
    if not body.startswith(b"%PDF"):
        raise RuntimeError(f"{share_url} did not return a PDF")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)


# --------------------------------------------------------------------------- recap
CODE = re.compile(r"^([A-Z]{2}[A-Z0-9]{3}[A-Z]\d[A-Z])$")   # goat/sheep units are letters: GEG01O1A
TOK = r"(?:\d+|-)"
ROW = re.compile(rf"^(?:1 )?(\d+) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK}) (?:1 )?(\d+) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK})$")
# Moose, Rocky Mountain bighorn and goat: two key columns, preference points (0-3) and
# weighted points. Row key "3w24" = 3 preference points, 24 weighted.
ROW_W = re.compile(rf"^(?:1 )?(\d+) (\d+) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK}) (?:1 )?(\d+) (\d+) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK})$")
TOT = re.compile(rf"^Total Choice (\d) ((?:{TOK} ){{5}}{TOK}) Total Choice \1 ((?:{TOK} ){{5}}{TOK})$")
EIGHT = re.compile(r"(?:^| )(\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)$")   # 2022 has labels before the numbers
HEADER = re.compile(r"(?i)^(colorado parks and wildlife|.*post draw report|\d+/\d+/\d{4} |page \d+ of )")
_n = lambda x: 0 if x == "-" else int(x)


WEIGHTED = {"moose", "goat", "rocky-bighorn"}   # preference + weighted points (two key columns)


def parse_recap(path, weighted=False):
    """{code: {quota, drawn, hybrid, nrcap, rows, choice}} from a CPW Draw Recap PDF.
      drawn  post-draw # drawn: [total, balance, adult R, adult N, youth R, youth N, LPP unres, LPP res]
      hybrid [max %, licenses drawn in the hybrid draw]   nrcap [nonresident cap %, nonresidents drawn]
      rows   {pts: [apps aR, aN, yR, yN, drew aR, aN, yR, yN]} for first choice
      choice {1-4: {"apps": [aR, aN, yR, yN], "drew": [...]}}
    Checked: every hunt's rows add up to CPW's own Total Choice 1 line (verify_recap)."""
    import pdfplumber
    hunts, cur, in_table = {}, None, False
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            lines = [l.strip() for l in (page.extract_text() or "").splitlines()]
            body = [l for l in lines if not HEADER.match(l)]
            # A hunt starts with its code on the first line. Older recaps (2022) also have
            # combined hunts: several codes sharing one quota and one table, listed together
            # ("EF003O2R EF003O3R"). Those are keyed "EF003O2R+EF003O3R" with "shared".
            first = body[0].split() if body else []
            if first and all(CODE.match(c) for c in first):
                cur = {"quota": None, "drawn": None, "hybrid": None, "nrcap": None, "rows": {}, "choice": {}}
                if len(first) > 1:
                    cur["shared"] = first
                hunts["+".join(first)] = cur
                in_table = False
                quota_from = None
            if cur is None:
                continue
            for i, l in enumerate(body):
                # Total quota: the first line after the "Total Quota ..." header that starts
                # with a number (2026: two lines down; 2022: the next line).
                if cur["quota"] is None and l.startswith("Total Quota"):
                    quota_from = i
                if cur["quota"] is None and quota_from is not None and i > quota_from:
                    m = re.match(r"^(\d+) ", l)
                    if m:
                        cur["quota"] = int(m.group(1))
                m = re.search(r"Hybrid Draw \(up to\) (\d+)% (\d+)", l)
                if m and cur["hybrid"] is None:
                    cur["hybrid"] = [int(m.group(1)), int(m.group(2))]
                m = re.search(r"NonResident Cap \(up to\) (\d+)% (\d+)", l)
                if m and cur["nrcap"] is None:
                    cur["nrcap"] = [int(m.group(1)), int(m.group(2))]
                if cur["drawn"] is None and "Hybrid Draw" in l:
                    for j in range(i, min(i + 5, len(body))):   # same line on goat/sheep/moose pages
                        m = EIGHT.search(body[j])
                        if m:
                            cur["drawn"] = [int(x) for x in m.groups()]
                            break
                # Table header. On weighted-point species it comes out scrambled
                # ("Choice Pre P fe o r in e t n s ce W P e o ig ..."), so key on its ends.
                if l.startswith("Choice ") and "Res NonRes" in l:
                    in_table = True
                    continue
                # A weighted row for 1 preference point ("1 0 5 3 ...") also fits the
                # one-column pattern with a choice label, so the species decides which.
                m = (ROW_W if weighted else ROW).match(l)
                if in_table and m:
                    g = [_n(x) for x in m.groups()]
                    if weighted:
                        cur["rows"][f"{g[0]}w{g[1]}"] = g[2:6] + g[10:14]
                    else:
                        cur["rows"][g[0]] = g[1:5] + g[8:12]
                    continue
                m = TOT.match(l)
                if m:
                    a = [_n(x) for x in m.group(2).split()]
                    b = [_n(x) for x in m.group(3).split()]
                    cur["choice"][int(m.group(1))] = {"apps": a[:4], "drew": b[:4]}
                    in_table = False
    return hunts


def verify_recap(hunts, quirks=None):
    """Hunts whose point rows don't add up to CPW's own Total Choice 1 line.
    A known CPW quirk is listed separately in `quirks` instead: on the once-in-a-lifetime
    species CPW's total counts 1-6 more APPLICANTS than its point rows show (checked by
    hand on SMS06O1A 2026: rows add to 28, total says 29), while the "drew" columns always
    match. That doesn't affect who drew, so it isn't treated as a parse error."""
    bad = []
    for code, h in hunts.items():
        c = h["choice"].get(1) or h["choice"].get("1")   # int keys when fresh, str after JSON
        s = [sum(r[i] for r in h["rows"].values()) for i in range(8)]
        if not c:
            bad.append(code); continue
        if s == c["apps"] + c["drew"]:
            continue
        extra_apps = [t - r for t, r in zip(c["apps"], s[:4])]
        if s[4:] == c["drew"] and all(0 <= x <= 6 for x in extra_apps):
            if quirks is not None:
                quirks.append(code)
            continue
        bad.append(code)
    return bad


# --------------------------------------------------------------------------- drawn out
DO_CODE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{3}[A-Z]\d[A-Z])\b")


def parse_drawnout(path):
    """{code: {"R": [label, k, n], "N": [...]}} from a "Drawn Out At" report (adults).
    2024 has no recap for most species, so this is that year's only record. Via
    pdfplumber's tables: a "Drawn Out At" row (code, list, label, Res, NonRes, youth...,
    e.g. "4 Pref\\nPoints", "Choice 2", "Leftover", "None\\nDrawn", "No Apps") followed by a
    "# Drawn at Final Level" row ("369 of\\n415"). k of n drew at that final level."""
    import pdfplumber
    out, cur = {}, None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for t in page.extract_tables():
                for row in t:
                    cells = [re.sub(r"\s+", " ", c or "").strip() for c in row]
                    if len(cells) < 5:
                        continue
                    if DO_CODE.fullmatch(cells[0] or "") and cells[2] == "Drawn Out At":
                        cur = cells[0]
                        out[cur] = {"R": [cells[3], None, None], "N": [cells[4], None, None]}
                    elif cur and cells[2].startswith("# Drawn at Final Level"):
                        for res, c in (("R", cells[3]), ("N", cells[4])):
                            m = re.match(r"(\d+) of (\d+)", c)
                            if m:
                                out[cur][res][1:] = [int(m.group(1)), int(m.group(2))]
                        cur = None
    return out


def drawnout_record(v):
    """[label, k, n] -> {"guar": points, "split": [pts, n, k] or None} the way the page reads a
    year (guaranteed = the level above a partly drawn final level), or None if nothing drew."""
    label, k, n = v
    m = re.match(r"(\d+) Pref Points$", label or "")
    if m:
        x = int(m.group(1))
        if k is not None and n and k < n:
            return {"guar": x + 1, "split": [x, n, k]}
        return {"guar": x, "split": None}
    if (label or "").startswith(("Choice", "Leftover")):
        return {"guar": 0, "split": None}          # every first choice drew
    return None


# --------------------------------------------------------------------------- W-2 units
W2_CODE = re.compile(r"\b([DEAMBSG][MEF][A-Z0-9]{3}[A-Z]\d[ARMX])\b")


def parse_w2_units(path):
    """{code: "41, 42, 52, 411, 421, 521"} from CPW Chapter W-2 via pdfplumber's tables.
    The unit cell is merged over a group of code rows (None below the first row, '' at
    the top of a continued page), so the last unit text carries down. Ranching for
    Wildlife codes aren't in W-2."""
    import pdfplumber
    out, carry = {}, ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for t in page.extract_tables():
                if not t:
                    continue
                hdr = [((c or "").replace("\n", " ")) for c in t[0]]
                ucol = next((i for i, c in enumerate(hdr) if c.lower().startswith("unit")), 0 if len(t[0]) >= 3 else None)
                if ucol is None:
                    continue
                for row in t:
                    cells = [(c or "") for c in row]
                    codes = [m.group(1) for c in cells for m in W2_CODE.finditer(c)]
                    u = row[ucol] if ucol < len(row) else None
                    if u and u.strip() and not W2_CODE.search(u) and re.match(r"^\s*(\d|Public|All |Statewide)", u):
                        carry = re.sub(r"\s+", " ", u).replace(",,", ",").strip()
                    for c in codes:
                        if carry:
                            out[c] = carry
    return out


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reparse", action="store_true")
    ap.add_argument("--only", help="species key to limit to (e.g. elk)")
    ap.add_argument("--year", type=int, help="draw year to limit to (e.g. 2022)")
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    src_path = RAW / "colorado_sources.json"
    sources = json.loads(src_path.read_text(encoding="utf-8")) if src_path.exists() else {}

    found = discover()
    print(f"  CPW links found: {len(found)}")
    for (key, year, kind), url in sorted(found.items()):
        if (a.only and key != a.only) or (a.year and year != a.year):
            continue
        if kind == "drawnout" and (key, year, "recap") in found:
            continue   # the recap already has everything the drawn-out report does
        pdf = PDF_DIR / f"{key}_{year}_{kind}.pdf"
        out = RAW / f"colorado_{key}_{year}_{kind}.json"
        if not pdf.exists():
            print(f"  downloading {key} {year} {kind} ...")
            download_share(url, pdf)
        sources[f"{key}_{year}_{kind}"] = url
        if out.exists() and not a.reparse:
            continue
        if kind == "recap":
            data = parse_recap(pdf, weighted=key in WEIGHTED)
            quirks = []
            bad = verify_recap(data, quirks)
            print(f"  parsed {key} {year} recap: {len(data)} hunt codes, {len(bad)} not matching CPW's totals {bad[:5]}"
                  + (f" ({len(quirks)} with CPW's extra-applicant quirk)" if quirks else ""))
        else:
            data = parse_drawnout(pdf)
            print(f"  parsed {key} {year} drawn-out: {len(data)} hunt codes")
        out.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    w2_pdf = PDF_DIR / f"w2_{W2_YEAR}.pdf"
    w2_out = RAW / f"colorado_w2_units_{W2_YEAR}.json"
    if not w2_pdf.exists():
        w2_pdf.parent.mkdir(parents=True, exist_ok=True)
        w2_pdf.write_bytes(get(W2_URL))
    sources[f"w2_{W2_YEAR}"] = W2_URL
    if not w2_out.exists() or a.reparse:
        units = parse_w2_units(w2_pdf)
        w2_out.write_text(json.dumps(units, separators=(",", ":")), encoding="utf-8")
        print(f"  parsed W-2 units: {len(units)} hunt codes")
    src_path.write_text(json.dumps(sources, indent=1, sort_keys=True), encoding="utf-8")


# --------------------------------------------------------------------------- season dates
# 2026 dates per hunt code, from CPW's 2026 big game brochure and the 2026 sheep and goat
# brochure (state library copies, kept in PDF_DIR). Two kinds:
#  - row dates: "Oct. 14–18 Cow E-F-018-O1-R B", or with a license count on sheep/goat
#    "Sept. 8–22 3 Ram S-M-S03-O1-R";
#  - table dates: a title like "Archery — Limited Licenses — Season Dates: Sept. 2–30"
#    covering codes on that page without a date of their own.
# Codes the brochures don't date readably get the most common dates of their species,
# season and method (e.g. elk 1st rifle Oct. 14–18), marked "standard" on the page.
BROCHURES = {
    "biggame_brochure_2026.pdf": "https://spl.cde.state.co.us/artemis/nrserials/nr1431internet/nr14312026internet.pdf",
    "sheepgoat_brochure_2026.pdf": "https://spl.cde.state.co.us/artemis/nrserials/nr1430internet/nr14302026internet.pdf",
}
_MON = r"(?:Jan|Feb|March|Mar|April|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)\.?"
_DATE = rf"{_MON} \d{{1,2}}\s?[–-]\s?(?:{_MON} )?\d{{1,2}}"
_SEX = r"(?:New\s+)?(?:\d+\s+)?(?:Either|Bull|Cow|Buck|Doe|Antlered|Antlerless|Ram|Ewe|Billy|Nanny|Male|Female|Either-sex|Any)?"
_ROWD = re.compile(rf"({_DATE})\s+{_SEX}\s*\+?\s*([A-Z]-[A-Z]-[A-Z0-9]{{3}}-[A-Z]\d-[A-Z])")
_BCODE = re.compile(r"\b([A-Z]-[A-Z]-[A-Z0-9]{3}-[A-Z]\d-[A-Z])\b")
_TITLE = re.compile(rf"(?i)(Archery|Muzzleloader|Rifle)[^:]{{0,80}}?Season Dates?:\s*({_DATE})")
_TITLE_METHOD = {"archery": "A", "muzzleloader": "M", "rifle": "R"}
_MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _iso(text, year):
    m = re.match(rf"({_MON}) (\d+)\s?[–-]\s?(?:({_MON}) )?(\d+)", text)
    if not m:
        return None
    m1, d1 = _MONTHS[m.group(1)[:3]], int(m.group(2))
    m2, d2 = (_MONTHS[m.group(3)[:3]] if m.group(3) else m1), int(m.group(4))
    return [f"{year}-{m1:02d}-{d1:02d}", f"{year + 1 if m2 < m1 else year}-{m2:02d}-{d2:02d}"]


def parse_brochure_dates(path, year):
    """{code: [start, end]} (ISO dates) from one brochure PDF."""
    import pdfplumber
    out = {}
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            flat = " ".join((pg.extract_text() or "").split())
            for m in _ROWD.finditer(flat):
                out.setdefault(m.group(2).replace("-", ""), _iso(m.group(1), year))
            # A table title's dates cover that table's codes only: same weapon as the title
            # ("Archery — Limited Licenses — Season Dates: Sept. 2–30" doesn't date a
            # muzzleloader code printed elsewhere on the page). No weapon in the title: none.
            tm = _TITLE.search(flat)
            if tm and tm.group(1):
                d, meth = _iso(tm.group(2), year), _TITLE_METHOD[tm.group(1).lower()]
                for m in _BCODE.finditer(flat):
                    c = m.group(1).replace("-", "")
                    if c[7] == meth:
                        out.setdefault(c, d)
    return out


def season_dates(year=2026):
    """All brochure dates, cached as data/draw-odds/raw/colorado_dates_<year>.json."""
    cache = RAW / f"colorado_dates_{year}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    out = {}
    for name, url in BROCHURES.items():
        pdf = PDF_DIR / name
        if not pdf.exists():
            pdf.write_bytes(get(url))
        for k, v in parse_brochure_dates(pdf, year).items():
            out.setdefault(k, v)
    cache.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    return out


def standard_dates(hunts, dates, agree=0.8, min_dated=3):
    """{(species letter, season, method): most common [start, end]} from the dated codes, only
    where those dates mostly agree (>= 80% of >= 3 dated codes). Checked 2026: the regular
    seasons agree 85-100% (elk rifle, deer 2nd-4th rifle, archery, muzzleloader); Ranching for
    Wildlife, sheep, goat and some private-land seasons vary by hunt, so they get no guess."""
    import collections
    by = collections.defaultdict(collections.Counter)
    for c in hunts:
        if dates.get(c):
            by[(c[0], c[5:7], c[7])][tuple(dates[c])] += 1
    out = {}
    for k, v in by.items():
        top, n = v.most_common(1)[0]
        if sum(v.values()) >= min_dated and n / sum(v.values()) >= agree:
            out[k] = list(top)
    return out


# --------------------------------------------------------------------------- harvest
# CPW's harvest reports are a hunter survey reported by game management unit and season,
# not by hunt code (unlike Utah's). The newest posted is 2023. Each hunt gets the harvest
# and hunters of its season's table summed over its valid units: antlered harvest for
# antlered hunts, total harvest for either-sex. All license types in those units and that
# season are mixed in, so it's an approximation, said so on the page. CPW withholds tiny
# samples ("su5m"); those units are skipped. Bear's report has no hunter counts, so bear
# gets no success rate.
HARVEST_YEAR = 2023
HARVEST_NAMES = {   # species key -> (statistics page slug, link name on it)
    "elk": ("elk", "2023-statewide-elk-hunting-harvest-estimates"),
    "deer": ("deer", "2023statewidedeerhuntingharvestestimates"),
    "pronghorn": ("pronghorn", "2023-statewide-pronghorn-harvest-estimates"),
    "moose": ("moose", "2023-statewide-moose-hunting-estimated-harvest-statistics"),
    "rocky-bighorn": ("bighorn-sheep", "2023-statewide-rocky-mountain-bighorn-sheep-hunting-harvest"),
    "desert-bighorn": ("bighorn-sheep", "2023-statewide-desert-bighorn-sheep-harvest"),
    "goat": ("mountain-goat", "2023-statewide-mountain-goat-hunting-harvest"),
}
_HROW = re.compile(r"^([0-9]{1,3}|[SG]\d{2})\s+((?:[\d,.]+|su\S*)(?:\s+(?:[\d,.]+|su\S*|#DIV/0!))+)$")


def parse_harvest_report(path):
    """{table title: {unit: [numbers or None]}}; the title is each page's first line.
    Some tables (deer percent-success) put a row number before the unit ("33 22 12 14 87 0
    0 0" = row 33, unit 22): a row with one value more than its table's usual count is
    read that way."""
    import pdfplumber, collections
    raw = collections.defaultdict(list)
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            lines = [l.strip() for l in (pg.extract_text() or "").splitlines() if l.strip()]
            if not lines:
                continue
            title = re.sub(r"^20\d\d\s+", "", lines[0])
            for l in lines[1:]:
                m = _HROW.match(l)
                if m:
                    raw[title].append((m.group(1), m.group(2).split()))
    num = lambda v: None if (v.startswith("su") or "DIV" in v) else float(v.replace(",", ""))
    norm = lambda u: u.lstrip("0") if u[0].isdigit() else u
    out = {}
    for title, rows in raw.items():
        # Expected number columns: percent-success tables have 6 (antlered harvest, hunters,
        # %, antlerless ...); elk/deer/pronghorn recreation-days tables 7 (bulls, cows,
        # calves, total, hunters, %, days). Some pages number every row, so the most
        # common width can't be trusted there. Other species' tables: the most common.
        if "Percent Success for" in title:
            width = 6
        elif title.startswith(("Elk Harvest", "Deer Harvest", "Pronghorn Harvest")) and "Recreation Days" in title:
            width = 7
        else:
            width = collections.Counter(len(v) for _, v in rows).most_common(1)[0][0]
        t = out.setdefault(title, {})
        for first, vals in rows:
            if len(vals) == width + 1 and re.fullmatch(r"[0-9]{1,3}|[SG]\d{2}", vals[0]):
                first, vals = vals[0], vals[1:]          # leading row number
            if len(vals) == width:
                t[norm(first)] = [num(v) for v in vals]
    return out


def harvest_tables(key):
    cache = RAW / f"colorado_{key}_harvest_{HARVEST_YEAR}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    if key not in HARVEST_NAMES:
        return None
    slug, name = HARVEST_NAMES[key]
    html = get(STATS.format(slug=slug)).decode("utf-8", "ignore")
    m = re.search(r'href="(https://cpw\.widen\.net/s/[a-z0-9]+/' + re.escape(name) + r')"', html)
    if not m:
        print(f"  ! no {HARVEST_YEAR} harvest report link for {key}", file=sys.stderr)
        return None
    pdf = PDF_DIR / f"{key}_harvest_{HARVEST_YEAR}.pdf"
    if not pdf.exists():
        download_share(m.group(1), pdf)
    t = parse_harvest_report(pdf)
    cache.write_text(json.dumps({"url": m.group(1), "tables": t}, separators=(",", ":")), encoding="utf-8")
    return {"url": m.group(1), "tables": t}


_ORD_WORD = {"1": "First", "2": "Second", "3": "Third", "4": "Fourth"}
_ORD_NUM = {"1": "1st", "2": "2nd", "3": "3rd", "4": "4th"}


def harvest_source(code, tables):
    """(table title, harvest column, hunters column) for a hunt code, or None."""
    sp, sex, season, n, method = code[0], code[1], code[5], code[6], code[7]
    T = lambda s: next((t for t in tables if t.startswith(s)), None)
    # Bulls/Bucks Cows/Does Calves/Fawns Total Hunters ...: antlered = col 0, total = col 3, hunters = col 4
    rec = lambda title: (title, 0 if sex == "M" else 3, 4) if title else None
    pct = lambda title: (title, 0, 1) if title else None            # Antlered Harvest, Antlered Hunters, ...
    if sp == "E":
        if season == "O" and method == "R":
            return rec(T(f"Elk Harvest, Hunters and Recreation Days for {_ORD_NUM.get(n, n)} Season Limited {'Antlered' if sex == 'M' else 'Either-sex'} Seasons"))
        if method == "A" or season == "V": return rec(T("Elk Harvest, Hunters and Recreation Days for All Archery Seasons"))
        if method == "M": return (pct if sex == "M" else rec)(T("Elk Harvest, Hunters and Percent Success for All Muzzleloader") if sex == "M" else T("Elk Harvest, Hunters and Recreation Days for All Muzzleloader"))
        if season == "E": return rec(T("Elk Harvest, Hunters and Recreation Days for Early Seasons"))
        if season == "L": return rec(T("Elk Harvest, Hunters and Recreation Days for All Late Seasons"))
        if season == "P": return rec(T("Elk Harvest, Hunters and Recreation Days for Private Land Only Seasons"))
        if season in "WJ": return rec(T("Elk Harvest, Hunters and Recreation Days for All Ranching for Wildlife"))
    if sp == "D":
        if season == "O" and method == "R":
            if sex == "M" and n in "234": return pct(T(f"Deer Harvest, Hunters and Percent Success for {_ORD_NUM[n]} Rifle Seasons"))
            if n in "234": return rec(T(f"Deer Harvest, Hunters and Recreation Days for {_ORD_NUM[n]} Rifle Seasons"))
            return rec(T("Deer Harvest, Hunters and Recreation Days for All Rifle Seasons"))
        if method == "A" or season == "V": return rec(T("Deer Harvest, Hunters and Recreation Days for All Archery Seasons"))
        if method == "M": return (pct if sex == "M" else rec)(T("Deer Harvest, Hunters and Percent Success for All Muzzleloader") if sex == "M" else T("Deer Harvest, Hunters and Recreation Days for All Muzzleloader"))
        if season in "EL": return rec(T("Deer Harvest, Hunters and Recreation Days for Early and Late Seasons"))
        if season == "P": return rec(T("Deer Harvest, Hunters and Recreation Days for All Rifle Seasons"))
        if season in "WJ": return rec(T("Deer Harvest, Hunters and Recreation Days for All Ranching for Wildlife"))
    if sp == "A":
        if method == "A": return rec(T("Pronghorn Harvest, Hunters and Recreation Days for All Archery Seasons"))
        if method == "M": return rec(T("Pronghorn Harvest, Hunters and Recreation Days for All Muzzleloader Seasons"))
        if season == "L": return rec(T("Pronghorn Harvest, Hunters and Recreation Days for All Late Rifle Seasons"))
        if season == "P": return rec(T("Pronghorn Harvest, Hunters and Recreation Days for All Private Land Only"))
        if season in "WJ": return rec(T("Pronghorn Harvest, Hunters and Recreation Days for All Ranching for Wildlife"))
        return rec(T("Pronghorn Harvest, Hunters and Recreation Days for All Regular Rifle Seasons"))
    title = next(iter(tables), None)   # moose, sheep, goat: one table for all manners of take
    if not title:
        return None
    if sp == "M":                       # Licenses M F T, Hunters M F T, Harvest M F T, ...
        return (title, 6 if sex == "M" else 8, 3 if sex == "M" else 5)
    if sp in "SC":                      # same layout with Ram / Ewe
        return (title, 6 if sex == "M" else 8, 3 if sex == "M" else 5)
    if sp == "G":                       # Licenses, Hunters, Male, Female, Total, %, days
        return (title, 2 if sex == "M" else 4, 1)
    return None


def unit_tokens(units_text, code):
    toks = re.findall(r"\b([SG]\d{1,2}|\d{1,3})\b", units_text or "")
    out = []
    for t in toks or [code[2:5]]:
        t = t.lstrip("0") if t[0].isdigit() else (t[0] + t[1:].zfill(2))
        if t and t not in out:
            out.append(t)
    return out


def hunt_harvest(code, units_text, hv):
    """[None, hunters, harvested, percent] summed over the hunt's units, or None."""
    if not hv:
        return None
    src = harvest_source(code, hv["tables"])
    if not src:
        return None
    title, hcol, ncol = src
    t = hv["tables"].get(title) or {}
    har = hun = 0.0; used = []
    for u in unit_tokens(units_text, code):
        r = t.get(u)
        if not r or max(hcol, ncol) >= len(r) or r[hcol] is None or r[ncol] is None:
            continue
        har += r[hcol]; hun += r[ncol]; used.append(u)
    if not used or hun <= 0:
        return None
    return [None, round(hun), round(har), round(100 * har / hun, 1)]


# --------------------------------------------------------------------------- stage 2: assemble
# Turns the parsed recaps into data/draw-odds/co-<year>.json in the same shape as Utah's,
# so the page's analysis, projection and drop-in code work unchanged. Rows are
# [points, applicants, drew, drew by preference] per residency (adults, first choice);
# quotas are [tags, preference tags, random tags].
#
# The draw rules (checked against the 2026 results by point level, 2026-11-25):
#  - elk, deer, pronghorn, bear: preference points top-down. A few applicants at levels
#    above the cut-off miss (group applications draw at the lowest member's points), so the
#    split is found like Utah's general-season deer: scanning up from the bottom, the
#    guaranteed level is the lowest where >= 90% drew. Draws below the split are the hybrid
#    draw's: a flat random draw among first-choice applicants with 5+ points (hunts that took
#    10+ resident points the year before, 5+ licenses). That matched CPW's hybrid counts
#    exactly or within 2 on 88-99% of hunts. -> "rand": "hybrid"
#  - moose, Rocky bighorn, goat: nobody under 3 preference points drew (0 of ~29,000 in
#    2026). With 3, the random number is divided by (weighted points + 1): the chance is
#    linear in (weighted + 1) up to 1, which matched the 2026 draws by weighted band.
#    Points are entered as one number, 3 + weighted.  -> "rand": "weighted"
#  - desert bighorn: no points, pure random.  -> "rand": "flat"
SPECIES = [  # key, label, short, rand rule, icon
    ("elk", "Elk (antlered and either-sex)", "Elk", "hybrid", "img/drawodds-elk.png"),
    ("deer", "Deer (antlered and either-sex)", "Deer", "hybrid", "img/drawodds-deer.png"),
    ("pronghorn", "Pronghorn (antlered and either-sex)", "Pronghorn", "hybrid", "img/drawodds-pronghorn.png"),
    ("moose", "Moose (antlered and either-sex)", "Moose", "weighted", "img/drawodds-moose.png"),
    ("rocky-bighorn", "Rocky Mountain Bighorn Sheep (rams and either-sex)", "Rocky Sheep", "weighted", "img/drawodds-bighorn.png"),
    ("desert-bighorn", "Desert Bighorn Sheep (rams)", "Desert Sheep", "flat", "img/drawodds-bighorn.png"),
    ("goat", "Mountain Goat (billy and either-sex)", "Mtn Goat", "weighted", "img/drawodds-goat.png"),
    ("bear", "Black Bear (limited draw)", "Bear", "hybrid", "img/drawodds-bear.png"),
]
METHOD = {"A": "Archery", "M": "Muzzleloader", "R": "Rifle", "X": "Any method"}
ORD = {"1": "1st", "2": "2nd", "3": "3rd", "4": "4th", "5": "5th", "6": "6th"}


def season_label(code):
    s, n, m = code[5], code[6], METHOD.get(code[7], code[7])
    if s == "O":
        return m if m in ("Archery", "Muzzleloader") else f"{ORD.get(n, n)} rifle" if m == "Rifle" else m
    pre = {"P": "Private land", "E": "Early", "L": "Late", "S": "Special", "V": "Nonresident",
           "W": "Ranching for Wildlife", "J": "Ranching for Wildlife", "U": "Unlimited"}.get(s, s)
    num = f" {ORD.get(n, n)}" if s == "P" and m == "Rifle" else ""
    return f"{pre}{num} {m.lower()}"


def hunt_notes(code, choice2):
    notes = []
    if code[5] == "P":
        notes.append(["Private land only", "Valid only on private land in these units. You need permission from a landowner before you apply."])
    if code[5] in "WJ":
        notes.append(["Ranching for Wildlife", "Ranching for Wildlife: a hunt on a specific private ranch, for Colorado residents only."])
    if code[5] == "V":
        notes.append(["Nonresident only", "A limited license for nonresidents only."])
    if choice2:
        notes.append(["2nd choice", f"In the last draw {choice2} tag{'s' if choice2 != 1 else ''} went to 2nd-choice (or later) applicants after every first choice drew, so this hunt can be drawn as a second choice."])
    return notes


def split_index(rows):
    """rows [(pts, apps, drew)] high to low with apps > 0: index of the split row, or None."""
    i = len(rows) - 1
    while i >= 0 and rows[i][2] / rows[i][1] < 0.9:
        i -= 1
    return None if i == len(rows) - 1 else i + 1


def point_rows(x, ri, rule):
    """[[pts, apps, drew, drew_by_preference]] high to low for one residency (ri 0 = resident)."""
    out = []
    for key, r in x["rows"].items():
        if rule == "weighted":
            p, w = (int(v) for v in str(key).split("w"))
            pts = p if p < 3 else 3 + w      # one number: 3 preference points + weighted points
        else:
            pts = int(key)
        if r[ri] > 0:
            out.append([pts, r[ri], r[4 + ri], 0])
    out.sort(key=lambda r: -r[0])
    if rule == "hybrid":
        s = split_index([(r[0], r[1], r[2]) for r in out])
        for i, r in enumerate(out):
            r[3] = r[2] if s is None or i <= s else 0   # below the split: hybrid (random) draws
    return out


def assemble(year=2026, hist_years=(2022, 2023, 2024, 2025)):
    sys.path.insert(0, str(TOOL))
    import build_utah as U
    units = json.loads((RAW / f"colorado_w2_units_{W2_YEAR}.json").read_text(encoding="utf-8"))
    dates = season_dates(year)
    species = []
    for key, label, short, rule, icon in SPECIES:
        cur = json.loads((RAW / f"colorado_{key}_{year}_recap.json").read_text(encoding="utf-8"))
        hist, outs = {}, {}
        for y in hist_years:
            f = RAW / f"colorado_{key}_{y}_recap.json"
            if f.exists():
                for k, x in json.loads(f.read_text(encoding="utf-8")).items():
                    for code in k.split("+"):      # 2022 combined hunts: same table for each code
                        hist.setdefault(code, {})[str(y)] = x
                continue
            # No recap that year (2024 for most species): CPW's "Drawn Out At" report gives
            # the guaranteed level and split, not applicants. Only meaningful for the
            # preference species.
            f = RAW / f"colorado_{key}_{y}_drawnout.json"
            if f.exists() and rule == "hybrid":
                for code, v in json.loads(f.read_text(encoding="utf-8")).items():
                    rec = {res: drawnout_record(v[res]) for res in ("R", "N")}
                    if rec["R"] or rec["N"]:
                        outs.setdefault(code, {})[str(y)] = rec
        hunts = []
        for code, x in cur.items():
            if "+" in code or code[1] not in "ME" or code[5] == "K" or not x.get("drawn"):
                continue
            rows = {"R": point_rows(x, 0, rule), "N": point_rows(x, 1, rule)}
            if not rows["R"] and not rows["N"]:
                continue
            drawn = x["drawn"]
            quota = {}
            for res, ri in (("R", 2), ("N", 3)):
                tags = drawn[ri]
                if rule == "hybrid":
                    hyb = sum(r[2] - r[3] for r in rows[res])
                    quota[res] = [tags, max(0, tags - hyb), min(hyb, tags)]
                else:
                    quota[res] = [tags, 0, tags]
            ch = x["choice"]
            choice2 = sum(sum((ch.get(str(c)) or ch.get(c) or {"drew": [0, 0]})["drew"][:2]) for c in (2, 3, 4))
            unit_no = code[2:5].lstrip("0") or "0"
            h = {
                "code": code,
                "unit": f"Unit {unit_no}",
                "units": units.get(code) or unit_no,
                "weapon": season_label(code),
                "seasons": [],
                "wtype": METHOD.get(code[7], "Other"),     # Archery / Muzzleloader / Rifle / Any method
                "notes": hunt_notes(code, choice2),
                "map": "",
                "quota": quota,
                "rows": rows,
                "plo": code[5] == "P",
                "rfw": code[5] in "WJ",
            }
            hh = {}
            for y, hx in hist.get(code, {}).items():
                if hx.get("rows"):
                    hh[y] = {"R": point_rows(hx, 0, rule), "N": point_rows(hx, 1, rule)}
            for y, rec in outs.get(code, {}).items():
                hh[y] = {"R": [], "N": [], "out": rec}     # guaranteed/split only (no applicants)
            if hh:
                h["hist"] = dict(sorted(hh.items()))
            hunts.append(h)
        hv = harvest_tables(key)
        n_hv = 0
        for h in hunts:
            r = hunt_harvest(h["code"], h["units"], hv)
            if r:
                h["harvest"] = r; n_hv += 1
        print(f"    harvest ({HARVEST_YEAR}, by unit and season): {n_hv} of {len(hunts)} hunts")
        # Season dates: the brochure's own, else the standard dates for that species,
        # season and method ("standard": true, said so on the page).
        std = standard_dates([h["code"] for h in hunts], dates)
        n_own = n_std = 0
        for h in hunts:
            d = dates.get(h["code"])
            if d:
                h["seasons"] = [[h["weapon"], d[0], d[1]]]; n_own += 1
            elif std.get((h["code"][0], h["code"][5:7], h["code"][7])):
                d = std[(h["code"][0], h["code"][5:7], h["code"][7])]
                h["seasons"] = [[h["weapon"], d[0], d[1]]]; h["stdDates"] = True; n_std += 1
        print(f"    season dates: {n_own} from the brochures, {n_std} standard, {len(hunts) - n_own - n_std} none")
        hunts.sort(key=lambda h: (int(re.sub(r"\D", "", h["unit"]) or 0), h["unit"], h["weapon"], h["code"]))
        sp = {"key": key, "label": label, "short": short, "icon": icon, "system": "preference" if rule == "hybrid" else "bonus",
              "rand": rule, "hunts": hunts}
        if hv:
            sp["harvestYear"], sp["harvestSource"], sp["harvestByUnit"] = HARVEST_YEAR, hv["url"], True
            if rule != "hybrid":
                sp["harvestAllSeasons"] = True   # moose/sheep/goat: one table for every season
        species.append(sp)
        print(f"  {short}: {len(hunts)} antlered/either-sex hunts")
    # Drop-ins (people who show up above the split that last year's pool can't explain):
    # same fit and leave-one-year-out test as Utah, only for the preference species.
    pref = [s for s in species if s["rand"] == "hybrid"]
    U.fit_dropins(pref, year)
    for s in species:
        s.setdefault("dropin", {})
    state = {
        "state": "CO", "name": "Colorado", "drawYear": year, "nextYear": year + 1, "nextTags": False,
        "harvestYear": year - 1,
        "sources": {"odds": "https://cpw.state.co.us/hunting/big-game/elk/statistics", "harvest": "", "tags": ""},
        "species": species,
    }
    out = ROOT / "data" / "draw-odds" / f"co-{year}.json"
    out.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    print(f"  wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    return state


if __name__ == "__main__":
    if "--assemble" in sys.argv:
        assemble()
        import build_utah as U
        U.build_preview("CO")      # _preview-colorado.html (not in git) until Colorado goes live
    else:
        main()
