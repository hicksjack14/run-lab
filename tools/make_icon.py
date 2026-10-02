"""Draw the Run Lab app icon: the lime + coral rings from the logo, with the replay marker dot on the outer ring.

Needs Pillow (the system python has it):   python3 tools/make_icon.py
Writes web/icons/: icon.svg, icon-1024.png (upload this one to Strava), icon-512.png, apple-touch-icon.png, favicon-32.png.
Colours come from the same OKLCH tokens as the app's CSS.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"


def oklch_hex(L, C, h):
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    l_, m_, s_ = L + 0.3963377774 * a + 0.2158037573 * b, L - 0.1055613458 * a - 0.0638541728 * b, L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    enc = lambda v: round(255 * min(1, max(0, 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)))
    return "#%02x%02x%02x" % tuple(enc(v) for v in rgb)


BG, LIME, CORAL, CREAM = oklch_hex(0.165, 0.012, 55), oklch_hex(0.87, 0.16, 112), oklch_hex(0.72, 0.19, 33), oklch_hex(0.96, 0.02, 85)
# geometry on a 1024 grid: (outer radius, inner radius) of each ring, and the marker dot on the lime ring at -40 degrees
LIME_RING, CORAL_RING = (392, 296), (244, 160)
MARK_R, MARK_ANGLE, MARK_DOT, MARK_EDGE = 344, -40, 58, 16


def draw(size):
    k = 4                                   # draw 4x bigger, then shrink for smooth edges
    S = size * k
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)
    c, u = S / 2, S / 1024
    for (outer, inner), colour in ((LIME_RING, LIME), (CORAL_RING, CORAL)):
        d.ellipse([c - outer * u, c - outer * u, c + outer * u, c + outer * u], fill=colour)
        d.ellipse([c - inner * u, c - inner * u, c + inner * u, c + inner * u], fill=BG)
    mx, my = c + MARK_R * u * math.cos(math.radians(MARK_ANGLE)), c + MARK_R * u * math.sin(math.radians(MARK_ANGLE))
    for r, colour in ((MARK_DOT + MARK_EDGE, BG), (MARK_DOT, CREAM)):
        d.ellipse([mx - r * u, my - r * u, mx + r * u, my + r * u], fill=colour)
    return img.resize((size, size), Image.LANCZOS)


def svg():
    c = 512
    mx, my = c + MARK_R * math.cos(math.radians(MARK_ANGLE)), c + MARK_R * math.sin(math.radians(MARK_ANGLE))
    ring = lambda o, i, col: f'<circle cx="{c}" cy="{c}" r="{(o + i) / 2}" fill="none" stroke="{col}" stroke-width="{o - i}"/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-label="Run Lab">'
            f'<rect width="1024" height="1024" fill="{BG}"/>{ring(*LIME_RING, LIME)}{ring(*CORAL_RING, CORAL)}'
            f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="{MARK_DOT + MARK_EDGE}" fill="{BG}"/><circle cx="{mx:.1f}" cy="{my:.1f}" r="{MARK_DOT}" fill="{CREAM}"/></svg>\n')


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon-1024.png", 1024), ("icon-512.png", 512), ("apple-touch-icon.png", 180), ("favicon-32.png", 32)):
        draw(size).save(OUT / name)
    (OUT / "icon.svg").write_text(svg())
    print(f"Wrote icons to {OUT} (colours: bg {BG}, lime {LIME}, coral {CORAL})")
