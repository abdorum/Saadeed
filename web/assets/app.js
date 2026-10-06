/* سديد — منطق الواجهة. JavaScript صرف بلا مكتبات ولا خطوة بناء (ADR-0012).
   - ثلاث صفحات بالروابط الداخلية: #review و#settings و#faq.
   - «المتن والحاشية»: المسودة في الوسط كما هي، وما يحتاج الانتباه على يمينها، وما تؤيده المصادر على يسارها.
   - الفحص السريع (المسار الحتمي) يُعرض أولًا ويمرّ على الفقرات، ثم يحلّ محله التقرير الكامل.
   - الحالة والإجراء والشرح كلها من التقرير (جدول القواعد والقوالب)، والواجهة لا تحكم بشيء.
   - كل نص من المسودة أو المصدر يُهرَّب قبل العرض. ومفتاح المستخدم في sessionStorage فقط. */
(function () {
  "use strict";

  var $ = function (s, el) { return (el || document).querySelector(s); };
  var $$ = function (s, el) { return Array.prototype.slice.call((el || document).querySelectorAll(s)); };
  var esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  var EMBED = window.SAADEED_DATA || null; // المعاينة الثابتة: البيانات مضمّنة في الصفحة
  /* عنوان الـ API: من <meta name="saadeed-api"> حين تُستضاف الواجهة منفصلة (HF)، وإلا فالرابط نفسه. */
  var API = (function () { var m = document.querySelector('meta[name="saadeed-api"]'); return m && m.content ? m.content.replace(/\/?$/, "/") : ""; })();
  var LIVE = false;
  var HEALTH = null;
  var MAX_WORDS = 3000, MIN_WORDS = 8;
  var REDUCE = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  var ROLE_AR = {
    REFERENCE_TEXT: "النص المعتمد",
    AUTHENTIC: "مصدر احتجاج",
    RULING: "حكم منقول",
    LOCATE: "موضع وروده، دون حكم",
    LINK: "رابط بحث"
  };
  var RANK = { crit: 0, attn: 1, refer: 2, idle: 3, ok: 4 };
  /* كل صنف في التقرير معرَّف هنا صراحةً، فلا يمرّ صنف جديد بلا عرض (tests/unit/test_extensibility.py) */
  var BUCKETS = {
    NEEDS_VERIFICATION: "attn",   // ويصير «crit» إن كان أثر الخطأ حرجًا
    REFER: "refer",
    NOT_CHECKED: "idle",
    SUPPORTED_BY_SOURCES: "ok"
  };
  /* شريط نوع الفقرة على حافة الورقة: لون للآية والحديث والأقوال، ولا شيء لما سواها */
  var KIND_VAR = {
    QURAN: "--k-quran", HADITH: "--k-hadith", ATHAR: "--k-athar", SCHOLAR: "--k-scholar",
    DUA: "--k-dua", POETRY: "--k-poetry", STORY: "--k-story", RULING: "--k-ruling",
    FACT: "--k-fact", EXHORTATION: "--k-exhortation", OTHER: "--k-other", UNLABELED: "--k-unlabeled"
  };
  function kindOn(s) {
    var v = KIND_VAR[s.dataset.k] || "--k-unlabeled";
    s.style.setProperty("--stripe", "var(" + v + ")");
    s.classList.add("kinded", "k-" + s.dataset.k);
  }

  function words(t) { var m = String(t).trim().match(/\S+/g); return m ? m.length : 0; }
  /* العدد مع المعدود بالعربية: 1 و2 بصيغتهما، و3–10 جمع، و11 فما فوق مفرد منصوب */
  function ar(n, one, two, few, many) {
    if (n === 1) return one;
    if (n === 2) return two;
    return n + " " + (n % 100 >= 3 && n % 100 <= 10 ? few : many);
  }

  function getJSON(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }
  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body)
    }).catch(function () {
      throw new Error("تعذّر الاتصال بخادم سديد. تحقق من اتصالك بالإنترنت، ثم أعد المحاولة.");
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.ok) return j;
        var d = j.detail;
        if (Array.isArray(d)) d = "المسودة غير مقبولة. تأكد أنها نص عادي لا يتجاوز " + MAX_WORDS + " كلمة.";
        if (r.status === 429) d = d || "طلبات كثيرة في دقيقة واحدة. انتظر قليلًا ثم أعد المحاولة.";
        var e = new Error(d || "تعذّرت المراجعة بسبب خلل في الخادم (" + r.status + "). أعد المحاولة بعد قليل.");
        e.status = r.status;
        throw e;
      });
    });
  }

  /* ═════════════ الإعدادات: في هذه النافذة وحدها ═════════════ */
  var SKEY = "saadeed.llm";
  function loadSettings() {
    try { return JSON.parse(sessionStorage.getItem(SKEY)) || { provider: "server" }; }
    catch (e) { return { provider: "server" }; }
  }
  function saveSettings(s) {
    try { if (s.provider === "server") sessionStorage.removeItem(SKEY); else sessionStorage.setItem(SKEY, JSON.stringify(s)); }
    catch (e) { /* المتصفح يمنع التخزين: تبقى الإعدادات لهذه الصفحة فقط */ }
    SETTINGS = s;
  }
  var SETTINGS = loadSettings();
  function llmChoice(s) {
    s = s || SETTINGS;
    if (!s || s.provider === "server") return null;
    var c = { provider: s.provider };
    if (s.model) c.model = s.model;
    if (s.api_key) c.api_key = s.api_key;
    return c;
  }
  function serverModel() {
    return HEALTH && HEALTH.llm && HEALTH.llm !== "none" ? HEALTH.llm.replace(":", " · ") : null;
  }

  /* ═════════════ التنقل ═════════════ */
  var hasResult = false;
  function show(view) {
    ["compose", "result", "settings", "faq"].forEach(function (v) { $("#v-" + v).hidden = v !== view; });
    var page = view === "compose" || view === "result" ? "review" : view;
    $$(".top nav a").forEach(function (a) {
      if (a.dataset.page === page) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    if (view === "result") requestAnimationFrame(place);
    if (view === "settings") fillSettings();
  }
  function route() {
    var h = (location.hash || "#review").slice(1);
    if (h === "settings" || h === "faq") show(h);
    else show(hasResult ? "result" : "compose");
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);

  /* ═════════════ الإدخال ═════════════ */
  function updateCount() {
    var n = words($("#draft").value);
    $("#wc").textContent = n + " كلمة" + (n > MAX_WORDS ? " · أطول من الحد (" + MAX_WORDS + ")" : "");
    return n;
  }
  function composeMsg(text) {
    var m = $("#compose-msg");
    m.hidden = !text;
    m.className = "msg err";
    m.innerHTML = text || "";
  }

  /* ═════════════ الأمثلة ═════════════ */
  var EXAMPLES = [];
  function loadExampleIndex() {
    if (EMBED && EMBED.examples) return Promise.resolve(EMBED.examples);
    return getJSON("examples/index.json");
  }
  function loadExample(id) {
    if (EMBED && EMBED.examples) {
      for (var i = 0; i < EMBED.examples.length; i++) if (EMBED.examples[i].id === id) return Promise.resolve(EMBED.examples[i]);
    }
    return getJSON("examples/" + encodeURIComponent(id) + ".json");
  }
  function showExample(id) {
    var run = ++RUN;
    loadExample(id).then(function (ex) {
      if (run !== RUN) return;
      $("#draft").value = ex.text;
      updateCount();
      composeMsg("");
      startResult(ex.text, ex.title);
      var note = $("#example-note");
      note.hidden = false;
      note.innerHTML = "مثال جاهز بتقرير محفوظ: " + esc(ex.note) +
        (ex.source_url ? ' <a href="' + esc(ex.source_url) + '" target="_blank" rel="noopener">المصدر</a>' : "");
      render(ex.text, ex.report, { reading: true });
      sweep(run).then(function () {
        if (run !== RUN) return;
        finishReading();
        setStatus("اكتملت المراجعة. انقر رقمًا في النص أو حاشيةً لترى السبب والمصدر.");
      });
    }).catch(function () { composeMsg("تعذّر تحميل المثال. أعد تحميل الصفحة ثم حاول مرة أخرى."); });
  }

  /* ═════════════ المراجعة ═════════════ */
  var RUN = 0;          // رقم المحاولة: يُهمل ما يصل من محاولة سابقة
  var CURRENT = null;   // { text, report }

  function setStatus(msg, busy) {
    $("#status").innerHTML = (busy ? '<span class="dot" aria-hidden="true"></span>' : "") + esc(msg || "");
  }
  function startResult(text, title) {
    hasResult = true;
    if (location.hash !== "#review") history.replaceState(null, "", "#review");
    show("result");
    window.scrollTo(0, 0);
    $("#example-note").hidden = true;
    $("#banner").hidden = true;
    $("#audit").hidden = true;
    $("#sum-h").textContent = "يقرأ سديد مسودتك…";
    $("#counts").innerHTML = "";
    $("#m-notes").innerHTML = "";
    $("#doc-t").textContent = title ? "مثال: " + title : "مسودتك";
    $("#doc-w").textContent = words(text) + " كلمة";
    var matn = $("#matn");
    matn.className = "matn reading";
    matn.innerHTML = '<span class="seg">' + esc(text) + "</span>";
    $("#folio").classList.add("reading");
    setStatus("يقرأ سديد مسودتك…", true);
  }

  function runReview() {
    var text = $("#draft").value.replace(/\r\n/g, "\n");
    var n = updateCount();
    if (!text.trim()) { composeMsg("ألصق نص المسودة أولًا، ثم اضغط «راجِع المسودة»."); return; }
    if (n < MIN_WORDS) { composeMsg("النص قصير جدًا. ألصق فقرة كاملة على الأقل ليجد سديد ما يراجعه."); return; }
    if (n > MAX_WORDS) { composeMsg("المسودة أطول من الحد (" + n + " كلمة، والحد " + MAX_WORDS + "). راجعها على أجزاء."); return; }
    if (!LIVE) {
      composeMsg("المراجعة الحية تعمل على الرابط المنشور لسديد. وفي هذه المعاينة جرّب الأمثلة الجاهزة أدناه.");
      return;
    }
    composeMsg("");
    var run = ++RUN;
    var choice = llmChoice();
    startResult(text, null);
    var quickDone = postJSON(API + "v1/reviews", { text: text, mode: "quick" }).then(function (q) {
      if (run !== RUN) return;
      render(text, q, { reading: true, provisional: true });
      return sweep(run);
    }).catch(function () { /* الفحص السريع تمهيد؛ التقرير الكامل هو المرجع */ });
    var body = { text: text, mode: "full" };
    if (choice) body.llm = choice;
    var full = postJSON(API + "v1/reviews", body);
    quickDone.then(function () {
      if (run !== RUN) return;
      if (CURRENT && CURRENT.provisional) {
        finishReading();
        setStatus("ظهرت الآيات والأحاديث. ويكمل سديد الأقوال والأرقام ودعاوى الإجماع…", true);
      }
    });
    Promise.all([full, quickDone]).then(function (res) {
      if (run !== RUN) return;
      var rep = res[0];
      render(text, rep, { reading: false });
      finishReading();
      var nc = rep.summary.not_checked || [];
      setStatus(nc.length ? "اكتملت المراجعة، وبعضها لم يُفحص كما هو مبيّن أعلاه." :
        "اكتملت المراجعة. انقر رقمًا في النص أو حاشيةً لترى السبب والمصدر.");
    }).catch(function (e) {
      if (run !== RUN) return;
      quickDone.then(function () {
        if (run !== RUN) return;
        var keyHint = e.status === 400 ? ' <a href="#settings">افتح الإعدادات</a>' : "";
        if (CURRENT && CURRENT.provisional) {
          finishReading();
          CURRENT.provisional = false;
          banner("err", "<strong>المراجعة ناقصة:</strong> " + esc(e.message) + keyHint +
            " والمعروض نتائج الآيات والأحاديث المعلَّمة وحدها.");
          setStatus("");
          $("#sum-h").textContent = summaryTitle(CURRENT.report);
        } else {
          $("#folio").classList.remove("reading");
          $("#matn").classList.remove("reading");
          banner("err", "<strong>تعذّرت المراجعة:</strong> " + esc(e.message) + keyHint);
          $("#sum-h").textContent = "لم تكتمل المراجعة";
          setStatus("");
        }
      });
    });
  }

  function banner(kind, html) {
    var b = $("#banner");
    b.className = "banner" + (kind ? " " + kind : "");
    b.innerHTML = html;
    b.hidden = !html;
  }

  /* ما لم يُفحص، كما يصفه الخادم */
  function degradedWhat(rep) {
    var why = (rep.meta.warnings || []).filter(function (w) { return /^تعذّر/.test(w); })[0];
    why = why ? why.replace(/^[^:]*:\s*/, "") : "";
    var nc = rep.summary.not_checked || [];
    return (why ? "تعذّر نموذج الذكاء الاصطناعي (" + why + ")، " : "") +
      (nc.length ? nc.join("؛ و") : "والمعروض نتائج الآيات والأحاديث المعلَّمة وحدها") + ".";
  }

  /* ═════════════ التقرير ═════════════ */
  function stOf(f) {
    var st = BUCKETS[f.bucket] || "idle";
    return st === "attn" && f.severity === "CRITICAL" ? "crit" : st;
  }
  function stateLabel(f) {
    var L = f.labels_ar || {}, st = f._st;
    if (st === "ok" || st === "refer" || st === "idle") return L.bucket;
    var es = f.evidence_status === "OUT_OF_SCOPE" ? L.bucket : L.evidence_status;
    return st === "crit" ? "حرج · " + es : es;
  }
  function shortCite(c) { return String(c || "").replace(/\s*\(بترقيم[^)]*\)\s*$/, ""); }

  function summaryTitle(rep) {
    var F = rep.findings || [];
    var need = F.filter(function (f) { return f._st !== "ok"; }).length;
    if (!F.length) return (rep.summary.not_checked || []).length ? "لم يجد سديد فيما فحصه ما يُقابَل بالمصادر" : "لم يجد سديد في المسودة ما يُقابَل بالمصادر";
    var partial = (rep.summary.not_checked || []).length > 0;
    if (!need) return partial ? "لم يجد سديد ما يستدعي المراجعة فيما فحصه" : "لم يجد سديد ما يستدعي المراجعة";
    return ar(need, "موضع واحد يحتاج مراجعتك", "موضعان يحتاجان مراجعتك", "مواضع تحتاج مراجعتك", "موضعًا يحتاج مراجعتك");
  }

  function render(text, rep, opts) {
    opts = opts || {};
    var F = (rep.findings || []).slice().sort(function (a, b) { return a.claim.span.start - b.claim.span.start; });
    F.forEach(function (f, i) { f._n = i + 1; f._st = stOf(f); });
    rep.findings = F;
    CURRENT = { text: text, report: rep, provisional: !!opts.provisional };

    $("#matn").innerHTML = matnHTML(text, rep);
    $("#matn").className = "matn" + (opts.reading ? " reading" : "");
    $("#folio").classList.toggle("reading", !!opts.reading);
    if (!opts.reading) $$("#matn .seg").forEach(kindOn);

    $("#m-notes").innerHTML = F.length ? F.map(noteHTML).join("") :
      '<p class="margin-empty">' + (opts.provisional ? "…" : "لا ملاحظات على هذه المسودة.") + "</p>";

    renderSummary(rep, opts.provisional || opts.reading);

    var msgs = [];
    if (!opts.provisional) {
      var nc = rep.summary.not_checked || [];
      var mineNone = SETTINGS.provider === "none";
      if (mineNone && nc.length) msgs.push(["info", "اخترت في الإعدادات العمل بلا نموذج، ففُحصت الآيات والأحاديث المعلَّمة وحدها. <a href=\"#settings\">غيّر الإعدادات</a>"]);
      else if (rep.meta.degraded || nc.length) {
        var keyBad = (rep.meta.warnings || []).some(function (w) { return /مفتاح/.test(w); });
        msgs.push(["", "<strong>المراجعة ناقصة:</strong> " + esc(degradedWhat(rep)) +
          (keyBad && SETTINGS.api_key ? ' راجع مفتاحك في <a href="#settings">الإعدادات</a>، أو ارجع إلى نموذج الخادم.' : " أعد المحاولة بعد قليل لاستكمال الفحص.")]);
      }
      (rep.meta.warnings || []).forEach(function (w) { if (/^النص قصير/.test(w)) msgs.push(["info", esc(w)]); });
    }
    if (msgs.length) banner(msgs[0][0], msgs.map(function (m) { return m[1]; }).join("<br>"));
    else banner("", "");

    $("#audit").hidden = !!opts.provisional;
    $("#audit-body").innerHTML = auditHTML(rep);
    if (!opts.reading) requestAnimationFrame(place);
  }

  function renderSummary(rep, pending) {
    var F = rep.findings || [];
    var c = { crit: 0, attn: 0, refer: 0, idle: 0, ok: 0 };
    F.forEach(function (f) { c[f._st]++; });
    var chips = [];
    if (c.crit) chips.push(["crit", ar(c.crit, "موضع حرج", "موضعان حرجان", "مواضع حرجة", "موضعًا حرجًا")]);
    if (c.attn) chips.push(["attn", ar(c.attn, "واحد يتطلب تحققًا", "اثنان يتطلبان تحققًا", "تتطلب تحققًا", "يتطلب تحققًا")]);
    if (c.refer) chips.push(["refer", ar(c.refer, "إحالة إلى مختص", "إحالتان إلى مختص", "إحالات إلى مختص", "إحالة إلى مختص")]);
    if (c.idle) chips.push(["idle", ar(c.idle, "موضع لم يُفحص", "موضعان لم يُفحصا", "مواضع لم تُفحص", "موضعًا لم يُفحص")]);
    if (c.ok) chips.push(["ok", ar(c.ok, "موضع تؤيده المصادر", "موضعان تؤيدهما المصادر", "مواضع تؤيدها المصادر", "موضعًا تؤيده المصادر")]);
    $("#counts").innerHTML = pending ? "" : chips.map(function (x) {
      return '<span class="count ' + x[0] + '"><i aria-hidden="true"></i>' + x[1] + "</span>";
    }).join("");
    $("#sum-h").textContent = pending ? "يقرأ سديد مسودتك…" : summaryTitle(rep);

  }

  /* المتن: الفقرات بأنواعها، ومواضع الملاحظات، ورقم كل ملاحظة بعد موضعها */
  function matnHTML(text, rep) {
    var segs = (rep.draft_map || []).slice().sort(function (a, b) { return a.span.start - b.span.start; });
    var F = rep.findings, L = text.length;
    var pts = [0, L];
    segs.forEach(function (s) { pts.push(s.span.start, s.span.end); });
    F.forEach(function (f) { pts.push(f.claim.span.start, f.claim.span.end); });
    pts = pts.map(function (p) { return Math.max(0, Math.min(L, p)); })
      .filter(function (v, i, a) { return a.indexOf(v) === i; }).sort(function (a, b) { return a - b; });
    var out = "", openSeg = null;
    for (var i = 0; i < pts.length - 1; i++) {
      var a = pts[i], b = pts[i + 1];
      var seg = null;
      for (var k = 0; k < segs.length; k++) if (segs[k].span.start <= a && segs[k].span.end >= b) { seg = segs[k]; break; }
      if (seg !== openSeg) {
        if (openSeg) out += "</span>";
        if (seg) out += '<span class="seg" data-k="' + esc(seg.kind) + '" data-label="' + esc(seg.kind_ar || "") + '">';
        openSeg = seg;
      }
      // الأسطر الفارغة المتتالية تُعرض سطرًا فارغًا واحدًا (العرض وحده؛ مواضع النص لا تتغير)
      var piece = esc(text.slice(a, b).replace(/\n[ \t]*(?:\n[ \t]*){2,}/g, "\n\n"));
      var cov = F.filter(function (f) { return f.claim.span.start <= a && f.claim.span.end >= b; });
      if (cov.length) {
        var p = cov.slice().sort(function (x, y) {
          return RANK[x._st] - RANK[y._st] || (x.claim.span.end - x.claim.span.start) - (y.claim.span.end - y.claim.span.start);
        })[0];
        out += '<mark class="c s-' + p._st + '" data-id="' + p.id + '" data-ids="' +
          cov.map(function (f) { return f.id; }).join(" ") + '">' + piece + "</mark>";
      } else out += piece;
      F.forEach(function (f) {
        if (Math.min(L, f.claim.span.end) === b) {
          out += '<button type="button" class="n s-' + f._st + '" data-id="' + f.id + '" aria-label="الملاحظة ' + f._n + ': ' +
            esc(stateLabel(f)) + '">' + f._n + "</button>";
        }
      });
    }
    if (openSeg) out += "</span>";
    return out;
  }

  function sourceHTML(f) {
    var ev = f.evidence || [];
    if (!ev.length) {
      return '<div class="src"><div class="cite"><span>لم يجد سديد في مصادره ما يكفي للحكم في هذا الموضع' +
        (f.claim.type === "QURAN_QUOTE" || f.claim.type === "HADITH_QUOTE" ? "." : "، ولم تذكر المسودة مصدره.") + "</span></div></div>";
    }
    return ev.map(function (e) {
      var link = e.ref.url ? '<a href="' + esc(e.ref.url) + '" target="_blank" rel="noopener">' + (e.role === "LINK" ? "افتح البحث" : "افتح المصدر") + "</a>" : "";
      var head = '<div class="cite"><span>' + (e.role === "REFERENCE_TEXT" && f.claim.type.indexOf("QURAN") === 0 ? "المصحف · " : "") +
        esc(shortCite(e.ref.citation)) + (e.role !== "REFERENCE_TEXT" ? ' <span class="role">(' + esc(ROLE_AR[e.role] || e.role) + ")</span>" : "") +
        "</span>" + link + "</div>";
      var body = "";
      if (e.role === "REFERENCE_TEXT" && f.claim.type.indexOf("QURAN") === 0) {
        var d = e.diff || [];
        if (d.some(function (o) { return o.op !== "equal"; })) {
          body = '<div class="draftline">في مسودتك: ' + d.map(function (o) {
            return o.op === "equal" ? esc(o.draft) : o.draft ? "<del>" + esc(o.draft) + "</del>" : "";
          }).join(" ") + "</div>" +
            '<div class="ayah">﴿' + d.map(function (o) {
              return o.op === "equal" ? esc(o.source) : o.source ? "<ins>" + esc(o.source) + "</ins>" : "";
            }).join(" ") + "﴾</div>";
        } else if (e.text) {
          body = '<div class="ayah">﴿' + esc(String(e.text).replace(/\s*\(\d+\)\s*$/, "")) + "﴾</div>";
        }
      } else if (e.text && e.role !== "LINK") {
        body = '<div class="hadith-text">' + esc(e.text) + "</div>";
      }
      return '<div class="src">' + head + body + "</div>";
    }).join("");
  }

  function noteHTML(f) {
    var L = f.labels_ar || {}, ok = f._st === "ok";
    var cite = ok && f.evidence && f.evidence[0] ? shortCite(f.evidence[0].ref.citation) : "";
    return '<div class="note s-' + f._st + '" data-id="' + f.id + '" tabindex="0" role="button" aria-expanded="false">' +
      '<div class="note-h"><span class="n s-' + f._st + '" aria-hidden="true">' + f._n + '</span><span class="state">' +
      esc(stateLabel(f)) + '</span><span class="kind">' + esc(L.claim_type || "") + "</span></div>" +
      '<div class="q">' + (ok && cite ? esc(cite) : "«" + esc(f.claim.text) + "»") + "</div>" +
      (ok ? "" : '<div class="act">' + esc(L.action || "") + "</div>") +
      '<dl class="more">' +
      (ok && cite ? "<div><dt>العبارة</dt><dd>«" + esc(f.claim.text) + "»</dd></div>" : "") +
      "<div><dt>لماذا ظهرت هذه الملاحظة</dt><dd>" + esc(f.explanation) + "</dd></div>" +
      ((f.notes || []).length ? "<div><dt>تنبيه</dt><dd>" + f.notes.map(esc).join("<br>") + "</dd></div>" : "") +
      "<div><dt>المصدر</dt><dd>" + sourceHTML(f) + "</dd></div>" +
      (ok ? "" : '<div><dt>ما العمل: ' + esc(L.action || "") + '</dt><dd class="next">' + esc(f.next_step) + "</dd></div>") +
      (f.suggestion ? '<div class="sugg"><dt>اقتراح صياغة (مولَّد)، راجعه قبل اعتماده</dt><dd>' + esc(f.suggestion) + "</dd></div>" : "") +
      '<div><button type="button" class="close">إغلاق</button> · <button type="button" class="close goto">موضعها في النص</button></div>' +
      "</dl></div>";
  }

  function auditHTML(rep) {
    var m = rep.meta || {};
    var pv = Object.keys(m.prompt_versions || {}).map(function (k) { return k + " " + m.prompt_versions[k]; }).join("، ");
    var rows = [
      ["إصدار سديد", m.saadeed_version],
      ["النموذج", m.llm || "بلا نموذج"],
      ["إصدارات التعليمات", pv || "—"],
      ["جدول القواعد", m.policy_version],
      ["ملف المرجعية", m.manifest ? m.manifest.id + " · " + String(m.manifest.sha256 || "").slice(0, 12) : "—"],
      ["المدة", m.duration_ms != null ? (m.duration_ms / 1000).toFixed(1) + " ثانية" : "—"],
      ["نداءات النموذج", m.llm_calls != null ? m.llm_calls : "—"]
    ];
    var warn = (m.warnings || []).length ? "<dt>تنبيهات</dt><dd>" + m.warnings.map(esc).join("<br>") + "</dd>" : "";
    return "<dl>" + rows.map(function (r) { return "<dt>" + r[0] + "</dt><dd>" + esc(r[1]) + "</dd>"; }).join("") + warn + "</dl>";
  }

  /* ═════════════ الفحص الحي: يمرّ سديد على الفقرات واحدة واحدة ═════════════ */
  function sweep(run) {
    var segs = $$("#matn .seg");
    var step = REDUCE ? 0 : Math.max(110, Math.min(380, 3000 / Math.max(1, segs.length)));
    return new Promise(function (resolve) {
      var i = 0;
      (function next() {
        if (run !== RUN) return resolve();
        if (i > 0) segs[i - 1].classList.remove("scan");
        if (i >= segs.length) return resolve();
        var s = segs[i];
        s.classList.add("read", "scan");
        kindOn(s);
        var lbl = s.dataset.label && s.dataset.k !== "UNLABELED" ? ": " + s.dataset.label : "";
        setStatus("يقرأ الفقرة " + (i + 1) + " من " + segs.length + lbl, true);
        i++;
        setTimeout(next, step);
      })();
    });
  }
  function finishReading() {
    $$("#matn .seg").forEach(function (s) { s.classList.remove("scan"); kindOn(s); });
    $("#matn").classList.remove("reading");
    $("#folio").classList.remove("reading");
    if (CURRENT && !CURRENT.provisional) renderSummary(CURRENT.report, false);
    place();
  }

  /* ═════════════ الحاشية بمحاذاة موضعها (الشاشات الواسعة) ═════════════ */
  function wide() { return window.matchMedia("(min-width: 1151px)").matches; }
  function place() {
    ["#m-notes"].forEach(function (sel) {
      var col = $(sel);
      if (!col) return;
      var notes = $$(".note", col);
      if (!wide() || $("#v-result").hidden) {
        col.classList.remove("placed"); col.style.minHeight = "";
        notes.forEach(function (n) { n.style.top = ""; });
        return;
      }
      col.classList.add("placed");
      var base = col.getBoundingClientRect().top;
      // المسافات من getBoundingClientRect بعد المقياس، وstyle.top قبله: نقسم على المقياس
      var z = parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
      var y = 0;
      notes.forEach(function (n) {
        var m = $('.c[data-ids~="' + n.dataset.id + '"]') || $('.n[data-id="' + n.dataset.id + '"]');
        var want = m ? (m.getBoundingClientRect().top - base) / z - 4 : y;
        var top = Math.max(want, y);
        n.style.top = top + "px";
        y = top + n.offsetHeight + 10;
      });
      col.style.minHeight = y + "px";
    });
  }
  window.addEventListener("resize", function () { requestAnimationFrame(place); });

  /* ═════════════ الربط بين المتن والحاشية ═════════════ */
  function related(id) {
    return $$('.note[data-id="' + id + '"], .n[data-id="' + id + '"], .c[data-ids~="' + id + '"]');
  }
  function hot(id, on) { related(id).forEach(function (el) { el.classList.toggle("hot", on); }); }
  function inView(el) { var r = el.getBoundingClientRect(); return r.top > 70 && r.bottom < innerHeight - 20; }
  function openNote(id, from) {
    $$(".note.open").forEach(function (n) {
      if (n.dataset.id !== id) { n.classList.remove("open"); n.setAttribute("aria-expanded", "false"); }
    });
    $$(".hot").forEach(function (el) { el.classList.remove("hot"); });
    var note = $('.note[data-id="' + id + '"]');
    if (!note) return;
    note.classList.add("open");
    note.setAttribute("aria-expanded", "true");
    hot(id, true);
    place();
    if (from === "matn" && !inView(note)) note.scrollIntoView({ behavior: REDUCE ? "auto" : "smooth", block: "nearest" });
    if (from === "note" && wide()) showInMatn(id);
  }
  function showInMatn(id) {
    var m = $('.c[data-ids~="' + id + '"]') || $('.n[data-id="' + id + '"]');
    if (m && !inView(m)) m.scrollIntoView({ behavior: REDUCE ? "auto" : "smooth", block: "center" });
  }
  function closeNote(note) {
    note.classList.remove("open");
    note.setAttribute("aria-expanded", "false");
    hot(note.dataset.id, false);
    place();
  }

  document.addEventListener("mouseover", function (e) {
    var t = e.target.closest && e.target.closest("#folio [data-id]");
    if (t) hot(t.dataset.id, true);
  });
  document.addEventListener("mouseout", function (e) {
    var t = e.target.closest && e.target.closest("#folio [data-id]");
    if (!t) return;
    var id = t.dataset.id;
    if (!$('.note.open[data-id="' + id + '"]')) hot(id, false);
  });
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!t.closest || !t.closest("#folio")) return;
    if (t.closest("a")) return;
    var note = t.closest(".note");
    if (t.closest(".goto") && note) { showInMatn(note.dataset.id); hot(note.dataset.id, true); return; }
    if (t.closest(".close") && note) { closeNote(note); return; }
    var mark = t.closest(".n, .c");
    if (mark && !mark.closest(".note")) { openNote(mark.dataset.id, "matn"); return; }
    if (note && !note.classList.contains("open")) openNote(note.dataset.id, "note");
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { var o = $(".note.open"); if (o) closeNote(o); return; }
    if (e.key !== "Enter" && e.key !== " ") return;
    var note = e.target.closest && e.target.closest(".note");
    if (note && e.target === note) { e.preventDefault(); if (note.classList.contains("open")) closeNote(note); else openNote(note.dataset.id, "note"); }
  });

  /* ═════════════ صفحة الإعدادات ═════════════ */
  function fillSettings() {
    var s = SETTINGS;
    $("#set-provider").value = s.provider || "server";
    $("#set-model").value = s.model || "";
    $("#set-key").value = s.api_key || "";
    toggleFields();
    describeNow();
    $("#set-msg").hidden = true;
  }
  function defaultModel(p) {
    var d = HEALTH && HEALTH.providers && HEALTH.providers[p];
    return d ? d.default_model : ({ gemini: "gemini-3.5-flash-lite", groq: "openai/gpt-oss-120b" })[p] || "";
  }
  function toggleFields() {
    var p = $("#set-provider").value;
    var custom = p === "gemini" || p === "groq";
    $("#f-model").hidden = !custom;
    $("#f-key").hidden = !custom;
    if (custom && !$("#set-model").value) $("#set-model").value = defaultModel(p);
  }
  function describeNow() {
    var s = SETTINGS, t;
    if (s.provider === "none") t = "تعمل الآن <b>بلا نموذج</b>: تُطابَق الآيات وتُفحص الأحاديث المعلَّمة، ولا تُستخرج الأقوال والأرقام ودعاوى الإجماع.";
    else if (s.provider === "gemini" || s.provider === "groq") t = "تعمل الآن بـ<b dir=\"ltr\"> " + esc(s.provider + " · " + (s.model || defaultModel(s.provider))) + " </b>" +
      (s.api_key ? "وبمفتاحك المنتهي بـ <b dir=\"ltr\">…" + esc(s.api_key.slice(-4)) + "</b>." : "وبمفتاح الخادم.");
    else t = serverModel() ? "تعمل الآن بنموذج الخادم: <b dir=\"ltr\">" + esc(serverModel()) + "</b>." :
      LIVE ? "نموذج الخادم غير متاح الآن، فتعمل المراجعة بالآيات والأحاديث المعلَّمة وحدها. ويمكنك إدخال مفتاحك أدناه." :
      "هذه معاينة دون خادم. والإعدادات تعمل على الرابط المنشور.";
    $("#set-now").innerHTML = t;
  }
  function readForm() {
    var p = $("#set-provider").value;
    if (p === "server" || p === "none") return { provider: p };
    return { provider: p, model: $("#set-model").value.trim(), api_key: $("#set-key").value.trim() };
  }
  function setMsg(kind, html) {
    var m = $("#set-msg");
    m.className = "msg" + (kind ? " " + kind : "");
    m.innerHTML = html;
    m.hidden = false;
  }
  function initSettings() {
    $("#set-provider").addEventListener("change", function () { $("#set-model").value = ""; toggleFields(); });
    $("#set-show").addEventListener("click", function () {
      var k = $("#set-key"), show = k.type === "password";
      k.type = show ? "text" : "password";
      this.textContent = show ? "إخفاء" : "إظهار";
      this.setAttribute("aria-pressed", String(show));
    });
    $("#set-form").addEventListener("submit", function (e) {
      e.preventDefault();
      saveSettings(readForm());
      describeNow();
      setMsg("ok", "حُفظت الإعدادات، وتُستعمل في مراجعاتك في هذه النافذة.");
    });
    $("#set-reset").addEventListener("click", function () {
      saveSettings({ provider: "server" });
      fillSettings();
      setMsg("ok", "رجعت الإعدادات إلى الافتراضي، ومُسح مفتاحك من هذه النافذة.");
    });
    $("#set-test").addEventListener("click", function () {
      if (!LIVE) { setMsg("err", "اختبار الاتصال يعمل على الرابط المنشور لسديد."); return; }
      var f = readForm(), choice;
      if (f.provider === "server") {
        if (!HEALTH || HEALTH.llm === "none") { setMsg("err", "لا يوجد نموذج مضبوط على الخادم الآن. أدخل مفتاحك لمزوّد تختاره."); return; }
        var parts = HEALTH.llm.split(":");
        choice = { provider: parts[0], model: parts.slice(1).join(":") };
      } else choice = llmChoice(f) || { provider: "none" };
      var btn = this;
      btn.disabled = true;
      setMsg("", "جارٍ الاختبار…");
      postJSON(API + "v1/llm/check", choice).then(function (r) {
        if (r.ok) setMsg("ok", r.model === "none" ? "لا يحتاج هذا الخيار اتصالًا: تعمل المراجعة بالمسار الحتمي." :
          "الاتصال يعمل: <span dir=\"ltr\">" + esc(r.model) + "</span>. لا تنسَ الحفظ.");
        else setMsg("err", "لم ينجح الاتصال: " + esc(r.reason) + ".");
      }).catch(function (e) { setMsg("err", esc(e.message)); })
        .then(function () { btn.disabled = false; });
    });
  }

  /* ═════════════ صفحة س و ج: تُحمَّل الأرقام والمصادر عند الفتح ═════════════ */
  function pct(v) { return v == null ? "—" : (v * 100).toFixed(1) + "%"; }
  function renderResults(res) {
    var S = res.systems.saadeed, B = res.systems.B0;
    var rows = [
      ["المعيب الذي نُبّه عليه", pct(S.detection), pct(B.detection)],
      ["إنذار كاذب على السليم", pct(S.false_alarm), pct(B.false_alarm)],
      ["الحالات الحرجة الفائتة", S.critical_missed + " من " + S.critical_total, B.critical_missed + " من " + B.critical_total],
      ["مصادر مختلقة", String(S.fabricated_citations), String(B.fabricated_citations)],
      ["اتهام حديث صحيح بالضعف", String(S.false_accusation_H8), String(B.false_accusation_H8)]
    ].map(function (r) {
      return "<tr><td>" + r[0] + '</td><td class="num"><b>' + r[1] + '</b></td><td class="num">' + r[2] + "</td></tr>";
    }).join("");
    $("#results-body").innerHTML =
      "<p>قسنا سديد مقابل نموذج ذكاء اصطناعي عام وحده بتعليمات جيدة، لأنه البديل الذي يلجأ إليه الخطيب اليوم. والبروتوكول مسجّل قبل أي تشغيل.</p>" +
      '<div class="table-wrap"><table><thead><tr><th>المقياس</th><th class="num">سديد</th><th class="num">النموذج العام وحده</th></tr></thead><tbody>' +
      rows + "</tbody></table></div>" +
      "<p class=\"fine\">" + res.n_cases + " حالة في " + res.carriers + " نصًا حاملًا (مجموعة التطوير)، والنموذج: <span dir=\"ltr\">" + esc(res.model) +
      "</span>. وكل نداء مسجّل يُعاد دون مفتاح." +
      (res.mcnemar ? " والفرق دال إحصائيًا (McNemar: p = " + res.mcnemar.p + ")." : "") + "</p>";
  }
  function renderCoverage(cov) {
    var counts = {};
    (cov.sources || []).forEach(function (s) { counts[s.id] = s; });
    var rows = cov.connectors.map(function (c) {
      var s = counts[c.id];
      return "<tr><td>" + esc(c.name_ar) + "</td><td>" + esc(c.role_ar || ROLE_AR[c.role] || c.role) + '</td><td class="num">' +
        (s ? Number(s.count).toLocaleString("ar") : "—") + "</td></tr>";
    }).join("");
    $("#coverage-body").innerHTML =
      "<p>لكل مصدر دور يحدد ما يجوز له أن يقرره: المصحف نص معتمد يُطابَق حرفًا بحرف، والصحيحان مصدر احتجاج، وبقية الكتب الستة تخبر بموضع الحديث دون حكم.</p>" +
      '<div class="table-wrap"><table><thead><tr><th>المصدر</th><th>دوره</th><th class="num">العدد</th></tr></thead><tbody>' +
      rows + "</tbody></table></div>" +
      "<p><b>ما لا يفعله سديد:</b></p><ul class=\"plain\">" + cov.policies.map(function (p) { return "<li>" + esc(p) + "</li>"; }).join("") + "</ul>";
  }
  function lazy(detailsId, liveUrl, embedded, file, fn, bodyId) {
    var d = $("#" + detailsId), done = false;
    d.addEventListener("toggle", function () {
      if (!d.open || done) return;
      done = true;
      (LIVE ? getJSON(liveUrl) : Promise.resolve(EMBED && EMBED[embedded]).then(function (x) { return x || getJSON(file); }))
        .then(fn).catch(function () {
          done = false;
          $("#" + bodyId).innerHTML = '<p class="muted">تعذّر التحميل. أغلق السؤال وافتحه مرة أخرى.</p>';
        });
    });
  }

  /* ═════════════ البدء ═════════════ */
  function detectLive() {
    var ctl = "AbortController" in window ? new AbortController() : null;
    var t = setTimeout(function () { if (ctl) ctl.abort(); }, 3000);
    return fetch(API + "v1/health", ctl ? { signal: ctl.signal } : {})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { clearTimeout(t); HEALTH = j && j.ok ? j : null; if (HEALTH && HEALTH.max_words) MAX_WORDS = HEALTH.max_words; return !!HEALTH; })
      .catch(function () { clearTimeout(t); return false; });
  }

  function start() {
    $("#draft").addEventListener("input", function () { updateCount(); composeMsg(""); });
    $("#go").addEventListener("click", runReview);
    $("#clear").addEventListener("click", function () { $("#draft").value = ""; updateCount(); composeMsg(""); $("#draft").focus(); });
    $("#edit").addEventListener("click", function () {
      RUN++;
      if (CURRENT) $("#draft").value = CURRENT.text;
      updateCount();
      hasResult = false;
      show("compose");
      $("#draft").focus();
    });
    $("#new").addEventListener("click", function () {
      RUN++;
      $("#draft").value = "";
      updateCount();
      hasResult = false;
      CURRENT = null;
      show("compose");
      $("#draft").focus();
    });
    initSettings();
    lazy("faq-results", API + "v1/results", "results", "data/results.json", renderResults, "results-body");
    lazy("faq-coverage", API + "v1/coverage", "coverage", "data/coverage.json", renderCoverage, "coverage-body");
    route();
    detectLive().then(function (live) {
      LIVE = live;
      if (!$("#v-settings").hidden) fillSettings();
      return loadExampleIndex();
    }).then(function (list) {
      EXAMPLES = list || [];
      var box = $("#examples");
      EXAMPLES.forEach(function (ex) {
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = ex.title;
        b.title = ex.note || "";
        b.addEventListener("click", function () { showExample(ex.id); });
        box.appendChild(b);
      });
    }).catch(function () {});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
