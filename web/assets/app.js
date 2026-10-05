/* سديد — منطق الواجهة. صفحة واحدة، JavaScript صرف بلا مكتبات ولا خطوة بناء (ADR-0012).
   - تستهلك الواجهة البرمجية نفسها: /v1/reviews، /v1/coverage، /v1/results.
   - «الفحص السريع» يُعرض فورًا (المسار الحتمي)، ثم يستبدل به التقرير الكامل حين يكتمل.
   - إن لم تتوفر الواجهة البرمجية (معاينة ثابتة) تعمل الأمثلة الجاهزة بتقاريرها المحفوظة (FR-02).
   - كل نص من المسودة أو المصدر يُهرَّب قبل العرض. */
(function () {
  "use strict";

  var $ = function (s, el) { return (el || document).querySelector(s); };
  var esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  var EMBED = window.SAADEED_DATA || null; // في المعاينة الثابتة تُضمَّن البيانات في الصفحة

  var BUCKETS = {
    NEEDS_VERIFICATION: { ar: "يتطلب تحققًا", cls: "warn", rank: 0 },
    REFER: { ar: "إحالة إلى مختص", cls: "refer", rank: 1 },
    NOT_CHECKED: { ar: "لم يُفحص", cls: "idle", rank: 2 },
    SUPPORTED_BY_SOURCES: { ar: "تؤيده المصادر", cls: "ok", rank: 3 }
  };
  var SEV_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, NONE: 4 };
  var ROLE_AR = {
    REFERENCE_TEXT: "نص معتمد",
    AUTHENTIC: "مصدر احتجاج",
    RULING: "مصدر حكم منقول",
    LOCATE: "مصدر موضع (دون حكم)",
    LINK: "إحالة"
  };
  var ROLE_MEANING = {
    REFERENCE_TEXT: "يُطابَق به حرفًا بحرف",
    AUTHENTIC: "وجود الحديث فيه يكفي لـ«مؤيَّد بالمصدر»",
    RULING: "ينقل حكمًا موثقًا بلفظه ونسبته",
    LOCATE: "يخبر أين وُجد النص، ولا يحكم عليه",
    LINK: "رابط بحث يفتحه الإنسان، لا استدعاء آلي"
  };
  var CONF = { high: "عالية", medium: "متوسطة", low: "منخفضة" };
  var KIND_VAR = {
    QURAN: "--k-quran", HADITH: "--k-hadith", ATHAR: "--k-athar", SCHOLAR: "--k-scholar",
    DUA: "--k-dua", POETRY: "--k-poetry", STORY: "--k-story", RULING: "--k-ruling",
    FACT: "--k-fact", EXHORTATION: "--k-exhortation", OTHER: "--k-other", UNLABELED: "--k-unlabeled"
  };

  var LIVE = false;
  var current = null; // { text, report, provisional }

  function origin(o) {
    if (!o) return "—";
    if (o.indexOf("crosscheck") > 0) return "صنّفه النموذج، وصحّح الفحص المتقاطع نوعه بفهرس المصحف";
    return {
      llm: "استخرجه النموذج من المسودة، وتحقق منه سديد",
      marker: "التقطه المرور الحتمي (العلامات والصيغ)",
      both: "التقطه النموذج والمرور الحتمي معًا",
      crosscheck: "التقطه الفحص المتقاطع بفهرس المصحف"
    }[o] || o;
  }

  function words(t) { var m = String(t).trim().match(/\S+/g); return m ? m.length : 0; }
  function clip(t, n) { t = String(t); return t.length > n ? t.slice(0, n) + " …" : t; }

  function getJSON(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  function detectLive() {
    var ctl = "AbortController" in window ? new AbortController() : null;
    var t = setTimeout(function () { if (ctl) ctl.abort(); }, 2500);
    return fetch("v1/health", ctl ? { signal: ctl.signal } : {})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { clearTimeout(t); return !!(j && j.ok); })
      .catch(function () { clearTimeout(t); return false; });
  }

  /* ───────────── الأمثلة ───────────── */
  function loadExampleIndex() {
    if (EMBED && EMBED.examples) return Promise.resolve(EMBED.examples.map(function (e) {
      return { id: e.id, title: e.title, note: e.note };
    }));
    return getJSON("examples/index.json");
  }
  function loadExample(id) {
    if (EMBED && EMBED.examples) {
      for (var i = 0; i < EMBED.examples.length; i++) if (EMBED.examples[i].id === id) return Promise.resolve(EMBED.examples[i]);
    }
    return getJSON("examples/" + encodeURIComponent(id) + ".json");
  }
  function renderExampleButtons(list) {
    var box = $("#examples");
    list.forEach(function (ex) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = ex.title;
      b.setAttribute("aria-pressed", "false");
      b.dataset.id = ex.id;
      b.addEventListener("click", function () { showExample(ex.id); });
      box.appendChild(b);
    });
  }
  function showExample(id) {
    Array.prototype.forEach.call(document.querySelectorAll("#examples button"), function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.id === id));
    });
    setStatus("");
    loadExample(id).then(function (ex) {
      $("#draft").value = ex.text;
      updateCounter();
      var note = $("#example-note");
      note.hidden = false;
      note.innerHTML = esc(ex.note) + (ex.source_url ? ' <a href="' + esc(ex.source_url) + '" target="_blank" rel="noopener">المصدر ↗</a>' : "") +
        " · تقرير محفوظ مسبقًا، يُعرض فورًا.";
      render(ex.text, ex.report, false);
    }).catch(function () { setStatus("تعذّر تحميل المثال.", true); });
  }

  /* ───────────── المراجعة ───────────── */
  function setStatus(msg, isErr, busy) {
    var s = $("#status");
    s.className = "status" + (isErr ? " err" : "");
    s.innerHTML = (busy ? '<span class="dot" aria-hidden="true"></span>' : "") + esc(msg);
  }
  function updateCounter() {
    var n = words($("#draft").value);
    $("#counter").textContent = n + " كلمة" + (n > 3000 ? " · أطول من الحد (3000)" : "");
  }

  function post(text, mode) {
    return fetch("v1/reviews", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ text: text, mode: mode })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "تعذّرت المراجعة (" + r.status + ")");
        return j;
      });
    });
  }

  function runReview() {
    var text = $("#draft").value.replace(/\r\n/g, "\n");
    if (!text.trim()) { setStatus("ضع نص المسودة أولًا.", true); return; }
    if (!LIVE) {
      setStatus("الفحص الحي يعمل على الرابط المنشور. وفي هذه المعاينة جرّب الأمثلة الجاهزة بتقاريرها المحفوظة.", true);
      return;
    }
    Array.prototype.forEach.call(document.querySelectorAll("#examples button"), function (b) { b.setAttribute("aria-pressed", "false"); });
    $("#example-note").hidden = true;
    var btn = $("#run");
    btn.disabled = true;
    var full = false;
    setStatus("يقرأ سديد المسودة… تظهر نتائج المسار الحتمي أولًا، ثم تكتمل بطبقة الذكاء الاصطناعي.", false, true);
    post(text, "quick").then(function (r) {
      if (!full) render(text, r, true);
    }).catch(function (e) {
      if (!full) { setStatus(e.message, true); btn.disabled = false; }
    });
    post(text, "full").then(function (r) {
      full = true;
      render(text, r, false);
      if (r.meta.degraded) setStatus("المراجعة ناقصة: تعذّر نموذج الذكاء الاصطناعي، والمعروض نتائج المسار الحتمي وحده.", true);
      else setStatus("اكتملت المراجعة في " + (r.meta.duration_ms / 1000).toFixed(1) + " ثانية.");
    }).catch(function (e) {
      full = true;
      setStatus(e.message + (current ? " · المعروض نتائج المسار الحتمي وحده." : ""), true);
    }).then(function () { btn.disabled = false; });
  }

  /* ───────────── التقرير ───────────── */
  function byRisk(a, b) {
    var ra = BUCKETS[a.bucket].rank, rb = BUCKETS[b.bucket].rank;
    if (ra !== rb) return ra - rb;
    return (SEV_RANK[a.severity] || 9) - (SEV_RANK[b.severity] || 9);
  }

  function matnHTML(text, rep) {
    var fs = rep.findings;
    var pts = [0, text.length];
    fs.forEach(function (f) { pts.push(f.claim.span.start, f.claim.span.end); });
    pts = pts.filter(function (v, i, a) { return a.indexOf(v) === i; }).sort(function (a, b) { return a - b; });
    var html = "";
    for (var i = 0; i < pts.length - 1; i++) {
      var a = pts[i], b = pts[i + 1], seg = text.slice(a, b);
      var cov = fs.filter(function (f) { return f.claim.span.start <= a && f.claim.span.end >= b; });
      if (!cov.length) { html += esc(seg); continue; }
      cov.sort(byRisk);
      html += '<mark class="hl b-' + BUCKETS[cov[0].bucket].cls + '" tabindex="0" data-f="' +
        cov.map(function (f) { return f.id; }).join(" ") + '" title="' + esc(BUCKETS[cov[0].bucket].ar) + '">' + esc(seg) + "</mark>";
    }
    return html;
  }

  function snippet(text, hl) {
    var MAX = 520;
    if (hl && hl.length) {
      var h = hl[0];
      if (h.end - h.start >= text.length) return esc(text);
      var lo = Math.max(0, h.start - 140), hi = Math.min(text.length, h.end + 140);
      return (lo ? "… " : "") + esc(text.slice(lo, h.start)) + "<mark>" + esc(text.slice(h.start, h.end)) + "</mark>" +
        esc(text.slice(h.end, hi)) + (hi < text.length ? " …" : "");
    }
    // نص الحديث يبدأ بالإسناد؛ والمتن غالبًا في آخره، فنعرض الآخر إن طال.
    return text.length > MAX ? "… " + esc(text.slice(text.length - MAX)) : esc(text);
  }

  function diffHTML(ops) {
    if (!ops || !ops.some(function (o) { return o.op !== "equal"; })) return "";
    var d = ops.map(function (o) {
      return o.op === "equal" ? esc(o.draft) : "<del>" + (o.draft ? esc(o.draft) : "∅") + "</del>";
    }).join(" ");
    var s = ops.map(function (o) {
      return o.op === "equal" ? esc(o.source) : "<ins>" + (o.source ? esc(o.source) : "∅") + "</ins>";
    }).join(" ");
    return '<div class="diff" aria-label="الفرق كلمة بكلمة"><div class="row"><span>في مسودتك</span><span>' + d +
      '</span></div><div class="row"><span>في المصحف</span><span>' + s + "</span></div></div>";
  }

  function evidenceHTML(e) {
    if (e.role === "LINK" || !e.text) {
      return e.ref.url ? '<a class="ev-link" href="' + esc(e.ref.url) + '" target="_blank" rel="noopener">' + esc(e.ref.citation) + " ↗</a>" : "";
    }
    var quran = e.ref.source_id === "quran";
    return '<figure class="t-source"><figcaption><span>' + esc(e.ref.citation) + '</span><span class="role">' +
      esc(ROLE_AR[e.role] || e.role) + "</span>" +
      (e.ref.url ? '<a href="' + esc(e.ref.url) + '" target="_blank" rel="noopener">افتح المصدر ↗</a>' : "") +
      '</figcaption><div class="src-text' + (quran ? " quran" : "") + '">' + snippet(e.text, e.highlight) + "</div>" +
      diffHTML(e.diff) + "</figure>";
  }

  function cardHTML(f) {
    var b = BUCKETS[f.bucket], L = f.labels_ar;
    var how = '<dt>القاعدة</dt><dd>' + esc(f.rule_id) + " من جدول «ميزان السداد»، لا من النموذج</dd>" +
      "<dt>الثقة</dt><dd>" + esc(CONF[f.confidence] || f.confidence) + "</dd>" +
      "<dt>الادعاء</dt><dd>" + esc(origin(f.claim.origin)) + "</dd>";
    f.evidence.forEach(function (e) {
      if (e.role !== "LINK") how += "<dt>المطابقة</dt><dd>" + esc(e.match_reason) + "</dd>";
    });
    return '<article class="card c-' + b.cls + '" id="card-' + esc(f.id) + '" tabindex="-1">' +
      '<header><span class="chip b-' + b.cls + '">' + esc(b.ar) + '</span><span class="ctype">' + esc(L.claim_type) +
      '</span><span class="rule" title="رقم القاعدة في جدول ميزان السداد">' + esc(f.rule_id) + "</span></header>" +
      '<blockquote class="t-draft" data-goto="' + esc(f.id) + '" title="اعرض موضعه في المسودة">' + esc(clip(f.claim.text, 280)) + "</blockquote>" +
      '<dl class="dims"><div><dt>حالة الدليل</dt><dd>' + esc(L.evidence_status) + '</dd></div><div><dt>أثر الخطأ</dt><dd class="sev-' +
      esc(f.severity) + '">' + esc(L.severity) + "</dd></div><div><dt>الإجراء</dt><dd>" + esc(L.action) + "</dd></div></dl>" +
      '<p class="t-saadeed"><span class="lbl">شرح سديد</span>' + esc(f.explanation) + "</p>" +
      (f.action !== "NONE" ? '<p class="next"><span class="lbl">الخطوة التالية</span>' + esc(f.next_step) + "</p>" : "") +
      (f.suggestion ? '<div class="t-suggest"><span class="lbl">اقتراح صياغة (مولَّد، راجعه)</span>' + esc(f.suggestion) + "</div>" : "") +
      f.evidence.map(evidenceHTML).join("") +
      (f.notes && f.notes.length ? '<ul class="notes">' + f.notes.map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("") + "</ul>" : "") +
      '<details class="how"><summary>كيف عرف سديد؟</summary><dl>' + how + "</dl></details></article>";
  }

  function ribbonHTML(rep) {
    var map = rep.draft_map || [];
    if (!map.length) return "";
    var present = {};
    var spans = map.map(function (e) {
      present[e.kind] = e.kind_ar;
      var w = Math.max(1, e.span.end - e.span.start);
      return '<span title="' + esc(e.kind_ar) + (e.finding_ids.length ? " · فيها " + e.finding_ids.length + " ملاحظة" : "") +
        '" style="flex-grow:' + w + ";background:var(" + KIND_VAR[e.kind] + ')"></span>';
    }).join("");
    var legend = Object.keys(present).map(function (k) {
      return '<span><i style="background:var(' + KIND_VAR[k] + ')"></i>' + esc(present[k]) + "</span>";
    }).join("");
    var withF = map.filter(function (e) { return e.finding_ids.length; }).length;
    return '<div class="ribbon-wrap"><span class="lbl">خريطة المسودة: ' + map.length + " جملة، في " + withF +
      ' منها ادعاء مفحوص</span><div class="ribbon" aria-hidden="true">' + spans + '</div><div class="legend">' + legend + "</div></div>";
  }

  function auditHTML(rep) {
    var m = rep.meta, s = rep.summary;
    var pv = Object.keys(m.prompt_versions || {}).map(function (k) { return k + " " + m.prompt_versions[k]; }).join(" · ");
    var warn = (m.warnings || []).length ? '<ul class="warns">' + m.warnings.map(function (w) { return "<li>" + esc(w) + "</li>"; }).join("") + "</ul>" : "";
    var nc = (s.not_checked || []).length ? "<p><strong>ما لم يُفحص:</strong> " + s.not_checked.map(esc).join(" · ") + "</p>" : "";
    return '<section class="audit" aria-label="سجل المراجعة"><h3>سجل المراجعة</h3>' +
      "<p style=\"margin:0\">بماذا فُحصت هذه المسودة بالضبط. سجل مراجعة، لا شهادة صحة.</p><dl>" +
      "<dt>ملف المرجعية</dt><dd>" + esc(m.manifest.id) + " · بصمة " + esc(m.manifest.sha256.slice(0, 16)) + "</dd>" +
      "<dt>جدول القواعد</dt><dd>" + esc(m.policy_version) + "</dd>" +
      "<dt>النموذج</dt><dd>" + esc(m.llm === "none" ? "بلا نموذج (المسار الحتمي)" : m.llm) + "</dd>" +
      "<dt>التعليمات</dt><dd>" + esc(pv || "—") + "</dd>" +
      "<dt>الزمن والكلفة</dt><dd>" + (m.duration_ms / 1000).toFixed(1) + " ث · " + m.llm_calls + " نداء · " + (m.prompt_tokens + m.completion_tokens) + " رمز</dd>" +
      "<dt>إصدار سديد</dt><dd>" + esc(m.saadeed_version) + " · مخطط التقرير " + esc(rep.schema_version) + "</dd></dl>" + nc + warn +
      (LIVE ? '<div><button type="button" id="print">اطبع سجل المراجعة</button></div>' : "") + "</section>";
  }

  function claimsAr(n) {
    if (n === 1) return "ادعاء واحد";
    if (n === 2) return "ادعاءان";
    if (n >= 3 && n <= 10) return n + " ادعاءات";
    return n + " ادعاءً";
  }

  function render(text, rep, provisional) {
    current = { text: text, report: rep, provisional: provisional };
    var el = $("#report");
    el.hidden = false;
    var bb = rep.summary.by_bucket;
    var chips = ["NEEDS_VERIFICATION", "REFER", "NOT_CHECKED", "SUPPORTED_BY_SOURCES"].map(function (k) {
      var b = BUCKETS[k];
      return '<span class="chip b-' + b.cls + '"><b>' + (bb[k] || 0) + "</b> " + b.ar + "</span>";
    }).join("");
    var byId = {};
    rep.findings.forEach(function (f) { byId[f.id] = f; });
    var risky = rep.top_risks.map(function (id) { return byId[id]; }).filter(Boolean);
    var rest = rep.findings.filter(function (f) { return rep.top_risks.indexOf(f.id) < 0; });
    var idle = rest.filter(function (f) { return f.bucket === "NOT_CHECKED"; });
    var ok = rest.filter(function (f) { return f.bucket === "SUPPORTED_BY_SOURCES"; });

    var cards = "";
    if (risky.length) cards += '<p class="group-title">أخطر المواضع أولًا</p>' + risky.map(cardHTML).join("");
    if (idle.length) cards += '<p class="group-title">لم يُفحص</p>' + idle.map(cardHTML).join("");
    if (ok.length) {
      cards += '<details class="supported"' + (risky.length ? "" : " open") + "><summary>تؤيده المصادر (" + ok.length +
        ")</summary>" + ok.map(cardHTML).join("") + "</details>";
    }
    if (!rep.findings.length) cards = '<p class="lede">لم يجد سديد ادعاءً قابلًا للفحص في هذا النص. وعدم التنبيه لا يعني الصحة.</p>';

    el.innerHTML =
      '<div class="summary"><span class="total">خريطة الثغور: ' + claimsAr(rep.summary.total_claims) + " <small>في " + rep.draft.word_count + " كلمة</small></span>" +
      '<span class="tally">' + chips + "</span>" +
      (provisional ? '<span class="provisional">نتائج أولية من المسار الحتمي: الآيات والأحاديث. والتقرير الكامل في الطريق…</span>' : "") + "</div>" 
      (rep.meta.degraded ? '<div class="degraded" role="alert"><strong>المراجعة ناقصة:</strong> تعذّر نموذج الذكاء الاصطناعي' +
        ((rep.meta.warnings || []).length ? " (" + esc(rep.meta.warnings[0].replace(/^[^:]*:\s*/, "")) + ")" : "") +
        '. فُحصت الآيات والأحاديث المعلَّمة وحدها، ولم تُستخرج الأقوال والأرقام والإجماع والتعميم. أعد المحاولة بعد قليل.</div>' : "") +
      ribbonHTML(rep) +
      '<div class="folio"><div class="matn" id="matn"><span class="lbl">مسودتك. انقر الموضع المعلَّم لترى ملاحظته</span>' +
      matnHTML(text, rep) + '</div><div class="hawashi" id="hawashi">' + cards + "</div></div>" +
      auditHTML(rep);
  }

  function flash(node) {
    if (!node) return;
    node.classList.remove("flash");
    void node.offsetWidth;
    node.classList.add("flash");
  }
  function gotoCard(id) {
    var card = document.getElementById("card-" + id);
    if (!card) return;
    var det = card.closest("details");
    if (det) det.open = true;
    card.scrollIntoView({ behavior: "smooth", block: "start" });
    card.focus({ preventScroll: true });
    flash(card);
  }
  function gotoMark(id) {
    var marks = document.querySelectorAll("#matn mark.hl");
    for (var i = 0; i < marks.length; i++) {
      if ((" " + marks[i].dataset.f + " ").indexOf(" " + id + " ") >= 0) {
        marks[i].scrollIntoView({ behavior: "smooth", block: "center" });
        flash(marks[i]);
        return;
      }
    }
  }

  document.addEventListener("click", function (ev) {
    var t = ev.target;
    var mark = t.closest && t.closest("mark.hl");
    if (mark) { gotoCard(mark.dataset.f.split(" ")[0]); return; }
    var q = t.closest && t.closest(".t-draft");
    if (q) { gotoMark(q.dataset.goto); return; }
    if (t.id === "print") window.print();
  });
  document.addEventListener("keydown", function (ev) {
    if ((ev.key === "Enter" || ev.key === " ") && ev.target.matches && ev.target.matches("mark.hl")) {
      ev.preventDefault();
      ev.target.click();
    }
  });

  /* ───────────── التغطية ───────────── */
  function renderCoverage(cov) {
    var counts = {};
    (cov.sources || []).forEach(function (s) { counts[s.id] = s; });
    var rows = cov.connectors.map(function (c) {
      var s = counts[c.id];
      return "<tr><td>" + esc(c.name_ar) + "</td><td><strong>" + esc(c.role_ar || ROLE_AR[c.role]) + "</strong><br><small>" +
        esc(ROLE_MEANING[c.role] || "") + '</small></td><td class="num">' + (s ? s.count.toLocaleString("ar") : "—") +
        "</td><td>" + esc(c.license) + "</td></tr>";
    }).join("");
    $("#coverage-body").innerHTML =
      '<div class="table-wrap"><table><thead><tr><th>المصدر</th><th>دوره: ما يجوز له أن يقرره</th><th class="num">العدد</th><th>الرخصة</th></tr></thead><tbody>' +
      rows + "</tbody></table></div>" +
      '<p class="lede">كل مصدر «وصلة» تُفصل أو تُستبدل من ملف المرجعية دون تعديل الكود. والملف الحالي: ' + esc(cov.manifest.id) +
      "، وبصمته " + esc(cov.manifest.sha256.slice(0, 12)) + " في كل تقرير.</p>" +
      '<h3 style="margin-top:12px">ما لا يفعله سديد</h3><ul class="plain">' +
      cov.policies.map(function (p) { return "<li>" + esc(p) + "</li>"; }).join("") + "</ul>";
  }

  /* ───────────── النتائج ───────────── */
  function pct(v) { return v == null ? "—" : (v * 100).toFixed(1) + "%"; }
  function renderResults(res) {
    var S = res.systems.saadeed, B = res.systems.B0;
    var rows = [
      ["الكشف: المعيب نُبّه عليه", pct(S.detection), pct(B.detection)],
      ["الإنذار الكاذب على السليم", pct(S.false_alarm), pct(B.false_alarm)],
      ["صحة التنبيه", pct(S.precision), pct(B.precision)],
      ["الحالات الحرجة الفائتة", S.critical_missed + " من " + S.critical_total, B.critical_missed + " من " + B.critical_total],
      ["مصادر مختلقة", String(S.fabricated_citations), String(B.fabricated_citations)],
      ["اتهام حديث صحيح بالضعف", String(S.false_accusation_H8), String(B.false_accusation_H8)],
      ["الإحالة الملزمة (فتوى، خلاف)", pct(S.mandatory_referral), pct(B.mandatory_referral)]
    ].map(function (r) {
      return "<tr><td>" + r[0] + '</td><td class="num"><strong>' + r[1] + '</strong></td><td class="num">' + r[2] + "</td></tr>";
    }).join("");
    var mc = res.mcnemar ? "<p>أصاب سديد وحده في " + res.mcnemar.saadeed_only + " حالة، والنموذج العام وحده في " + res.mcnemar.b0_only +
      " (اختبار McNemar الدقيق: p = " + res.mcnemar.p + ").</p>" : "";
    $("#results-body").innerHTML =
      '<p class="lede" style="margin:0 0 10px">قسنا سديد مقابل النموذج العام وحده بتعليمات جيدة، لأنه البديل الحقيقي للخطيب. والبروتوكول مسجّل قبل أي تشغيل.</p>' +
      '<div class="table-wrap"><table><thead><tr><th>المقياس</th><th class="num">سديد</th><th class="num">النموذج العام وحده</th></tr></thead><tbody>' +
      rows + "</tbody></table></div>" + mc +
      '<ul class="plain"><li>مجموعة التطوير: ' + res.n_cases + " حالة في " + res.carriers + " نصًا حاملًا. وأرقام العرض النهائية من مجموعة test المجمّدة.</li>" +
      "<li>النموذج في هذا التقييم: " + esc(res.model) + "، وكل نداء مسجّل يُعاد دون مفتاح.</li>" +
      "<li>«لم يُعثر عليه» لا تعني «لا يصح»: حدود سديد حدود مصادره.</li></ul>";
  }

  /* ───────────── عن سديد: يُحمَّل عند الفتح ───────────── */
  function lazy(detailsId, live, embedded, file, renderFn, bodyId) {
    var d = $("#" + detailsId), done = false;
    d.addEventListener("toggle", function () {
      if (!d.open || done) return;
      done = true;
      (LIVE ? getJSON(live) : Promise.resolve(EMBED && EMBED[embedded]).then(function (x) { return x || getJSON(file); }))
        .then(renderFn).catch(function () { $("#" + bodyId).innerHTML = '<p class="status err">تعذّر التحميل.</p>'; });
    });
  }

  function start() {
    $("#run").addEventListener("click", runReview);
    $("#clear").addEventListener("click", function () {
      $("#draft").value = ""; updateCounter(); setStatus(""); $("#report").hidden = true; current = null;
      $("#example-note").hidden = true;
    });
    $("#draft").addEventListener("input", updateCounter);
    lazy("about-results", "v1/results", "results", "data/results.json", renderResults, "results-body");
    lazy("about-coverage", "v1/coverage", "coverage", "data/coverage.json", renderCoverage, "coverage-body");
    detectLive().then(function (live) {
      LIVE = live;
      return loadExampleIndex();
    }).then(function (list) {
      renderExampleButtons(list);
      if (list.length) showExample(list[0].id);
    }).catch(function () {});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
