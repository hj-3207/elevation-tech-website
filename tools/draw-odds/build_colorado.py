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
            kind = "recap" if "recap" in n else "drawnout" if ("drawnout" in n or "drawn-out" in n) else None
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
CODE = re.compile(r"^([A-Z]{2}\d{3}[A-Z]\d[A-Z])$")
TOK = r"(?:\d+|-)"
ROW = re.compile(rf"^(?:1 )?(\d+) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK}) (?:1 )?(\d+) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK}) ({TOK})$")
TOT = re.compile(rf"^Total Choice (\d) ((?:{TOK} ){{5}}{TOK}) Total Choice \1 ((?:{TOK} ){{5}}{TOK})$")
EIGHT = re.compile(r"(?:^| )(\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)$")   # 2022 has labels before the numbers
HEADER = re.compile(r"(?i)^(colorado parks and wildlife|.*post draw report|\d+/\d+/\d{4} |page \d+ of )")
_n = lambda x: 0 if x == "-" else int(x)


def parse_recap(path):
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
            if body and CODE.match(body[0]):
                cur = {"quota": None, "drawn": None, "hybrid": None, "nrcap": None, "rows": {}, "choice": {}}
                hunts[body[0]] = cur
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
                    for j in range(i + 1, min(i + 5, len(body))):
                        m = EIGHT.search(body[j])
                        if m:
                            cur["drawn"] = [int(x) for x in m.groups()]
                            break
                if l.startswith("Choice Preference Points"):
                    in_table = True
                    continue
                m = ROW.match(l)
                if in_table and m:
                    g = [_n(x) for x in m.groups()]
                    cur["rows"][g[0]] = g[1:5] + g[8:12]
                    continue
                m = TOT.match(l)
                if m:
                    a = [_n(x) for x in m.group(2).split()]
                    b = [_n(x) for x in m.group(3).split()]
                    cur["choice"][int(m.group(1))] = {"apps": a[:4], "drew": b[:4]}
                    in_table = False
    return hunts


def verify_recap(hunts):
    bad = []
    for code, h in hunts.items():
        c = h["choice"].get(1)
        s = [sum(r[i] for r in h["rows"].values()) for i in range(8)]
        if not c or s != c["apps"] + c["drew"]:
            bad.append(code)
    return bad


# --------------------------------------------------------------------------- drawn out
DO_CODE = re.compile(r"\b([A-Z]{2}\d{3}[A-Z]\d[A-Z])\b")


def parse_drawnout(path):
    """{code: [text lines]} from a "Drawn Out At" report. Kept as raw text per hunt for now
    (2024 has no recap, so this is that year's only record); turned into numbers later."""
    import pdfplumber
    out, cur = {}, None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for l in (page.extract_text() or "").splitlines():
                l = l.strip()
                m = DO_CODE.search(l)
                if m and (l == m.group(1) or l.startswith(m.group(1)) or l.endswith(m.group(1))):
                    cur = m.group(1)
                    out.setdefault(cur, [])
                if cur and l and not l.startswith(("Colorado Parks", "Drawn Out At Report", "Page ")):
                    out[cur].append(l)
    return out


# --------------------------------------------------------------------------- W-2 units
W2_CODE = re.compile(r"\b([DEAMBSG][MEF]\d{3}[A-Z]\d[ARMX])\b")


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
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    src_path = RAW / "colorado_sources.json"
    sources = json.loads(src_path.read_text(encoding="utf-8")) if src_path.exists() else {}

    found = discover()
    print(f"  CPW links found: {len(found)}")
    for (key, year, kind), url in sorted(found.items()):
        if a.only and key != a.only:
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
            data = parse_recap(pdf)
            bad = verify_recap(data)
            print(f"  parsed {key} {year} recap: {len(data)} hunt codes, {len(bad)} not matching CPW's totals {bad[:5]}")
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


if __name__ == "__main__":
    main()
