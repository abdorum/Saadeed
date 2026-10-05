"""يبني معاينة ثابتة من صفحة واحدة: الأمثلة الثلاثة والتغطية والنتائج مضمَّنة، بلا خادم.

الاستعمال: uv run python scripts/build_preview.py  ← build/preview/saadeed.html
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def main() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    body = re.sub(r'<script src="assets/app.js"></script>', "", body)
    body = body.replace(' · <a href="v1/docs">الواجهة البرمجية</a>', "")
    fonts = re.search(r'<link rel="stylesheet" href="https://fonts[^>]+>', html).group(0)
    index = json.loads((WEB / "examples" / "index.json").read_text(encoding="utf-8"))
    data = {
        "examples": [
            json.loads((WEB / "examples" / f"{e['id']}.json").read_text(encoding="utf-8"))
            for e in index
        ],
        "coverage": json.loads((WEB / "data" / "coverage.json").read_text(encoding="utf-8")),
        "results": json.loads((WEB / "data" / "results.json").read_text(encoding="utf-8")),
    }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    css = (WEB / "assets" / "app.css").read_text(encoding="utf-8")
    js = (WEB / "assets" / "app.js").read_text(encoding="utf-8")
    page = (
        "<title>سديد</title>\n"
        + fonts
        + "\n<style>\n"
        + css
        + "\n</style>\n<div dir=\"rtl\" lang=\"ar\">"
        + body
        + "</div>\n<script>window.SAADEED_DATA = "
        + blob
        + ";</script>\n<script>\n"
        + js
        + "\n</script>\n"
    )
    out = ROOT / "build" / "preview" / "saadeed.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(out, f"{len(page.encode()) // 1024} KB")


if __name__ == "__main__":
    main()
