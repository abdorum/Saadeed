"""عقد منفذ النموذج: كل محوّل يعيد JSON بالصيغة نفسها، والتسجيل يعيد الاستجابة حرفيًا."""

import pytest

from saadeed.adapters.llm.cache import CachedLLM
from saadeed.adapters.llm.fake import FakeLLM
from saadeed.adapters.llm.groq import parse_json_content
from saadeed.domain.ports import LLMError


def test_record_then_replay_is_identical(tmp_path):
    calls = []
    inner = FakeLLM(lambda s, u: (calls.append(u), {"claims": [{"quote": u}]})[1])
    rec = CachedLLM(inner, tmp_path, mode="use")
    a = rec.generate_json(system="s", user="مسودة")
    rep = CachedLLM(None, tmp_path, mode="replay", model_id=inner.model_id)
    b = rep.generate_json(system="s", user="مسودة")
    assert a.data == b.data and b.usage.cached
    assert len(calls) == 1


def test_replay_without_recording_fails_safely(tmp_path):
    rep = CachedLLM(None, tmp_path, mode="replay", model_id="fake")
    with pytest.raises(LLMError):
        rep.generate_json(system="s", user="جديد")


def test_salt_forces_fresh_call(tmp_path):
    n = []
    inner = FakeLLM(lambda s, u: (n.append(1), {"x": len(n)})[1])
    CachedLLM(inner, tmp_path, salt="run1").generate_json(system="s", user="u")
    CachedLLM(inner, tmp_path, salt="run2").generate_json(system="s", user="u")
    assert len(n) == 2


def test_json_parsing_tolerates_wrapping():
    assert parse_json_content('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_content('[{"a": 1}]') == {"items": [{"a": 1}]}
    with pytest.raises(LLMError):
        parse_json_content("لا JSON هنا")
