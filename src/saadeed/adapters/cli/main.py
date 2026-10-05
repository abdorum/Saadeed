"""محوّل سطر الأوامر (FR-70): أول محوّل دخول، وأقربه لخبرة محمد."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from saadeed.domain.models import ReviewReport

app = typer.Typer(add_completion=False, help="سديد: مراجِع ما قبل النشر للمسودات الدعوية العربية")
data_app = typer.Typer(help="بناء بيانات المصادر")
app.add_typer(data_app, name="data")


def render_text(report: ReviewReport, draft: str) -> str:
    """ملخص نصي للتقرير: خريطة الثغور ثم أخطر المواضع."""
    s = report.summary
    lines = [
        "═" * 60,
        f"خريطة الثغور — {s.total_claims} ادعاءً في {report.draft.word_count} كلمة",
        "═" * 60,
        f"✅ تؤيده المصادر: {s.by_bucket['SUPPORTED_BY_SOURCES']}   "
        f"⚠️ يتطلب تحققًا: {s.by_bucket['NEEDS_VERIFICATION']}   "
        f"🔵 إحالة: {s.by_bucket['REFER']}   ⏸️ لم يُفحص: {s.by_bucket['NOT_CHECKED']}",
    ]
    if report.draft_map:
        counts: dict[str, int] = {}
        for e in report.draft_map:
            counts[e.kind_ar] = counts.get(e.kind_ar, 0) + 1
        with_findings = sum(1 for e in report.draft_map if e.finding_ids)
        lines.append(
            f"🗺️ خريطة المسودة ({len(report.draft_map)} جملة، في {with_findings} منها ادعاء مفحوص): "
            + " · ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
        )
    lines.append("")
    by_id = {f.id: f for f in report.findings}
    order = report.top_risks + [f.id for f in report.findings if f.id not in report.top_risks]
    for fid in order:
        f = by_id[fid]
        icon = {
            "SUPPORTED_BY_SOURCES": "✅",
            "NEEDS_VERIFICATION": "⚠️",
            "REFER": "🔵",
            "NOT_CHECKED": "⏸️",
        }[f.bucket.value]
        lines.append(f"{icon} [{f.id}] {f.claim.type.label_ar} — «{f.claim.text[:90]}»")
        lines.append(
            f"   حالة الدليل: {f.evidence_status.label_ar} · الأثر: {f.severity.label_ar} · الإجراء: {f.action.label_ar} · ({f.rule_id})"
        )
        lines.append(f"   شرح سديد: {f.explanation}")
        if f.action.value != "NONE":
            lines.append(f"   الخطوة التالية: {f.next_step}")
        for ev in f.evidence:
            if ev.text:
                if ev.highlight and ev.highlight[0].end - ev.highlight[0].start < len(ev.text):
                    h = ev.highlight[0]
                    lo, hi = max(0, h.start - 30), min(len(ev.text), h.end + 30)
                    shown = (
                        ("…" if lo else "") + ev.text[lo:hi] + ("…" if hi < len(ev.text) else "")
                    )
                else:
                    shown = ev.text[:160] + ("…" if len(ev.text) > 160 else "")
                lines.append(f"   📖 {ev.ref.citation} [{ev.role.label_ar}]: {shown}")

            elif ev.ref.url:
                lines.append(f"   🔗 {ev.ref.citation}: {ev.ref.url}")
            changes = [d for d in ev.diff if d.op != "equal"]
            for d in changes[:4]:
                lines.append(f"      ↔ المسودة «{d.draft}» | المصحف «{d.source}»")
        if f.suggestion:
            lines.append(f"   ✍️ اقتراح صياغة (مولَّد، راجعه): {f.suggestion}")
        for n in f.notes:
            lines.append(f"   ملاحظة: {n}")
        lines.append("")
    m = report.meta
    lines.append(
        f"— النموذج: {m.llm} · نداءات: {m.llm_calls} · رموز: {m.prompt_tokens}+{m.completion_tokens} · "
        f"الزمن: {m.duration_ms} مللي ثانية · المرجعية: {m.manifest.id} ({m.manifest.sha256[:12]})"
    )
    for w in m.warnings:
        lines.append(f"⚠ {w}")
    lines.append(
        "سديد أداة مراجعة مدعومة بالذكاء الاصطناعي، وليست فتوى. وعدم التنبيه على شيء لا يعني صحته."
    )
    return "\n".join(lines)


@app.command()
def review(
    file: Path = typer.Argument(..., help="ملف نصي فيه المسودة، أو - للقراءة من المدخل القياسي"),
    out: Path | None = typer.Option(None, "--out", "-o", help="حفظ التقرير JSON في ملف"),
    provider: str | None = typer.Option(None, help="groq أو gemini أو none (المرور الحتمي وحده)"),
    model: str | None = typer.Option(None, help="اسم النموذج لدى المزود"),
    cache: str = typer.Option("use", help="use · replay · off"),
    overreach: bool = typer.Option(False, help="تفعيل فحص التجاوز (FR-36، تجريبي)"),
    as_json: bool = typer.Option(False, "--json", help="اطبع JSON بدل الملخص"),
) -> None:
    """راجِع مسودة: `saadeed review khutbah.txt`"""
    from saadeed.adapters.factory import build_engine, build_llm, cached
    from saadeed.application.review_draft import DraftError, ReviewConfig

    text = sys.stdin.read() if str(file) == "-" else file.read_text(encoding="utf-8")
    engine = build_engine()
    llm = (
        cached(build_llm(provider, model) if cache != "replay" else None, mode=cache)
        if provider != "none"
        else None
    )
    reviewer = engine.reviewer(llm, ReviewConfig(enable_overreach=overreach))
    try:
        report = reviewer.review(text)
    except DraftError as e:
        typer.echo(f"خطأ في المسودة: {e}", err=True)
        raise typer.Exit(2) from e
    payload = report.model_dump(mode="json")
    if out:
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=1))
    else:
        typer.echo(render_text(report, text))


@data_app.command("build")
def data_build(fetch: bool = typer.Option(True, help="تنزيل الملفات الخام الناقصة أولًا")) -> None:
    """ينزّل المصادر الخام ويبني الملفات المعالجة ويطبع بصماتها."""
    from saadeed.adapters.bootstrap import DATA_DIR
    from saadeed.adapters.sources.build import build_processed, fetch_raw

    if fetch:
        for p in fetch_raw(DATA_DIR):
            typer.echo(f"نُزّل: {p}")
    for name, (n, h) in build_processed(DATA_DIR).items():
        typer.echo(f"{name}: {n} · sha256 {h[:16]}")


@app.command()
def coverage() -> None:
    """ما يغطيه سديد، من ملف المرجعية (FR-66)."""
    from saadeed.adapters.factory import build_engine

    eng = build_engine()
    for s in eng.sources.coverage.sources:
        typer.echo(
            f"- {s.name_ar} [{s.role.label_ar}] · {s.count} · {s.version} · {s.license} · {s.review_status}"
        )
    m = eng.sources.manifest
    typer.echo(f"ملف المرجعية: {m.id} · sha256 {m.sha256[:16]}")


def _register_eval() -> None:
    try:
        from saadeed.adapters.eval.cli import eval_app
    except ImportError:  # قبل بناء منظومة التقييم
        return
    app.add_typer(eval_app, name="eval")


_register_eval()

if __name__ == "__main__":
    app()
