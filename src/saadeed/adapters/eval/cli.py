"""أوامر التقييم: `saadeed eval build-bank` و`saadeed eval run` و`saadeed eval freeze`."""

from __future__ import annotations

import hashlib
import json
from collections import Counter

import typer

eval_app = typer.Typer(help="منظومة التقييم (البروتوكول المسجّل مسبقًا)")


@eval_app.command("build-bank")
def build_bank_cmd() -> None:
    """يبني بنك الاختبار: الحالات البرمجية + المصوغة، ثم التقسيم والنصوص الحاملة (بذرة 70)."""
    from saadeed.adapters.bootstrap import ROOT
    from saadeed.adapters.eval.bank import (
        CRITICAL,
        Expected,
        TestCase,
        build_carriers,
        expected_for,
        save_bank,
        split_cases,
    )
    from saadeed.adapters.eval.generators import hadith_cases, quran_cases
    from saadeed.adapters.eval.runner import BANK_DIR
    from saadeed.adapters.factory import build_engine
    from saadeed.text.normalize import normalize

    eng = build_engine()
    cases = quran_cases(eng) + hadith_cases(eng)
    doc = json.loads((ROOT / "eval" / "bank" / "drafted_v1.json").read_text(encoding="utf-8"))
    counters: Counter[str] = Counter()
    warnings: list[str] = []
    for d in doc["cases"]:
        cat = d["category"]
        counters[cat] += 1
        exp = Expected(**d["expected"]) if d.get("expected") else expected_for(cat)
        case = TestCase(
            case_id=f"{cat}-d{counters[cat]:02d}",
            category=cat,
            critical=cat in CRITICAL
            or (
                cat == "OF"
                and exp.action in ("REFER", "CORRECT_FROM_SOURCE")
                or cat == "OF"
                and exp.reason == "NOT_FOUND"
            ),
            surface=d["surface"],
            claim_text=d["claim_text"],
            expected=exp,
            label_source="drafted",
            reviewer=doc.get("reviewer"),
            notes=d.get("notes"),
        )
        # فحص آلي لصلاحية الحالات المختلقة وما خارج الستة: يجب ألّا توجد في المخزن.
        if cat in ("H7", "H8b"):
            q = normalize(case.claim_text)
            if any(eng.hadith.index.book_contains(b, q) for b in eng.hadith.index.sources):
                warnings.append(f"{case.case_id}: موجود في الكتب الستة، فاستُبعد")
                continue
        cases.append(case)
    split_cases(cases)
    carriers = build_carriers(cases)
    save_bank(BANK_DIR, cases, carriers)
    by = Counter((c.split, c.category) for c in cases)
    typer.echo(
        f"الحالات: {len(cases)} · النصوص الحاملة: {len(carriers)} (dev {sum(1 for k in carriers if k.split == 'dev')} · test {sum(1 for k in carriers if k.split == 'test')})"
    )
    typer.echo(
        " · ".join(
            f"{cat}:{by[('dev', cat)]}/{by[('test', cat)]}" for cat in sorted({c for _, c in by})
        )
    )
    for w in warnings:
        typer.echo(f"⚠ {w}")


@eval_app.command("run")
def run_cmd(
    split: str = typer.Option("dev", help="dev أو test"),
    systems: str = typer.Option("saadeed,B0", help="saadeed,B0,B1"),
    k: int = typer.Option(1, help="عدد التشغيلات (للاتساق)"),
    replay: bool = typer.Option(False, help="إعادة من التسجيلات دون مفتاح (J4)"),
    overreach: bool = typer.Option(False, help="تفعيل فحص التجاوز"),
    limit: int | None = typer.Option(None, help="أول N نصوص حاملة فقط"),
    name: str | None = typer.Option(None, help="اسم ملف التقرير"),
) -> None:
    """يشغّل التقييم ويحفظ التقرير في eval/reports/."""
    from saadeed.adapters.eval.runner import run_eval, save_report
    from saadeed.adapters.factory import build_engine

    res = run_eval(
        build_engine(),
        split,
        systems.split(","),
        k=k,
        replay=replay,
        overreach=overreach,
        limit=limit,
        log=typer.echo,
    )
    jp, mp = save_report(res, name)
    typer.echo(mp.read_text(encoding="utf-8"))
    typer.echo(f"\nحُفظ: {jp}\n      {mp}")


@eval_app.command("extend-bank")
def extend_bank_cmd() -> None:
    """يضيف فئتي v2.5 (Q8، Q9) في نصوص حاملة جديدة، ولا يمس حالات v1 ونصوصها (البروتوكول §١٢ بند 9)."""
    from saadeed.adapters.eval.bank import build_carriers, load_bank, save_bank, split_cases
    from saadeed.adapters.eval.generators import quran_v25_cases
    from saadeed.adapters.eval.runner import BANK_DIR
    from saadeed.adapters.factory import build_engine

    cases, carriers = load_bank(BANK_DIR)
    new_cats = {"Q8", "Q9"}
    old_ids = {c.case_id for c in cases if c.category in new_cats}
    cases = [c for c in cases if c.category not in new_cats]
    carriers = [k for k in carriers if not set(k.case_ids) & old_ids]
    new = quran_v25_cases(build_engine())
    split_cases(new)
    added = build_carriers(new)
    for n, k in enumerate(added, start=1):
        cid = f"{k.split}-v25-{n:02d}"
        for c in new:
            if c.carrier_id == k.carrier_id:
                c.carrier_id = cid
        k.carrier_id = cid
    save_bank(BANK_DIR, cases + new, carriers + added)
    by = Counter((c.category, c.split) for c in new)
    typer.echo(f"أُضيفت {len(new)} حالة في {len(added)} نصوص حاملة: {dict(sorted(by.items()))}")


@eval_app.command("freeze")
def freeze_cmd() -> None:
    """يحسب بصمة SHA-256 لمجموعة test (البروتوكول §١١)."""
    from saadeed.adapters.eval.runner import BANK_DIR

    for f in ("cases.jsonl", "carriers.jsonl"):
        h = hashlib.sha256((BANK_DIR / f).read_bytes()).hexdigest()
        typer.echo(f"{f}: {h}")
