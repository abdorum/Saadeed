"""ما يعيده كل متحقق: «إشارة» لجدول القواعد، وشواهد من المخزن، ومعطيات للقوالب."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from saadeed.domain.enums import Confidence
from saadeed.domain.models import Evidence, RelationResult
from saadeed.domain.policy import Signal


@dataclass
class Outcome:
    signal: Signal
    evidence: list[Evidence] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    confidence: Confidence = Confidence.MEDIUM
    notes: list[str] = field(default_factory=list)
    relation: RelationResult | None = None
