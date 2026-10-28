"""يرسم ملف HTML أو SVG محليًا إلى PNG بـ Chromium.

    uv run --with playwright python render.py IN OUT WIDTH HEIGHT [SCALE] [transparent]

(مرة واحدة قبلها: uv run --with playwright playwright install chromium)
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

src, out, w, h = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
scale = float(sys.argv[5]) if len(sys.argv) > 5 else 2
transparent = len(sys.argv) > 6 and sys.argv[6] == "transparent"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
    pg.goto(Path(src).resolve().as_uri(), wait_until="networkidle")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(400)
    el = pg.query_selector("#canvas") or pg.query_selector("svg")
    el.screenshot(path=out, omit_background=transparent)
    b.close()
print("ok", out)
