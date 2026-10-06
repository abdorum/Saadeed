"""تحميل ملفات التعليمات المُصدَّرة برقم (`prompts/*_vN.md`). ورقم الإصدار يُسجَّل في `meta`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)


@dataclass(frozen=True)
class Prompt:
    id: str
    version: str
    system: str
    user: str

    def render(self, **values: str) -> tuple[str, str]:
        user = self.user
        for k, v in values.items():
            user = user.replace("{{" + k + "}}", v)
        return self.system, user


def load_prompt(path: Path) -> Prompt:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    m = _FRONT.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        text = text[m.end() :]
    parts = re.split(r"^## (system|user)\s*$", text, flags=re.M)
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    return Prompt(
        meta.get("id", path.stem), meta.get("version", "v?"), sections["system"], sections["user"]
    )


def _optional(path: Path) -> Prompt | None:
    return load_prompt(path) if path.exists() else None


@dataclass(frozen=True)
class PromptSet:
    extract: Prompt
    judge: Prompt
    baseline: Prompt
    sayings: Prompt | None = None
    rulings: Prompt | None = None
    gate: Prompt | None = None

    @classmethod
    def load(cls, prompts_dir: Path) -> PromptSet:
        return cls(
            extract=load_prompt(prompts_dir / "extract_v4.md"),
            judge=load_prompt(prompts_dir / "judge_hadiths_v2.md"),
            baseline=load_prompt(prompts_dir / "baseline_v1.md"),
            sayings=_optional(prompts_dir / "judge_sayings_v1.md"),
            rulings=_optional(prompts_dir / "extract_rulings_v1.md"),
            gate=_optional(prompts_dir / "gate_generalization_v1.md"),
        )

    def versions(self) -> dict[str, str]:
        ps = (self.extract, self.judge, self.sayings, self.rulings, self.gate)
        return {p.id: p.version for p in ps if p}
