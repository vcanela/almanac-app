"""Draw the Almanac icons: the map symbol for a capital city (a star in a ring)
on almanac paper. Run from the project root: python3 tools/make-icons.py"""

import math
from pathlib import Path
from PIL import Image, ImageDraw

PAPER = (245, 241, 232)
INK = (29, 35, 43)
ACCENT = (168, 67, 44)
BIG = 2048  # draw large, then downsample for smooth edges

img = Image.new("RGB", (BIG, BIG), PAPER)
d = ImageDraw.Draw(img)
c = BIG / 2

# Ring, kept inside the maskable safe zone (central 80%).
outer, width = BIG * 0.30, BIG * 0.045
d.ellipse([c - outer, c - outer, c + outer, c + outer], outline=INK, width=round(width))

# Five-pointed star, point up.
R = BIG * 0.19
r = R * 0.382
pts = []
for i in range(10):
    rad = R if i % 2 == 0 else r
    a = -math.pi / 2 + i * math.pi / 5
    pts.append((c + rad * math.cos(a), c + rad * math.sin(a) + BIG * 0.012))
d.polygon(pts, fill=ACCENT)

out = Path("icons")
out.mkdir(exist_ok=True)
for name, size in [("icon-512.png", 512), ("icon-192.png", 192), ("apple-touch-icon.png", 180)]:
    img.resize((size, size), Image.LANCZOS).save(out / name)
print("icons written")
