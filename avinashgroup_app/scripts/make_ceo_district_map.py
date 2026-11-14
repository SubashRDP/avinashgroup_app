"""Build public/js/ceo_nepal_districts.json, the district outlines the CEO
Dashboard's "Sales by district" map draws.

Input: a GeoJSON of Nepal's 77 districts with the official 2020 political map
(the "chuchche" map: Limpiyadhura, Lipulekh and Kalapani inside Darchula). The
clients are Nepali, so the old boundary is not acceptable (the CEO's call,
2026-11-11). Used: Nepal_Administrative_Boundary_District.geojson from
github.com/manishacharya60/nepal-geojson, converted there from the Survey
Department's shapefiles on the National GeoPortal of Nepal
(nationalgeoportal.gov.np). Check before swapping the source: Darchula must
reach about 30.47 N (the pre-2020 boundary stops at 30.25 N).

The source is ~23 MB; this simplifies each outline (Douglas-Peucker, under a
pixel at the size the map is drawn) to ~60 KB of SVG paths.

Run:  python -I make_ceo_district_map.py <districts.geojson> <out.json>
One-off; nothing imports it.
"""
import json, math, sys
src, out = sys.argv[1], sys.argv[2]
g = json.load(open(src))
W = 1000.0
def _points(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        yield from poly[0]

_all = [p for f in g["features"] for p in _points(f["geometry"])]
lon0, lon1 = min(p[0] for p in _all), max(p[0] for p in _all)
lat0, lat1 = min(p[1] for p in _all), max(p[1] for p in _all)
# The district name is in DISTRICT (GeoPortal files) or DIST_EN (OCHA files).
NAME_KEY = next(k for k in ("DISTRICT", "DIST_EN") if k in g["features"][0]["properties"])
SOURCE = "National GeoPortal of Nepal (Survey Department) district boundaries, 2020 political map, via github.com/manishacharya60/nepal-geojson; simplified"
k = math.cos(math.radians((lat0 + lat1) / 2))            # equirectangular, true scale at mid latitude
sx = W / ((lon1 - lon0) * k); H = (lat1 - lat0) * sx
proj = lambda p: ((p[0] - lon0) * k * sx, (lat1 - p[1]) * sx)
TOL = 0.9                                                # px; outlines are drawn ~1 px wide

def simplify(pts, tol):
    # iterative Douglas-Peucker
    keep = [False] * len(pts); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1: continue
        ax, ay = pts[a]; bx, by = pts[b]; dx, dy = bx - ax, by - ay; L = math.hypot(dx, dy) or 1e-9
        best, bi = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / L if L > 1e-6 else math.hypot(px - ax, py - ay)
            if d > best: best, bi = d, i
        if best > tol:
            keep[bi] = True; stack.append((a, bi)); stack.append((bi, b))
    return [p for p, kf in zip(pts, keep) if kf]

def area(r):
    return abs(sum(r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1] for i in range(len(r) - 1))) / 2

districts = []
for f in g["features"]:
    geom = f["geometry"]
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    d, cx, cy, ca = "", 0.0, 0.0, 0.0
    for poly in polys:
        ring = [proj(p) for p in poly[0]]                # outer ring only; holes are not needed at this size
        a = area(ring)
        if a < 6: continue                               # specks
        s = simplify(ring, TOL)
        if len(s) < 4: continue
        d += "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in s[:-1]) + "Z"
        if a > ca:                                       # label point: centre of the largest piece's box
            xs = [p[0] for p in s]; ys = [p[1] for p in s]
            cx, cy, ca = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, a
    districts.append({"name": str(f["properties"][NAME_KEY]).strip().title(), "d": d, "x": round(cx, 1), "y": round(cy, 1)})
districts.sort(key=lambda x: x["name"])
json.dump({"source": SOURCE,
           "w": int(W), "h": round(H), "districts": districts}, open(out, "w"), separators=(",", ":"))
print(len(districts), "districts", round(H), "px high", sum(len(x["d"]) for x in districts) // 1024, "KB of paths")
