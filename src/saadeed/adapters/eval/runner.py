"""مشغّل التقييم (FR-81–83): الأنظمة × التشغيلات على نصوص حاملة، مع التسجيل والإعادة."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saadeed.adapters.bootstrap import ROOT
from saadeed.adapters.eval.bank import Carrier, TestCase, load_bank
from saadeed.adapters.eval.metrics import compute
from saadeed.adapters.eval.systems import SystemRun, run_baseline, run_saadeed
from saadeed.adapters.factory import Engine, build_llm, cached

BANK_DIR = ROOT / "eval" / "bank" / "v1"
RECORDINGS = ROOT / "eval" / "recordings"
REPORTS = ROOT / "eval" / "reports"


def run_eval(
    engine: Engine,
    split: str,
    systems: list[str],
    k: int = 1,
    replay: bool = False,
    overreach: bool = False,
    limit: int | None = None,
    log=print,
) -> dict[str, Any]:
    cases, carriers = load_bank(BANK_DIR)
    carriers = [c for c in carriers if c.split == split]
    if limit:
        carriers = carriers[:limit]
    keep = {c.carrier_id for c in carriers}
    cases = [c for c in cases if c.carrier_id in keep]
    base_llm = None if replay else build_llm()
    runs: dict[str, list[SystemRun]] = {s: [] for s in systems}
    for run in range(1, k + 1):
        salt = "" if run == 1 else f"run{run}"
        llm = cached(base_llm, mode="replay" if replay else "use", salt=salt, cache_dir=RECORDINGS)
        if replay:
            llm.model_id  # noqa: B018 — للتأكد من التهيئة
        for carrier in carriers:
            for system in systems:
                t0 = time.monotonic()
                try:
                    if system == "saadeed":
                        r = run_saadeed(engine, llm, carrier.text, overreach)
                    elif system == "B1":
                        r = run_saadeed(engine, llm, carrier.text, overreach, quran_mode="llm")
                    elif system == "B0":
                        if run > 1:
                            continue  # الاتساق يُقاس لسديد؛ وB0 تشغيل واحد
                        r = run_baseline(engine, llm, carrier.text)
                    else:
                        raise ValueError(system)
                except Exception as e:  # تشغيل فاشل يُسجَّل ولا يوقف التقييم
                    r = SystemRun(
                        system=system,
                        carrier_id=carrier.carrier_id,
                        run=run,
                        error=f"{type(e).__name__}: {e}",
                    )
                r.system, r.carrier_id, r.run = system, carrier.carrier_id, run
                runs[system].append(r)
                log(
                    f"[{system} · run {run}] {carrier.carrier_id}: {len(r.preds)} ملاحظة · {int((time.monotonic() - t0) * 1000)} ms"
                    + (f" · ⚠ {r.error[:80]}" if r.error else "")
                )
    metrics = compute(cases, runs, engine)
    metrics.update(
        split=split,
        k=k,
        systems=systems,
        overreach=overreach,
        replay=replay,
        model=(base_llm.model_id if base_llm else "replay"),
        prompt_versions=engine.prompts.versions(),
        manifest=engine.sources.manifest.stamp.model_dump(),
        carriers=len(carriers),
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    return {
        "metrics": metrics,
        "runs": {s: [r.model_dump() for r in rs] for s, rs in runs.items()},
        "cases": [c.model_dump() for c in cases],
    }


def save_report(result: dict[str, Any], name: str | None = None) -> tuple[Path, Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    m = result["metrics"]
    stem = (
        name
        or f"{m['split']}_{'-'.join(m['systems'])}_k{m['k']}_{datetime.now().strftime('%Y%m%d-%H%M')}"
    )
    jp = REPORTS / f"{stem}.json"
    mp = REPORTS / f"{stem}.md"
    jp.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    mp.write_text(render_markdown(m), encoding="utf-8")
    return jp, mp


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def render_markdown(m: dict[str, Any]) -> str:
    sys_names = list(m["systems"].keys()) if isinstance(m["systems"], dict) else m["systems"]
    S = m["systems"]
    lines = [
        f"# تقرير التقييم — {m['split']} · k={m['k']}",
        "",
        f"- **النموذج:** {m['model']} · **التعليمات:** {m['prompt_versions']} · **المرجعية:** {m['manifest']['id']} ({m['manifest']['sha256'][:12]})",
        f"- **الحالات:** {m['n_cases']} في {m['carriers']} نصًا حاملًا · **فحص التجاوز:** {'مفعّل' if m['overreach'] else 'مطفأ'} · **الإعادة:** {'نعم' if m['replay'] else 'لا'}",
        f"- **التاريخ:** {m['generated_at']}",
        "",
        "## الجدول الرئيسي (البروتوكول §١٣)",
        "",
        "| المقياس | " + " | ".join(sys_names) + " |",
        "|---|" + "---|" * len(sys_names),
    ]
    rows = [
        ("الكشف", lambda s: f"{_pct(s['detection'])} {s['detection_ci'] or ''}"),
        ("الكشف الصارم (بالسبب)", lambda s: _pct(s["detection_strict"])),
        ("الإنذار الكاذب", lambda s: f"{_pct(s['false_alarm'])} {s['false_alarm_ci'] or ''}"),
        ("صحة التنبيه", lambda s: _pct(s["precision"])),
        ("الحرج الفائت", lambda s: f"{s['critical_missed']} من {s['critical_total']}"),
        ("الاستشهادات المختلقة", lambda s: str(s["fabricated_citations"])),
        ("تأكيد المختلق (H7)", lambda s: str(s["fabricated_confirmed_H7"])),
        ("الإسناد غير القابل للتحقق (O1، وصفي)", lambda s: str(s["unverifiable_sourcing_O1"])),
        ("الاتهام الكاذب (H8a وH8b)", lambda s: str(s["false_accusation_H8"])),
        ("الإحالة الملزمة (O5، O6)", lambda s: _pct(s["mandatory_referral"])),
        ("صحة تنبيه التجاوز (H9/H10)", lambda s: _pct(s["exceeds_precision"])),
        ("كشف الاستخراج", lambda s: _pct(s["extraction_recall"])),
        ("الاتساق", lambda s: _pct(s["consistency"])),
        ("الزمن p50 / p95", lambda s: f"{s['latency_p50_ms']} / {s['latency_p95_ms']} ms"),
        ("الرموز (المجموع)", lambda s: str(s["tokens"])),
    ]
    for label, fn in rows:
        lines.append(f"| {label} | " + " | ".join(fn(S[n]) for n in sys_names) + " |")
    if "mcnemar_saadeed_vs_B0" in m:
        mc = m["mcnemar_saadeed_vs_B0"]
        lines += [
            "",
            f"**McNemar (سديد مقابل B0):** أصاب سديد وحده في {mc['saadeed_only']}، وB0 وحده في {mc['b0_only']}، p = {mc['p']}",
        ]
    lines += [
        "",
        "## الصحة بحسب نوع الادعاء",
        "",
        "| النوع | " + " | ".join(sys_names) + " |",
        "|---|" + "---|" * len(sys_names),
    ]
    groups = sorted({g for n in sys_names for g in S[n]["by_group"]})
    for g in groups:
        lines.append(
            f"| {g} | " + " | ".join(_pct(S[n]["by_group"].get(g)) for n in sys_names) + " |"
        )
    lines += [
        "",
        "## الصحة بحسب الفئة",
        "",
        "| الفئة | " + " | ".join(sys_names) + " |",
        "|---|" + "---|" * len(sys_names),
    ]
    cats = sorted({c for n in sys_names for c in S[n]["by_category"]})
    for c in cats:
        lines.append(
            f"| {c} | " + " | ".join(_pct(S[n]["by_category"].get(c)) for n in sys_names) + " |"
        )
    for n in sys_names:
        if S[n]["critical_missed_ids"]:
            lines.append(
                f"\n- **{n} — حالات حرجة فائتة:** {', '.join(S[n]['critical_missed_ids'])}"
            )
        if S[n]["errors"]:
            lines.append(f"- **{n} — أخطاء تشغيل:** {len(S[n]['errors'])}")
    lines += ["", "> «الصحة» = المعيب نُبّه عليه، والسليم لم يُنبَّه عليه. والتعريفات في البروتوكول §٦."]
    return "\n".join(lines) + "\n"


def bank_cases(split: str | None = None) -> tuple[list[TestCase], list[Carrier]]:
    cases, carriers = load_bank(BANK_DIR)
    if split:
        cases = [c for c in cases if c.split == split]
        carriers = [c for c in carriers if c.split == split]
    return cases, carriers
