"""المرور الحتمي على العلامات (FR-13): يكمّل استخراج النموذج ولا يعتمد عليه.

ما يكشفه بالقواعد وحدها:
- ما بين القوسين القرآنيين ﴿ ﴾، أو بعد «قال تعالى» بين علامات تنصيص.
- ما بين «» بعد ذكر النبي ﷺ.
- نسبة التخريج بعد الحديث: «رواه البخاري»، «متفق عليه».
- الإحالة القرآنية بعد الآية: [البقرة: 255].
- صيغة «ما معناه» التي تجعل النقل بالمعنى.

فلو تعطل النموذج كليًا، بقيت الآيات والأحاديث المعلَّمة تُفحص (الفشل الآمن، م١٦).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from saadeed.domain.quran_meta import SURA_ALIASES, SURA_NAMES
from saadeed.text.normalize import _is_dropped, normalize

_DIG = "0-9٠-٩"


@dataclass
class Marked:
    kind: str  # quran | hadith
    text: str
    start: int
    end: int
    cited_ref: str | None = None
    ref_parsed: tuple[int, int, int] | None = None  # (sura, from, to)
    cited_book: str | None = None
    verbatim: bool = True
    notes: list[str] = field(default_factory=list)


_QURAN_BRACKETS = re.compile(r"﴿([^﴾]{2,1500})﴾")
_QURAN_INTRO = re.compile(
    r"(?:قال|يقول|وقال|ويقول|قوله|لقوله|كقوله)\s+(?:الله\s+)?(?:تعالى|سبحانه(?:\s+وتعالى)?|عز\s+وجل|جل\s+وعلا|تبارك\s+وتعالى)"
    r"\s*[:：،]?\s*[«\"“{(]([^»\"”})]{2,1500})[»\"”})]"
)
_PROPHET = r"(?:ﷺ|صلى\s+الله\s+عليه\s+وسلم|عليه\s+الصلاة\s+والسلام|عليه\s+السلام|النبي|رسول\s+الله|المصطفى)"
_HADITH_QUOTE = re.compile(_PROPHET + r"[^«\"“\n(]{0,60}?[:：،]?\s*[«\"“]([^»\"”]{4,1500})[»\"”]")
_HADITH_DOUBLE_PAREN = re.compile(_PROPHET + r"[^(\n«]{0,80}?[:：،]?\s*\(\(([^)]{4,1500})\)\)")
_MEANING = re.compile(r"(?:ما\s+معناه|بمعناه|معنى\s+الحديث|ما\s+مفاده|نحو\s+قوله|في\s+معناه)")
_BOOKS = (
    r"(?:الإمام\s+)?(?:البخاري|مسلم|أبو\s+داود|ابو\s+داود|أبي\s+داود|الترمذي|النسائي|ابن\s+ماجه|ابن\s+ماجة|أحمد|مالك|الدارمي|"
    r"ابن\s+حبان|الحاكم|الطبراني|البيهقي|ابن\s+خزيمة|الدارقطني)"
)
_TAKHRIJ = re.compile(
    r"^\s*[\(\[]?\s*(?:(?:رواه|أخرجه|اخرجه|رواها)\s+("
    + _BOOKS
    + r"(?:\s+في\s+(?:السنن\s+)?الكبرى)?(?:\s+و\s*"
    + _BOOKS
    + r")*)|(متفق\s+عليه|(?:رواه|أخرجه|اخرجه)\s+(?:الشيخان|الشيخين)))"
)
_REF = re.compile(
    r"^\s*[\[(]\s*(?:سورة\s+)?([^\]):：،0-9٠-٩]{1,20}?)\s*[:：،,\-]?\s*(?:الآية|آية|الاية|اية)?\s*(["
    + _DIG
    + r"]+)"
    r"(?:\s*[-–—،,]\s*([" + _DIG + r"]+))?\s*[\])]"
)

_SURA_INDEX: dict[str, int] = {normalize(n): i + 1 for i, n in enumerate(SURA_NAMES)}
_SURA_INDEX.update({normalize(k): v for k, v in SURA_ALIASES.items()})
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def parse_ref(raw: str) -> tuple[int, int, int] | None:
    """يحلل إحالة مثل «البقرة: 255» أو «[الأحزاب: ٧٠–٧١]» إلى (السورة، من، إلى)."""
    text = raw.strip()
    if not text.startswith(("[", "(")):
        text = f"[{text}]"
    m = _REF.match(text)
    if not m:
        return None
    name = normalize(m.group(1)).replace("سوره ", "").strip()
    sura = _SURA_INDEX.get(name)
    if sura is None:
        return None
    a = int(m.group(2).translate(_ARABIC_DIGITS))
    b = int(m.group(3).translate(_ARABIC_DIGITS)) if m.group(3) else a
    return sura, a, b


def _ref_after(text: str, pos: int) -> tuple[str | None, tuple[int, int, int] | None]:
    window = text[pos : pos + 60]
    m = _REF.match(window)
    if not m:
        return None, None
    return m.group(0).strip(), parse_ref(m.group(0))


def _takhrij_after(text: str, pos: int) -> str | None:
    window = text[pos : pos + 80]
    m = _TAKHRIJ.match(window)
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").strip() or None


def _skeleton(text: str) -> tuple[str, list[int]]:
    """النص بلا تشكيل ولا تطويل ولا محارف خفية، مع خريطة لموضع كل حرف في الأصل.

    أنماط العلامات مكتوبة بلا تشكيل، والخطب المنشورة كثيرًا ما تُشكَّل كاملة
    («صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ»، «رَوَاهُ مُسْلِمٌ»). فالبحث يجري على الهيكل، والنص المعروض من الأصل.
    """
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        if _is_dropped(ch) and ch != "ء":
            continue
        out.append(ch)
        idx.append(i)
    idx.append(len(text))
    return "".join(out), idx


def _orig_span(idx: list[int], s: int, e: int) -> tuple[int, int]:
    """موضع [s, e) في الهيكل ← موضعه في الأصل، بحركات الحرف الأخير."""
    return idx[s], (idx[e - 1] + 1 if e > s else idx[s])


_NARRATION = re.compile(
    _PROPHET
    + r"|(?:^|\s)(?:و|ف)?(?:حديث|رواية|روايه|رواه|اخرجه|أخرجه|متفق|يرفعه|مرفوعا)(?:\s|$|[:،])"
)

_PROPHET_RX = re.compile(_PROPHET)


def takhrij_after(fragment: str) -> str | None:
    """نسبة التخريج في أول النص بعد الاقتباس («» رواه ابن ماجه»)، على الهيكل بلا تشكيل."""
    sk, _ = _skeleton(fragment)
    return _takhrij_after(_CLOSERS.sub("", sk), 0)


_CLOSERS = re.compile(r'^[»"”) ]+')


def has_prophetic_context(text: str, start: int, end: int) -> bool:
    """هل نُسب الاقتباس إلى النبي ﷺ أو قُدّم رواية؟ نافذة قبله (القائل) وبعده (التخريج).

    والنافذة قبله لا تتجاوز جملته: «ﷺ» في آخر الفقرة السابقة لا تجعل ما بعدها حديثًا.
    """
    before, _ = _skeleton(text[max(0, start - 400) : start])
    before = re.split(r"[.!؟?\n]", before[-120:])[-1]
    after, _ = _skeleton(text[end : end + 200])
    head, _ = _skeleton(text[start : min(end, start + 200)])
    if _PROPHET_RX.search(head[:80]):
        return True  # «وكان النبي ﷺ إذا حزبه أمر صلى»: النسبة في الادعاء نفسه
    return bool(_NARRATION.search(before) or _takhrij_after(_CLOSERS.sub("", after), 0))


def scan(text: str) -> list[Marked]:
    """يكشف الآيات والأحاديث المعلَّمة في المسودة، بمواضعها في الأصل."""
    sk, idx = _skeleton(text)
    found: list[Marked] = []
    quran_taken: list[tuple[int, int]] = []
    hadith_taken: list[tuple[int, int]] = []

    def overlaps(s: int, e: int, taken: list[tuple[int, int]]) -> bool:
        return any(s < te and ts < e for ts, te in taken)

    def span(m: re.Match[str]) -> tuple[int, int, str]:
        s, e = _orig_span(idx, m.start(1), m.end(1))
        while e < len(text) and _is_dropped(text[e]) and not text[e].isspace():
            e += 1
        raw = text[s:e]
        lead = len(raw) - len(raw.lstrip())
        return s + lead, s + len(raw.rstrip()), raw.strip()

    for rx in (_QURAN_BRACKETS, _QURAN_INTRO):
        for m in rx.finditer(sk):
            if overlaps(m.start(1), m.end(1), quran_taken):
                continue
            s, e, body = span(m)
            cited, parsed = _ref_after(sk, m.end())
            found.append(Marked("quran", body, s, e, cited_ref=cited, ref_parsed=parsed))
            quran_taken.append((m.start(1), m.end(1)))

    hadith_matches = sorted(
        [*_HADITH_QUOTE.finditer(sk), *_HADITH_DOUBLE_PAREN.finditer(sk)],
        key=lambda m: m.start(1),
    )
    for m in hadith_matches:
        ss, se = m.start(1), m.end(1)
        # الحديث قد يتضمن آية (آية الكرسي في حديث أبي هريرة): لا يُسقط لذلك، ويُسقط إن تداخل مع حديث آخر
        # أو وقع بكامله داخل آية.
        if overlaps(ss, se, hadith_taken) or any(ts <= ss and se <= te for ts, te in quran_taken):
            continue
        before = sk[max(0, m.start() - 40) : ss]
        verbatim = not _MEANING.search(before)
        book = _takhrij_after(sk, m.end())
        s, e, body = span(m)
        found.append(Marked("hadith", body, s, e, cited_book=book, verbatim=verbatim))
        hadith_taken.append((ss, se))

    found.sort(key=lambda x: x.start)
    return found


_BOOK_CANON = {
    "البخاري": "bukhari",
    "مسلم": "muslim",
    "ابو داود": "abudawud",
    "ابي داود": "abudawud",
    "الترمذي": "tirmidhi",
    "النسائي": "nasai",
    "ابن ماجه": "ibnmajah",
}


def canonical_books(cited: str | None) -> set[str]:
    """«رواه البخاري ومسلم» ← {bukhari, muslim}. و«متفق عليه» ← كذلك.

    كتب خارج الستة تعود باسم `other`.
    """
    if not cited:
        return set()
    n = normalize(cited)
    if "متفق عليه" in n or "الصحيحين" in n or "الشيخين" in n or "الشيخان" in n:
        return {"bukhari", "muslim"}
    books: set[str] = set()
    for key, canon in _BOOK_CANON.items():
        if normalize(key) in n:
            books.add(canon)
    # «النسائي في الكبرى» غير «سنن النسائي» (المجتبى) الذي في مصادرنا: خارج التغطية.
    if "nasai" in books and "الكبري" in n:
        books.discard("nasai")
        books.add("other")
    if not books and n:
        books.add("other")
    return books
