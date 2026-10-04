"""قارئ ملف المرجعية المعتمدة (ADR-0010، FR-55). مكتبة قياسية فقط (tomllib)."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

from saadeed.domain.enums import SourceRole
from saadeed.domain.models import ManifestStamp


class SourceEntry(BaseModel):
    id: str
    adapter: str
    role: SourceRole
    name_ar: str
    files: list[str] = Field(default_factory=list)
    version: str = "—"
    license: str = "—"


class SourceManifest(BaseModel):
    id: str
    description: str = ""
    reviewed_by: str = ""
    reviewed_on: str = ""
    sources: list[SourceEntry]
    sha256: str

    @property
    def stamp(self) -> ManifestStamp:
        return ManifestStamp(id=self.id, sha256=self.sha256)

    def by_role(self, role: SourceRole) -> list[SourceEntry]:
        return [s for s in self.sources if s.role is role]


def load_manifest(path: Path) -> SourceManifest:
    raw = path.read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    head = data["manifest"]
    return SourceManifest(
        id=head["id"],
        description=head.get("description", ""),
        reviewed_by=head.get("reviewed_by", ""),
        reviewed_on=head.get("reviewed_on", ""),
        sources=[SourceEntry(**s) for s in data.get("source", [])],
        sha256=hashlib.sha256(raw).hexdigest(),
    )
