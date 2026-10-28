"""الشعار: «سديد» بخط Aref Ruqaa Bold، مشكَّلًا بـ HarfBuzz ومحوَّلًا إلى مسارات (لا يحتاج عرضه إلى الخط).

    uv run --with fonttools --with uharfbuzz python logo.py ArefRuqaa-Bold.ttf ../logo.svg

والخط من https://github.com/google/fonts/tree/main/ofl/arefruqaa (SIL OFL).
"""
import sys

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

font_path, out = sys.argv[1], sys.argv[2]
blob = hb.Blob.from_file_path(font_path)
face = hb.Face(blob)
font = hb.Font(face)
buf = hb.Buffer()
buf.add_str("سديد")
buf.guess_segment_properties()
hb.shape(font, buf, {"kern": True, "liga": True})

tt = TTFont(font_path)
gs = tt.getGlyphSet()
order = tt.getGlyphOrder()
upem = tt["head"].unitsPerEm

paths, x = [], 0
xmin, xmax, ymin, ymax = 1e9, -1e9, 1e9, -1e9
for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
    name = order[info.codepoint]
    pen = SVGPathPen(gs)
    ox, oy = x + pos.x_offset, pos.y_offset
    gs[name].draw(TransformPen(pen, (1, 0, 0, -1, ox, -oy)))  # y-down for SVG
    d = pen.getCommands()
    if d:
        paths.append(d)
    bp = BoundsPen(gs)
    gs[name].draw(TransformPen(bp, (1, 0, 0, -1, ox, -oy)))
    if bp.bounds:
        a, b, c, d2 = bp.bounds
        xmin, ymin, xmax, ymax = min(xmin, a), min(ymin, b), max(xmax, c), max(ymax, d2)
    x += pos.x_advance

w, h = xmax - xmin, ymax - ymin
S = 512                         # square mark
inner = 0.70 * S                # wordmark width inside the mark
k = inner / w
tx = (S - w * k) / 2 - xmin * k
ty = (S - h * k) / 2 - ymin * k + 0.02 * S   # optical centring (Ruqaa sits low)
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}" width="{S}" height="{S}" role="img" aria-labelledby="t">
  <title id="t">سديد</title>
  <rect width="{S}" height="{S}" rx="{S*0.22:.0f}" fill="#1F3A63"/>
  <rect x="{S*0.055:.1f}" y="{S*0.055:.1f}" width="{S*0.89:.1f}" height="{S*0.89:.1f}" rx="{S*0.18:.0f}" fill="none" stroke="#B8913F" stroke-width="{S*0.008:.1f}" opacity=".85"/>
  <g transform="translate({tx:.2f} {ty:.2f}) scale({k:.5f})" fill="#DCC386">
    {"".join(f'<path d="{p}"/>' for p in paths)}
  </g>
</svg>
'''
open(out, "w", encoding="utf-8").write(svg)
print("glyphs:", len(buf.glyph_infos), "bbox:", round(w), round(h), "bytes:", len(svg))
