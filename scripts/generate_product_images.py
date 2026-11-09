#!/usr/bin/env python3
"""Generate one flat "Hard Cap" SVG product image per catalog SKU.

Standard library only, deterministic (variation derives from SHA-256 of the SKU).
Reads services/catalog/app_catalog/seed/catalog_seed.json; each item may carry an
``art`` glyph key, otherwise a glyph is derived from ``category_id``.

    python3 scripts/generate_product_images.py [--out DIR] [--check]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "services/catalog/app_catalog/seed/catalog_seed.json"
DEFAULT_OUT = ROOT / "services/web/public/products"

CREAM, MUTE, PANEL, PANEL2 = "#f3f0e6", "#b1aea3", "#131315", "#1c1c20"
LINE, LINE_STRONG, DARK = "#2b2b31", "#4a4a53", "#0a0a0b"
BLUE, ORANGE, LIME = "#5c86ff", "#ff6a3d", "#bef542"

MERCHANTS = {
    "mrc_trailhead": (BLUE, "TRAILHEAD"),
    "mrc_hearth": (ORANGE, "HEARTH"),
    "mrc_pixelwire": (LIME, "PIXELWIRE"),
}
CATEGORY_ART = {
    "running": "running-shoe",
    "outdoor": "tent",
    "kitchen": "skillet",
    "home": "lamp",
    "electronics": "earbuds",
    "consumable": "gift-box",
}
FALLBACK_ART = "gift-box"

# ---------------------------------------------------------------- primitives
# Colour keys: c cream, a accent, s secondary, m mute, d dark, p panel-2.
# Lower-case class = fill, upper-case class = stroke (fill none).


def n(v: float) -> str:
    v = round(v, 1)
    return str(int(v)) if v == int(v) else str(v)


def r(x, y, w, h, k):
    return f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" class="{k}"/>'


def rs(x, y, w, h, k, sw):
    return f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" class="{k.upper()}" stroke-width="{sw}"/>'


def pg(pts, k):
    return f'<polygon points="{pts}" class="{k}"/>'


def o(cx, cy, rad, k):
    return f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(rad)}" class="{k}"/>'


def ln(x1, y1, x2, y2, k, w=6):
    return f'<path d="M{n(x1)} {n(y1)}L{n(x2)} {n(y2)}" class="{k.upper()}" stroke-width="{w}"/>'


def ring(cx, cy, rad, k, w=6):
    return f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(rad)}" class="{k.upper()}" stroke-width="{w}"/>'


def pa(d, k, w=6, extra=""):
    return f'<path d="{d}" class="{k.upper()}" stroke-width="{w}"{extra}/>'


def pf(d, k):
    return f'<path d="{d}" class="{k}"/>'


def arc(cx, cy, rad, a0, a1, k, w=6):
    def pt(a):
        t = math.radians(a)
        return cx + rad * math.sin(t), cy - rad * math.cos(t)

    x0, y0 = pt(a0)
    x1, y1 = pt(a1)
    return pa(f"M{n(x0)} {n(y0)}A{n(rad)} {n(rad)} 0 0 1 {n(x1)} {n(y1)}", k, w)


def g(inner, tr):
    return f'<g transform="{tr}">{inner}</g>'


def leaf(cx, cy, w, h, rot, k):
    return g(pg(f"0,0 {-w},{-h / 2} 0,{-h} {w},{-h / 2}", k), f"translate({n(cx)} {n(cy)}) rotate({rot})")


# --------------------------------------------------------------------- glyphs


def running_shoe():
    return "".join([
        pg("-115,50 -115,-40 -80,-52 -45,-14 5,-4 60,18 118,42 122,52", "c"),
        pg("-115,-40 -80,-52 -68,-14 -115,0", "m"),
        r(-124, 50, 250, 26, "a"),
        pg("-100,50 -20,50 60,20 -10,-4", "a"),
        ln(-34, -4, -8, 22, "d"), ln(-12, 4, 14, 28, "d"), ln(10, 10, 36, 34, "d"),
        ln(-120, 60, 126, 60, "d", 3),
    ])


def socks():
    def sock(dx, dy, body, band):
        return g(
            pg("-90,-110 -20,-110 -20,20 100,20 100,90 -90,90", body)
            + r(-90, -110, 70, 26, band) + r(60, 20, 40, 70, band) + r(-90, 62, 28, 28, band),
            f"translate({dx} {dy})")
    return sock(34, -26, "m", "m").replace('class="m"', 'class="m"', 1) + sock(-12, 6, "c", "a")


def shorts():
    return "".join([
        pg("-90,-62 90,-62 112,92 12,92 0,0 -12,92 -112,92", "c"),
        r(-92, -92, 184, 32, "a"),
        ln(-14, -76, -14, -30, "d", 4), ln(14, -76, 14, -30, "d", 4),
        ln(-100, 20, -108, 92, "m", 8), ln(100, 20, 108, 92, "m", 8),
    ])


def bottle():
    return "".join([
        r(-46, -62, 92, 172, "c"), r(-26, -96, 52, 36, "m"), r(-34, -128, 68, 32, "a"),
        r(-46, -6, 92, 54, "a"), r(-30, -52, 10, 90, "m"),
        ln(-34, -112, 34, -112, "d", 3),
    ])


def headlamp():
    return "".join([
        pa("M-132 66Q0 -130 132 66", "m", 18), pa("M-132 66Q0 -130 132 66", "a", 4),
        r(-68, 20, 136, 20, "m"), r(-60, -56, 120, 80, "c"), r(-60, -56, 120, 14, "a"),
        o(0, -10, 34, "a"), o(0, -10, 20, "d"), o(0, -10, 7, "c"), r(-14, -72, 28, 16, "s"),
    ])


def trail_pack():
    return "".join([
        r(-96, -62, 26, 130, "m"), r(70, -62, 26, 130, "m"),
        pg("-56,-122 56,-122 72,-80 -72,-80", "m"), r(-72, -80, 144, 192, "c"),
        r(-52, 8, 104, 70, "a"), ln(-52, 30, 52, 30, "d", 3),
        ln(-72, -40, 72, -40, "d", 4), r(-12, -52, 24, 24, "s"),
    ])


def tent():
    return "".join([
        pg("-132,92 0,-104 0,92", "c"), pg("0,-104 132,92 0,92", "m"),
        pg("0,-40 -42,92 42,92", "d"), pg("0,-40 0,92 42,92", "p"),
        r(-142, 92, 284, 10, "a"), ln(0, -104, 0, -40, "a", 6),
        ln(-132, 92, -150, 100, "a", 4), ln(132, 92, 150, 100, "a", 4),
    ])


def sleeping_bag():
    baffles = "".join(ln(-58 + abs(y) * 0.0, y, 58, y, "d", 4) for y in (-10, 30, 70))
    return "".join([
        pf("M-54 -66A54 54 0 0 1 54 -66L44 114H-44Z", "c"), o(0, -62, 30, "d"), o(0, -62, 16, "m"),
        baffles, r(-4, -26, 8, 140, "a"), r(-54, 94, 108, 20, "a"), o(0, -32, 8, "s"),
        r(-96, 40, 36, 74, "m"), ln(-96, 62, -60, 62, "d", 3),
    ])


def trek_pole():
    def pole(dx, body):
        return g(
            r(-13, -132, 26, 62, "a") + r(-6, -70, 12, 170, body) + ring(0, 62, 18, "m", 5)
            + pg("-6,100 6,100 0,128", "m") + r(-6, -20, 12, 10, "d"),
            f"translate({dx} 0) rotate(22)")
    return pole(-34, "m") + pole(30, "c")


def camp_stove():
    return "".join([
        r(-74, -112, 148, 62, "m"), r(74, -96, 40, 14, "m"),
        pg("-30,-14 -14,-44 0,-62 14,-40 30,-14", "a"), pg("-12,-14 0,-36 12,-14", "c"),
        r(-90, -14, 180, 10, "c"),
        r(-62, -4, 124, 38, "c"), r(-100, 34, 200, 20, "m"),
        r(-90, 54, 18, 28, "m"), r(72, 54, 18, 28, "m"), o(0, 15, 10, "a"),
    ])


def water_filter():
    return "".join([
        r(-44, -28, 88, 140, "c"), r(-28, -110, 56, 82, "a"), r(-16, -132, 32, 22, "m"),
        ln(-28, -85, 28, -85, "d", 4), ln(-28, -60, 28, -60, "d", 4),
        pg("0,20 16,52 0,70 -16,52", "s"), r(-44, 84, 88, 12, "m"),
    ])


def compass():
    ticks = "".join(g(ln(0, -86, 0, -76, "m", 5), f"rotate({a})") for a in range(0, 360, 30))
    return "".join([
        o(0, 0, 118, "c"), o(0, 0, 96, "d"), ticks,
        pg("0,-76 14,0 -14,0", "a"), pg("0,76 14,0 -14,0", "c"), o(0, 0, 6, "d"),
        r(-12, -134, 24, 16, "m"),
    ])


def jacket():
    return "".join([
        pg("-56,-100 -122,70 -90,82 -56,-4", "m"), pg("56,-100 122,70 90,82 56,-4", "m"),
        pg("-60,-104 60,-104 72,112 -72,112", "c"),
        r(-30, -120, 60, 28, "a"), ln(0, -92, 0, 112, "d", 4),
        r(-58, 40, 38, 8, "a"), r(20, 40, 38, 8, "a"), r(-92, 74, 36, 10, "d"), r(56, 74, 36, 10, "d"),
    ])


def beanie():
    ribs = "".join(ln(x, -12, x * 0.9, 34, "d", 3) for x in (-60, -30, 0, 30, 60))
    return "".join([
        o(0, -78, 24, "m"), pf("M-100 36A100 100 0 0 1 100 36Z", "c"), ribs,
        r(-112, 30, 224, 56, "a"), ln(-112, 46, 112, 46, "d", 3), ln(-112, 70, 112, 70, "d", 3),
    ])


def gloves():
    fingers = "".join(r(-52 + i * 26, -20 - h, 24, h, "c") for i, h in enumerate((72, 92, 84, 66)))
    return "".join([
        fingers, r(-52, -22, 102, 106, "c"), pg("-52,24 -104,-22 -84,-44 -52,-6", "c"),
        r(-58, 76, 114, 46, "a"), ln(-58, 99, 56, 99, "d", 3),
        ln(-26, -20, -26, 30, "d", 3), ln(0, -20, 0, 30, "d", 3), ln(26, -20, 26, 30, "d", 3),
    ])


def sunglasses():
    lens = (pg("-126,-34 -10,-34 -18,36 -40,58 -100,58 -120,28", "c")
            + pg("-112,-22 -24,-22 -31,32 -46,46 -94,46 -108,24", "d")
            + pg("-100,-14 -70,-14 -100,16", "a"))
    return "".join([
        lens, g(lens, "scale(-1 1)"), r(-14, -28, 28, 12, "c"),
        ln(-126, -30, -140, -50, "c", 8), ln(126, -30, 140, -50, "c", 8),
    ])


def skillet():
    return "".join([
        r(60, -16, 78, 32, "c"), o(128, 0, 6, "d"), o(-24, 0, 98, "c"), o(-24, 0, 78, "d"),
        o(-24, 0, 36, "c"), o(-24, 0, 15, "a"), arc(-24, 0, 62, 220, 320, "m", 5),
    ])


def saucepan():
    return "".join([
        r(-82, -34, 164, 118, "c"), r(-90, -54, 180, 22, "m"), r(-14, -76, 28, 22, "a"),
        r(82, -18, 62, 22, "a"), r(-82, 8, 164, 16, "a"), ln(-90, -32, 90, -32, "d", 3),
    ])


def kettle():
    return "".join([
        pa("M-52 -14Q-122 -20 -104 62L-68 62", "a", 16),
        pg("56,-4 112,-76 124,-64 72,40", "c"),
        pg("-76,84 -54,-30 54,-30 76,84", "c"), r(-46, -44, 92, 14, "m"), o(0, -56, 12, "a"),
        r(-82, 84, 164, 14, "m"), r(-52, 20, 104, 12, "a"),
    ])


def coffee_set():
    return "".join([
        pg("-76,-84 76,-84 26,-26 -26,-26", "a"), r(-34, -26, 68, 12, "m"),
        pg("-78,108 -42,-6 42,-6 78,108", "c"), pg("-70,108 -62,56 62,56 70,108", "d"),
        o(0, 8, 6, "s"), o(0, 26, 6, "s"),
    ])


def knife():
    return g("".join([
        pg("-132,14 -104,-30 44,-30 44,14", "c"), ln(-120, 8, 44, 8, "m", 3),
        r(44, -26, 92, 32, "a"), o(70, -10, 5, "d"), o(100, -10, 5, "d"), r(40, -30, 8, 40, "m"),
    ]), "rotate(-18)")


def cutting_board():
    return "".join([
        r(-104, -74, 208, 150, "c"), r(-104, 76, 208, 14, "m"), o(-72, 0, 13, "d"),
        ln(-40, -50, 90, -50, "m", 3), ln(-40, 50, 90, 50, "m", 3),
        o(30, 0, 30, "a"), r(24, -40, 12, 14, "s"),
    ])


def mixing_bowl():
    return "".join([
        pf("M-112 -20A112 108 0 0 0 112 -20Z", "c"), r(-124, -34, 248, 16, "m"),
        pf("M-96 14A100 90 0 0 0 96 14Z", "a"), r(-44, 86, 88, 14, "m"),
    ])


def jar():
    return "".join([
        r(-66, -60, 132, 162, "c"), r(-74, -104, 148, 44, "a"),
        ln(-50, -104, -50, -62, "d", 3), ln(-25, -104, -25, -62, "d", 3), ln(0, -104, 0, -62, "d", 3),
        r(-50, -16, 100, 74, "d"), ln(-34, 4, 34, 4, "m", 5), ln(-34, 24, 12, 24, "m", 5),
        ln(-34, 44, 24, 44, "a", 5),
    ])


def tea_tin():
    return "".join([
        r(-82, -64, 164, 154, "c"), r(-90, -98, 180, 36, "a"), r(-82, -62, 164, 8, "m"),
        o(0, 14, 50, "d"), leaf(0, 50, 20, 56, 0, "a"), leaf(0, 50, 20, 40, 60, "s"),
    ])


def gift_box():
    return "".join([
        r(-92, -30, 184, 124, "c"), r(-104, -62, 208, 36, "m"), r(-16, -62, 32, 156, "a"),
        ring(-34, -88, 26, "a", 10), ring(34, -88, 26, "a", 10), r(-12, -100, 24, 24, "s"),
    ])


def apron():
    return "".join([
        pa("M-46 -120Q0 -172 46 -120", "m", 8),
        pg("-44,-120 44,-120 52,-40 -52,-40", "c"),
        pg("-52,-40 52,-40 92,112 -92,112", "c"),
        ln(-52, -40, -112, -30, "m", 8), ln(52, -40, 112, -30, "m", 8),
        r(-46, 22, 92, 54, "a"), ln(0, 22, 0, 76, "d", 3), ln(-30, -80, 30, -80, "d", 4),
    ])


def candle():
    return "".join([
        pg("0,-112 15,-76 0,-52 -15,-76", "a"), pg("0,-92 7,-76 0,-64 -7,-76", "c"),
        ln(0, -52, 0, -34, "d", 5), r(-48, -34, 96, 124, "c"), r(-48, 18, 96, 40, "a"),
        r(-64, 90, 128, 14, "m"), pg("-48,-34 -20,-34 -48,-6", "m"),
    ])


def blanket():
    stripes = "".join(r(x, -62, 14, 46, "d") for x in (-70, -30, 10, 50, 90))
    fringe = "".join(ln(x, 78, x, 98, "m", 4) for x in range(-100, 101, 20))
    return "".join([
        r(-112, 28, 224, 50, "m"), r(-104, -16, 224, 44, "c"), r(-112, -62, 224, 46, "a"),
        stripes, ln(-112, 28, 112, 28, "d", 3), fringe,
    ])


def pillow():
    pts = "-100,-86 -60,-100 0,-92 60,-100 100,-86 114,0 100,86 60,100 0,92 -60,100 -100,86 -114,0"
    return "".join([
        pg(pts, "c"),
        pa("M-82 -66L-46 -78L0 -72L46 -78L82 -66L94 0L82 66L46 78L0 72L-46 78L-82 66L-94 0Z",
           "a", 4, ' stroke-dasharray="10 8"'),
        o(0, 0, 12, "a"), o(0, 0, 4, "d"),
    ])


def vase():
    return "".join([
        ln(0, -100, -32, -138, "m", 5), ln(0, -100, 0, -146, "m", 5), ln(0, -100, 34, -136, "m", 5),
        o(-32, -140, 13, "a"), o(0, -148, 13, "s"), o(34, -138, 13, "a"),
        pg("-24,-104 24,-104 24,-68 74,0 54,100 -54,100 -74,0 -24,-68", "c"),
        pg("-68,28 68,28 62,60 -62,60", "a"),
    ])


def plant_pot():
    return "".join([
        leaf(0, -14, 28, 110, 0, "a"), leaf(0, -14, 26, 90, -48, "s"), leaf(0, -14, 26, 90, 48, "s"),
        leaf(0, -14, 20, 66, -86, "a"), leaf(0, -14, 20, 66, 86, "a"),
        r(-82, -14, 164, 30, "c"), pg("-68,16 68,16 52,108 -52,108", "m"),
        r(-52, 54, 104, 12, "a"),
    ])


def lamp():
    return "".join([
        pg("-62,-112 62,-112 94,-28 -94,-28", "a"), r(-8, -28, 16, 108, "c"), r(-54, 80, 108, 16, "c"),
        r(-62, -112, 124, 8, "c"), o(0, -14, 9, "c"),
        ln(-120, 20, -100, 6, "m", 4), ln(120, 20, 100, 6, "m", 4), ln(-124, 50, -104, 40, "m", 4),
        ln(124, 50, 104, 40, "m", 4),
    ])


def clock():
    ticks = "".join(g(ln(0, -84, 0, -72 if a % 90 else -66, "c", 5 if a % 90 else 7), f"rotate({a})")
                    for a in range(0, 360, 30))
    return "".join([
        o(0, 0, 118, "c"), o(0, 0, 100, "d"), ticks,
        ln(0, 0, 0, -50, "c", 8), ln(0, 0, 50, 22, "a", 6), o(0, 0, 9, "a"),
    ])


def rug():
    fringe = "".join(ln(-124, y, -140, y, "m", 4) + ln(124, y, 140, y, "m", 4) for y in range(-48, 49, 16))
    inner = (r(-120, -64, 240, 128, "c") + rs(-100, -50, 200, 100, "d", 3)
             + pg("0,-40 70,0 0,40 -70,0", "a") + pg("0,-22 36,0 0,22 -36,0", "d") + o(0, 0, 6, "c"))
    return g(inner + fringe, "skewX(-16)")


def towel():
    return "".join([
        r(-82, -112, 164, 218, "c"), r(-82, -112, 164, 42, "m"), r(-84, -122, 168, 12, "a"),
        r(-82, 36, 164, 14, "a"), r(-82, 60, 164, 14, "a"),
        "".join(ln(x, 106, x, 126, "m", 4) for x in range(-72, 73, 18)),
        ln(-82, -70, 82, -70, "d", 3),
    ])


def frame():
    return "".join([
        r(-126, -96, 252, 192, "c"), r(-98, -68, 196, 136, "d"),
        pg("-98,68 -36,-18 0,26 36,-30 98,68", "a"), pg("36,-30 50,-8 22,-8", "c"),
        o(-52, -34, 14, "m"), pa("M-8 -96L0 -128L8 -96", "m", 4),
    ])


def earbuds():
    def bud(sx):
        return g(r(-8, -14, 17, 70, "c") + o(0, -34, 28, "a") + o(0, -34, 11, "d"),
                 f"translate({sx * 54} -62) rotate({sx * 14})")
    return "".join([
        bud(-1), bud(1), r(-76, 16, 152, 90, "c"), r(-76, 50, 152, 6, "d"),
        o(0, 80, 6, "a"), r(-76, 96, 152, 10, "m"),
    ])


def headphones():
    def cup(s):
        return g(r(-124, 6, 52, 98, "a") + r(-76, 14, 18, 82, "m"), f"scale({s} 1)")
    return "".join([
        pa("M-92 20A92 92 0 0 1 92 20", "c", 16), r(-18, -80, 36, 12, "m"), cup(1), cup(-1),
    ])


def speaker():
    return "".join([
        r(-72, -116, 144, 224, "c"), o(0, -62, 22, "d"), ring(0, -62, 26, "a", 5), o(0, -62, 6, "m"),
        o(0, 36, 50, "d"), ring(0, 36, 56, "a", 6), o(0, 36, 28, "m"), o(0, 36, 10, "d"),
        r(-60, 108, 22, 14, "m"), r(38, 108, 22, 14, "m"),
    ])


def cable():
    return "".join([
        pa("M-92 70C-92 -70 0 -70 0 10S92 90 92 -40", "c", 12),
        pa("M-92 40L-92 12", "a", 12), pa("M92 -60L92 -86", "a", 12),
        r(-110, 66, 36, 44, "m"), r(-102, 110, 20, 18, "c"), r(76, -112, 32, 54, "m"),
        r(84, -132, 16, 22, "c"), o(-92, 88, 5, "d"),
    ])


def charger():
    return "".join([
        r(-34, 56, 16, 40, "m"), r(18, 56, 16, 40, "m"), r(-66, -98, 132, 158, "c"),
        r(-34, -74, 68, 14, "d"), pg("10,-42 -26,16 -4,16 -14,52 28,-8 4,-8", "a"),
        ln(-66, 40, 66, 40, "m", 3),
    ])


def power_bank():
    bars = "".join(r(-78 + i * 36, -6, 28, 46, "a" if i < 3 else "m") for i in range(4))
    return "".join([
        pg("-114,-56 -94,-84 130,-84 110,-56", "m"), pg("110,-56 130,-84 130,40 110,66", "p"),
        r(-114, -56, 224, 122, "c"), r(-30, -56, 60, 12, "d"), bars,
        pg("8,-34 -8,-18 2,-18 -6,-4 12,-24 2,-24", "d"),
    ])


def keyboard():
    keys = []
    for row in range(3):
        for i in range(9 if row < 2 else 8):
            x = -108 + i * 26 + (10 if row == 2 else 0)
            keys.append(r(x, -40 + row * 26, 22, 20, "a" if (row, i) in ((0, 0), (2, 7)) else "d"))
    keys.append(r(-68, 40, 136, 20, "d"))
    keys.append(r(-108, 40, 36, 20, "d"))
    keys.append(r(72, 40, 36, 20, "a"))
    return r(-126, -56, 252, 128, "c") + "".join(keys)


def mouse():
    return "".join([
        pf("M0 -112C70 -112 82 -60 82 0L82 40C82 96 50 116 0 116C-50 116 -82 96 -82 40L-82 0C-82 -60 -70 -112 0 -112Z", "c"),
        ln(0, -112, 0, -22, "d", 4), pa("M-82 -22H82", "d", 4), r(-9, -84, 18, 44, "a"),
        pf("M-82 20H-60V70Q-60 98 -30 108Q-82 100 -82 40Z", "m"),
    ])


def webcam():
    return "".join([
        r(-16, 38, 32, 40, "m"), r(-66, 78, 132, 18, "m"),
        o(0, -34, 78, "c"), o(0, -34, 54, "d"), o(0, -34, 34, "a"), o(0, -34, 14, "d"), o(-10, -46, 5, "c"),
        o(60, -84, 6, "a"),
    ])


def monitor_stand():
    return "".join([
        r(-76, -102, 152, 104, "c"), r(-62, -88, 124, 76, "d"), r(-52, -76, 50, 8, "a"),
        r(-52, -58, 80, 8, "m"), r(-52, -40, 36, 8, "m"), r(-14, 2, 28, 18, "m"),
        r(-130, 20, 260, 22, "c"), r(-118, 42, 22, 56, "m"), r(96, 42, 22, 56, "m"),
        r(-118, 74, 236, 8, "a"),
    ])


def smartwatch():
    return "".join([
        r(-38, -128, 76, 76, "m"), r(-38, 52, 76, 76, "m"),
        o(0, 76, 5, "d"), o(0, 94, 5, "d"), o(0, 112, 5, "d"),
        r(-64, -58, 128, 116, "c"), r(-50, -44, 100, 88, "d"), r(64, -18, 12, 28, "a"),
        ring(0, 0, 26, "a", 8), ln(0, 0, 0, -16, "c", 5), ln(0, 0, 12, 8, "c", 5),
    ])


def fitness_band():
    holes = "".join(o(70 + i * 20, 0, 5, "d") for i in range(3))
    return "".join([
        r(-134, -26, 268, 52, "m"), holes, r(-134, -26, 20, 52, "a"),
        r(-54, -38, 108, 76, "c"), r(-42, -26, 84, 52, "d"),
        o(-7, -6, 8, "a"), o(7, -6, 8, "a"), pg("-15,-2 15,-2 0,16", "a"),
    ])


def phone_case():
    return "".join([
        r(-68, -124, 136, 248, "c"), r(-56, -112, 112, 224, "d"),
        rs(-68, -124, 136, 248, "a", 8),
        r(-48, -104, 58, 74, "c"), o(-30, -86, 14, "d"), o(-30, -50, 14, "d"), o(-30, -86, 6, "a"),
        o(-30, -50, 6, "a"), o(30, -90, 5, "m"), r(-56, 40, 112, 20, "a"),
    ])


def router():
    leds = "".join(o(-80 + i * 24, 40, 6, "a" if i < 4 else "m") for i in range(5))
    ports = "".join(r(30 + i * 22, 30, 16, 20, "d") for i in range(3))
    return "".join([
        g(r(-8, -110, 16, 120, "m"), "translate(-94 0) rotate(-12)"),
        g(r(-8, -110, 16, 120, "m"), "translate(94 0) rotate(12)"),
        r(-118, 10, 236, 76, "c"), leds, ports,
        arc(0, 0, 24, -50, 50, "a", 7), arc(0, 0, 46, -50, 50, "a", 7), arc(0, 0, 68, -50, 50, "a", 7),
        o(0, 0, 7, "a"),
    ])


def ssd():
    return "".join([
        pg("-112,-72 80,-72 112,-40 112,72 -112,72", "c"), r(-86, -46, 124, 62, "d"),
        ln(-70, -26, 20, -26, "m", 5), ln(-70, -8, -10, -8, "a", 5),
        r(60, -46, 30, 30, "m"), r(-60, 72, 96, 22, "m"),
        "".join(ln(-52 + i * 14, 72, -52 + i * 14, 86, "d", 4) for i in range(6)),
        r(-112, 36, 224, 12, "a"),
    ])


def game_controller():
    body = ("M-90 -52H90Q132 -52 126 20L110 86Q100 112 74 86L46 46H-46L-74 86Q-100 112 -110 86"
            "L-126 20Q-132 -52 -90 -52Z")
    return "".join([
        pf(body, "c"), r(-80, -34, 16, 52, "d"), r(-98, -16, 52, 16, "d"),
        o(86, -30, 10, "a"), o(104, -10, 10, "s"), o(68, -10, 10, "m"), o(86, 10, 10, "d"),
        o(-34, 18, 18, "d"), ring(-34, 18, 12, "m", 4), o(34, 18, 18, "d"), ring(34, 18, 12, "m", 4),
        r(-20, -30, 14, 8, "m"), r(6, -30, 14, 8, "m"),
    ])


def desk_mat():
    return "".join([
        pg("-136,-24 84,-78 138,28 -84,82", "a"), pg("-122,-22 78,-68 124,24 -76,70", "d"),
        pa("M-110 -21L74 -62L112 23L-69 62Z", "c", 3, ' stroke-dasharray="8 6"'),
        pg("-40,-12 30,-28 52,12 -18,28", "p"), pg("-6,6 20,-2 28,14 2,22", "a"),
        pg("-90,6 -60,0 -52,16 -82,24", "m"),
    ])


def notebook():
    rings = "".join(o(-67, -88 + i * 29, 7, "d") for i in range(7))
    return "".join([
        r(76, -104, 12, 216, "m"), r(-82, -112, 164, 224, "c"), r(-82, -112, 28, 224, "a"),
        rings, r(-24, -72, 80, 58, "d"), ln(-12, -54, 42, -54, "m", 5), ln(-12, -36, 24, -36, "a", 5),
        r(40, -112, 14, 224, "m"), pg("-4,112 18,112 18,136 7,126 -4,136", "a"),
    ])


def backpack():
    return "".join([
        pa("M-26 -102Q0 -138 26 -102", "m", 10), r(-98, -54, 20, 120, "m"), r(78, -54, 20, 120, "m"),
        pf("M-80 112V-32Q-80 -104 0 -104Q80 -104 80 -32V112Z", "c"),
        pa("M-66 -30Q0 -76 66 -30", "d", 4), r(-62, 22, 124, 72, "a"), ln(-62, 44, 62, 44, "d", 3),
        r(-12, 36, 24, 14, "d"),
    ])


GLYPHS = {
    "running-shoe": running_shoe, "socks": socks, "shorts": shorts, "bottle": bottle,
    "headlamp": headlamp, "trail-pack": trail_pack, "tent": tent, "sleeping-bag": sleeping_bag,
    "trek-pole": trek_pole, "camp-stove": camp_stove, "water-filter": water_filter,
    "compass": compass, "jacket": jacket, "beanie": beanie, "gloves": gloves,
    "sunglasses": sunglasses, "skillet": skillet, "saucepan": saucepan, "kettle": kettle,
    "coffee-set": coffee_set, "knife": knife, "cutting-board": cutting_board,
    "mixing-bowl": mixing_bowl, "jar": jar, "tea-tin": tea_tin, "gift-box": gift_box,
    "apron": apron, "candle": candle, "blanket": blanket, "pillow": pillow, "vase": vase,
    "plant-pot": plant_pot, "lamp": lamp, "clock": clock, "rug": rug, "towel": towel,
    "frame": frame, "earbuds": earbuds, "headphones": headphones, "speaker": speaker,
    "cable": cable, "charger": charger, "power-bank": power_bank, "keyboard": keyboard,
    "mouse": mouse, "webcam": webcam, "monitor-stand": monitor_stand,
    "smartwatch": smartwatch, "fitness-band": fitness_band, "phone-case": phone_case,
    "router": router, "ssd": ssd, "game-controller": game_controller, "desk-mat": desk_mat,
    "notebook": notebook, "backpack": backpack,
}

# ----------------------------------------------------------------- composition

CARD = "8,8 582,8 618,44 618,460 8,460"
SHADOW = "22,22 596,22 632,58 632,474 22,474"
MONO = "IBM Plex Mono, ui-monospace, monospace"


def style_block(acc: str, sec: str) -> str:
    fills = {"c": CREAM, "a": acc, "s": sec, "m": MUTE, "d": DARK, "p": PANEL2}
    css = "".join(f".{k}{{fill:{v}}}.{k.upper()}{{stroke:{v};fill:none}}" for k, v in fills.items())
    return f"<style>{css}</style>"


def decoration(h: bytes) -> str:
    style, cnt = h[2] % 4, 2 + h[3] % 4
    if style == 0:  # corner ticks
        def t(x, y, sx, sy):
            return pa(f"M{x + sx * 22} {y}H{x}V{y + sy * 22}", "s", 3)
        return t(30, 30, 1, 1) + t(30, 380, 1, -1) + t(588, 380, -1, -1) + "".join(
            o(46 + i * 14, 50, 3, "s") for i in range(cnt - 1))
    if style == 1:  # dots
        return "".join(o(38 + i * 16, 40, 4, "s") for i in range(cnt + 1))
    if style == 2:  # diagonal stripes
        return "".join(
            pg(f"{34 + i * 14},46 {44 + i * 14},34 {50 + i * 14},34 {40 + i * 14},46", "s") for i in range(cnt))
    return "".join(r(30, 32 + i * 10, 44 - i * 8, 4, "s") for i in range(cnt))  # bars


def render(item: dict) -> str:
    sku = str(item["sku"])
    acc, short = MERCHANTS.get(item.get("merchant_id", ""), (BLUE, "SAFEPAY"))
    h = hashlib.sha256(sku.encode()).digest()
    sec = [c for c in (BLUE, ORANGE, LIME) if c != acc][h[0] % 2]
    rot = h[1] % 13 - 6
    default_art = CATEGORY_ART.get(item.get("category_id", ""), FALLBACK_ART)
    glyph = GLYPHS.get(item.get("art") or "", GLYPHS[default_art])
    uid = re.sub(r"[^A-Za-z0-9]", "", sku) or "x"
    title = escape(str(item.get("title") or sku))
    tag_w = len(sku) * 13 + 26
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480" width="640" height="480" role="img">',
        f"<title>{title}</title>",
        style_block(acc, sec),
        f'<defs><clipPath id="k{uid}"><polygon points="{CARD}"/></clipPath>'
        f'<pattern id="g{uid}" width="40" height="40" patternUnits="userSpaceOnUse">'
        f'<path d="M40 0H0V40" fill="none" stroke="{LINE}" stroke-width="1"/></pattern></defs>',
        f'<polygon points="{SHADOW}" fill="{acc}"/>',
        f'<polygon points="{CARD}" fill="{PANEL}"/>',
        f'<g clip-path="url(#k{uid})"><rect width="640" height="480" fill="url(#g{uid})" opacity=".55"/></g>',
        decoration(h),
        f'<rect x="160" y="46" width="320" height="324" fill="{PANEL2}" stroke="{LINE}" stroke-width="2"/>'
        f'<g transform="translate(320 208) scale(1.16) rotate({rot})">{glyph()}</g>',
        f'<path d="M8 400H618" stroke="{LINE}" stroke-width="2"/>',
        f'<rect x="28" y="412" width="{tag_w}" height="32" fill="{DARK}" stroke="{acc}" stroke-width="2"/>',
        f'<text x="{n(28 + tag_w / 2)}" y="434" text-anchor="middle" font-family="{MONO}" '
        f'font-size="17" font-weight="700" letter-spacing="2" fill="{CREAM}">{escape(sku.upper())}</text>',
        f'<text x="598" y="434" text-anchor="end" font-family="{MONO}" '
        f'font-size="14" letter-spacing="3" fill="{MUTE}">{escape(short)}</text>',
        f'<path d="M582 8L618 44" stroke="{acc}" stroke-width="3"/>',
        f'<polygon points="{CARD}" fill="none" stroke="{LINE_STRONG}" stroke-width="3"/>',
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def placeholder() -> str:
    cube = (
        f'<polygon points="32,2 60,18 32,34 4,18" fill="{CREAM}"/>'
        f'<polygon points="4,18 32,34 32,62 4,46" fill="{BLUE}"/>'
        f'<polygon points="32,34 60,18 60,46 32,62" fill="{ORANGE}"/>'
        f'<path d="M4 18L32 34L60 18M32 34V62" fill="none" stroke="{DARK}" stroke-width="1.6"/>'
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480" width="640" height="480" role="img">\n'
        "<title>Product image unavailable</title>\n"
        f'<polygon points="{SHADOW}" fill="{LINE_STRONG}"/>\n'
        f'<polygon points="{CARD}" fill="{PANEL}"/>\n'
        f'<rect x="168" y="76" width="304" height="304" fill="{PANEL2}" stroke="{LINE}" stroke-width="2"/>\n'
        f'<g transform="translate(240 148) scale(2.5)">{cube}</g>\n'
        f'<path d="M8 400H618" stroke="{LINE}" stroke-width="2"/>\n'
        f'<rect x="28" y="412" width="102" height="32" fill="{DARK}" stroke="{LINE_STRONG}" stroke-width="2"/>\n'
        f'<text x="79" y="434" text-anchor="middle" font-family="{MONO}" '
        f'font-size="15" font-weight="700" letter-spacing="2" fill="{MUTE}">NO IMAGE</text>\n'
        f'<polygon points="{CARD}" fill="none" stroke="{LINE_STRONG}" stroke-width="3"/>\n'
        "</svg>\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="verify files exist and parse; write nothing")
    args = ap.parse_args()

    items = json.loads(SEED.read_text(encoding="utf-8"))["items"]
    out: Path = args.out
    names = [f"{i['sku']}.svg" for i in items] + ["placeholder.svg"]

    if args.check:
        bad = 0
        for name in names:
            try:
                ET.parse(out / name)
            except (OSError, ET.ParseError) as e:
                print(f"FAIL {name}: {e}", file=sys.stderr)
                bad += 1
        print(f"checked {len(names)} files, {bad} failing")
        return 1 if bad else 0

    out.mkdir(parents=True, exist_ok=True)
    for item in items:
        svg = render(item)
        ET.fromstring(svg)
        (out / f"{item['sku']}.svg").write_text(svg, encoding="utf-8")
    (out / "placeholder.svg").write_text(placeholder(), encoding="utf-8")
    print(f"wrote {len(items)} product images + placeholder to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
