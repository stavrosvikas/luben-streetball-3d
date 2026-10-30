"""Extract the floor-plan vectors from the Illustrator PDF into ../plan.json (metres).

Usage:  python tools/extract.py [path/to/plan.pdf]
Needs:  pip install pymupdf
The wall outline (thick dark closed path) defines scale: its first edge is 39.85 m.
"""
import json, math, os, sys
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "katopsi_v02d.pdf")
OUT = os.path.join(HERE, "..", "plan.json")
LEGEND_X = 1950          # everything right of this (pt) is title/legend
FIRST_EDGE_M = 39.85     # Γ→Δ measured on the technical plan


def hexc(c):
    return None if c is None else "#%02x%02x%02x" % tuple(round(v * 255) for v in c[:3])


def bez(p0, p1, p2, p3, n=8):
    out = []
    for i in range(1, n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        out.append((a * p0.x + b * p1.x + c * p2.x + d * p3.x, a * p0.y + b * p1.y + c * p2.y + d * p3.y))
    return out


def subpaths(d):
    """Split a drawing into point lists (one per subpath)."""
    paths, cur = [], []
    for it in d["items"]:
        op = it[0]
        if op == "re":
            r = it[1]
            paths.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)])
            continue
        if op == "qu":
            q = it[1]
            paths.append([(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)])
            continue
        start = it[1]
        if cur and (abs(cur[-1][0] - start.x) > 0.5 or abs(cur[-1][1] - start.y) > 0.5):
            paths.append(cur)
            cur = []
        if not cur:
            cur.append((start.x, start.y))
        if op == "l":
            cur.append((it[2].x, it[2].y))
        elif op == "c":
            cur.extend(bez(it[1], it[2], it[3], it[4]))
    if cur:
        paths.append(cur)
    return paths


page = pymupdf.open(PDF)[0]
drawings = page.get_drawings()

# Wall = dark, thick, stroked path with the most line segments.
wall = max((d for d in drawings if d.get("color") and d.get("width", 0) >= 4 and sum(d["color"][:3]) < 0.5),
           key=lambda d: len(d["items"]))
wp = subpaths(wall)[0]
scale = math.dist(wp[0], wp[1]) / FIRST_EDGE_M          # pt per metre
ox, oy = wp[0]


def m(p):
    return [round((p[0] - ox) / scale, 3), round((p[1] - oy) / scale, 3)]


shapes = []
for i, d in enumerate(drawings):
    if d is wall or d["rect"].x0 > LEGEND_X:
        continue
    for pts in subpaths(d):
        if len(pts) < 2:
            continue
        shapes.append({
            "pts": [m(p) for p in pts],
            "fill": hexc(d.get("fill")) if "f" in d["type"] else None,
            "stroke": hexc(d.get("color")) if "s" in d["type"] else None,
            "w": round((d.get("width") or 0) / scale, 3),
            "dash": bool(d.get("dashes") and d["dashes"] not in ("[] 0", "")),
            "closed": bool(d.get("closePath")) or len(pts) == 4 and d["items"][0][0] in ("re", "qu"),
        })

# Latin/number labels (booth numbers, DJ, ...). Greek glyphs come out unreadable from this PDF, so skip them.
texts = []
for b in page.get_text("blocks"):
    t = " ".join(b[4].split())
    if b[0] > LEGEND_X or not t or not all(32 <= ord(ch) < 127 for ch in t):
        continue
    texts.append({"t": t, "at": m(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))})

plan = {"scale_pt_per_m": round(scale, 3), "wall": [m(p) for p in wp], "shapes": shapes, "texts": texts}
json.dump(plan, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
# Same data as a script so index.html also opens straight from disk (file://).
with open(os.path.join(HERE, "..", "plan.js"), "w", encoding="utf-8") as f:
    f.write("window.PLAN = " + json.dumps(plan, ensure_ascii=False) + ";\n")
print(f"scale {scale:.2f} pt/m, wall {len(wp)} pts, {len(shapes)} shapes, {len(texts)} texts -> {os.path.normpath(OUT)}")
