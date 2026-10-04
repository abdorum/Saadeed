"""تجهيزات مشتركة. الاختبارات التي تحتاج البيانات الحقيقية تُتخطى إن لم تُبنَ (`saadeed data build`)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HAS_DATA = (ROOT / "data" / "processed" / "bukhari.json").exists() and (
    ROOT / "data" / "raw" / "tanzil" / "quran-simple.txt"
).exists()
needs_data = pytest.mark.skipif(not HAS_DATA, reason="البيانات غير مبنية: saadeed data build")


@pytest.fixture(scope="session")
def engine():
    if not HAS_DATA:
        pytest.skip("البيانات غير مبنية")
    from saadeed.adapters.factory import build_engine

    return build_engine()
