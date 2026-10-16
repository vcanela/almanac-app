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


def equal_earth(lon, lat):
    """Equal Earth projection (Šavrič, Patterson and Jenny, 2018)."""
    A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
    lam, phi = math.radians(lon), math.radians(lat)
    t = math.asin(math.sqrt(3) / 2 * math.sin(phi))
    t2 = t * t
    t6 = t2 ** 3
    x = 2 * math.sqrt(3) * lam * math.cos(t) / (3 * (9 * A4 * t6 * t2 + 7 * A3 * t6 + 3 * A2 * t2 + A1))
    y = t * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))
    return x, -y


def ring_area(r):
    return abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2


def inside(pt, r):
    x, y = pt
    hit = False
    for i in range(len(r)):
        (x1, y1), (x2, y2) = r[i - 1], r[i]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def label_point(r):
    """A point well inside the ring: the grid point farthest from its edge."""
    xs, ys = [p[0] for p in r], [p[1] for p in r]
    edge = r[:: max(1, len(r) // 300)]
    best, best_d = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2), -1
    for i in range(1, 30):
        for j in range(1, 30):
            pt = (min(xs) + (max(xs) - min(xs)) * i / 30, min(ys) + (max(ys) - min(ys)) * j / 30)
            if inside(pt, r):
                d = min(math.hypot(pt[0] - e[0], pt[1] - e[1]) for e in edge)
                if d > best_d:
                    best, best_d = pt, d
    return best


WORLD_WIDTH = 2000
WORLD_TOLERANCE = 0.3   # finer than the regional maps, because journeys zoom in
NEAR = 60               # for borders, a polygon counts as part of a country's main territory
                        # within this many units (about 1,200 km) of it: Kaliningrad and
                        # East Malaysia yes, French Guiana and Hawaii no
NEAR_BOX = 25           # for the map window, a tighter rule (about 500 km), so outlying
                        # islands (the Azores, the Canaries, Svalbard) do not stretch it


def build_world(features, world):
    deck_ids = {c["id"][2:].upper(): c["id"] for c in world}
    x_edge, _ = equal_earth(180, 0)
    _, y_top = equal_earth(0, 84)
    _, y_bottom = equal_earth(0, -58)
    scale = WORLD_WIDTH / (2 * x_edge)
    height = round((y_bottom - y_top) * scale)
    view = lambda lon, lat: ((equal_earth(lon, lat)[0] + x_edge) * scale, (equal_earth(lon, lat)[1] - y_top) * scale)

    countries = {}  # card id -> list of (view outer ring, raw vertices of all its rings)
    plain_land = []
    for f in features:
        if f["properties"]["ADMIN"] == "Antarctica":
            continue
        card_id = deck_ids.get(f["properties"]["ISO_A2_EH"])
        geom = f["geometry"]
        for poly in geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]:
            vr = [view(lo, max(-58, min(84, la))) for lo, la in poly[0]]
            # Holes matter for borders: Lesotho, San Marino and Vatican City are holes in their neighbours.
            raw = [pt for ring in poly for pt in ring]
            if card_id:
                countries.setdefault(card_id, []).append((vr, raw))
            else:
                plain_land.append(vr)

    def simplified_d(rings):
        parts = []
        for r in rings:
            k = max(range(len(r)), key=lambda i: math.hypot(r[i][0] - r[0][0], r[i][1] - r[0][1]))
            s = (simplify(r[:k + 1], WORLD_TOLERANCE)[:-1] + simplify(r[k:] + [r[0]], WORLD_TOLERANCE)[:-1]) if k else r[:1]
            if len(s) >= 3:
                parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in s) + "Z")
        return "".join(parts)

    # Each country's main territory: its largest polygon, plus any polygon within
    # NEAR of a polygon already included, so island chains link up (Indonesia's
    # islands reach New Guinea) but distant territories do not (French Guiana).
    def box_of(r):
        xs, ys = [p[0] for p in r], [p[1] for p in r]
        return min(xs), min(ys), max(xs), max(ys)

    def box_gap(a, b):
        dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
        dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
        return math.hypot(dx, dy)

    meta, vertex_sets = {}, {}
    for cid, rings in countries.items():
        main = max(rings, key=lambda r: ring_area(r[0]))
        boxes = [box_of(vr) for vr, _ in rings]

        def cluster(limit):
            included = {rings.index(main)}
            grew = True
            while grew:
                grew = False
                for i in range(len(rings)):
                    if i not in included and any(box_gap(boxes[i], boxes[j]) < limit for j in included):
                        included.add(i)
                        grew = True
            return [rings[i] for i in sorted(included)]

        core = cluster(NEAR_BOX)
        xs = [p[0] for vr, _ in core for p in vr]
        ys = [p[1] for vr, _ in core for p in vr]
        meta[cid] = {"box": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
                     "label": [round(v, 1) for v in label_point(main[0])], "near": []}
        vertex_sets[cid] = {(round(lo, 3), round(la, 3)) for _, raw in cluster(NEAR) for lo, la in raw}

    # Neighbours share border vertices in the Natural Earth data.
    by_vertex = {}
    for cid, vs in vertex_sets.items():
        for v in vs:
            by_vertex.setdefault(v, set()).add(cid)
    shared = {}
    for ids in by_vertex.values():
        for a in ids:
            for b in ids:
                if a < b:
                    shared[(a, b)] = shared.get((a, b), 0) + 1
    for (a, b), n in shared.items():
        if n >= 2:
            meta[a]["near"].append(b)
            meta[b]["near"].append(a)
    for m in meta.values():
        m["near"].sort()

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WORLD_WIDTH} {height}" role="img" aria-label="World map">',
           f'<rect class="sea" x="-2000" y="-2000" width="{WORLD_WIDTH + 4000}" height="{height + 4000}"/>',
           f'<path class="land" d="{simplified_d(plain_land)}"/>']
    for cid, rings in sorted(countries.items()):
        out.append(f'<path class="land country" id="{cid}" d="{simplified_d([vr for vr, _ in rings])}"/>')
    out.append('<g class="labels"></g></svg>')
    svg = "".join(out)
    Path("maps/world.svg").write_text(svg)
    Path("maps/world.json").write_text(json.dumps({"width": WORLD_WIDTH, "height": height, "countries": meta},
                                                  ensure_ascii=False, separators=(",", ":")) + "\n")
    linked = sum(1 for m in meta.values() if m["near"])
    print(f"world: {len(meta)} countries, {linked} with land neighbours, {len(svg) // 1024} KB")

    # Every named journey must be overland: each step a land neighbour of the last.
    names = {c["id"]: c["prompt"] for c in world}
    for j in json.load(open("maps/journeys.json")):
        route = j["countries"]
        bad = [f"{names[a]} / {names[b]}" for a, b in zip(route, route[1:]) if b not in meta[a]["near"]]
        print(f"  journey {j['id']}: {len(route)} countries" + (f", NOT ADJACENT: {bad}" if bad else ", ok"))


if __name__ == "__main__":
    build(sys.argv[1])
    build_world(json.load(open(sys.argv[1]))["features"], json.load(open("decks/world-capitals.json"))["cards"])
