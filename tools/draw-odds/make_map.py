"""Make tools/draw-odds/west-map.json, the state outlines for the Draw Odds map (draw-odds.html).

Source: us-atlas 3.0.1 states-albers-10m.json (TopoJSON, already Albers-projected), built
from US Census Bureau cartographic boundaries (public domain):
  https://cdn.jsdelivr.net/npm/us-atlas@3.0.1/states-albers-10m.json
Only needed again to add or remove a state on the map (edit WANT below):
  python -I tools/draw-odds/make_map.py <downloaded json> tools/draw-odds/west-map.json
Writes JSON: {viewBox, states:{code:{d, cx, cy}}}; cx/cy are label points."""
import json, sys

src, out = sys.argv[1], sys.argv[2]
topo = json.load(open(src, encoding="utf-8"))
sx, sy = topo["transform"]["scale"]; tx, ty = topo["transform"]["translate"]

arcs = []
for arc in topo["arcs"]:
    x = y = 0; pts = []
    for dx, dy in arc:
        x += dx; y += dy
        pts.append((x * sx + tx, y * sy + ty))
    arcs.append(pts)

def ring(idx):
    pts = []
    for i in idx:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return pts

WANT = {"Washington": "WA", "Oregon": "OR", "California": "CA", "Idaho": "ID", "Nevada": "NV",
        "Utah": "UT", "Arizona": "AZ", "Montana": "MT", "Wyoming": "WY", "Colorado": "CO",
        "New Mexico": "NM", "Kansas": "KS"}
polys = {}
for g in topo["objects"]["states"]["geometries"]:
    name = g["properties"]["name"]
    if name not in WANT:
        continue
    rings = g["arcs"] if g["type"] == "Polygon" else [r for p in g["arcs"] for r in p]
    polys[WANT[name]] = [ring(r) for r in rings]

xs = [p[0] for rs in polys.values() for r in rs for p in r]
ys = [p[1] for rs in polys.values() for r in rs for p in r]
x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
pad = 6
W, H = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
res = {"viewBox": f"0 0 {W:.0f} {H:.0f}", "states": {}}
for code, rs in polys.items():
    d = ""
    area_pts = max(rs, key=len)
    for r in rs:
        if len(r) < 4:
            continue
        d += "M" + "L".join(f"{p[0]-x0+pad:.1f},{p[1]-y0+pad:.1f}" for p in r) + "Z"
    # label point: bbox centre of the biggest ring
    rx = [p[0] for p in area_pts]; ry = [p[1] for p in area_pts]
    res["states"][code] = {"d": d, "cx": round((min(rx) + max(rx)) / 2 - x0 + pad, 1), "cy": round((min(ry) + max(ry)) / 2 - y0 + pad, 1)}
json.dump(res, open(out, "w", encoding="utf-8"))
print(res["viewBox"], {k: len(v["d"]) for k, v in res["states"].items()})
