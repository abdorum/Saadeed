"""مقارنة ميدانية: سديد مقابل النموذج العام وحده (B0) على خطب حقيقية من الألوكة.

الاستعمال:
    uv run python scripts/field_compare.py                      # البنك الافتراضي
    uv run python scripts/field_compare.py --bank ملف.json

المخرجات:
- eval/reports/field_alukah_v2.json       المخرجات الخام للنظامين لكل خطبة.
- eval/field/review_alukah_v2.json        ملف المراجعة البشرية: كل تنبيه من النظامين، وخانة حكم المراجع.
- docs/التحقق-العلمي.md                   جدول النتائج يُكتب بين علامتي «نتائج-ميدانية».

المقاييس هنا لا تحتاج إجابات معدّة مسبقًا، لأنها تُتحقق آليًا من المصادر نفسها:
- **المراجع المختلقة:** مرجع ذكره النظام (سورة وآية، أو كتاب حديث) ونص الخطبة ليس فيه.
- **الآيات المخالفة للمصحف:** آية بين ﴿﴾ يخالف نصها نص المصحف، ومن نبّه عليها من النظامين.
- **التغطية:** الآيات والأحاديث المقتبسة في الخطبة، وكم منها فحصه كل نظام بمرجع.
وصحة كل تنبيه تحكم فيها المراجعة البشرية في ملف المراجعة.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saadeed.adapters.eval.metrics import CitationChecker  # noqa: E402
from saadeed.adapters.eval.systems import run_baseline, run_saadeed  # noqa: E402
from saadeed.adapters.factory import build_engine, build_llm, cached  # noqa: E402
from saadeed.text.markers import scan  # noqa: E402

BANK = ROOT / "eval" / "field" / "bank_alukah_v2.json"
RAW = ROOT / "eval" / "reports" / "field_alukah_v2.json"
REVIEW = ROOT / "eval" / "field" / "review_alukah_v2.json"
DOC = ROOT / "docs" / "التحقق-العلمي.md"
RECORDINGS = ROOT / "eval" / "recordings"
START, END = "<!-- نتائج-ميدانية:بداية -->", "<!-- نتائج-ميدانية:نهاية -->"


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def quoted_spans(text: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """الآيات والأحاديث المقتبسة في الخطبة بعلاماتها (حتميًا، دون نموذج)."""
    ayat, hadith = [], []
    for m in scan(text):
        (ayat if m.kind == "quran" else hadith).append((m.start, m.end))
    return ayat, hadith


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", type=Path, default=BANK)
    ap.add_argument("--score", action="store_true", help="احسب الدقة من أحكام المراجع البشري")
    args = ap.parse_args()
    if args.score:
        return score()
    bank = json.loads(args.bank.read_text(encoding="utf-8"))
    khutab = [k for k in bank["khutab"] if k.get("text", "").strip()]
    if not khutab:
        sys.exit("البنك فارغ: املأ نصوص الخطب في " + str(args.bank))

    engine = build_engine()
    llm = cached(build_llm(), mode="use", cache_dir=RECORDINGS)
    checker = CitationChecker(engine)
    rows, raw, review = [], [], []
    for k in khutab:
        text = k["text"].replace("\r\n", "\n")
        print(f"{k['id']} {k['title'][:40]} …", flush=True)
        t0 = time.monotonic()
        sad = run_saadeed(engine, llm, text, overreach=False, live=True)
        b0 = run_baseline(engine, llm, text)
        ayat, hadith = quoted_spans(text)
        # الآيات المخالفة للمصحف: الحقيقة من المصحف نفسه (مطابقة حتمية)، ثم: من نبّه عليها؟
        bad_ayat = [
            p.span
            for p in sad.preds
            if p.claim_type == "QURAN_QUOTE" and p.reason in ("TEXT_MISMATCH", "NOT_QURAN")
        ]
        row = {"id": k["id"], "title": k["title"], "words": len(text.split())}
        for name, run in (("saadeed", sad), ("B0", b0)):
            verdicts = [checker.check_pred(p) for p in run.preds]
            sourced = [p for p, v in zip(run.preds, verdicts, strict=True) if v == "ok"]
            row[name] = {
                "error": run.error,
                "findings": len(run.preds),
                "flagged": sum(p.action != "NONE" for p in run.preds),
                "with_verified_source": len(sourced),
                "fabricated": verdicts.count("fabricated"),
                "unverifiable": verdicts.count("unverifiable"),
                "ayat_covered": sum(any(overlaps(a, p.span) for p in sourced) for a in ayat),
                "hadith_covered": sum(any(overlaps(h, p.span) for p in sourced) for h in hadith),
                "bad_ayat_flagged": sum(
                    any(overlaps(b, p.span) and p.action != "NONE" for p in run.preds)
                    for b in bad_ayat
                ),
                "latency_ms": run.latency_ms,
                "tokens": run.prompt_tokens + run.completion_tokens,
            }
            for p, v in zip(run.preds, verdicts, strict=True):
                review.append(
                    {
                        "khutba": k["id"],
                        "system": name,
                        "quote": p.quote[:300],
                        "type": p.claim_type,
                        "status": p.evidence_status,
                        "action": p.action,
                        "source": p.source
                        or "؛ ".join(f"{e['source_id']}:{e['item_id']}" for e in p.evidence[:2]),
                        "citation_check": v,
                        "reviewer_verdict": None,
                        "reviewer_note": "",
                    }
                )
        row["ayat_quoted"], row["hadith_quoted"], row["bad_ayat"] = (
            len(ayat),
            len(hadith),
            len(bad_ayat),
        )
        rows.append(row)
        raw.append({"khutba": k, "saadeed": sad.model_dump(), "B0": b0.model_dump()})
        print(f"   {time.monotonic() - t0:.0f}s", flush=True)

    meta = {
        "bank": str(args.bank.resolve().relative_to(ROOT)) if args.bank.resolve().is_relative_to(ROOT) else args.bank.name,
        "source": bank.get("source"),
        "selection": bank.get("selection"),
        "model": llm.model_id,
        "date": time.strftime("%Y-%m-%d %H:%M"),
    }
    RAW.write_text(
        json.dumps({"meta": meta, "rows": rows, "raw": raw}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    REVIEW.write_text(
        json.dumps(
            {
                "about": "ملف المراجعة البشرية: لكل تنبيه ضع reviewer_verdict = correct أو wrong أو unsure، وملاحظة إن لزم. ثم: uv run python scripts/field_compare.py --score",
                "items": review,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    write_doc(meta, rows)
    print(f"✓ {RAW.relative_to(ROOT)} · {REVIEW.relative_to(ROOT)} · {DOC.relative_to(ROOT)}")


def write_doc(meta: dict, rows: list[dict]) -> None:
    def tot(sys_: str, key: str) -> int:
        return sum(r[sys_][key] or 0 for r in rows if not r[sys_]["error"])

    ay, hd, bad = (sum(r[k] for r in rows) for k in ("ayat_quoted", "hadith_quoted", "bad_ayat"))
    lines = [
        START,
        f"- **البنك:** `{meta['bank']}` · **المصدر:** {meta['source']} · **عدد الخطب:** {len(rows)} · **الكلمات:** {sum(r['words'] for r in rows):,}",
        f"- **النموذج:** `{meta['model']}` للنظامين · **التاريخ:** {meta['date']}",
        f"- **الاختيار:** {meta['selection']}",
        "",
        "| المقياس | سديد | النموذج وحده (B0) |",
        "|---|---|---|",
        f"| المراجع المختلقة (مرجع ذكره النظام ولا يحمل نص الخطبة) | **{tot('saadeed', 'fabricated')}** | **{tot('B0', 'fabricated')}** |",
        f"| تنبيهات بمرجع تحقّقنا منه في المصدر | {tot('saadeed', 'with_verified_source')} | {tot('B0', 'with_verified_source')} |",
        f"| مراجع لا يمكن التحقق منها | {tot('saadeed', 'unverifiable')} | {tot('B0', 'unverifiable')} |",
        f"| الآيات المقتبسة بين ﴿﴾ التي فُحصت بمرجع (من {ay}) | {tot('saadeed', 'ayat_covered')} | {tot('B0', 'ayat_covered')} |",
        f"| الأحاديث المقتبسة التي فُحصت بمرجع (من {hd}) | {tot('saadeed', 'hadith_covered')} | {tot('B0', 'hadith_covered')} |",
        f"| آيات يخالف نصها المصحف ونُبّه عليها (من {bad}) | {tot('saadeed', 'bad_ayat_flagged')} | {tot('B0', 'bad_ayat_flagged')} |",
        f"| كل الملاحظات / ما يطلب إجراءً | {tot('saadeed', 'findings')} / {tot('saadeed', 'flagged')} | {tot('B0', 'findings')} / {tot('B0', 'flagged')} |",
        f"| الزمن الوسيط للخطبة | {sorted(r['saadeed']['latency_ms'] for r in rows)[len(rows) // 2] / 1000:.0f} ث | {sorted(r['B0']['latency_ms'] for r in rows)[len(rows) // 2] / 1000:.0f} ث |",
        "",
        "| # | الخطبة | الكلمات | آيات | أحاديث | مختلق: سديد / B0 | ملاحظات: سديد / B0 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['title']} | {r['words']} | {r['ayat_quoted']} | {r['hadith_quoted']} | {r['saadeed']['fabricated']} / {r['B0']['fabricated']} | {r['saadeed']['findings']} / {r['B0']['findings']} |"
        )
    lines.append(END)
    doc = DOC.read_text(encoding="utf-8")
    a, b = doc.find(START), doc.find(END)
    doc = (
        doc[:a] + "\n".join(lines) + doc[b + len(END) :]
        if a >= 0 and b >= 0
        else doc + "\n" + "\n".join(lines) + "\n"
    )
    DOC.write_text(doc, encoding="utf-8")


def score() -> None:
    """صحة التنبيه من أحكام المراجع: ما حكم عليه بـ correct من كل ما حكم عليه."""
    items = json.loads(REVIEW.read_text(encoding="utf-8"))["items"]
    lines = [
        "",
        "**المراجعة البشرية** (حكم المراجع على كل تنبيه في `eval/field/review_alukah_v2.json`):",
        "",
        "| النظام | حُكم عليه | صحيح | خطأ | غير متيقن | صحة التنبيه |",
        "|---|---|---|---|---|---|",
    ]
    for name in ("saadeed", "B0"):
        mine = [i for i in items if i["system"] == name and i["action"] != "NONE"]
        v = [i["reviewer_verdict"] for i in mine if i["reviewer_verdict"]]
        ok, bad, uns = v.count("correct"), v.count("wrong"), v.count("unsure")
        prec = f"{100 * ok / (ok + bad):.1f}%" if ok + bad else "—"
        label = "سديد" if name == "saadeed" else "النموذج وحده (B0)"
        lines.append(f"| {label} | {len(v)} من {len(mine)} | {ok} | {bad} | {uns} | **{prec}** |")
    block = "\n".join(lines)
    doc = DOC.read_text(encoding="utf-8")
    a, b = doc.find(START), doc.find(END)
    if a < 0 or b < 0:
        sys.exit("شغّل المقارنة أولًا")
    body = doc[a:b].split("\n**المراجعة البشرية**")[0].rstrip()
    DOC.write_text(doc[:a] + body + "\n" + block + "\n" + doc[b:], encoding="utf-8")
    print(block)


if __name__ == "__main__":
    main()
