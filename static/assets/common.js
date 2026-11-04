/* Shared learner features for every learning path page: pace line + start date, search, "Report a problem",
   completion badge. A page calls DROnb.init({...}) once its content is built, and DROnb.onSaved(response)
   after each successful save. */
(function () {
  "use strict";
  var O = null, status = null, searchIndex = null;
  function skillName() { return (O && O.skill) || (status && status.skill) || ""; }

  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k === "html") el.innerHTML = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      [].concat(c).forEach(function (x) { if (x != null) el.appendChild(typeof x === "string" ? document.createTextNode(x) : x); });
    }
    return el;
  }
  function fmtDate(iso) {
    if (!iso) return "";
    var d = new Date(iso + "T12:00:00");
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }
  function todayIso() { var d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); }
  function api(path, opts) {
    return fetch(O.api + path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.detail || ("Request failed (" + r.status + ")")); return j; });
    });
  }

  var FLAG = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 11V1.5h7l-1.5 2.5L9 6.5H2" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>';
  var LENS = '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M11 11l3.5 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
  function badgeSvg() {
    return '<svg viewBox="0 0 120 120" role="img" aria-label="Completion badge"><path d="M60 6l46.8 27v54L60 114 13.2 87V33z" fill="#81FBA5"/>' +
      '<path d="M60 18l36.4 21v42L60 102 23.6 81V39z" fill="none" stroke="#0B0B0B" stroke-width="2"/>' +
      '<path d="M42 61l12 12 25-27" fill="none" stroke="#0B0B0B" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }

  /* ---------------------------------------------------------------- pace line */
  var paceEl, editing = false;
  function renderPace() {
    if (!paceEl) return;
    paceEl.textContent = "";
    if (!status) return;
    var p = status.pace || {};
    if (editing) {
      var inp = h("input", { type: "date", class: "onb-date", value: status.start || todayIso(), "aria-label": "Your start date" });
      var saveBtn = h("button", { type: "button", class: "btn ghost", style: "padding:3px 10px;font-size:14px" }, "Save");
      var cancel = h("button", { type: "button", class: "onb-linkbtn" }, "Cancel");
      saveBtn.addEventListener("click", function () {
        if (!inp.value) return;
        saveBtn.disabled = true;
        api("start", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ date: inp.value }) })
          .then(function (j) { status = j.status; editing = false; renderPace(); renderBadge(); }, function (e) { saveBtn.disabled = false; alertIn(paceEl, e.message); });
      });
      cancel.addEventListener("click", function () { editing = false; renderPace(); });
      paceEl.appendChild(h("label", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap" }, h("span", null, "Start date"), inp, saveBtn, cancel));
      setTimeout(function () { inp.focus(); }, 0);
      return;
    }
    if (!status.enrolled) {
      var eb = h("button", { type: "button", class: "btn primary", style: "padding:5px 14px" }, "Enroll in this path");
      eb.addEventListener("click", function () { ensureEnrolled(); });
      paceEl.appendChild(eb);
      paceEl.appendChild(h("span", null, "You're browsing. Enroll to track your progress and pace" + (skillName() && mascotEl ? ", and start growing your " + skillName() + " skill." : ".")));
      return;
    }
    var chip = h("span", { class: "onb-chip", "data-s": p.status }, p.label || "");
    var change = h("button", { type: "button", class: "onb-linkbtn" }, status.start ? "Change" : "Set your start date");
    change.addEventListener("click", function () { editing = true; renderPace(); });
    paceEl.appendChild(chip);
    if (status.start) paceEl.appendChild(h("span", null, "Start date " + fmtDate(status.start) + (status.cohort ? " · " + status.cohort + " cohort" : "")));
    else paceEl.appendChild(h("span", null, "Your start date is set when you tick your first step."));
    paceEl.appendChild(change);
    if (O && O.serverMode) {
      var leave = h("button", { type: "button", class: "onb-linkbtn" }, "Leave this path");
      leave.addEventListener("click", confirmLeave);
      paceEl.appendChild(leave);
    }
  }
  // Leaving drops the learner out of the team views; their ticks, badge and certificate stay for if they come back.
  function confirmLeave() {
    var stay = h("button", { type: "button", class: "btn ghost" }, "Stay enrolled");
    var go = h("button", { type: "button", class: "btn primary" }, "Leave this path");
    var err = h("p", { class: "err", hidden: true });
    var m = modal(h("div", { class: "onb-dialog", role: "dialog", "aria-modal": "true", "aria-label": "Leave this path" },
      h("h2", null, "Leave the " + O.title + "?"),
      h("p", null, "You'll no longer show up in the team view or count toward this path's pace. Your ticks, stars, badge and certificate are kept, and come back if you enroll again."),
      err, h("div", { class: "row" }, stay, go)));
    stay.addEventListener("click", m.close);
    go.addEventListener("click", function () {
      go.disabled = true; go.textContent = "Leaving…";
      api("enroll", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ leave: true }) })
        .then(function (j) { status = j.status; m.close(); renderPace(); renderMascot(false); renderBadge(); },
          function (e) { go.disabled = false; go.textContent = "Leave this path"; err.textContent = e.message; err.hidden = false; });
    });
  }
  function alertIn(el, msg) { el.appendChild(h("span", { style: "color:#B00020" }, " " + msg)); }

  /* ---------------------------------------------------------------- badge */
  var badgeEl;
  function renderBadge() {
    if (!badgeEl) return;
    badgeEl.textContent = "";
    var b = status && status.badge;
    if (!b || !b.earned) { badgeEl.hidden = true; return; }
    badgeEl.hidden = false;
    var el = h("div", { class: "onb-badge", title: "Completed" }, h("span", { html: badgeSvg() }),
      h("span", { class: "bt" }, h("span", null, "Completed"), h("b", null, O.title), b.at ? h("span", null, fmtDate(b.at)) : null));
    badgeEl.appendChild(el);
    if (O.serverMode) badgeEl.appendChild(h("button", { type: "button", class: "onb-linkbtn onb-cert-link", onclick: function () { openCertificate(); } }, "Get your certificate"));
  }
  function celebrate() {
    var cert = O.serverMode ? h("button", { type: "button", class: "btn primary" }, "Get your certificate") : null;
    var close = h("button", { type: "button", class: "btn " + (cert ? "ghost" : "primary") }, "Back to the plan");
    var m = modal(h("div", { class: "onb-dialog center", role: "dialog", "aria-modal": "true", "aria-label": "Path completed" },
      h("div", { class: "onb-badge big", html: badgeSvg() }),
      h("h2", null, "You've completed the " + O.title),
      h("p", null, "Every required step is ticked. Your badge is on this page and on the hub, and your admins can see it."),
      h("div", { class: "row", style: "justify-content:center" }, cert, close)));
    close.addEventListener("click", m.close);
    if (cert) cert.addEventListener("click", function () { m.close(); openCertificate(); });
    (cert || close).focus();
  }

  /* ---------------------------------------------------------------- modal */
  function modal(dialog, onClose) {
    var last = document.activeElement;
    var wrap = h("div", { class: "onb-modal" }, dialog);
    var closed = false;
    function close() { if (closed) return; closed = true; wrap.remove(); document.removeEventListener("keydown", esc); if (last && last.focus) last.focus(); if (onClose) onClose(); }
    function esc(e) { if (e.key === "Escape") close(); }
    wrap.addEventListener("click", function (e) { if (e.target === wrap) close(); });
    document.addEventListener("keydown", esc);
    document.body.appendChild(wrap);
    return { close: close, el: wrap };
  }

  /* ---------------------------------------------------------------- report a problem */
  function rootApi() { return (O && O.rootApi) || String(O.api).replace(/[^\/]+\/api\/$/, "api/"); }
  function openReport(ctx) {
    ctx = ctx || (O.context ? O.context() : {}) || {};
    var about = h("div", { class: "about" }, ctx.label ? "About: " + ctx.label : "About: " + O.title + " (general)");
    var dlg = h("div", { class: "onb-dialog", role: "dialog", "aria-modal": "true", "aria-label": "Report a problem" });
    var m = modal(dlg);
    function fork() {
      dlg.textContent = "";
      var a = h("button", { type: "button", class: "onb-fork" }, h("span", { class: "fk" }, "Learning path"), h("b", null, "Something is wrong in this learning path"),
        h("span", null, "A broken link, an unclear or outdated step, or you're stuck and need help."), h("span", { class: "to" }, O.custom ? "Goes to the path's owners" : "Goes to the onboarding admins"));
      var b = h("button", { type: "button", class: "onb-fork" }, h("span", { class: "fk" }, "DataRobot"), h("b", null, "Something is broken in DataRobot"),
        h("span", null, "The product doesn't do what the step says: an error, a crash, a button that doesn't work."), h("span", { class: "to" }, "Creates a Jira issue for engineering"));
      var cancel = h("button", { type: "button", class: "btn ghost" }, "Cancel");
      a.addEventListener("click", pathForm); b.addEventListener("click", bugForm); cancel.addEventListener("click", m.close);
      add(dlg, [h("h2", null, "Report a problem"), about, h("p", null, "What kind of problem is it?"), a, b, h("div", { class: "row" }, cancel)]);
      a.focus();
    }
    function add(el, kids) { kids.forEach(function (k) { if (k) el.appendChild(k); }); }
    function thanks(title, text, extra) {
      dlg.textContent = "";
      var ok = h("button", { type: "button", class: "btn " + (extra ? "ghost" : "primary") }, "Close");
      ok.addEventListener("click", m.close);
      add(dlg, [h("h2", null, title)].concat(text.map(function (t) { return typeof t === "string" ? h("p", null, t) : t; })).concat([h("div", { class: "row" }, ok, extra || null)]));
      (extra || ok).focus();
    }
    function pathForm() {
      dlg.textContent = "";
      var ta = h("textarea", { "aria-label": "What's wrong?", placeholder: "For example: the link is broken, a command fails, the step is unclear, or you're stuck and need help." });
      var err = h("p", { class: "err", hidden: true });
      var send = h("button", { type: "button", class: "btn primary" }, "Send");
      var back = h("button", { type: "button", class: "btn ghost" }, "Back");
      add(dlg, [h("span", { class: "label" }, "Learning path"), h("h2", null, "Report a problem with this path"), about,
        h("p", null, "Your message goes to " + (O.custom ? "the path's owners and " : "") + "the onboarding admins with your name and this step."), ta, err, h("div", { class: "row" }, back, send)]);
      back.addEventListener("click", fork);
      send.addEventListener("click", function () {
        var msg = ta.value.trim();
        if (!msg) { err.textContent = "Write a short description first."; err.hidden = false; ta.focus(); return; }
        send.disabled = true; send.textContent = "Sending…";
        api("reports", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind: "path", message: msg, itemId: ctx.itemId || "", itemLabel: ctx.label || "", anchor: ctx.anchor || "" }) })
          .then(function () { thanks("Thanks, it's sent", [(O.custom ? "The path's owners and the onboarding admins have" : "The onboarding admins have") + " your report. Carry on with the next step in the meantime."]); },
            function (e) { send.disabled = false; send.textContent = "Send"; err.textContent = e.message; err.hidden = false; });
      });
      setTimeout(function () { ta.focus(); }, 0);
    }
    function bugForm() {
      dlg.textContent = "";
      var ta = h("textarea", { "aria-label": "What happened, and what did you expect?", placeholder: "What you did, what happened, and what you expected. Paste any error message." });
      var files = [], links = [];
      var thumbs = h("div", { class: "onb-thumbs" });
      var picker = h("input", { type: "file", multiple: true, hidden: true });
      var browse = h("button", { type: "button", class: "onb-linkbtn" }, "browse");
      var drop = h("div", { class: "onb-paste", tabindex: "0" }, thumbs, h("p", null, "Paste screenshots with ⌘V / Ctrl+V, drop files here, or ", browse, ". Up to 10 files, 20 MB each."), picker);
      var linkList = h("div", { class: "onb-links" });
      var linkIn = h("input", { placeholder: "Paste a link: the page, the use case, a doc…", "aria-label": "Add a link" });
      var linkAdd = h("button", { type: "button", class: "btn ghost" }, "Add");
      var err = h("p", { class: "err", hidden: true });
      var send = h("button", { type: "button", class: "btn primary" }, "Create Jira issue");
      var back = h("button", { type: "button", class: "btn ghost" }, "Back");
      function upload(file) {
        if (files.length >= 10) { err.textContent = "Up to 10 files."; err.hidden = false; return; }
        if (file.size > 20000000) { err.textContent = file.name + " is larger than 20 MB."; err.hidden = false; return; }
        var name = file.name && file.name !== "image.png" ? file.name : "screenshot-" + (files.filter(function (f) { return /^screenshot-/.test(f.name); }).length + 1) + "." + ((file.type.split("/")[1] || "png").replace("jpeg", "jpg"));
        var f = { name: name, size: file.size, id: null, state: "up" };
        files.push(f);
        var isImg = /^image\//.test(file.type);
        var rm = h("button", { type: "button", class: "x", "aria-label": "Remove " + name }, "×");
        var fig = h("figure", { class: "up" }, isImg ? h("img", { src: URL.createObjectURL(file), alt: "" }) : h("div", { class: "doc" }, (name.split(".").pop() || "file").toUpperCase().slice(0, 4)), h("figcaption", null, name), rm);
        rm.addEventListener("click", function () { files.splice(files.indexOf(f), 1); fig.remove(); });
        thumbs.appendChild(fig);
        fetch(rootApi() + "uploads", { method: "POST", headers: { "content-type": file.type || "application/octet-stream", "x-file-name": encodeURIComponent(name) }, body: file })
          .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || r.status); return j; }); })
          .then(function (j) { f.id = j.id; f.state = "ok"; fig.classList.remove("up"); }, function (e) { f.state = "err"; fig.classList.add("bad"); fig.title = e.message; err.textContent = "Couldn't upload " + name + ": " + e.message; err.hidden = false; });
      }
      function addLink() {
        var v = linkIn.value.trim();
        if (!v) return;
        if (!/^https?:\/\//i.test(v)) v = "https://" + v;
        links.push(v); linkIn.value = "";
        var rm = h("button", { type: "button", "aria-label": "Remove link" }, "×");
        var row = h("div", { class: "onb-link" }, h("span", null, v), rm);
        rm.addEventListener("click", function () { links.splice(links.indexOf(v), 1); row.remove(); });
        linkList.appendChild(row);
      }
      browse.addEventListener("click", function () { picker.click(); });
      picker.addEventListener("change", function () { Array.prototype.forEach.call(picker.files, upload); picker.value = ""; });
      dlg.addEventListener("paste", function (e) {
        var its = (e.clipboardData && e.clipboardData.files) || [];
        if (its.length) { e.preventDefault(); Array.prototype.forEach.call(its, upload); }
      });
      ["dragover", "dragenter"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); }); });
      ["dragleave", "drop"].forEach(function (ev) { drop.addEventListener(ev, function () { drop.classList.remove("over"); }); });
      drop.addEventListener("drop", function (e) { e.preventDefault(); Array.prototype.forEach.call(e.dataTransfer.files || [], upload); });
      linkAdd.addEventListener("click", addLink);
      linkIn.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); addLink(); } });
      back.addEventListener("click", fork);
      add(dlg, [h("span", { class: "label" }, "DataRobot bug"), h("h2", null, "Report a bug in DataRobot"), about,
        h("span", { class: "onb-fl" }, "What happened, and what did you expect?"), ta,
        h("span", { class: "onb-fl" }, "Screenshots and files"), drop,
        h("span", { class: "onb-fl" }, "Links"), linkList, h("div", { class: "onb-linkin" }, linkIn, linkAdd),
        h("p", { class: "small" }, "The app adds the step, the path, your email, your browser and the time. The LLM writes the Jira summary and picks the right project."),
        err, h("div", { class: "row" }, back, send)]);
      send.addEventListener("click", function () {
        var msg = ta.value.trim();
        if (!msg) { err.textContent = "Describe what happened first."; err.hidden = false; ta.focus(); return; }
        if (linkIn.value.trim()) addLink();
        if (files.some(function (f) { return f.state === "up"; })) { err.textContent = "Wait until the files have uploaded."; err.hidden = false; return; }
        send.disabled = true; back.disabled = true; send.textContent = "Creating the Jira issue…"; err.hidden = true;
        api("reports", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind: "bug", message: msg, itemId: ctx.itemId || "", itemLabel: ctx.label || "", anchor: ctx.anchor || "",
          stepText: ctx.text || "", links: links, uploads: files.filter(function (f) { return f.id; }).map(function (f) { return f.id; }), browser: navigator.userAgent }) })
          .then(function (j) {
            if (j.jira) {
              var open = h("a", { class: "btn primary", href: j.jira.url, target: "_blank", rel: "noopener" }, "Open in Jira ↗");
              var card = h("div", { class: "onb-jira" }, h("div", { class: "jk" }, h("span", { class: "key" }, j.jira.key), h("span", { class: "onb-chip" }, "Bug"), h("span", { class: "onb-chip" }, "Open")),
                h("b", null, j.jira.summary), h("span", { class: "small" }, "Project: " + j.jira.project + (j.jira.attached ? " · " + j.jira.attached + " file" + (j.jira.attached === 1 ? "" : "s") + " attached" : "") + (links.length ? " · " + links.length + " link" + (links.length === 1 ? "" : "s") : "")));
              thanks("Jira issue created", [card, "You're the reporter, so Jira emails you now and every time the issue changes. The onboarding admins and the path owners can see it in Problem reports.", "Carry on with the next step in the meantime, or skip this one for now."], open);
            } else thanks("Thanks, it's sent", [j.jiraError || "The onboarding admins have your report."]);
          }, function (e) { send.disabled = false; back.disabled = false; send.textContent = "Create Jira issue"; err.textContent = e.message; err.hidden = false; });
      });
      setTimeout(function () { ta.focus(); }, 0);
    }
    fork();
  }
  function reportButton(ctx) {
    var b = h("button", { type: "button", class: "onb-report", title: "Report a problem with this step", html: FLAG + "<span>Report a problem</span>" });
    b.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); openReport(ctx); });
    return b;
  }

  /* ---------------------------------------------------------------- search */
  function norm(s) { return (s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, ""); }
  function buildSearch(mount) {
    var input = h("input", { type: "search", placeholder: "Search this path  ( / )", "aria-label": "Search this learning path", autocomplete: "off", spellcheck: "false", role: "combobox", "aria-expanded": "false", "aria-controls": "onb-results" });
    var list = h("div", { class: "onb-results", id: "onb-results", role: "listbox", hidden: true });
    var box = h("div", { class: "onb-search" }, h("span", { html: LENS }), input, list);
    mount.appendChild(box);
    var results = [], sel = -1;
    function hl(text, terms) {
      var frag = document.createDocumentFragment(), low = norm(text), i = 0;
      var ranges = [];
      terms.forEach(function (t) { var p = low.indexOf(t); if (p >= 0) ranges.push([p, p + t.length]); });
      ranges.sort(function (a, b) { return a[0] - b[0]; });
      ranges.forEach(function (r) { if (r[0] < i) return; frag.appendChild(document.createTextNode(text.slice(i, r[0]))); frag.appendChild(h("mark", null, text.slice(r[0], r[1]))); i = r[1]; });
      frag.appendChild(document.createTextNode(text.slice(i)));
      return frag;
    }
    function run() {
      var q = norm(input.value.trim());
      list.textContent = ""; sel = -1;
      if (q.length < 2) { list.hidden = true; input.setAttribute("aria-expanded", "false"); return; }
      if (!searchIndex) searchIndex = O.searchEntries().map(function (e) { e._t = norm(e.title + " " + (e.text || "")); e._title = norm(e.title); return e; });
      var terms = q.split(/\s+/).filter(Boolean);
      results = searchIndex.filter(function (e) { return terms.every(function (t) { return e._t.indexOf(t) >= 0; }); })
        .map(function (e) { var s = 0; terms.forEach(function (t) { if (e._title.indexOf(t) >= 0) s += 2; }); return { e: e, s: s }; })
        .sort(function (a, b) { return b.s - a.s; }).slice(0, 25).map(function (x) { return x.e; });
      if (!results.length) list.appendChild(h("div", { class: "none" }, "No matches."));
      results.forEach(function (e, i) {
        var b = h("button", { type: "button", role: "option", id: "onb-r" + i, "aria-selected": "false" }, h("span", { class: "s" }, e.where), h("span", { class: "t" }, hl(e.title, terms)));
        b.addEventListener("mousedown", function (ev) { ev.preventDefault(); pick(i); });
        list.appendChild(b);
      });
      list.hidden = false; input.setAttribute("aria-expanded", "true");
    }
    function mark() { $$(list, "button").forEach(function (b, i) { b.setAttribute("aria-selected", String(i === sel)); if (i === sel) { b.scrollIntoView({ block: "nearest" }); input.setAttribute("aria-activedescendant", b.id); } }); }
    function pick(i) { var e = results[i]; if (!e) return; list.hidden = true; input.blur(); e.go(); }
    input.addEventListener("input", run);
    input.addEventListener("focus", run);
    input.addEventListener("blur", function () { setTimeout(function () { list.hidden = true; input.setAttribute("aria-expanded", "false"); }, 120); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(results.length - 1, sel + 1); mark(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); mark(); }
      else if (e.key === "Enter") { e.preventDefault(); pick(sel < 0 ? 0 : sel); }
      else if (e.key === "Escape") { input.value = ""; run(); input.blur(); }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement || {}).tagName || "")) { e.preventDefault(); input.focus(); }
    });
  }
  function $$(r, s) { return Array.prototype.slice.call(r.querySelectorAll(s)); }

  /* ---------------------------------------------------------------- enroll */
  var enrollWaiters = null;
  function ensureEnrolled() {
    if (!O || !O.serverMode || (status && status.enrolled)) return Promise.resolve(true);
    if (!status) return api("status").then(function (j) { status = j; renderPace(); renderMascot(false); return ensureEnrolled(); }, function () { return true; });
    if (enrollWaiters) return enrollWaiters;
    enrollWaiters = new Promise(function (resolve) {
      var date = h("input", { type: "date", class: "onb-date", value: todayIso(), "aria-label": "Start date" });
      var go = h("button", { type: "button", class: "btn primary" }, "Enroll");
      var later = h("button", { type: "button", class: "btn ghost" }, "Not now");
      var err = h("p", { class: "err", hidden: true });
      var done = false;
      var m = modal(h("div", { class: "onb-dialog", role: "dialog", "aria-modal": "true", "aria-label": "Enroll" },
        h("h2", null, "Enroll in the " + O.title + "?"),
        h("p", null, "Enrolling starts your progress, pace" + (mascotEl ? " and skill growth" : "") + ", and adds you to the team view. You can browse without enrolling, but ticks are only saved once you're enrolled."),
        h("label", { style: "display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:15px" }, "Start date", date),
        err, h("div", { class: "row" }, later, go)), function () { if (!done) { done = true; enrollWaiters = null; resolve(false); } });
      later.addEventListener("click", m.close);
      go.addEventListener("click", function () {
        go.disabled = true; go.textContent = "Enrolling…";
        api("enroll", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ date: date.value || todayIso() }) })
          .then(function (j) {
            status = j.status; done = true; enrollWaiters = null; m.close(); renderPace(); renderMascot(true); resolve(true);
            if (O.onEnrolled) O.onEnrolled();
          }, function (e) { go.disabled = false; go.textContent = "Enroll"; err.textContent = e.message; err.hidden = false; });
      });
      setTimeout(function () { go.focus(); }, 0);
    });
    return enrollWaiters;
  }

  /* ---------------------------------------------------------------- stars */
  var STAR_OFF = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.6l1.9 4 4.3.5-3.2 3 .9 4.3L8 11.2l-3.9 2.2.9-4.3-3.2-3 4.3-.5z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>';
  var STAR_ON = STAR_OFF.replace('fill="none"', 'fill="#FFC72C"').replace('stroke="currentColor"', 'stroke="#C99400"');
  var starBtns = {};
  function starButton(id, label) {
    var b = h("button", { type: "button", class: "onb-star", "aria-pressed": "false", title: "Star this step" });
    function paint() { var on = !!(O && O.isStarred && O.isStarred(id)); b.setAttribute("aria-pressed", String(on)); b.innerHTML = (on ? STAR_ON : STAR_OFF) + "<span>" + (on ? "Starred" : "Star") + "</span>"; b.title = on ? "Remove from your starred steps" : "Star this step to find it quickly"; }
    b.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); if (O && O.toggleStar) O.toggleStar(id); refreshStars(); });
    (starBtns[id] = starBtns[id] || []).push(paint);
    paint();
    return b;
  }
  function refreshStars() { Object.keys(starBtns).forEach(function (k) { starBtns[k].forEach(function (f) { f(); }); }); if (O && O.onStarsChanged) O.onStarsChanged(); }

  /* ---------------------------------------------------------------- mascot */
  var MASCOT_GLOW = ["#2E7BEA", "#E21CB0", "#2CC24A", "#F2382E", "#F5C518", "#2C88E8", "#F0A21E", "#39C24A", "#F2671F", "#A35CF2"];
  function mascotSrc(k) { return (O.assetBase || "") + "mascots/year-" + (k < 10 ? "0" : "") + k + ".png"; }
  var mascotEl, lastStage = null;
  function stepsFor(stage) { var t = (status && status.requiredTotal) || 0; return Math.ceil(stage * t / 10); }
  function renderMascot(animate) {
    if (!mascotEl || !status) return;
    var st = status.enrolled ? (status.mascot || 0) : 0;
    var shown = Math.max(1, st);
    var next = Math.min(10, st + 1);
    var need = st >= 10 ? 0 : Math.max(0, stepsFor(next) - (status.requiredDone || 0));
    var prevAt = stepsFor(st), nextAt = stepsFor(next);
    var frac = st >= 10 ? 1 : (nextAt > prevAt ? ((status.requiredDone || 0) - prevAt) / (nextAt - prevAt) : 0);
    mascotEl.textContent = "";
    var card = h("button", { type: "button", class: "onb-mascot" + (st === 0 ? " locked" : ""), style: "--glow:#44BFFC", title: "See your skill growth", "aria-label": "Skill growth: stage " + st + " of 10. Open the growth view." },
      h("span", { class: "sky", "aria-hidden": "true" }),
      h("span", { class: "fig" }, h("img", { src: mascotSrc(shown), alt: "", class: animate && lastStage !== null && st > lastStage ? "pop" : "" })),
      h("span", { class: "info" },
        h("span", { class: "k" }, "Skill growth"),
        h("b", null, !status.enrolled ? "Enroll to start growing your " + skillName() + " skill" : st >= 10 ? "Fully grown!" : st === 0 ? "Just getting started" : "Growing stronger"),
        h("span", { class: "meter" }, h("i", { style: "width:" + Math.round(100 * frac) + "%" })),
        h("span", { class: "s" }, !status.enrolled ? "It grows with every required step you complete" : st >= 10 ? "Every required step done" : need + " more required step" + (need === 1 ? "" : "s") + " to grow"),
        status.enrolled ? h("span", { class: "dots" }, [1,2,3,4,5,6,7,8,9,10].map(function (k) { return h("i", { class: k <= st ? "on" : "", style: k <= st ? "background:#44BFFC" : "" }); })) : null));
    card.addEventListener("click", openCollection);
    mascotEl.appendChild(card);
    lastStage = st;
  }
  function openCollection() {
    var st = status && status.enrolled ? (status.mascot || 0) : 0;
    var close = h("button", { type: "button", class: "btn primary" }, "Close");
    var grid = h("div", { class: "onb-collection" }, [1,2,3,4,5,6,7,8,9,10].map(function (k) {
      var on = k <= st;
      return h("figure", { class: on ? "on" : "", style: "--glow:#44BFFC" },
        h("img", { src: mascotSrc(k), alt: on ? "Growth stage " + k + ", reached" : "Growth stage " + k + ", not reached yet" }),
        h("figcaption", null, h("span", null, on ? "Reached" : stepsFor(k) + " required steps")));
    }));
    var m = modal(h("div", { class: "onb-dialog wide space", role: "dialog", "aria-modal": "true", "aria-label": "Skill growth" },
      h("h2", null, "Your " + skillName() + " skill growth"),
      h("p", null, "Your " + skillName() + " skill grows stronger with every required step of the " + O.title + " you complete."),
      grid, h("div", { class: "row" }, close)));
    close.addEventListener("click", m.close);
  }
  function levelUp(stage, then) {
    var ok = h("button", { type: "button", class: "btn primary" }, "Keep going");
    var fig = h("div", { class: "onb-evolve", style: "--glow:#44BFFC" },
      stage > 1 ? h("img", { class: "old", src: mascotSrc(stage - 1), alt: "" }) : null,
      h("img", { class: "new", src: mascotSrc(stage), alt: "" }),
      h("span", { class: "burst", "aria-hidden": "true" }, [0,1,2,3,4,5,6,7,8,9,10,11].map(function (i) { return h("i", { style: "--a:" + (i * 30) + "deg" }); })));
    var m = modal(h("div", { class: "onb-dialog center space", role: "dialog", "aria-modal": "true", "aria-label": "Your skill grew" },
      fig,
      h("h2", null, stage === 10 ? "Your " + skillName() + " skill is fully grown!" : stage === 1 ? "Your " + skillName() + " skill is growing!" : "Your " + skillName() + " skill grew stronger!"),
      h("p", null, stage < 10 ? "Keep completing required steps to grow it further." : "You've completed every required step."),
      h("div", { class: "row", style: "justify-content:center" }, ok)), then);
    ok.addEventListener("click", m.close);
    ok.focus();
  }

  /* ---------------------------------------------------------------- public */

  /* ---------------------------------------------------------------- path author (next to the path's length) */
  function byline(a, big) {
    if (!a || !a.name) return null;
    var ini = h("span", { class: "onb-av ini", "aria-hidden": "true" }, a.initials || "");
    var av = ini;
    if (a.photo) {
      av = h("img", { class: "onb-av", src: a.photo, alt: "" });
      av.addEventListener("error", function () { if (av.parentNode) av.parentNode.replaceChild(ini, av); });
    }
    return h("span", { class: "onb-byline" + (big ? " lg" : ""), title: "Created by " + a.name }, av, h("span", null, a.name));
  }
  var authorDone = false;
  function renderAuthor() {
    if (authorDone || !status || !status.author || !status.author.name) return;
    var title = document.getElementById("doc-title"); if (!title) return;
    authorDone = true;
    var len = document.getElementById("doc-length");
    var row = h("div", { class: "onb-meta" });
    if (len) { len.parentNode.insertBefore(row, len); row.appendChild(len); }
    else { title.parentNode.insertBefore(row, title); if (status.length) row.appendChild(h("span", { class: "onb-meta-len" }, status.length)); }
    row.appendChild(byline(status.author, true));
  }

  /* ---------------------------------------------------------------- certificate
     Drawn on a canvas in the browser from the learner's data (api/certificate), in two looks (white with a green
     panel, all green) and two shapes (landscape for LinkedIn, portrait for phones). Downloads as PNG or PDF. */
  var CERT_LOGO = "data:image/png;base64,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";
  var CERT_FONTS = "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400&family=DM+Mono:wght@400&display=swap";
  var INK = "#0B0B0B", GREEN = "#81FBA5", GREY = "#3A3A3A", INDIGO = "#5C41FF";
  var certFontsReady = null;
  function loadCertFonts() {
    if (certFontsReady) return certFontsReady;
    if (!document.querySelector('link[data-cert-fonts]')) document.head.appendChild(h("link", { rel: "stylesheet", href: CERT_FONTS, "data-cert-fonts": "1" }));
    var logo = new Image(); logo.src = CERT_LOGO;
    var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
    var fonts = (document.fonts && document.fonts.load) ? Promise.all([document.fonts.load('400 100px "DM Sans"'), document.fonts.load('400 40px "DM Mono"')]) : Promise.resolve();
    certFontsReady = Promise.all([Promise.race([fonts, wait(4000)]), new Promise(function (r) { if (logo.complete) r(); else { logo.onload = r; logo.onerror = r; } })])
      .then(function () { return logo; });
    return certFontsReady;
  }
  function longDate(iso) { var d = new Date(iso + "T12:00:00"); return d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" }); }
  function setFont(c, family, px, tracking) {
    c.font = "400 " + px + "px " + (family === "mono" ? '"DM Mono", ui-monospace, Menlo, monospace' : '"DM Sans", "Barlow", system-ui, sans-serif');
    if ("letterSpacing" in c) c.letterSpacing = (tracking * px).toFixed(2) + "px";
  }
  function textW(c, t) { return c.measureText(t).width; }
  /* Wrap text into at most maxLines lines of maxW; shrink the size (down to minPx) when it doesn't fit.
     Breaks at spaces, or after "/" for links. Returns {lines, px}. */
  function fit(c, family, px, tracking, text, maxW, maxLines, minPx) {
    var size = px;
    for (;;) {
      setFont(c, family, size, tracking);
      var lines = [];
      text.split("\n").forEach(function (para) {
        var parts = para.replace(/\//g, "/\u0000").replace(/ /g, "\u0000 ").split("\u0000"), cur = "";
        parts.forEach(function (p) {
          var next = cur + p;
          if (cur && textW(c, next.trim()) > maxW) { lines.push(cur.trim()); cur = p.trim(); }
          else cur = next;
        });
        if (cur.trim()) lines.push(cur.trim());
      });
      var widest = Math.max.apply(null, lines.map(function (l) { return textW(c, l); }));
      if ((lines.length <= maxLines && widest <= maxW) || size <= minPx) return { lines: lines.slice(0, maxLines), px: size };
      size = Math.max(minPx, size * 0.94);
    }
  }
  function put(c, family, px, tracking, color, text, x, y, opts) {
    opts = opts || {};
    var f = fit(c, family, px, tracking, text, opts.maxW || 99999, opts.lines || 1, opts.minPx || px * 0.5);
    c.fillStyle = color; c.textBaseline = "alphabetic"; c.textAlign = opts.right ? "right" : "left";
    var lh = f.px * (opts.lh || 1.25), dir = opts.up ? -1 : 1, ls = opts.up ? f.lines.slice().reverse() : f.lines;
    ls.forEach(function (l, i) { c.fillText(l, x, y + dir * i * lh); });
    c.textAlign = "left";
    return { bottom: y + (f.lines.length - 1) * lh, top: y - (f.lines.length - 1) * lh, n: f.lines.length, px: f.px };
  }
  function symbol(c, x, y, w) {
    // the DataRobot symbol: 9 rows of data bricks, in quarters of its width
    var rows = [[0, 2], [2, 3], [0, 2], [3, 4], [0, 3], [3, 4], [0, 2], [2, 3], [0, 2]], q = w / 4, rh = (w / 1.035) / 9;
    c.fillStyle = INK;
    rows.forEach(function (r, i) { c.fillRect(x + r[0] * q, y + i * rh, (r[1] - r[0]) * q, rh + 0.5); });
  }
  function drawCertificate(d, look, shape, logo, scale) {
    var land = shape === "landscape", W = land ? 2000 : 1600, H = land ? 1045 : 2000;
    var cv = document.createElement("canvas"); cv.width = Math.round(W * scale); cv.height = Math.round(H * scale);
    var c = cv.getContext("2d"); c.scale(scale, scale);
    var date = longDate(d.issued);
    var drawLogo = function (x, y, hh) { if (logo && logo.naturalWidth) c.drawImage(logo, x, y, hh * logo.naturalWidth / logo.naturalHeight, hh); };
    if (look === "white") {
      c.fillStyle = "#FFFFFF"; c.fillRect(0, 0, W, H);
      if (land) {
        c.fillStyle = GREEN; c.fillRect(1500, 0, 500, H);
        drawLogo(107, 93.3, 66);
        put(c, "mono", 25.4, 0.19, GREY, "CERTIFICATE OF COMPLETION", 108, 410.8);
        put(c, "sans", 101, -0.043, INK, d.name, 108, 532, { maxW: 1300, minPx: 60 });
        put(c, "sans", 54, -0.015, INK, d.course, 108, 637.7, { maxW: 1300, lines: 2, lh: 1.15, minPx: 38 });
        put(c, "mono", 21, 0.19, GREY, "ISSUED", 109, 898.3);
        put(c, "sans", 30, -0.01, INK, date, 109, 943.8);
        symbol(c, 1573, 93.3, 172.5);
        put(c, "mono", 21, 0.19, INK, "CREDENTIAL ID", 1574, 906);
        put(c, "mono", 21, 0.15, INK, d.certId, 1574, 943);
      } else {
        c.fillStyle = GREEN; c.fillRect(0, 1525.9, W, H - 1525.9);
        drawLogo(107, 118.5, 64.5);
        put(c, "mono", 25.7, 0.19, GREY, "CERTIFICATE OF COMPLETION", 108, 636.3);
        put(c, "sans", 118, -0.046, INK, d.name, 108, 779, { maxW: 1386, minPx: 64 });
        put(c, "sans", 56, -0.02, INK, d.course, 108, 898.5, { maxW: 1386, lines: 2, lh: 1.15, minPx: 40 });
        put(c, "mono", 21, 0.19, GREY, "ISSUED", 109.6, 1362.2);
        put(c, "sans", 31, -0.01, INK, date, 109, 1410.6);
        symbol(c, 106.7, 1727.4, 184.4);
        put(c, "mono", 22, 0.19, INK, "CREDENTIAL ID", 1188, 1858.5);
        put(c, "mono", 22, 0.15, INK, d.certId, 1188, 1895);
      }
    } else {
      c.fillStyle = GREEN; c.fillRect(0, 0, W, H);
      var bricks = function (x0, x1, y, hh, gap) {
        var n = 12, bw = (x1 - x0 - gap * (n - 1)) / n;
        for (var i = 0; i < n; i++) { c.fillStyle = i === n - 1 ? INDIGO : INK; c.fillRect(x0 + i * (bw + gap), y, bw, hh); }
      };
      var up = function (t) { return t.toUpperCase(); };
      if (land) {
        drawLogo(107, 93.3, 59.2);
        put(c, "mono", 25.4, 0.19, INK, "CERTIFICATE OF COMPLETION", 1887.5, 132.5, { right: true });
        put(c, "sans", 152, -0.05, INK, d.name, 108, 503.9, { maxW: 1786, minPx: 80 });
        put(c, "sans", 54, -0.02, INK, d.course, 108, 611, { maxW: 1786, lines: 2, lh: 1.15, minPx: 38 });
        bricks(106.7, 1892.5, 843.3, 60, 11.7);
        put(c, "mono", 21.4, 0.19, INK, up("Issued " + date), 108, 951.7, { maxW: 900 });
        put(c, "mono", 21.4, 0.19, INK, "CREDENTIAL ID " + d.certId, 1887, 951.7, { right: true, maxW: 900 });
      } else {
        drawLogo(107, 118.5, 58.5);
        put(c, "mono", 25.7, 0.19, INK, "CERTIFICATE OF COMPLETION", 1487.4, 157, { right: true });
        put(c, "sans", 169, -0.049, INK, d.name, 108, 927.3, { maxW: 1386, minPx: 80 });
        put(c, "sans", 59, -0.025, INK, d.course, 108, 1048.9, { maxW: 1386, lines: 2, lh: 1.15, minPx: 40 });
        bricks(107.4, 1491.9, 1668.1, 94, 13.3);
        put(c, "mono", 22, 0.19, INK, up("Issued " + date), 108, 1826.6, { maxW: 680 });
        put(c, "mono", 22, 0.19, INK, "CREDENTIAL ID " + d.certId, 832.6, 1826.6, { maxW: 660 });
      }
    }
    return cv;
  }
  function pdfFromCanvas(cv, wPt, hPt) {
    var bin = atob(cv.toDataURL("image/jpeg", 0.95).split(",")[1]), img = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) img[i] = bin.charCodeAt(i);
    var enc = new TextEncoder(), parts = [], offs = [], len = 0;
    function add(x) { var b = typeof x === "string" ? enc.encode(x) : x; parts.push(b); len += b.length; }
    function obj(n, body) { offs[n] = len; add(n + " 0 obj\n" + body + "\nendobj\n"); }
    add("%PDF-1.4\n%âãÏÓ\n");
    var content = "q " + wPt + " 0 0 " + hPt + " 0 0 cm /Im0 Do Q";
    obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
    obj(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
    obj(3, "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 " + wPt + " " + hPt + "] /Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>");
    obj(4, "<< /Length " + content.length + " >>\nstream\n" + content + "\nendstream");
    offs[5] = len;
    add("5 0 obj\n<< /Type /XObject /Subtype /Image /Width " + cv.width + " /Height " + cv.height + " /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length " + img.length + " >>\nstream\n");
    add(img); add("\nendstream\nendobj\n");
    var xref = len, x = "xref\n0 6\n0000000000 65535 f \n";
    for (var n = 1; n <= 5; n++) x += String(offs[n]).padStart(10, "0") + " 00000 n \n";
    add(x + "trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + xref + "\n%%EOF");
    return new Blob(parts, { type: "application/pdf" });
  }
  function saveBlob(blob, name) {
    var url = URL.createObjectURL(blob), a = h("a", { href: url, download: name });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }
  function prefGet(k, d) { try { return localStorage.getItem("onb-cert-" + k) || d; } catch (e) { return d; } }
  function prefSet(k, v) { try { localStorage.setItem("onb-cert-" + k, v); } catch (e) {} }
  function openCertificate() {
    var look = prefGet("look", "green"), shape = window.matchMedia && matchMedia("(max-width: 640px)").matches ? "portrait" : prefGet("shape", "landscape");
    var data = null, logo = null;
    var preview = h("div", { class: "onb-cert-preview", "aria-live": "polite" }, h("span", { class: "onb-cert-wait" }, "Preparing your certificate…"));
    function seg(name, opts, cur, onPick) {
      var box = h("div", { class: "onb-seg", role: "radiogroup", "aria-label": name });
      opts.forEach(function (o) {
        var b = h("button", { type: "button", role: "radio", "aria-checked": String(o[0] === cur) }, o[1]);
        b.addEventListener("click", function () { [].forEach.call(box.children, function (x) { x.setAttribute("aria-checked", "false"); }); b.setAttribute("aria-checked", "true"); onPick(o[0]); });
        box.appendChild(b);
      });
      return box;
    }
    var looks = seg("Look", [["green", "Green"], ["white", "White"]], look, function (v) { look = v; prefSet("look", v); draw(); });
    var shapes = seg("Shape", [["landscape", "Landscape"], ["portrait", "Portrait"]], shape, function (v) { shape = v; prefSet("shape", v); draw(); });
    var li = h("a", { class: "btn primary", target: "_blank", rel: "noopener", href: "#", "aria-disabled": "true" }, "Add to LinkedIn");
    var png = h("button", { type: "button", class: "btn ghost", disabled: true }, "Download PNG");
    var pdf = h("button", { type: "button", class: "btn ghost", disabled: true }, "Download PDF");
    var close = h("button", { type: "button", class: "btn ghost" }, "Close");
    var meta = h("p", { class: "onb-cert-meta" });
    var err = h("p", { class: "err", hidden: true });
    var m = modal(h("div", { class: "onb-dialog onb-cert", role: "dialog", "aria-modal": "true", "aria-label": "Your certificate" },
      h("h2", null, "Your certificate"),
      h("div", { class: "onb-cert-opts" }, looks, shapes),
      preview, meta, err,
      h("div", { class: "row" }, li, png, pdf, h("span", { class: "sp" }), close)));
    close.addEventListener("click", m.close);
    function fileName(ext) { return (data.course + " certificate - " + data.name).replace(/[\\/:*?"<>|]+/g, "") + "." + ext; }
    function draw() {
      if (!data) return;
      var cv = drawCertificate(data, look, shape, logo, 0.6);
      cv.setAttribute("role", "img"); cv.setAttribute("aria-label", "Certificate of completion: " + data.name + ", " + data.course);
      preview.textContent = ""; preview.className = "onb-cert-preview " + shape; preview.appendChild(cv);
    }
    png.addEventListener("click", function () {
      drawCertificate(data, look, shape, logo, 1.5).toBlob(function (b) { saveBlob(b, fileName("png")); }, "image/png");
    });
    pdf.addEventListener("click", function () {
      var land = shape === "landscape";
      saveBlob(pdfFromCanvas(drawCertificate(data, look, shape, logo, 1.5), land ? 792 : 612, land ? 414 : 765), fileName("pdf"));
    });
    Promise.all([api("certificate"), loadCertFonts()]).then(function (r) {
      data = r[0]; logo = r[1];
      meta.textContent = "Credential ID " + data.certId + " · issued " + longDate(data.issued);
      li.href = data.linkedinUrl; li.removeAttribute("aria-disabled");
      png.disabled = false; pdf.disabled = false;
      draw();
    }, function (e) { preview.textContent = ""; err.textContent = e.message; err.hidden = false; });
  }

  /* ---------------------------------------------------------------- generated drafts: "ready" notice */
  // The creation wizard records the paths this browser started generating (per user). While there are any, the hub
  // and admin pages ask every 20 seconds whether they're done, and show a notice with a link when they are.
  function draftsKey(uid) { return "onb.generating." + uid; }
  function draftsOf(uid) { try { return JSON.parse(localStorage.getItem(draftsKey(uid)) || "[]"); } catch (e) { return []; } }
  function setDrafts(uid, ids) { try { if (ids.length) localStorage.setItem(draftsKey(uid), JSON.stringify(ids)); else localStorage.removeItem(draftsKey(uid)); } catch (e) {} }
  function toast(text, href, label) {
    var close = h("button", { type: "button", class: "x", "aria-label": "Close" }, "×");
    var el = h("div", { class: "onb-toast", role: "status" }, h("span", null, text), href ? h("a", { href: href }, label || "Open") : null, close);
    close.addEventListener("click", function () { el.remove(); });
    var box = document.querySelector(".onb-toasts") || document.body.appendChild(h("div", { class: "onb-toasts" }));
    box.appendChild(el);
    return el;
  }
  var watching = null;
  function watchDrafts(root, uid, onChange) {
    if (!uid || watching) return;
    watching = true;
    function check() {
      var ids = draftsOf(uid);
      if (!ids.length) { watching = null; return; }
      fetch(root + "api/admin/paths?generating=1").then(function (r) { return r.ok ? r.json() : { paths: [] }; }).then(function (j) {
        var byId = {};
        (j.paths || []).forEach(function (p) { byId[p.id] = p; });
        var left = ids.filter(function (id) {
          var p = byId[id];
          if (!p) return false;
          if (p.status === "draft") toast("Your draft " + p.title + " is ready.", root + id + "/", "Open the draft");
          else if (p.status === "failed") toast("Generating " + p.title + " failed: " + (p.error || "unknown error").replace(/\.?$/, "."), root + "admin/#content", "See Content");
          else return true;
          return false;
        });
        setDrafts(uid, left);
        if (left.length !== ids.length && onChange) onChange();
      }, function () {}).then(function () { if (draftsOf(uid).length) setTimeout(check, 20000); else watching = null; });
    }
    setTimeout(check, 20000);
  }

  /* ---------------------------------------------------------------- built-in paths: edit mode */
  // While the AI Engineer or Agentic path is in edit mode the back link returns to Admin -> Content, and when the
  // path has saved edits (an in-app edit or an old upload) admins can make the deployed files live again.
  function builtinEditing(on, root, pathId) {
    var back = document.querySelector(".backlink");
    if (back) { back.href = on ? root + "admin/#content" : root; back.textContent = on ? "\u2190 Content" : "\u2190 All learning paths"; }
    var old = document.getElementById("ed-revert");
    if (old) old.remove();
    if (!on) return;
    fetch(root + "api/admin/content").then(function (r) { return r.ok ? r.json() : { paths: [] }; }).then(function (j) {
      var p = (j.paths || []).filter(function (x) { return x.id === pathId; })[0];
      var discard = document.getElementById("ed-discard");
      if (!p || !p.source || p.source.kind !== "uploaded" || !discard || document.getElementById("ed-revert")) return;
      var b = h("button", { type: "button", class: "btn", id: "ed-revert" }, "Go back to the deployed version");
      b.addEventListener("click", function () {
        if (!confirm("Go back to the content deployed with the app? Every edit made in the app to this path stops being live, for learners too.")) return;
        b.disabled = true;
        fetch(root + "api/admin/content/" + pathId + "/revert", { method: "POST" }).then(function (r) {
          if (!r.ok) throw new Error("Request failed (" + r.status + ")");
          history.replaceState(null, "", location.pathname);
          location.reload();
        }).catch(function (e) { b.disabled = false; alert("Couldn't go back: " + e.message); });
      });
      discard.parentNode.insertBefore(b, discard);
    }, function () {});
  }

  window.DROnb = {
    builtinEditing: builtinEditing,
    watchDrafts: watchDrafts,
    addGenerating: function (uid, id) { var ids = draftsOf(uid); if (ids.indexOf(id) < 0) ids.push(id); setDrafts(uid, ids); },
    toast: toast,
    init: function (opts) {
      O = Object.assign(O || {}, opts);
      if (opts.paceMount) paceEl = opts.paceMount;
      if (opts.mascotMount) mascotEl = opts.mascotMount;
      if (opts.badgeMount) badgeEl = opts.badgeMount;
      if (opts.toolsMount && !opts.toolsMount.querySelector(".onb-tools")) {
        var tools = h("div", { class: "onb-tools" });
        opts.toolsMount.appendChild(tools);
        buildSearch(tools);
        var rb = h("button", { type: "button", class: "btn ghost", html: FLAG.replace("viewBox", 'style="width:12px;height:12px" viewBox') + "<span>Report a problem</span>" });
        rb.addEventListener("click", function () { openReport(); });
        tools.appendChild(rb);
      }
      (opts.rows ? opts.rows() : []).forEach(function (r) { r.mount.appendChild(reportButton(r)); });
      if (opts.server) { O.serverMode = true; api("status").then(function (j) { status = j; renderPace(); renderBadge(); renderMascot(false); renderAuthor(); }, function () { /* offline: no pace line */ }); }
    },
    onSaved: function (resp) {
      if (!resp || !resp.status) return;
      status = resp.status;
      if (!editing) renderPace();
      renderBadge();
      renderMascot(true);
      if (resp.levelUp && status.mascot > 0 && mascotEl && status.skillEnabled !== false) levelUp(status.mascot, resp.newBadge ? celebrate : null);
      else if (resp.newBadge) celebrate();
    },
    ensureEnrolled: ensureEnrolled,
    isEnrolled: function () { return !O || !O.serverMode || !!(status && status.enrolled); },
    starButton: starButton,
    refreshStars: refreshStars,
    mascotSrc: function (k) { return mascotSrc(k); },
    mascotGlow: MASCOT_GLOW,
    reportButton: reportButton,
    openReport: openReport,
    badgeSvg: badgeSvg,
    byline: byline,
    openCertificate: openCertificate,
    drawCertificate: function (d, look, shape, scale) { return loadCertFonts().then(function (logo) { return drawCertificate(d, look, shape, logo, scale || 1); }); },
    resetSearch: function () { searchIndex = null; starBtns = {}; }
  };
})();
