"""يبني prompts/prompts.json: فهرس كل التعليمات التي تُرسل إلى النموذج، بمعرّفها وإصدارها وموضع استعمالها.

الاستعمال:  uv run python scripts/build_prompts_index.py
"""

import json
from pathlib import Path

from saadeed.application.prompts import load_prompt

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"

# أين يُستعمل كل معرّف، ومتى، وما الذي لا يُسمح للنموذج بقراره فيه.
USAGE = {
    "extract": {
        "stage": "٢ الاستخراج",
        "code": "src/saadeed/application/extraction.py",
        "when": "كل مراجعة كاملة؛ المسودة تُقسَّم أجزاءً ونداء لكل جزء بالتوازي",
        "model_decides": "مواضع الادعاءات وأنواعها، وصنف كل جملة، واقتراح صياغة للتعميم والإجماع",
        "model_never": "نص آية أو حديث، والحالة والأثر والإجراء",
    },
    "judge_hadiths": {
        "stage": "٤ مطابقة الحديث",
        "code": "src/saadeed/application/review_draft.py (_judge)",
        "when": "حديث لم يُحسم حرفيًا: خمسة مرشحين من مخزن الكتب الستة",
        "model_decides": "لفظ أم معنى أم لا يطابق، ورقم المرشح",
        "model_never": "صحة الحديث، أو معرّف ليس بين المرشحين (حارس الإسناد يُسقطه)",
    },
    "judge_sayings": {
        "stage": "٤ مطابقة الأقوال (v2.6)",
        "code": "src/saadeed/application/library_check.py (check_sayings)",
        "when": "قول منسوب إلى عالم أو قصة منقولة؛ المواضع من مكتبة تراث (وصلة حية)",
        "model_decides": "لفظ أم معنى أم لا، ورقم الموضع، وهل مؤلفه هو المنسوب إليه",
        "model_never": "نص الموضع (يُعرض من المكتبة نفسها)، والحالة والأثر والإجراء",
    },
    "extract_rulings": {
        "stage": "٤ حكم الحديث المنقول (v2.6)",
        "code": "src/saadeed/application/library_check.py (check_rulings)",
        "when": "حديث وُجد في السنن دون حكم، أو لم يُعثر عليه",
        "model_decides": "نقل الحكم ومن قاله من نص الموضع، وحارس حتمي يتأكد أن الحكم والاسم في الموضع",
        "model_never": "الحكم من عنده",
    },
    "gate_generalization": {
        "stage": "٥ بوابة العرض (v2.6)",
        "code": "src/saadeed/application/library_check.py (gate_generalizations)",
        "when": "عبارة اشتُبه أنها تعميم: هل هي في سياق فقرتها تعميم مضلل؟ نعم/لا",
        "model_decides": "عرض الملاحظة أو إسقاطها",
        "model_never": "نص الملاحظة ولا إجراءها (من جدول القواعد والقوالب)",
    },
    "baseline": {
        "stage": "التقييم: خط الأساس B0",
        "code": "src/saadeed/adapters/eval/systems.py",
        "when": "التقييم فقط: النموذج وحده بتعليمات جيدة، للمقارنة",
        "model_decides": "كل شيء (وهذا ما نقيسه)",
        "model_never": "—",
    },
    "b1_quran_judge": {
        "stage": "التقييم: خط الأساس B1",
        "code": "src/saadeed/adapters/eval/systems.py",
        "when": "التقييم فقط: النموذج يحكم على الآية بدل المطابق الحتمي",
        "model_decides": "مطابقة الآية (وهذا ما نقيسه)",
        "model_never": "—",
    },
}


def main() -> None:
    latest: dict[str, Path] = {}
    for f in sorted(PROMPTS.glob("*_v*.md")):
        p = load_prompt(f)
        prev = latest.get(p.id)
        if prev is None or int(p.version.lstrip("v") or 0) > int(load_prompt(prev).version.lstrip("v") or 0):
            latest[p.id] = f
    items = []
    for pid, f in sorted(latest.items()):
        p = load_prompt(f)
        front = f.read_text(encoding="utf-8").split("---")[1] if f.read_text().startswith("---") else ""
        purpose = next((ln.split(":", 1)[1].strip() for ln in front.splitlines() if ln.startswith("purpose:")), "")
        older = sorted(x.name for x in PROMPTS.glob(f"{f.stem.rsplit('_v', 1)[0]}_v*.md") if x != f)
        items.append(
            {
                "id": pid,
                "version": p.version,
                "file": f"prompts/{f.name}",
                "purpose": purpose,
                **USAGE.get(pid, {}),
                "previous_versions": older,
                "system": p.system,
                "user": p.user,
            }
        )
    out = {
        "about": "كل التعليمات التي يرسلها سديد إلى النموذج اللغوي. المصدر هو ملفات prompts/*_vN.md، وهذا الفهرس يُبنى منها، ورقم الإصدار يُسجَّل في meta.prompt_versions لكل تقرير.",
        "model": "gemini-3.5-flash-lite (افتراضي؛ وGroq بديل بتغيير متغير بيئة)",
        "prompts": items,
    }
    (PROMPTS / "prompts.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"prompts/prompts.json: {len(items)} تعليمات")


if __name__ == "__main__":
    main()
