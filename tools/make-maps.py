"""Build the regional maps and the Maps deck from Natural Earth country borders.

Usage (from the project root):
    python3 tools/make-maps.py path/to/ne_50m_admin_0_countries.geojson

The GeoJSON (public domain, ~3 MB) comes from
https://github.com/nvkelso/natural-earth-vector/tree/master/geojson
and is not committed; only the small SVGs it produces are.

Each map uses a Lambert azimuthal equal-area projection centred on its region,
is clipped to the region and simplified to keep files small. Countries in
decks/world-capitals.json get a path id equal to their card id (e.g. "w-fr");
everything else is plain land. Countries too small to see get a ring.
"""

import json
import math
import sys
from pathlib import Path

WIDTH = 1000          # SVG viewBox width
TOLERANCE = 0.9       # simplification tolerance, in viewBox units
SMALL = 30            # countries drawn smaller than this (about 10 px on a phone) get a ring
RING = 16             # ring radius, viewBox units

# name: (title, centre lon, centre lat, (lon_min, lon_max, lat_min, lat_max), subregions,
#        [extra card ids], [excluded card ids])
MAPS = {
    "europe": ("Europe", 14, 52, (-24, 42, 34, 71),
               ["Northern Europe", "Western Europe", "Southern Europe", "Eastern Europe"]),
    "north-america": ("North America", -100, 45, (-168, -52, 14, 72), ["Northern America"],
                      ["w-mx"]),
    "caribbean": ("Central America and the Caribbean", -76, 17, (-93, -58, 6.5, 27.5),
                  ["Central America", "Caribbean"], [], ["w-mx"]),
    "south-america": ("South America", -60, -20, (-82, -33, -56, 13), ["South America"]),
    "africa": ("Africa", 18, 2, (-26, 60, -36, 38),
               ["Northern Africa", "Western Africa", "Middle Africa", "Eastern Africa", "Southern Africa"]),
    "asia": ("Asia", 88, 28, (25, 148, -11, 56),
             ["Western Asia", "Central Asia", "Southern Asia", "Eastern Asia", "South-eastern Asia"]),
    "oceania": ("Oceania", 160, -12, (110, 212, -48, 14),
                ["Australia and New Zealand", "Melanesia", "Micronesia", "Polynesia"]),
}


def laea(lon0, lat0):
    l0, p0 = math.radians(lon0), math.radians(lat0)
    def project(lon, lat):
        l, p = math.radians(lon), math.radians(lat)
        k = math.sqrt(2 / (1 + math.sin(p0) * math.sin(p) + math.cos(p0) * math.cos(p) * math.cos(l - l0)))
        x = k * math.cos(p) * math.sin(l - l0)
        y = k * (math.cos(p0) * math.sin(p) - math.sin(p0) * math.cos(p) * math.cos(l - l0))
        return x, -y
    return project


def clip(ring, xmin, xmax, ymin, ymax):
    """Sutherland-Hodgman clip of a closed ring to a rectangle."""
    def edge(pts, inside, cross):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
        return out
    def at_x(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))
    def at_y(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)
    pts = ring
    for inside, cross in [
        (lambda p: p[0] >= xmin, at_x(xmin)), (lambda p: p[0] <= xmax, at_x(xmax)),
        (lambda p: p[1] >= ymin, at_y(ymin)), (lambda p: p[1] <= ymax, at_y(ymax)),
    ]:
        if not pts:
            break
        pts = edge(pts, inside, cross)
    return pts


def simplify(pts, tol):
    """Douglas-Peucker on an open polyline."""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    norm = math.hypot(dx, dy) or 1e-12
    far, idx = -1, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * (pts[i][0] - a[0]) - dx * (pts[i][1] - a[1])) / norm
        if d > far:
            far, idx = d, i
    if far <= tol:
        return [a, b]
    return simplify(pts[:idx + 1], tol)[:-1] + simplify(pts[idx:], tol)


def rings_of(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        yield poly[0]  # outer ring only; holes are rare at this scale


def build(ne_path):
    features = json.load(open(ne_path))["features"]
    world = json.load(open("decks/world-capitals.json"))["cards"]
    card_by_iso = {c["id"][2:].upper(): c for c in world}
    deck_cards = []
    Path("maps").mkdir(exist_ok=True)

    for name, (title, lon0, lat0, (lo0, lo1, la0, la1), subregions, *more) in MAPS.items():
        extra, excluded = (more + [[], []])[:2]
        project = laea(lon0, lat0)
        wrap = lo1 > 180  # Oceania crosses the antimeridian
        # Projected extent of the lon/lat window, sampled along its edges.
        edge = [(lo, la) for lo in (lo0, lo1) for la in range(int(la0), int(la1) + 1)] + \
               [(lo, la) for la in (la0, la1) for lo in range(int(lo0), int(lo1) + 1)]
        xs, ys = zip(*(project(lo, la) for lo, la in edge))
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        scale = WIDTH / (x1 - x0)
        height = round((y1 - y0) * scale)
        to_view = lambda p: ((p[0] - x0) * scale, (p[1] - y0) * scale)
        m = 30  # clip margin, so borders do not show at the frame edge
        box = (-m, WIDTH + m, -m, height + m)

        targets = {c["id"] for c in world if c["subregion"] in subregions or c["id"] in extra} - set(excluded)
        shapes = {}  # path id (or "" for plain land) -> list of view rings
        for f in features:
            iso = f["properties"]["ISO_A2_EH"]
            card = card_by_iso.get(iso)
            key = card["id"] if card and card["id"] in targets else ""
            for ring in rings_of(f["geometry"]):
                pts = [((lo + 360 if wrap and lo < 0 else lo), la) for lo, la in ring]
                if not any(lo0 - 25 <= lo <= lo1 + 25 and la0 - 15 <= la <= la1 + 15 for lo, la in pts):
                    continue
                view = clip([to_view(project(lo, la)) for lo, la in pts], *box)
                if len(view) >= 3:
                    shapes.setdefault(key, []).append(view)

        def simplify_ring(r):
            # A closed ring has no baseline (start = end), so split it at the
            # point farthest from the start and simplify the two halves.
            k = max(range(len(r)), key=lambda i: math.hypot(r[i][0] - r[0][0], r[i][1] - r[0][1]))
            if k == 0:
                return r[:1]
            return simplify(r[:k + 1], TOLERANCE)[:-1] + simplify(r[k:] + [r[0]], TOLERANCE)[:-1]

        def path_d(rings):
            parts = []
            for r in rings:
                s = simplify_ring(r)
                if len(s) < 3:
                    s = r[:: max(1, len(r) // 4)][:4]
                if len(s) >= 3:
                    parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in s) + "Z")
            return "".join(parts)

        out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="Map of {title}">',
               f'<rect class="sea" width="{WIDTH}" height="{height}"/>']
        if "" in shapes:
            out.append(f'<path class="land" d="{path_d(shapes[""])}"/>')
        rings_svg = []
        for key, rings in shapes.items():
            if not key:
                continue
            out.append(f'<path class="land country" id="{key}" d="{path_d(rings)}"/>')
            # Countries too small to see overall get a ring on each island group.
            extent = lambda r: max(max(p[0] for p in r) - min(p[0] for p in r),
                                   max(p[1] for p in r) - min(p[1] for p in r))
            if max(extent(r) for r in rings) >= SMALL:
                continue
            placed = []
            for r in rings:
                rx, ry = [p[0] for p in r], [p[1] for p in r]
                if max(max(rx) - min(rx), max(ry) - min(ry)) >= SMALL:
                    continue
                cx, cy = (min(rx) + max(rx)) / 2, (min(ry) + max(ry)) / 2
                if not (0 <= cx <= WIDTH and 0 <= cy <= height):
                    continue
                if any(math.hypot(cx - px, cy - py) < RING * 1.5 for px, py in placed):
                    continue
                placed.append((cx, cy))
                rings_svg.append(f'<circle class="ring" data-for="{key}" cx="{cx:.1f}" cy="{cy:.1f}" r="{RING}"/>')
        out += rings_svg
        out.append("</svg>")
        svg = "".join(out)
        Path(f"maps/{name}.svg").write_text(svg)

        missing = targets - set(shapes)
        print(f"{name}: {len(targets)} countries, {len(rings_svg)} rings, {len(svg) // 1024} KB"
              + (f", MISSING {sorted(missing)}" if missing else ""))

        for c in world:
            if c["id"] in targets:
                deck_cards.append({
                    "id": "map-" + c["id"][2:],
                    "prompt": title,
                    "answer": c["prompt"],
                    "map": name,
                    "target": c["id"],
                    "group": title,
                    "note": f"Capital: {c['answer']}.",
                })

    deck = {
        "id": "maps",
        "title": "Maps",
        "subtitle": "Which country is highlighted?",
        "promptLabel": "Which country is highlighted",
        "reversible": False,
        "about": "Every country in the world capitals deck, highlighted on a map of its region. "
                 "Countries too small to see are ringed. Borders from Natural Earth, which is in the public domain.",
        "cards": deck_cards,
    }
    Path("decks/maps.json").write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n")
    print(f"decks/maps.json: {len(deck_cards)} cards")


if __name__ == "__main__":
    build(sys.argv[1])
