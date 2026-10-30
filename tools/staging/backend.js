/* Staging backend: the onboarding app's API, simulated in the browser.
   A port of app.py, paths.py, custom_paths.py and roles.py. Jira, Confluence, GitHub, Slack and the LLM Gateway
   are stand-ins. Data lives in this browser (localStorage), per viewer. */
(function () {
  "use strict";
  var SRC = JSON.parse(document.getElementById("stg-src").textContent);
  var SYSTEM_ADMINS = ["lidiia.saakian@datarobot.com"];
  var INACTIVE_DAYS = 7;
  var DAY = 86400000;
  var LS_KEY = "onb-staging-v1";
  var JIRA = "https://datarobot.atlassian.net";

  // ------------------------------------------------------------------ helpers
  function now() { return Date.now(); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function today() { var d = new Date(); d.setHours(0, 0, 0, 0); return d; }
  function todayIso() { return iso(today()); }
  function parseIso(s) { var p = String(s).split("-"); var d = new Date(+p[0], +p[1] - 1, +p[2]); return isNaN(d) ? null : d; }
  function addDays(d, n) { var x = new Date(d); x.setDate(x.getDate() + n); return x; }
  function daysBetween(a, b) { return Math.round((b - a) / DAY); }
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function hex(n) { var s = ""; while (s.length < n) s += Math.floor(Math.random() * 16).toString(16); return s; }
  function token(n) { var a = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"; var s = ""; for (var i = 0; i < n; i++) s += a[Math.floor(Math.random() * a.length)]; return s; }
  function clone(x) { return x == null ? x : JSON.parse(JSON.stringify(x)); }
  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function HttpError(status, detail) { this.status = status; this.detail = detail; }
  function fail(status, detail) { throw new HttpError(status, detail); }
  var _ta = document.createElement("textarea");
  function unescapeHtml(s) { _ta.innerHTML = s; return _ta.value; }
  function cohortOf(start) { if (!start) return ""; var d = parseIso(start); return MON[d.getMonth()] + " " + d.getFullYear(); }
  function titleName(email) { return email.split("@")[0].split(".").map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); }).join(" "); }

  // ------------------------------------------------------------------ activity log (what would leave the app)
  var listeners = [];
  function event(kind, text, detail) {
    DB.events.unshift({ at: now(), kind: kind, text: text, detail: detail || "" });
    DB.events = DB.events.slice(0, 200);
    save();
    listeners.forEach(function (f) { try { f(); } catch (e) {} });
  }

  // ------------------------------------------------------------------ path models (paths.py)
  function PathModel(o) { for (var k in o) this[k] = o[k]; this.items = this.items || []; this.source = this.source || {}; }
  PathModel.prototype.ids = function () { var s = {}; this.items.forEach(function (i) { s[i.id] = true; }); return s; };
  PathModel.prototype.required = function (state) {
    var fast = (state || {}).track === "fast";
    return this.items.filter(function (i) { return i.path === "Required" && !(fast && i.fastStretch); });
  };
  PathModel.prototype.labelOf = function (id) { for (var i = 0; i < this.items.length; i++) if (this.items[i].id === id) return this.items[i].label; return id; };
  PathModel.prototype.summarize = function (state) {
    state = state || {}; var done = state.done || {};
    var req = this.required(state), gates = this.items.filter(function (i) { return i.gate; });
    function n(list) { return list.filter(function (i) { return i.id in done; }).length; }
    return { done: n(this.items), total: this.items.length, requiredDone: n(req), requiredTotal: req.length,
      gatesDone: n(gates), gatesTotal: gates.length, updatedAt: state.updatedAt == null ? null : state.updatedAt, started: Object.keys(done).length > 0 };
  };
  PathModel.prototype.badge = function (state) {
    var done = (state || {}).done || {}, req = this.required(state || {});
    if (!req.length || req.some(function (i) { return !(i.id in done); })) return { earned: false };
    var stamps = req.map(function (i) { return done[i.id]; }).filter(function (t) { return typeof t === "number" && t > 1e11; });
    return { earned: true, at: stamps.length ? new Date(Math.max.apply(null, stamps)).toISOString().slice(0, 10) : null };
  };
  PathModel.prototype.firstOpen = function (state) {
    var done = (state || {}).done || {}, req = this.required(state || {});
    for (var i = 0; i < req.length; i++) if (!(req[i].id in done)) return req[i];
    return null;
  };
  PathModel.prototype.currentUnit = function (start, t) {
    if (this.unitName === "Week") return Math.floor(daysBetween(start, t) / 7) + 1;
    var d = new Date(start), n = 0;
    while (d <= t) { var wd = d.getDay(); if (wd >= 1 && wd <= 5) n++; d = addDays(d, 1); }
    return Math.max(n, 1);
  };
  PathModel.prototype.pace = function (state, start, t) {
    state = state || {};
    if (this.badge(state).earned) return { status: "finished", label: "Finished" };
    if (!start) return { status: "not_started", label: "Not started" };
    var s = parseIso(start);
    if (t < s) return { status: "upcoming", label: "Starts " + s.getDate() + " " + MON[s.getMonth()] };
    var cur = this.currentUnit(s, t), nxt = this.firstOpen(state), at = nxt ? nxt.unit : this.units, diff = cur - at;
    var unit = this.unitName.toLowerCase();
    var where = cur <= this.units ? this.unitName + " " + Math.min(cur, this.units) + " of " + this.units : "Past " + unit + " " + this.units;
    if (diff > 0) return { status: "behind", by: diff, current: cur, label: where + " · Behind by " + diff + " " + unit + (diff > 1 ? "s" : "") };
    if (diff < 0) return { status: "ahead", by: -diff, current: cur, label: where + " · Ahead by " + (-diff) + " " + unit + (diff < -1 ? "s" : "") };
    return { status: "on_track", current: cur, label: where + " · On track" };
  };
  function inactiveDays(state, earned, t) {
    state = state || {};
    if (earned || !Object.keys(state.done || {}).length) return 0;
    var last = state.updatedAt;
    if (typeof last !== "number" || last <= 0) return 0;
    var d = Math.floor((t - last) / DAY);
    return d >= INACTIVE_DAYS ? d : 0;
  }

  var AI_BLURB = "10 weeks, about 5 hours a week: Python, LLM APIs, RAG, MCP, agents, evals, production hardening and security, with a capstone agent you build week by week.";
  var AGENTIC_BLURB = "7 working days on DataRobot Agentic AI: LLM gateway, vector databases and RAG, the Agentic Starter, evaluation, deployment and monitoring.";

  function aiModel(content, source) {
    var items = [], roadmap = (content.roadmap || {}).weeks || {};
    (content.weeks || []).forEach(function (w) {
      var wk = parseInt(w.week, 10);
      w.items.forEach(function (it) {
        items.push({ id: it.id, unit: Math.max(wk, 1), label: "Week " + wk + ": " + it.title, anchor: "w" + wk, path: it.path, gate: !!it.gate,
          fastStretch: wk === 1 && it.path === "Required" && ["1", "2", "3", "4"].indexOf(String(it.day)) >= 0 });
      });
      if (String(wk) in roadmap) items.push({ id: "cap.w" + wk, unit: Math.max(wk, 1), label: "Week " + wk + ": capstone check", anchor: "w" + wk, path: "Required", gate: false });
    });
    (content.anyWeek || []).forEach(function (w) {
      w.items.forEach(function (it) { items.push({ id: it.id, unit: 1, label: "Any week: " + it.title, anchor: "w0", path: it.path, gate: false }); });
    });
    var blob = JSON.stringify(content).replace(/<\//g, "<\\/");
    var page = SRC.pages.aiTemplate.replace("<!-" + "-CONTENT_JSON-->", '<script id="content" type="application/json">' + blob + "<\/script>");
    var m = new PathModel({ id: "ai-engineer", title: "AI Engineer Learning Plan", blurb: AI_BLURB, length: "10 weeks", unitName: "Week",
      skill: "AI Engineering", units: 10, items: items, html: page, source: source });
    m.content = content;
    return m;
  }
  function htmlText(fragment, limit) {
    limit = limit || 90;
    var t = unescapeHtml(fragment.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
    return t.length <= limit ? t : t.slice(0, limit - 1).replace(/\s+$/, "") + "…";
  }
  function agenticModel(page, source) {
    var items = [], sec, re = /<section data-page="([^"]+)"[^>]*>([\s\S]*?)<\/section>/g;
    while ((sec = re.exec(page))) {
      var pid = sec[1], body = sec[2];
      if (pid === "team") continue;
      var m = /^day(\d+)$/.exec(pid);
      var day = m ? +m[1] : (pid === "start" ? 1 : 7);
      var dayLabel = m ? "Day " + day : (pid === "start" ? "Day 0" : "Appendix");
      var t, tr = /<([a-z0-9]+)([^>]*)\bdata-t="([^"]+)"([^>]*)>/g;
      while ((t = tr.exec(body))) {
        var attrs = t[2] + t[4];
        if (attrs.indexOf("data-opt") >= 0) continue;
        var end = t.index + t[0].length, snippet = body.slice(end, end + 1200);
        if (t[1] === "span") {
          var rs = Math.max(body.lastIndexOf("<tr", t.index - 3), body.lastIndexOf('<div class="lab-head"', t.index - 21));
          snippet = rs >= 0 ? body.slice(rs, t.index) + snippet.slice(0, 300) : snippet;
        }
        items.push({ id: t[3], unit: day, label: dayLabel + ": " + htmlText(snippet), anchor: pid, path: "Required", gate: false });
      }
    }
    return new PathModel({ id: "agentic", title: "Agentic AI Learning Path", blurb: AGENTIC_BLURB, length: "7 days", unitName: "Day",
      skill: "agentic", units: 7, items: items, html: page, source: source });
  }

  // ------------------------------------------------------------------ custom paths (custom_paths.py)
  var TYPES = ["Required", "Stretch", "Optional"];
  var RESERVED = ["admin", "api", "assets", "static", "new", "path", "agentic", "ai-engineer", "p"];
  var MAX_STEPS = 600;
  function newId(prefix) { return prefix + hex(8); }
  function slugify(t) { var s = String(t || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48).replace(/^-+|-+$/g, ""); return s || "path"; }
  function uniqueSlug(title, taken) {
    var base = slugify(title); if (RESERVED.indexOf(base) >= 0) base += "-path";
    var s = base, n = 2;
    while (taken[s] || RESERVED.indexOf(s) >= 0) { s = base + "-" + n; n++; }
    return s;
  }
  function blankContent(title, level, useDays, pace) {
    return { title: title || "Untitled learning path", blurb: "", length: "", pace: pace === "days" ? "days" : "weeks", level: level || "Week",
      useDays: !!useDays, skill: { enabled: false, name: "" }, groups: [{ id: newId("g"), title: "", days: [{ id: newId("d"), title: "", steps: [] }] }] };
  }
  function txt(v, limit) { return String(v == null ? "" : v).replace(/[ \t\r\f\v]+/g, " ").trim().slice(0, limit); }
  function link(v) {
    if (typeof v === "string") v = { url: v, label: "" };
    if (!v || typeof v !== "object") return null;
    var url = txt(v.url, 2000);
    if (!/^https?:\/\//i.test(url)) return null;
    return { url: url, label: txt(v.label, 200) || url };
  }
  function normalize(content) {
    if (!content || typeof content !== "object") fail(400, "The path content must be an object.");
    var seen = {};
    function ident(v, prefix) {
      v = String(v == null ? "" : v).replace(/[^A-Za-z0-9_.-]/g, "").slice(0, 40);
      if (!v || seen[v] || ["new", "none", "null"].indexOf(v.toLowerCase()) >= 0) { do { v = newId(prefix); } while (seen[v]); }
      seen[v] = true; return v;
    }
    var sk = content.skill || {};
    var out = { title: txt(content.title, 140) || "Untitled learning path", blurb: txt(content.blurb, 600), length: txt(content.length, 40),
      pace: content.pace === "days" ? "days" : "weeks", level: txt(content.level, 24) || "Week",
      useDays: content.useDays === undefined ? true : !!content.useDays, skill: { enabled: !!sk.enabled, name: txt(sk.name, 60) }, groups: [] };
    var n = 0;
    (content.groups || []).forEach(function (g) {
      if (!g || typeof g !== "object") return;
      var days = g.days;
      if (days == null && Array.isArray(g.steps)) days = [{ title: "", steps: g.steps }];
      var gd = { id: ident(g.id, "g"), title: txt(g.title, 160), days: [] };
      (days || []).forEach(function (d) {
        if (!d || typeof d !== "object") return;
        var dd = { id: ident(d.id, "d"), title: txt(d.title, 160), steps: [] };
        (d.steps || []).forEach(function (st) {
          if (!st || typeof st !== "object") return;
          var title = txt(st.title, 400); if (!title) return;
          n++; if (n > MAX_STEPS) fail(400, "A path can have at most " + MAX_STEPS + " steps.");
          dd.steps.push({ id: ident(st.id, "s"), title: title, details: String(st.details || "").trim().slice(0, 4000), link: link(st.link),
            type: TYPES.indexOf(st.type) >= 0 ? st.type : "Required", gate: !!st.gate, source: txt(st.source, 300) });
        });
        gd.days.push(dd);
      });
      if (!gd.days.length) gd.days.push({ id: ident(null, "d"), title: "", steps: [] });
      if (!out.useDays && gd.days.length > 1) {
        var merged = []; gd.days.forEach(function (d) { merged = merged.concat(d.steps); });
        gd.days = [Object.assign({}, gd.days[0], { title: "", steps: merged })];
      }
      out.groups.push(gd);
    });
    if (!out.groups.length) out.groups.push({ id: ident(null, "g"), title: "", days: [{ id: ident(null, "d"), title: "", steps: [] }] });
    return out;
  }
  function allSteps(c) {
    var out = [];
    (c.groups || []).forEach(function (g, gi) { (g.days || []).forEach(function (d, di) { (d.steps || []).forEach(function (st) { out.push({ gi: gi, g: g, di: di, d: d, st: st }); }); }); });
    return out;
  }
  function stepCount(c) { return allSteps(c || {}).length; }
  function whereLabel(c, gi, di) {
    var s = (c.level || "Week") + " " + (gi + 1);
    if (c.useDays && (c.groups[gi].days || []).length > 0) s += " · Day " + (di + 1);
    return s;
  }
  function customPage(doc, content) {
    var blob = JSON.stringify({ id: doc.id, status: doc.status, content: content }).replace(/<\//g, "<\\/");
    return SRC.pages.path.replace("<!-" + "-PATH_JSON-->", '<script id="path-data" type="application/json">' + blob + "<\/script>");
  }
  function customModel(doc, content) {
    var items = [], dayNo = 0;
    content.groups.forEach(function (g, gi) {
      g.days.forEach(function (d, di) {
        dayNo++;
        var unit = content.pace === "weeks" ? gi + 1 : dayNo;
        d.steps.forEach(function (st) { items.push({ id: st.id, unit: unit, label: whereLabel(content, gi, di) + ": " + st.title, anchor: "s-" + st.id, path: st.type, gate: st.gate }); });
      });
    });
    var units = content.pace === "weeks" ? content.groups.length : Math.max(dayNo, 1);
    var length = content.length || (content.pace === "weeks" ? units + " week" + (units !== 1 ? "s" : "") : units + " day" + (units !== 1 ? "s" : ""));
    var m = new PathModel({ id: doc.id, title: content.title, blurb: content.blurb || "", length: length, unitName: content.pace === "weeks" ? "Week" : "Day",
      skill: content.skill.enabled ? content.skill.name : "", units: Math.max(units, 1), items: items, html: customPage(doc, content), source: { kind: "custom" } });
    m.custom = true; m.skillEnabled = !!content.skill.enabled; m.owners = (doc.owners || []).slice();
    return m;
  }
  function diffContent(old, neu) {
    function index(c) { var idx = {}; allSteps(c).forEach(function (x) { idx[x.st.id] = { gi: x.gi, di: x.di, st: x.st, where: whereLabel(c, x.gi, x.di) }; }); return idx; }
    var a = index(old), b = index(neu), out = [], lvl = neu.level || "Week";
    var og = {}, ng = {};
    (old.groups || []).forEach(function (g, i) { og[g.id] = { i: i, g: g }; });
    (neu.groups || []).forEach(function (g, i) { ng[g.id] = { i: i, g: g }; });
    Object.keys(ng).forEach(function (id) {
      var x = ng[id], g = x.g;
      if (!og[id]) { var n = 0; g.days.forEach(function (d) { n += d.steps.length; }); out.push({ kind: "add", text: "New " + lvl.toLowerCase() + ": " + lvl + " " + (x.i + 1) + (g.title ? " — " + g.title : "") + " (" + n + " step" + (n !== 1 ? "s" : "") + ")" }); }
      else if (og[id].g.title !== g.title) out.push({ kind: "upd", text: lvl + " " + (x.i + 1) + " renamed: " + (g.title || "(no title)") });
    });
    Object.keys(og).forEach(function (id) { if (!ng[id]) { var x = og[id]; out.push({ kind: "del", text: "Removed " + lvl.toLowerCase() + ": " + lvl + " " + (x.i + 1) + (x.g.title ? " — " + x.g.title : "") }); } });
    var oldDays = {}; (old.groups || []).forEach(function (g) { g.days.forEach(function (d) { oldDays[d.id] = true; }); });
    (neu.groups || []).forEach(function (g, gi) {
      if (!og[g.id]) return;
      g.days.forEach(function (d, di) { if (neu.useDays && !oldDays[d.id]) out.push({ kind: "add", text: "New day: " + lvl + " " + (gi + 1) + " · Day " + (di + 1) + (d.title ? " — " + d.title : "") }); });
    });
    var moved = 0;
    Object.keys(b).forEach(function (sid) {
      var x = b[sid];
      if (!a[sid]) { out.push({ kind: "add", text: x.where + ": " + x.st.title, source: x.st.source || "" }); return; }
      var o = a[sid];
      if (old.groups[o.gi].days[o.di].id !== neu.groups[x.gi].days[x.di].id) moved++;
      else if (["title", "details", "link", "type", "gate"].some(function (k) { return !same(o.st[k], x.st[k]); })) out.push({ kind: "upd", text: "Changed " + x.where + ": " + x.st.title });
    });
    if (moved) out.push({ kind: "mov", text: "Moved " + moved + " step" + (moved !== 1 ? "s" : "") + " to another day or " + lvl.toLowerCase() });
    var removed = Object.keys(a).filter(function (x) { return !b[x]; });
    removed.slice(0, 20).forEach(function (sid) { out.push({ kind: "del", text: "Removed " + a[sid].where + ": " + a[sid].st.title }); });
    if (removed.length > 20) out.push({ kind: "del", text: "…and " + (removed.length - 20) + " more steps removed" });
    return out;
  }

  // ------------------------------------------------------------------ data
  var DB;
  function save() { try { localStorage.setItem(LS_KEY, JSON.stringify(DB)); } catch (e) {} }
  function load() {
    try { var raw = localStorage.getItem(LS_KEY); if (raw) { var d = JSON.parse(raw); if (d && d.v === SRC.version) return d; } } catch (e) {}
    return null;
  }
  var PATHS = {}, ORDER = [];
  function activate() {
    var ai = DB.content["ai-engineer"], ag = DB.content.agentic;
    var p = {};
    p["ai-engineer"] = aiModel(ai && !ai.reverted ? ai.content : SRC.aiContent,
      ai && !ai.reverted ? { kind: "uploaded", at: ai.publishedAt, by: ai.publishedBy, file: ai.file || "" } : { kind: "deployed", at: SRC.aiContent.meta.generatedAt, note: "" });
    p.agentic = agenticModel(ag && !ag.reverted ? ag.html : SRC.pages.agentic,
      ag && !ag.reverted ? { kind: "uploaded", at: ag.publishedAt, by: ag.publishedBy, file: ag.file || "" } : { kind: "deployed" });
    Object.keys(DB.custom).map(function (k) { return DB.custom[k]; })
      .sort(function (a, b) { return (a.publishedAt || 0) - (b.publishedAt || 0); })
      .forEach(function (doc) { if (doc.status === "published" && doc.live) p[doc.id] = customModel(doc, doc.live); });
    PATHS = p; ORDER = Object.keys(p);
  }

  // ------------------------------------------------------------------ learners
  function pathState(rec, pid) { if (!rec) return null; return pid === "agentic" ? rec.state || null : ((rec.paths || {})[pid] || null); }
  function startOf(rec, pid) {
    if (!rec) return null;
    var s = (rec.start || {})[pid]; if (s) return s;
    var st = pathState(rec, pid) || {};
    var stamps = [st.startedAt].concat(Object.keys(st.done || {}).map(function (k) { return st.done[k]; })).filter(function (t) { return typeof t === "number" && t > 1e11; });
    if (!stamps.length && Object.keys(st.done || {}).length && typeof st.updatedAt === "number") stamps = [st.updatedAt];
    return stamps.length ? iso(new Date(Math.min.apply(null, stamps))) : null;
  }
  function isEnrolled(rec, pid) {
    var e = ((rec || {}).enrolled || {})[pid];
    if (e && typeof e === "object") return !e.removed;
    return Object.keys((pathState(rec, pid) || {}).done || {}).length > 0;
  }
  function enrolledAt(rec, pid) {
    var e = ((rec || {}).enrolled || {})[pid];
    if (e && typeof e === "object" && !e.removed && typeof e.at === "number") return e.at;
    var s = startOf(rec, pid);
    if (s && isEnrolled(rec, pid)) { var d = parseIso(s); d.setHours(9); return d.getTime(); }
    return null;
  }
  function mascotStage(sm) { var d = sm.requiredDone, t = sm.requiredTotal; return t && d >= t ? 10 : (t ? Math.floor(10 * d / t) : 0); }
  function itemHref(pid, id) {
    var p = PATHS[pid];
    for (var i = 0; i < p.items.length; i++) if (p.items[i].id === id) {
      var prefix = p.custom ? "s-" : pid === "ai-engineer" ? "i-" : "t-";
      return pid + "/#" + prefix + id.replace(/[^A-Za-z0-9_-]/g, "-");
    }
    return pid + "/";
  }
  function learnerView(rec, pid) {
    var p = PATHS[pid], st = pathState(rec, pid) || {}, enrolled = isEnrolled(rec, pid);
    var start = enrolled ? startOf(rec, pid) : null, badge = p.badge(st);
    var kept = ((rec || {}).badges || {})[pid];
    if (!badge.earned && kept) badge = { earned: true, at: kept.at };
    var nxt = p.firstOpen(st), sm = p.summarize(st);
    var stage = Math.max(mascotStage(sm), parseInt(((rec || {}).mascots || {})[pid] || 0, 10));
    var stars = st.stars || {}, ids = p.ids();
    var v = Object.assign({}, sm, {
      skill: p.skill, skillEnabled: p.skillEnabled === undefined ? true : p.skillEnabled, custom: !!p.custom, enrolled: enrolled, start: start,
      cohort: cohortOf(start), pace: enrolled ? p.pace(st, start, today()) : { status: "not_enrolled", label: "Not enrolled" },
      badge: badge, mascot: stage, inactiveDays: enrolled ? inactiveDays(st, badge.earned, now()) : 0,
      nowOn: nxt ? nxt.label : (badge.earned ? "Finished" : ""), track: st.track || "", option: st.option || "",
      length: p.length, author: pathAuthor(pid),
      starred: Object.keys(stars).sort(function (a, b) { return stars[b] - stars[a]; }).filter(function (i) { return ids[i] || i.indexOf("cert.") === 0; }).slice(0, 50)
        .map(function (i) { return { id: i, label: p.labelOf(i), href: itemHref(pid, i) }; })
    });
    return v;
  }
  function statusPayload(v) {
    var o = {}; ["skill", "skillEnabled", "enrolled", "start", "cohort", "pace", "badge", "mascot", "done", "total", "requiredDone", "requiredTotal", "length", "author"].forEach(function (k) { o[k] = v[k]; });
    return o;
  }
  function rec(key) { return DB.records[key] || null; }
  function update(key, fn) { var r = DB.records[key] || (DB.records[key] = {}); fn(r); save(); return r; }

  // ------------------------------------------------------------------ users and roles (roles.py)
  var ROLES = ["admin", "author"];
  function normalizeEmail(raw) {
    var e = String(raw || "").trim().toLowerCase();
    if (e && e.indexOf("@") < 0) e += "@datarobot.com";
    if (!/^[a-z0-9._%+'-]+@[a-z0-9.-]+\.[a-z]{2,}$/.test(e)) throw new Error("Enter a valid email address.");
    if (!/@datarobot\.com$/.test(e)) throw new Error("Only @datarobot.com emails can be invited.");
    return e;
  }
  function isSystem(email) { return SYSTEM_ADMINS.indexOf((email || "").toLowerCase()) >= 0; }
  function rolesOf(email) {
    email = (email || "").toLowerCase(); if (!email) return [];
    var r = ((DB.users.users[email] || {}).roles || []).slice();
    if (isSystem(email) && r.indexOf("admin") < 0) r.push("admin");
    return ROLES.filter(function (x) { return r.indexOf(x) >= 0; });
  }
  function listing() {
    var users = DB.users.users, all = {};
    Object.keys(users).concat(SYSTEM_ADMINS).forEach(function (e) { all[e] = true; });
    return Object.keys(all).sort().map(function (email) {
      var u = users[email] || {};
      return { email: email, name: u.name || "", roles: rolesOf(email), system: isSystem(email), addedBy: u.addedBy || "", addedAt: u.addedAt || null,
        lastSeen: u.lastSeen || null, invited: !!u.invited };
    });
  }
  function ulog(by, what) { DB.users.log.push({ at: now(), by: by, what: what }); DB.users.log = DB.users.log.slice(-500); }
  function seen(email, name) {
    email = (email || "").toLowerCase();
    var users = DB.users.users;
    if (!users[email] && !isSystem(email)) return;
    var u = users[email] || (users[email] = { invited: false, roles: [], addedBy: "Runtime parameters", addedAt: null });
    if (u.lastSeen && now() - u.lastSeen < 6 * 3600000) return;
    u.lastSeen = now(); if (name) u.name = name; save();
  }

  // ------------------------------------------------------------------ identity
  var VIEWER = null;  // {email, name}
  function identify() {
    var email = VIEWER.email.toLowerCase(), roles = rolesOf(email), system = isSystem(email);
    var owns = Object.keys(DB.custom).filter(function (pid) { return (DB.custom[pid].owners || []).map(function (o) { return o.toLowerCase(); }).indexOf(email) >= 0; }).sort();
    seen(email, VIEWER.name);
    return { app: "dr-onboarding", id: email, name: VIEWER.name, email: VIEWER.email, roles: roles, isManager: roles.indexOf("admin") >= 0,
      isAuthor: roles.indexOf("author") >= 0 || roles.indexOf("admin") >= 0, isSystemAdmin: system, owns: owns,
      canAdmin: roles.length > 0 || owns.length > 0, welcome: welcomeBanner(email) };
  }
  function welcomeText(roles, by) {
    var admin = roles.indexOf("admin") >= 0, author = roles.indexOf("author") >= 0; by = by || "An admin";
    if (admin && author) return { title: "You're now an admin and an author", text: by + " gave you the Admin and Author roles. You can manage every learning path, see team progress and problem reports, invite people, and create learning paths: by hand, or from Jira, Confluence, GitHub and files with the LLM.", action: { label: "Open Admin", path: "admin/" } };
    if (admin) return { title: "You're now an admin", text: by + " gave you the Admin role. You can manage every learning path, see team progress and problem reports, and invite people.", action: { label: "Open Admin", path: "admin/" } };
    return { title: "You're now an author", text: by + " gave you the Author role. You can create learning paths: by hand, or from Jira, Confluence, GitHub and files with the LLM. You own the paths you create and see their progress and problem reports.", action: { label: "Create a learning path", path: "admin/#create" } };
  }
  function welcomeBanner(email) {
    var w = (DB.users.users[email] || {}).welcome;
    if (!w || !(w.roles || []).length) return null;
    return Object.assign({ roles: w.roles, label: w.roles.length > 1 ? "New roles" : "New role" }, welcomeText(w.roles, w.by));
  }
  function requirePath(pid) { if (!PATHS[pid]) fail(404, "Unknown learning path."); return PATHS[pid]; }
  function requireManager(me) { if (!me.isManager) fail(403, "Admins only."); }
  function canManage(me, pid) { return !!(me.isManager || me.owns.indexOf(pid) >= 0); }
  function requireManage(me, pid) { if (!canManage(me, pid)) fail(403, "Only this path's owners and the admins can do this."); }
  function requireAdminPage(me) { if (!me.canAdmin) fail(403, "Admins and authors only."); }
  function managedPaths(me) { return ORDER.filter(function (pid) { return canManage(me, pid); }); }
  function visibleReports(me) {
    return DB.reports.filter(function (r) {
      var kind = r.kind || "path";
      if (kind === "system") return me.isSystemAdmin;
      return me.isManager || me.owns.indexOf(r.path) >= 0;
    });
  }

  // ------------------------------------------------------------------ team
  function teamRows(pids) {
    pids = pids || ORDER;
    var rows = [];
    Object.keys(DB.records).forEach(function (key) {
      var r = DB.records[key], paths = {};
      pids.forEach(function (pid) { paths[pid] = learnerView(r, pid); });
      var vals = pids.map(function (p) { return paths[p]; });
      if (!vals.some(function (v) { return v.enrolled; })) return;
      var starts = vals.map(function (v) { return v.start; }).filter(Boolean).sort();
      var last = Math.max.apply(null, vals.map(function (v) { return v.updatedAt || 0; }).concat([0]));
      rows.push({ id: key, name: r.name || r.email || "", email: r.email || "", cohort: starts.length ? cohortOf(starts[0]) : "",
        lastActive: last || null, inactiveDays: Math.max.apply(null, vals.map(function (v) { return v.inactiveDays; }).concat([0])), paths: paths });
    });
    rows.sort(function (a, b) { return (b.lastActive || 0) - (a.lastActive || 0); });
    return rows;
  }
  function cohortKey(c) { var p = c.split(" "); return (+p[1] || 0) * 12 + MON.indexOf(p[0]); }
  function weekStart(d) { var x = new Date(d); x.setHours(0, 0, 0, 0); var wd = (x.getDay() + 6) % 7; return addDays(x, -wd); }
  function ticksOn(ids, pid) {
    var n = 0;
    Object.keys(DB.records).forEach(function (k) { var done = (pathState(DB.records[k], pid) || {}).done || {}; if (ids.some(function (i) { return i in done; })) n++; });
    return n;
  }

  // ------------------------------------------------------------------ uploads (in memory only)
  var UPLOADS = {};
  function takeUploads(me, ids, limit) {
    return (ids || []).slice(0, limit || 10).map(function (id) { return UPLOADS[String(id)]; }).filter(function (u) { return u && u.owner === me.id; });
  }
  function keepFiles(files) { return files.map(function (f) { return { name: f.name, size: f.size, type: f.type, blob: f.id }; }); }

  // ------------------------------------------------------------------ stand-in Jira
  var ROUTES = [
    [/vector|rag|embedding|chunk|knowledge base/i, "GENAI", "GenAI: vector databases and RAG"],
    [/agent|llm|gateway|playground|prompt/i, "AGENT", "Agentic workflows"],
    [/deploy|prediction|monitor|drift|inference/i, "MLOPS", "MLOps: deployments and monitoring"],
    [/notebook|codespace/i, "NB", "Notebooks and codespaces"],
    [/doc|typo|tutorial/i, "DOCS", "Documentation"],
    [/application|custom app|app source/i, "APPS", "Custom applications"]
  ];
  function jiraIssue(report, files) {
    var text = report.message + " " + (report.stepText || "") + " " + (report.links || []).join(" ");
    var hit = ROUTES.filter(function (r) { return r[0].test(text); })[0];
    var project = hit ? hit[1] : "SUPPORT";
    DB.jiraSeq = (DB.jiraSeq || 9000) + 1;
    var key = project + "-" + DB.jiraSeq;
    var first = report.message.trim().split("\n")[0];
    var summary = first.length > 90 ? first.slice(0, 89) + "…" : first;
    summary = summary.charAt(0).toUpperCase() + summary.slice(1);
    return { key: key, url: JIRA + "/browse/" + key, project: project, pod: hit ? hit[2] : "", routedTo: hit ? "page" : "fallback",
      summary: summary, why: hit ? "Matched the " + hit[2] + " pod on the org page." : "No pod on the org page matched, so it went to the fallback project.",
      attached: files.length, status: "Open", category: "new", syncedAt: now(), visible: true, simulated: true };
  }
  var JIRA_FLOW = [["Open", "new"], ["In Progress", "indeterminate"], ["Done", "done"]];
  function syncJira() {
    var n = 0;
    DB.reports.forEach(function (r) {
      var j = r.jira || {}; if (!j.key) return;
      n++;
      var i = JIRA_FLOW.map(function (x) { return x[0]; }).indexOf(j.status);
      var dupe = /duplicate|again|same/i.test(r.message);
      if (i >= 0 && i < JIRA_FLOW.length - 1) {
        var nx = dupe && i === 0 ? ["Closed", "done"] : JIRA_FLOW[i + 1];
        j.status = nx[0]; j.category = nx[1];
        if (nx[0] === "In Progress") j.assignee = "Alex Rivera";
        if (nx[1] === "done") { j.resolution = dupe ? "Duplicate" : "Done"; j.resolved = new Date().toISOString(); if (dupe) j.duplicateOf = { key: j.project + "-8812", url: JIRA + "/browse/" + j.project + "-8812", status: "In Progress" }; }
      }
      j.syncedAt = now(); j.visible = true; j.updated = new Date().toISOString();
      if (j.category === "done" && r.status !== "resolved") { r.status = "resolved"; r.resolvedBy = "Jira"; r.resolvedAt = now(); r.autoResolved = true; }
      else if (j.category !== "done" && r.status === "resolved" && r.autoResolved) { r.status = "open"; r.resolvedBy = ""; r.resolvedAt = null; r.autoResolved = false; }
      r.jira = j;
    });
    DB.meta.jiraSync = now(); save();
    if (n) event("jira", "Jira sync: read " + n + " issue" + (n !== 1 ? "s" : ""), "Each sync moves simulated issues one status along: Open → In Progress → Done (Closed as a duplicate when the report says it happened again).");
    return { synced: n };
  }

  // ------------------------------------------------------------------ jobs (find / generate / LLM edit)
  var JOBS = {};
  function startJob(kind, me, plan) {
    // plan: [{text, done?, wait}] progress steps, then result() run at the end
    var id = token(12), job = { id: id, kind: kind, owner: me.id, status: "running", progress: [], result: null, error: "" };
    JOBS[id] = job;
    var i = 0;
    function tick() {
      if (i < plan.steps.length) {
        var s = plan.steps[i++];
        if (job.progress.length && !job.progress[job.progress.length - 1].done) job.progress[job.progress.length - 1].done = true;
        if (s.final) { var last = job.progress[job.progress.length - 1]; if (last && last.text === s.replaces) { last.text = s.text; last.done = true; } else job.progress.push({ text: s.text, done: true }); }
        else job.progress.push({ text: s.text, done: !!s.done });
        setTimeout(tick, s.wait || 700);
        return;
      }
      try { job.result = plan.result(job); job.status = "done"; }
      catch (e) { job.status = "error"; job.error = e instanceof HttpError ? e.detail : String(e.message || e); }
    }
    setTimeout(tick, 200);
    return job;
  }
  function publicJob(j) { return { id: j.id, kind: j.kind, status: j.status, progress: j.progress, result: j.result, error: j.error }; }
  function getJob(me, jid) { var j = JOBS[jid]; if (!j || j.owner !== me.id) fail(404, "This job has expired. Start again."); return j; }

  function linkKind(u) {
    if (/^[A-Z][A-Z0-9]+-\d+$/.test(u) || /atlassian\.net\/browse\//.test(u)) return "jira";
    if (/atlassian\.net\/wiki\//.test(u)) return "confluence";
    if (/github\.com\//.test(u)) return "github";
    if (/docs\.google\.com/.test(u)) return "gdoc";
    return "web";
  }
  function findResult(links, files) {
    var groups = [], n = 0, chars = 0, images = 0;
    function g(kind, title, summary, items, warnings) { n++; var id = "g" + n; groups.push({ id: id, kind: kind, title: title, summary: summary || "", warnings: warnings || [],
      items: items.map(function (it, i) { return Object.assign({ id: id + "i" + (i + 1), checked: true, note: "", count: 1 }, it); }) }); }
    links.forEach(function (u) {
      var k = linkKind(u);
      if (k === "jira") {
        var key = (/([A-Z][A-Z0-9]+-\d+)/.exec(u) || [u])[1];
        var tmpl = SRC.found.groups.filter(function (x) { return x.kind === "jira"; })[0];
        if (tmpl) { var copy = clone(tmpl); copy.title = key + " · " + copy.title.split(" · ").slice(1).join(" · "); n++; copy.id = "g" + n; copy.items.forEach(function (it, i) { it.id = copy.id + "i" + (i + 1); }); groups.push(copy); }
        chars += 18000; images += 1;
      } else if (k === "confluence") {
        var title = decodeURIComponent((u.split("/").pop() || "Page").replace(/\+/g, " "));
        g("confluence", "Confluence: " + title, "3 pages", [{ label: "3 pages (the page and its child pages)" }]); chars += 9000;
      } else if (k === "github") {
        var repo = u.replace(/^https?:\/\/github\.com\//, "").split("/").slice(0, 2).join("/");
        g("github", "GitHub: " + repo, "README, 6 docs pages, 4 examples", [{ label: "README and 6 docs pages" }, { label: "4 examples" }],
          [{ title: "Source code isn't read", text: "The app reads the README, docs and examples. Add a docs link if a feature is only described in code." }]); chars += 12000;
      } else if (k === "gdoc") {
        g("web", "Google Doc", "", [], [{ title: "The app can't open Google Docs", text: "Download it as PDF or Word and upload it below." }]);
      } else {
        g("web", u.replace(/^https?:\/\//, "").slice(0, 80), "1 page", [{ label: "1 web page" }]); chars += 4000;
      }
    });
    if (files.length) {
      g("files", "Your files", "", files.map(function (f) { return { label: f.name }; }));
      files.forEach(function (f) { chars += Math.min(f.size, 40000); if (/^image\//.test(f.type)) images++; });
    }
    return { groups: groups, chars: chars, pages: chars ? Math.max(1, Math.round(chars / 3000)) : 0, images: images };
  }
  function sampleContent(settings) {
    var c = clone(SRC.generated);
    if (settings.title) c.title = settings.title;
    if (settings.level) c.level = settings.level;
    if (settings.useDays !== undefined) c.useDays = !!settings.useDays;
    if (settings.pace) c.pace = settings.pace;
    c.skill = { enabled: !!settings.skillEnabled, name: String(settings.skillName || "") };
    return c;
  }
  function editScope(content, scope) {
    scope = scope || {};
    var t = scope.type || "path", id = scope.id;
    if (t === "step") { var hit = allSteps(content).filter(function (x) { return x.st.id === id; })[0]; if (hit) return { kind: "step", st: hit.st, d: hit.d }; }
    if (t === "day") { var d = null; content.groups.forEach(function (g) { g.days.forEach(function (x) { if (x.id === id) d = x; }); }); if (d) return { kind: "day", d: d }; }
    if (t === "group") { var g = content.groups.filter(function (x) { return x.id === id; })[0]; if (g) return { kind: "group", g: g }; }
    return { kind: "all" };
  }
  function simulatedEdit(content, instruction, scope) {
    var c = clone(content), sc = editScope(c, scope), ins = instruction.trim();
    var short = ins.length > 70 ? ins.slice(0, 69) + "…" : ins;
    var removing = /\b(remove|delete|drop|cut|shorter|fewer)\b/i.test(ins);
    if (sc.kind === "step") {
      if (removing) sc.d.steps = sc.d.steps.filter(function (s) { return s !== sc.st; });
      else { sc.st.details = (sc.st.details ? sc.st.details + "\n\n" : "") + "Rewritten for: " + short; if (/stretch|optional/i.test(ins)) sc.st.type = /optional/i.test(ins) ? "Optional" : "Stretch"; }
    } else if (sc.kind === "day" || sc.kind === "group") {
      var day = sc.kind === "day" ? sc.d : sc.g.days[sc.g.days.length - 1];
      if (removing && day.steps.length) day.steps.pop();
      else day.steps.push({ id: "new", title: "Lab: " + short.replace(/^(add|write|create)\s+(a|an)?\s*/i, ""), details: "Written by the stand-in LLM from your instruction.", link: null, type: "Required", gate: false, source: "" });
      
    } else {
      if (removing) { var g = c.groups[c.groups.length - 1]; var d = g.days[g.days.length - 1]; if (d.steps.length) d.steps.pop(); }
      else c.groups.push({ id: "new", title: short.replace(/^(add|write|create)\s+(a|an)?\s*/i, "").replace(/^./, function (x) { return x.toUpperCase(); }),
        days: [{ id: "new", title: "", steps: [{ id: "new", title: "Read: " + short, details: "Written by the stand-in LLM from your instruction.", link: null, type: "Required", gate: false, source: "" },
          { id: "new", title: "Check yourself: explain it to a teammate in two minutes", details: "", link: null, type: "Stretch", gate: false, source: "" }] }] });
    }
    return normalize(c);
  }

  // ------------------------------------------------------------------ paths made in the app
  function pathDoc(pid) { var d = DB.custom[pid]; if (!d) fail(404, "No such path."); return d; }
  function savePath(doc) { doc.updatedAt = now(); DB.custom[doc.id] = doc; save(); }
  function parseOwners(raw, creator) {
    var items = Array.isArray(raw) ? raw : String(raw || "").split(/[,;\s]+/);
    var out = creator ? [creator.toLowerCase()] : [];
    items.forEach(function (x) {
      x = String(x).trim(); if (!x || ["you", "me"].indexOf(x.toLowerCase()) >= 0) return;
      var e; try { e = normalizeEmail(x); } catch (err) { fail(400, "Owners: " + x + ": " + err.message); }
      if (out.indexOf(e) < 0) out.push(e);
    });
    return out;
  }
  function newPath(me, content, ownersRaw, origin) {
    var taken = {}; Object.keys(DB.custom).concat(ORDER).forEach(function (k) { taken[k] = true; });
    var pid = uniqueSlug(content.title || "path", taken);
    var doc = { id: pid, status: "draft", owners: parseOwners(ownersRaw, me.email), createdBy: me.name, createdByEmail: me.email.toLowerCase(),
      createdAt: now(), origin: origin || "app", draft: normalize(content), live: null };
    savePath(doc); return doc;
  }
  function pathRow(pid, counts) {
    if (DB.custom[pid]) {
      var d = DB.custom[pid], c = d.draft || d.live || {};
      return { id: pid, title: c.title || pid, status: d.status, custom: true, steps: stepCount(c), enrolled: counts[pid] || 0, owners: d.owners || [],
        unpublished: d.status === "published" && !same(d.draft, d.live), updatedAt: d.updatedAt };
    }
    var p = PATHS[pid];
    return { id: pid, title: p.title, status: "published", custom: false, steps: p.items.length, enrolled: counts[pid] || 0, owners: [], source: p.source };
  }

  // ------------------------------------------------------------------ routes
  var R = [];
  function route(method, pattern, fn) { R.push({ method: method, re: new RegExp("^" + pattern.replace(/\{(\w+)\}/g, "([^/]+)") + "$"), fn: fn }); }
  function body(req) { if (req.json === undefined) { try { req.json = req.text ? JSON.parse(req.text) : {}; } catch (e) { fail(400, "Body must be JSON."); } } return req.json || {}; }

  route("GET", "/api/me", function () { return identify(); });
  route("GET", "/api/summary", function () {
    var me = identify(), r = rec(me.id);
    var out = { me: me, paths: ORDER.map(function (pid) { var p = PATHS[pid]; return Object.assign({ id: pid, title: p.title, skill: p.skill, blurb: p.blurb, length: p.length }, learnerView(r, pid)); }) };
    if (me.canAdmin) out.openReports = visibleReports(me).filter(function (x) { return x.status === "open"; }).length;
    return out;
  });
  route("GET", "/api/team-summary", function () {
    var me = identify(); requireAdminPage(me);
    var pids = managedPaths(me), rows = teamRows(pids), cs = {};
    rows.forEach(function (r) { if (r.cohort) cs[r.cohort] = true; });
    return { paths: pids.map(function (pid) { return { id: pid, title: PATHS[pid].title, unit: PATHS[pid].unitName }; }), learners: rows,
      cohorts: Object.keys(cs).sort(function (a, b) { return cohortKey(b) - cohortKey(a); }), inactiveAfterDays: INACTIVE_DAYS };
  });
  route("GET", "/api/reports", function () {
    var me = identify(); requireAdminPage(me);
    var reps = clone(visibleReports(me)).sort(function (a, b) { return b.createdAt - a.createdAt; });
    reps.forEach(function (r) { r.kind = r.kind || "path"; (r.files || []).forEach(function (f) { delete f.blob; }); });
    return { reports: reps, lastSync: DB.meta.jiraSync || null, jira: true };
  });
  route("POST", "/api/reports/{id}", function (req, m) {
    var me = identify(); requireAdminPage(me);
    var status = body(req).status;
    if (status !== "open" && status !== "resolved") fail(400, 'status must be "open" or "resolved".');
    if (!visibleReports(me).some(function (r) { return r.id === m[1]; })) fail(404, "No such report.");
    var r = DB.reports.filter(function (x) { return x.id === m[1]; })[0];
    r.status = status; r.resolvedBy = status === "resolved" ? me.name : ""; r.resolvedAt = status === "resolved" ? now() : null;
    save(); return { ok: true, report: r };
  });
  route("POST", "/api/jira/sync", function () { requireAdminPage(identify()); var res = syncJira(); res.lastSync = DB.meta.jiraSync; return res; });
  route("GET", "/api/reports/{id}/files/{n}", function (req, m) {
    var me = identify(); requireAdminPage(me);
    var r = visibleReports(me).filter(function (x) { return x.id === m[1]; })[0], f = r && (r.files || [])[+m[2]];
    var u = f && UPLOADS[f.blob];
    if (!u) fail(404, "Files from earlier staging sessions aren't kept.");
    return { __blob: u.file, name: f.name };
  });

  route("GET", "/api/admin/content", function () {
    requireManager(identify());
    return { paths: ["ai-engineer", "agentic"].map(function (pid) { var p = PATHS[pid]; return { id: pid, title: p.title, steps: p.items.length, source: p.source }; }) };
  });
  route("GET", "/api/admin/content/ai-engineer/content.json", function () { requireManager(identify()); return PATHS["ai-engineer"].content; });
  var PENDING = {};
  route("POST", "/api/admin/content/{pid}/preview", function (req, m) {
    var me = identify(); requireManager(me);
    var pid = m[1], p = requirePath(pid), inApp = /^application\/json/.test(req.headers["content-type"] || ""), payload, summary, newModel, file = req.headers["x-file-name"] || "";
    if (!inApp) {
      if (pid === "ai-engineer") fail(400, "Staging can't read .xlsx uploads. Use Edit in the app, or try the upload in DataRobot.");
      payload = { html: req.text };
    }
    if (pid === "ai-engineer") {
      var content = body(req).content;
      if (!content || !content.weeks || !content.weeks.length) fail(400, "The plan has no weeks.");
      content.meta = Object.assign({}, (p.content || {}).meta, content.meta);
      function idx(c) { var o = {}; (c.weeks || []).concat(c.anyWeek || []).forEach(function (w) { w.items.forEach(function (it) { o[it.id] = "Week " + w.week + ": " + it.title; }); }); ((c.certs || {}).rows || []).forEach(function (r) { o[r.id] = "Certification: " + r.name; }); return o; }
      var oi = idx(p.content), ni = idx(content);
      newModel = aiModel(content, {}); payload = { content: content }; file = "edited in the app";
      var rows = 0; content.weeks.concat(content.anyWeek || []).forEach(function (w) { rows += w.items.length; });
      summary = { counts: content.weeks.length + " weeks, " + rows + " plan steps, " + content.options.options.length + " capstone options, " + content.certs.rows.length + " certifications",
        added: Object.keys(ni).filter(function (i) { return !oi[i]; }).sort().map(function (i) { return { id: i, label: ni[i] }; }),
        removed: Object.keys(oi).filter(function (i) { return !ni[i]; }).sort().map(function (i) { return { id: i, label: oi[i] }; }) };
    } else {
      var html = payload ? payload.html : null;
      if (inApp) {
        var main = (body(req).main || "").replace(/<script\b[\s\S]*?<\/script>/gi, "");
        if (!/<main id="main">[\s\S]*?<\/main>/.test(p.html)) fail(400, "The live page has no <main> section to update.");
        html = p.html.replace(/(<main id="main">)([\s\S]*?)(<\/main>)/, function (_, a, b2, c) { return a + "\n" + main + "\n  " + c; });
        file = "edited in the app";
      }
      var seenT = {};
      html = html.replace(/data-t="([^"]+)"/g, function (all, t) { seenT[t] = (seenT[t] || 0) + 1; return seenT[t] === 1 ? all : 'data-t="' + t + "-n" + seenT[t] + '"'; });
      if (html.indexOf("<section data-page=") < 0 || html.indexOf("data-t=") < 0) fail(400, "This isn't the Agentic learning-path page: it has no learning-path sections or steps. Download the current page from this screen, edit it, and upload that file.");
      newModel = agenticModel(html, {}); payload = { html: html };
      var oids = p.ids(), nids = newModel.ids();
      summary = { counts: Object.keys(nids).length + " steps",
        added: Object.keys(nids).filter(function (i) { return !oids[i]; }).sort().map(function (i) { return { id: i, label: newModel.labelOf(i) }; }),
        removed: Object.keys(oids).filter(function (i) { return !nids[i]; }).sort().map(function (i) { return { id: i, label: p.labelOf(i) }; }) };
    }
    summary.learnersAffected = ticksOn(summary.removed.map(function (r) { return r.id; }), pid);
    summary.stepsBefore = p.items.length; summary.stepsAfter = newModel.items.length;
    var tk = token(16); PENDING[tk] = { path: pid, payload: payload, file: decodeURIComponent(file) };
    return { token: tk, summary: summary };
  });
  route("POST", "/api/admin/content/{pid}/publish", function (req, m) {
    var me = identify(); requireManager(me); requirePath(m[1]);
    var pend = PENDING[body(req).token || ""]; delete PENDING[body(req).token || ""];
    if (!pend || pend.path !== m[1]) fail(400, "This preview has expired. Upload the file again.");
    DB.content[m[1]] = Object.assign({}, pend.payload, { publishedAt: now(), publishedBy: me.name, file: pend.file });
    save(); activate();
    return { ok: true, source: PATHS[m[1]].source, steps: PATHS[m[1]].items.length };
  });
  route("POST", "/api/admin/content/{pid}/revert", function (req, m) {
    var me = identify(); requireManager(me); requirePath(m[1]);
    DB.content[m[1]] = { reverted: true, publishedAt: now(), publishedBy: me.name }; save(); activate();
    return { ok: true, source: PATHS[m[1]].source };
  });

  route("GET", "/api/dashboard", function (req) {
    var me = identify(); requireAdminPage(me);
    var pids = managedPaths(me), weeks = Math.max(4, Math.min(+((/weeks=(\d+)/.exec(req.query) || [])[1] || 12), 52)), t = now();
    var thisWeek = weekStart(today()), starts = [];
    for (var i = 0; i < weeks; i++) starts.push(addDays(thisWeek, -7 * (weeks - 1 - i)));
    var idx = {}; starts.forEach(function (d, i) { idx[iso(d)] = i; });
    function wi(ts) { var k = iso(weekStart(new Date(ts))); return k in idx ? idx[k] : null; }
    var out = {}, anyL = {}, anyA = {};
    pids.forEach(function (pid) {
      var p = PATHS[pid], ids = p.ids();
      var tiles = { enrolled: 0, newThisMonth: 0, active7: 0, notStarted: 0, completed: 0, completed30: 0, onTrack: 0, behind: 0, ahead: 0 }, pct = 0;
      var active = starts.map(function () { return {}; }), ticks = starts.map(function () { return 0; }), enrolls = starts.map(function () { return 0; });
      Object.keys(DB.records).forEach(function (key) {
        var r = DB.records[key]; if (!isEnrolled(r, pid)) return;
        var v = learnerView(r, pid), st = pathState(r, pid) || {};
        tiles.enrolled++; anyL[key] = true;
        var ea = enrolledAt(r, pid);
        if (ea && ea >= t - 30 * DAY) tiles.newThisMonth++;
        if (ea) { var w = wi(ea); if (w !== null) enrolls[w]++; }
        if (!v.started) tiles.notStarted++;
        if (v.badge.earned) { tiles.completed++; if (v.badge.at && parseIso(v.badge.at) >= addDays(today(), -30)) tiles.completed30++; }
        var s = v.pace.status;
        if (s === "on_track" || s === "finished") tiles.onTrack++; else if (s === "behind") tiles.behind++; else if (s === "ahead") tiles.ahead++;
        pct += v.requiredTotal ? v.requiredDone / v.requiredTotal : 0;
        Object.keys(st.done || {}).forEach(function (id) { var ts = st.done[id]; if (!ids[id] || typeof ts !== "number" || ts < 1e11) return; var w = wi(ts); if (w !== null) { ticks[w]++; active[w][key] = true; } });
        if (typeof st.updatedAt === "number" && st.updatedAt >= t - 7 * DAY && Object.keys(st.done || {}).length) { tiles.active7++; anyA[key] = true; }
      });
      tiles.avgRequiredPct = tiles.enrolled ? Math.round(100 * pct / tiles.enrolled) : 0;
      out[pid] = { title: p.title, tiles: tiles, activeLearners: active.map(function (a) { return Object.keys(a).length; }), ticks: ticks, enrollments: enrolls };
    });
    return { weeks: starts.map(iso), paths: out, order: pids,
      overall: { learners: Object.keys(anyL).length, active7: Object.keys(anyA).length, openReports: visibleReports(me).filter(function (r) { return r.status === "open"; }).length } };
  });
  route("GET", "/api/health", function () {
    return { storage: "staging (this browser)", progressFilesId: null, managers: SYSTEM_ADMINS.length, slack: true,
      jira: { connected: true, site: JIRA, issueType: "Bug", fallback: "SUPPORT", routingPage: { url: JIRA + "/wiki/spaces/ENG/overview", title: "Engineering (simulated)", readAt: now(), error: "" }, extraProjects: [] },
      llm: { available: true, generate: "stand-in", reports: "stand-in", catalog: ["stand-in"] },
      paths: (function () { var o = {}; ORDER.forEach(function (pid) { o[pid] = { steps: PATHS[pid].items.length, content: PATHS[pid].source.kind }; }); return o; })(),
      customPaths: (function () { var o = {}; Object.keys(DB.custom).forEach(function (k) { o[k] = DB.custom[k].status; }); return o; })(),
      problems: ["This is the staging copy: Jira, Confluence, the LLM Gateway and Slack are simulated."] };
  });
  route("POST", "/api/uploads", function (req) {
    var me = identify();
    if (!req.file || !req.file.size) fail(400, "The file is empty.");
    if (req.file.size > 20000000) fail(413, "Each file can be at most 20 MB.");
    var name = decodeURIComponent(req.headers["x-file-name"] || req.file.name || "file").replace(/[\\/\x00-\x1f]/g, "_").slice(0, 160) || "file";
    var id = token(14);
    UPLOADS[id] = { id: id, name: name, type: (req.headers["content-type"] || req.file.type || "application/octet-stream").slice(0, 100), size: req.file.size, owner: me.id, file: req.file, at: now() };
    return { id: id, name: name, size: req.file.size };
  });

  route("GET", "/api/admin/users", function () {
    var me = identify(); requireManager(me);
    var owns = {};
    Object.keys(DB.custom).forEach(function (pid) { var d = DB.custom[pid], c = d.live || d.draft || {}; (d.owners || []).forEach(function (o) { (owns[o.toLowerCase()] = owns[o.toLowerCase()] || []).push({ id: pid, title: c.title || pid, status: d.status }); }); });
    var rows = listing();
    rows.forEach(function (u) { u.owns = owns[u.email] || []; if (!u.name) { var r = DB.records[u.email]; u.name = (r && r.name) || titleName(u.email); } });
    return { users: rows, me: me.email.toLowerCase() };
  });
  route("POST", "/api/admin/users", function (req) {
    var me = identify(); requireManager(me);
    var email; try { email = normalizeEmail(body(req).email); } catch (e) { fail(400, e.message); }
    var u = DB.users.users[email];
    if (!(u && u.invited)) { DB.users.users[email] = Object.assign({}, u || {}, { invited: true, roles: (u || {}).roles || [], addedBy: me.name, addedAt: now() }); ulog(me.name, "invited " + email); save(); }
    return { user: listing().filter(function (x) { return x.email === email; })[0] };
  });
  route("PUT", "/api/admin/users/{email}", function (req, m) {
    var me = identify(); requireManager(me);
    var email = decodeURIComponent(m[1]).toLowerCase(), want = body(req).roles || [];
    var roles = ROLES.filter(function (r) { return want.indexOf(r) >= 0; });
    if (isSystem(email) && roles.indexOf("admin") < 0) fail(400, "System admins are set in the app's runtime parameters and keep the Admin role.");
    var u = DB.users.users[email];
    if (!u && !isSystem(email)) fail(404, "Invite this person first.");
    u = u || { invited: true, addedBy: "Runtime parameters", addedAt: null };
    var before = (u.roles || []).slice().sort();
    u.roles = roles.filter(function (r) { return !(r === "admin" && isSystem(email)); });
    var addedR = u.roles.filter(function (r) { return before.indexOf(r) < 0; });
    var pend = ((u.welcome || {}).roles || []).filter(function (r) { return u.roles.indexOf(r) >= 0; });
    pend = ROLES.filter(function (r) { return pend.indexOf(r) >= 0 || addedR.indexOf(r) >= 0; });
    if (addedR.length) u.welcome = { roles: pend, by: me.name, at: now() }; else if (pend.length) u.welcome.roles = pend; else delete u.welcome;
    DB.users.users[email] = u;
    ulog(me.name, "roles of " + email + ": " + (before.join(", ") || "none") + " -> " + (roles.join(", ") || "none"));
    save();
    if (addedR.length) { var wt = welcomeText(addedR, me.name), nm = (u.name || titleName(email)).split(" ")[0];
      event("slack", "Slack DM to " + (u.name || titleName(email)) + ": " + wt.title + " in DataRobot Onboarding", "Hi " + nm + ", " + wt.text + "\n" + wt.action.label + " · Open the onboarding hub"); }
    return { user: listing().filter(function (x) { return x.email === email; })[0] };
  });
  route("DELETE", "/api/admin/users/{email}", function (req, m) {
    var me = identify(); requireManager(me);
    var email = decodeURIComponent(m[1]).toLowerCase();
    if (isSystem(email)) fail(400, "System admins are set in the app's runtime parameters and can't be removed here.");
    if (!DB.users.users[email]) fail(404, "No such user.");
    delete DB.users.users[email]; ulog(me.name, "removed " + email); save();
    return { ok: true };
  });
  route("POST", "/api/welcome/dismiss", function () { var me = identify(), u = DB.users.users[me.email.toLowerCase()]; if (u && u.welcome) { delete u.welcome; save(); } return { ok: true }; });
  route("POST", "/api/admin/system-report", function (req) {
    var me = identify(); requireManager(me);
    var d = body(req), message = String(d.message || "").trim();
    if (!message) fail(400, "Write a short description of the problem.");
    var rid = hex(12);
    var report = { id: rid, kind: "system", path: "admin", pathTitle: "Admin", itemId: "", itemLabel: String(d.about || "Admin → Users").slice(0, 200), anchor: "",
      message: message.slice(0, 4000), learnerId: me.id, name: me.name, email: me.email, createdAt: now(), status: "open", files: keepFiles(takeUploads(me, d.uploads)) };
    DB.reports.push(report); save();
    event("slack", "Slack (#onboarding): problem report to the system admins from " + me.name, message.slice(0, 300));
    return { ok: true };
  });

  route("GET", "/api/admin/paths", function () {
    var me = identify(); requireAdminPage(me);
    var counts = {};
    Object.keys(DB.records).forEach(function (k) { ORDER.forEach(function (pid) { if (isEnrolled(DB.records[k], pid)) counts[pid] = (counts[pid] || 0) + 1; }); });
    var ids = ORDER.filter(function (pid) { return !DB.custom[pid] && me.isManager; })
      .concat(Object.keys(DB.custom).map(function (k) { return DB.custom[k]; }).sort(function (a, b) { return (a.createdAt || 0) - (b.createdAt || 0); })
        .filter(function (d) { return canManage(me, d.id); }).map(function (d) { return d.id; }));
    return { paths: ids.map(function (pid) { return pathRow(pid, counts); }), canCreate: me.isAuthor, jira: true, llm: true };
  });
  route("POST", "/api/admin/paths", function (req) {
    var me = identify(); if (!me.isAuthor) fail(403, "Only admins and authors can create learning paths.");
    var d = body(req);
    var c = blankContent(d.title || "", d.level || "Week", d.useDays === undefined ? true : d.useDays, d.pace || "weeks");
    c.blurb = String(d.blurb || "").slice(0, 600);
    c.skill = { enabled: !!d.skillEnabled, name: String(d.skillName || "").slice(0, 60) };
    return { id: newPath(me, c, d.owners || "").id };
  });
  route("GET", "/api/admin/jobs/{id}", function (req, m) { return publicJob(getJob(identify(), m[1])); });
  route("POST", "/api/admin/paths/find", function (req) {
    var me = identify(); if (!me.isAuthor) fail(403, "Only admins and authors can create learning paths.");
    var d = body(req);
    var links = (d.links || []).map(function (x) { return String(x).trim(); }).filter(Boolean).slice(0, 20);
    var files = takeUploads(me, d.uploads, 20);
    if (!links.length && !files.length) fail(400, "Add at least one link or file.");
    var xl = files.filter(function (f) { return /\.xlsx$/i.test(f.name); })[0];
    if (xl) {
      var st = d.settings || {}, c = sampleContent(st);
      c.title = st.title || xl.name.replace(/\.xlsx$/i, "");
      var doc = newPath(me, c, st.owners || "", "template");
      return { imported: doc.id, note: "The .xlsx template was imported as it is." + (links.length || files.length > 1 ? " Your other links and files weren't used." : "") + " (Staging can't read .xlsx files, so this is the sample path.)" };
    }
    var steps = [];
    links.forEach(function (u) {
      var k = linkKind(u);
      if (k === "jira") { var key = (/([A-Z][A-Z0-9]+-\d+)/.exec(u) || [u])[1]; steps.push({ text: "Reading " + key + "…", wait: 700 }, { text: "Reading attachment PRD v3.pdf…", wait: 700 }); }
      else if (k === "confluence") steps.push({ text: "Reading the Confluence page and its child pages…", wait: 600 });
      else if (k === "github") steps.push({ text: "Reading the GitHub repo " + u.replace(/^https?:\/\/github\.com\//, "").split("/").slice(0, 2).join("/") + "…", wait: 700 });
      else steps.push({ text: "Reading " + u.replace(/^https?:\/\//, "").slice(0, 60) + "…", wait: 400 });
    });
    files.forEach(function (f) { steps.push({ text: "Reading " + f.name + "…", wait: 400 }); });
    var res = findResult(links, files);
    steps.push({ text: "Found about " + res.pages + " page" + (res.pages !== 1 ? "s" : "") + " of material", final: true, wait: 100 });
    var job = startJob("find", me, { steps: steps, result: function (j) { j.found = true; return res; } });
    return { job: job.id };
  });
  route("POST", "/api/admin/paths/generate", function (req) {
    var me = identify(); if (!me.isAuthor) fail(403, "Only admins and authors can create learning paths.");
    var d = body(req), found = getJob(me, String(d.job || ""));
    if (found.status !== "done" || found.kind !== "find") fail(400, "Wait until the sources have been read.");
    var settings = d.settings || {}; parseOwners(settings.owners || "", me.email);
    var content = sampleContent(settings), n = stepCount(content), groups = content.groups.length, lvl = (content.level || "Week").toLowerCase();
    var kinds = {}; found.result.groups.forEach(function (g) { kinds[g.kind] = (kinds[g.kind] || 0) + 1; });
    var read = Object.keys(kinds).map(function (k) { return kinds[k] + " " + ({ jira: "Jira source", confluence: "Confluence source", github: "GitHub repo", files: "file group", web: "web page" }[k] || k) + (kinds[k] !== 1 ? "s" : ""); }).join(", ");
    var steps = [{ text: "Read " + read, done: true, wait: 500 }, { text: "Planning the path and writing the steps…", wait: 2200 },
      { text: "Planned " + groups + " " + lvl + (groups !== 1 ? "s" : "") + ", " + n + " steps", final: true, replaces: "Planning the path and writing the steps…", wait: 300 },
      { text: "Checking every link…", wait: 900 }, { text: "Checked every link: 1 didn't open", final: true, replaces: "Checking every link…", wait: 100 }];
    var job = startJob("generate", me, { steps: steps, result: function () {
      var doc = newPath(me, content, settings.owners || "", "sources");
      var cov = clone(SRC.generateMeta);
      doc.generation = { coverage: cov.coverage, broken: cov.broken, warnings: cov.warnings, at: now() };
      savePath(doc);
      return { id: doc.id, coverage: cov.coverage, broken: cov.broken, warnings: cov.warnings };
    } });
    return { job: job.id };
  });
  route("GET", "/api/admin/paths/{pid}", function (req, m) { var me = identify(); requireManage(me, m[1]); return { path: pathDoc(m[1]), canEdit: true }; });
  route("PUT", "/api/admin/paths/{pid}/draft", function (req, m) {
    var me = identify(); requireManage(me, m[1]);
    var doc = pathDoc(m[1]), d = body(req);
    doc.draft = normalize(d.content || {});
    if ("owners" in d) doc.owners = parseOwners(d.owners, (doc.owners || [me.email])[0]);
    doc.editedBy = me.name; savePath(doc);
    return { ok: true, draft: doc.draft, owners: doc.owners, updatedAt: doc.updatedAt };
  });
  route("POST", "/api/admin/paths/{pid}/publish", function (req, m) {
    var me = identify(); requireManage(me, m[1]);
    var doc = pathDoc(m[1]), content = normalize(doc.draft);
    if (!stepCount(content)) fail(400, "Add at least one step before publishing.");
    var removed = [];
    if (doc.live) { var nids = {}; allSteps(content).forEach(function (x) { nids[x.st.id] = true; }); removed = allSteps(doc.live).map(function (x) { return x.st.id; }).filter(function (i) { return !nids[i]; }); }
    doc.live = content; doc.draft = clone(content); doc.status = "published";
    doc.publishedAt = doc.publishedAt || now(); doc.publishedBy = me.name; doc.lastPublishedAt = now();
    savePath(doc); activate();
    return { ok: true, url: m[1] + "/", learnersAffected: removed.length ? ticksOn(removed, m[1]) : 0 };
  });
  route("DELETE", "/api/admin/paths/{pid}", function (req, m) {
    var me = identify(); requireManage(me, m[1]);
    var doc = pathDoc(m[1]); if (doc.status === "published") fail(400, "A published path can't be deleted.");
    delete DB.custom[m[1]]; save(); return { ok: true };
  });
  route("POST", "/api/admin/paths/{pid}/llm-edit", function (req, m) {
    var me = identify(); requireManage(me, m[1]); pathDoc(m[1]);
    var d = body(req), ins = String(d.instruction || "").trim();
    if (!ins) fail(400, "Write what should change.");
    var old = d.content || DB.custom[m[1]].draft;
    var job = startJob("edit", me, { steps: [{ text: "Reading the draft…", done: true, wait: 300 }, { text: "Writing the changes…", wait: 1600 }],
      result: function (j) {
        var neu = simulatedEdit(normalize(old), ins.slice(0, 3000), d.scope || {}), changes = diffContent(normalize(old), neu);
        j.progress[j.progress.length - 1] = { text: changes.length + " change" + (changes.length !== 1 ? "s" : "") + " suggested", done: true };
        return { content: neu, changes: changes };
      } });
    return { job: job.id };
  });

  // per path
  route("GET", "/{pid}/api/me", function (req, m) { if (!DB.custom[m[1]]) requirePath(m[1]); return identify(); });
  route("GET", "/{pid}/api/content", function (req, m) {
    var doc = DB.custom[m[1]]; if (!doc) fail(404, "Unknown learning path.");
    var me = identify(), out = { id: m[1], status: doc.status, live: doc.live, canEdit: canManage(me, m[1]), jira: true };
    if (out.canEdit) Object.assign(out, { draft: doc.draft, owners: doc.owners || [], generation: doc.generation || null, updatedAt: doc.updatedAt, llm: true });
    else if (doc.status !== "published") fail(404, "This learning path isn't published yet.");
    return out;
  });
  route("GET", "/ai-engineer/content.json", function () { return PATHS["ai-engineer"].content; });
  route("GET", "/{pid}/api/progress", function (req, m) { requirePath(m[1]); var me = identify(); return { state: pathState(rec(me.id), m[1]) }; });
  route("PUT", "/{pid}/api/progress", function (req, m) {
    var pid = m[1]; requirePath(pid); var me = identify(), state = body(req).state;
    if (!state || typeof state !== "object" || (state.done && typeof state.done !== "object")) fail(400, "state.done must be an object.");
    var ov = learnerView(rec(me.id), pid), before = ov.badge.earned, stageBefore = ov.mascot;
    var r = update(me.id, function (r) {
      r.name = me.name; r.email = me.email;
      if (pid === "agentic") r.state = state; else (r.paths = r.paths || {})[pid] = state;
      var starts = r.start = r.start || {};
      var hasDone = Object.keys(state.done || {}).length > 0;
      if (!starts[pid] && hasDone) starts[pid] = startOf(r, pid) || todayIso();
      var enr = r.enrolled = r.enrolled || {};
      if (hasDone && !(enr[pid] && typeof enr[pid] === "object" && !enr[pid].removed)) enr[pid] = { at: now(), date: starts[pid] };
    });
    var v = learnerView(r, pid);
    if ((v.badge.earned && !before) || v.mascot > stageBefore) {
      update(me.id, function (r) { if (v.badge.earned) { r.badges = r.badges || {}; if (!r.badges[pid]) r.badges[pid] = { at: v.badge.at || todayIso() }; } (r.mascots = r.mascots || {})[pid] = v.mascot; });
    }
    if (v.badge.earned && !before) event("slack", "Slack (#onboarding): " + me.name + " finished " + PATHS[pid].title, "Posted in the weekly summary on Monday.");
    return { ok: true, status: statusPayload(v), newBadge: v.badge.earned && !before, levelUp: v.mascot > stageBefore };
  });
  route("GET", "/{pid}/api/status", function (req, m) { requirePath(m[1]); return statusPayload(learnerView(rec(identify().id), m[1])); });
  route("PUT", "/{pid}/api/start", function (req, m) {
    var pid = m[1]; requirePath(pid); var me = identify(), d = body(req);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(d.date || "")) || !parseIso(d.date)) fail(400, "date must be YYYY-MM-DD.");
    var key = me.id;
    if (d.learner && d.learner !== me.id) { requireManage(me, pid); key = d.learner; if (!DB.records[key]) fail(404, "No such learner."); }
    var r = update(key, function (r) { (r.start = r.start || {})[pid] = d.date; if (key === me.id) { r.name = me.name; r.email = me.email; } });
    return { ok: true, status: statusPayload(learnerView(r, pid)) };
  });
  route("PUT", "/{pid}/api/enroll", function (req, m) {
    var pid = m[1]; requirePath(pid); var me = identify(), d = body(req), key = me.id;
    if (d.learner && d.learner !== me.id) { requireManage(me, pid); key = d.learner; if (!DB.records[key]) fail(404, "No such learner."); }
    if (d.remove) { requireManage(me, pid); var rr = update(key, function (r) { (r.enrolled = r.enrolled || {})[pid] = { removed: true, at: now(), by: me.name }; }); return { ok: true, status: statusPayload(learnerView(rr, pid)) }; }
    var date = String(d.date || todayIso());
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !parseIso(date)) fail(400, "date must be YYYY-MM-DD.");
    var r = update(key, function (r) { if (key === me.id) { r.name = me.name; r.email = me.email; } (r.enrolled = r.enrolled || {})[pid] = { at: now(), date: date }; (r.start = r.start || {})[pid] = date; });
    return { ok: true, status: statusPayload(learnerView(r, pid)) };
  });
  route("POST", "/{pid}/api/reports", function (req, m) {
    var pid = m[1], p = requirePath(pid), me = identify(), d = body(req), message = String(d.message || "").trim();
    if (!message) fail(400, "Write a short description of the problem.");
    var itemId = String(d.itemId || "").slice(0, 120), kind = d.kind === "bug" ? "bug" : "path";
    var report = { id: hex(12), kind: kind, path: pid, pathTitle: p.title, itemId: itemId,
      itemLabel: (itemId && p.ids()[itemId] ? p.labelOf(itemId) : String(d.itemLabel || "")).slice(0, 200),
      anchor: String(d.anchor || "").replace(/[^A-Za-z0-9_.-]/g, "").slice(0, 80), message: message.slice(0, 4000),
      learnerId: me.id, name: me.name, email: me.email, createdAt: now(), status: "open" };
    var out = { ok: true };
    if (kind === "bug") {
      var files = takeUploads(me, d.uploads);
      report.links = (d.links || []).map(function (x) { return String(x).trim().slice(0, 500); }).filter(function (x) { return /^https?:\/\//.test(x); }).slice(0, 10);
      report.browser = String(d.browser || navigator.userAgent).slice(0, 300);
      report.stepText = String(d.stepText || "").slice(0, 1500);
      var t = new Date(); report.when = iso(t) + " " + pad(t.getHours()) + ":" + pad(t.getMinutes());
      report.files = keepFiles(files);
      report.jira = jiraIssue(report, files);
      out.jira = { key: report.jira.key, url: report.jira.url, project: report.jira.project, summary: report.jira.summary, attached: report.jira.attached };
      event("jira", "Jira: created Bug " + report.jira.key + " in " + report.jira.project + " (reporter and watcher: " + me.email + ")",
        report.jira.summary + "\n" + (report.jira.pod ? "Pod: " + report.jira.pod + ". " : "") + report.jira.why + (files.length ? "\n" + files.length + " file" + (files.length !== 1 ? "s" : "") + " attached." : "") +
        "\nJira emails the reporter a link to the issue.");
    }
    DB.reports.push(report); save();
    event("slack", "Slack (#onboarding): " + (kind === "bug" ? "DataRobot bug" : "Problem with " + p.title) + " from " + me.name, message.slice(0, 300));
    return out;
  });
  route("GET", "/{pid}/api/team", function (req, m) {
    var pid = m[1]; requirePath(pid); requireManage(identify(), pid);
    var learners = [];
    Object.keys(DB.records).forEach(function (k) {
      var r = DB.records[k], v = learnerView(r, pid); if (!v.enrolled) return;
      learners.push({ id: k, name: r.name || r.email || "", email: r.email || "", state: pathState(r, pid) || {}, meta: Object.assign(statusPayload(v), { inactiveDays: v.inactiveDays }) });
    });
    return { learners: learners, inactiveAfterDays: INACTIVE_DAYS };
  });

  // certificates
  var BUILTIN_AUTHORS = { "ai-engineer": "raghavendran.nehru@datarobot.com", "agentic": "lidiia.saakian@datarobot.com" };
  function avatar(bg, fg) { return "data:image/svg+xml;base64," + btoa('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect width="48" height="48" fill="' + bg + '"/><circle cx="24" cy="19" r="9" fill="' + fg + '"/><path d="M6 48c2-11 9-16 18-16s16 5 18 16z" fill="' + fg + '"/></svg>'); }
  var SLACK_PHOTOS = {  // stand-in Slack photos; everyone else shows initials
    "lidiia.saakian@datarobot.com": avatar("#A6B0FF", "#5C41FF"),
    "maria.novak@datarobot.com": avatar("#44BFFC", "#0B6E9E")
  };
  var CERT_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  function newCertId() {
    var taken = {}; Object.keys(DB.records).forEach(function (k) { var bs = DB.records[k].badges || {}; Object.keys(bs).forEach(function (p) { if (bs[p] && bs[p].certId) taken[bs[p].certId] = true; }); });
    for (;;) { var id = "DR-"; for (var i = 0; i < 8; i++) { if (i === 4) id += "-"; id += CERT_CHARS[Math.floor(Math.random() * CERT_CHARS.length)]; } if (!taken[id]) return id; }
  }
  function pathAuthor(pid) {
    var doc = DB.custom[pid], email = (doc ? (doc.createdByEmail || (doc.owners || [])[0]) : BUILTIN_AUTHORS[pid]) || "";
    email = email.toLowerCase(); if (!email) return { name: "", photo: "", initials: "" };
    var name = (doc && doc.createdBy) || ((DB.users.users[email] || {}).name) || ((DB.records[email] || {}).name) || titleName(email);
    return { name: name, photo: SLACK_PHOTOS[email] || "", initials: name.split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join("").toUpperCase() };
  }
  function longDate(isoD) { var d = parseIso(isoD); return ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][d.getMonth()] + " " + d.getDate() + ", " + d.getFullYear(); }
  route("GET", "/{pid}/api/certificate", function (req, m) {
    var pid = m[1], p = requirePath(pid), me = identify(), v = learnerView(rec(me.id), pid);
    if (!v.badge.earned) fail(404, "Finish every required step to get your certificate.");
    var issued = v.badge.at || todayIso();
    var r = update(me.id, function (r) { r.badges = r.badges || {}; var b = r.badges[pid] = r.badges[pid] || { at: issued }; if (!b.certId) { b.certId = newCertId(); b.certName = me.name; b.certAt = now(); } });
    var b = r.badges[pid], d = parseIso(b.at || issued);
    var q = { startTask: "CERTIFICATION_NAME", name: p.title, issueYear: d.getFullYear(), issueMonth: d.getMonth() + 1, certId: b.certId, organizationName: "DataRobot" };
    return { name: b.certName || me.name, course: p.title, issued: iso(d), certId: b.certId,
      linkedinUrl: "https://www.linkedin.com/profile/add?" + Object.keys(q).map(function (k) { return k + "=" + encodeURIComponent(q[k]); }).join("&") };
  });
  function verifyPage(cid) {
    cid = String(cid || "").toUpperCase();
    var esc = function (t) { return String(t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
    var body = '<span class="k">DataRobot · Certificate of completion</span><h1>No certificate with this ID</h1><p>Check the credential ID: ' + esc(cid) + "</p>";
    Object.keys(DB.records).forEach(function (k) {
      var r = DB.records[k], bs = r.badges || {};
      Object.keys(bs).forEach(function (pid) {
        var b = bs[pid]; if (!b || b.certId !== cid) return;
        var title = PATHS[pid] ? PATHS[pid].title : (((DB.custom[pid] || {}).live || {}).title || pid);
        var rows = [["Learning path", title], ["Issued", b.at ? longDate(b.at) : ""], ["Credential ID", cid]];
        body = '<span class="k">DataRobot · Certificate of completion</span><h1>' + esc(b.certName || r.name || "") + '</h1><span class="ok">Valid</span><dl>' +
          rows.filter(function (x) { return x[1]; }).map(function (x) { return "<dt>" + x[0] + "</dt><dd>" + esc(x[1]) + "</dd>"; }).join("") + "</dl>";
      });
    });
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Credential check</title>' +
      '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400&family=DM+Mono:wght@400&display=swap"><style>' +
      ':root{--bg:#fff;--ink:#0B0B0B;--muted:#4C5650;--line:#E4E4E4;--green:#81FBA5;color-scheme:light}' +
      '@media (prefers-color-scheme:dark){:root{--bg:#0B0B0B;--ink:#EDF1EE;--muted:#A2ACA5;--line:#2A2F2C;color-scheme:dark}}' +
      'body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.45 Barlow,system-ui,sans-serif}main{max-width:720px;margin:0 auto;padding:56px 20px;display:grid;gap:22px}' +
      '.k{font:12px/1.4 "DM Mono",ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}h1{font-weight:400;font-size:44px;line-height:1.05;margin:0;letter-spacing:-.015em}' +
      '.ok{justify-self:start;background:var(--green);color:#0B0B0B;border-radius:999px;padding:4px 12px;font:12px/1.4 "DM Mono",monospace;letter-spacing:.08em;text-transform:uppercase}' +
      'dl{display:grid;grid-template-columns:max-content 1fr;gap:10px 28px;margin:0;border-top:1px solid var(--line);padding-top:20px}dt{font:12px/1.9 "DM Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}dd{margin:0}' +
      "</style></head><body><main>" + body + "</main></body></html>";
  }

  function handle(method, path, query, req) {
    for (var i = 0; i < R.length; i++) {
      var r = R[i]; if (r.method !== method) continue;
      var m = r.re.exec(path); if (m) return r.fn(req, m);
    }
    fail(404, "Not Found");
  }

  // ------------------------------------------------------------------ seed
  function seed() {
    DB = { v: SRC.version, users: { users: {}, log: [] }, reports: [], meta: {}, records: {}, custom: {}, content: {}, events: [], jiraSeq: 9040 };
    var t = now();
    function ago(days, hour) { var d = addDays(today(), -days); d.setHours(hour || 10, Math.floor(Math.random() * 50)); return d.getTime(); }
    var U = DB.users.users;
    U["lidiia.saakian@datarobot.com"] = { invited: false, roles: ["author"], addedBy: "Runtime parameters", addedAt: null, name: "Lidiia Saakian", lastSeen: ago(0) };
    U["maria.novak@datarobot.com"] = { invited: true, roles: ["author"], addedBy: "Lidiia Saakian", addedAt: ago(20), name: "Maria Novak", lastSeen: ago(1) };
    U["jen.walsh@datarobot.com"] = { invited: true, roles: ["admin"], addedBy: "Lidiia Saakian", addedAt: ago(40), name: "Jen Walsh", lastSeen: ago(3), welcome: { roles: ["admin"], by: "Lidiia Saakian", at: ago(0) } };
    U["omar.haddad@datarobot.com"] = { invited: true, roles: ["admin", "author"], addedBy: "Jen Walsh", addedAt: ago(12), name: "Omar Haddad", lastSeen: ago(2) };
    U["priya.raman@datarobot.com"] = { invited: true, roles: [], addedBy: "Lidiia Saakian", addedAt: ago(1) };
    DB.users.log.push({ at: ago(20), by: "Lidiia Saakian", what: "invited maria.novak@datarobot.com" });

    // the app-made path: published, with an unpublished change in the draft
    var live = normalize(SRC.generated);
    live.title = "Agent Workforce Monitoring"; live.blurb = "Three modules on monitoring deployed agents: what it tracks, alerts and costs, and a hands-on gate.";
    var draft = clone(live); draft.groups[1].days[0].steps.splice(1, 0, { id: "s" + hex(8), title: "Lab: compare cost per task for two agents", details: "Use the Monitoring tab. Note which agent costs more per completed task.", link: null, type: "Stretch", gate: false, source: "" });
    var awm = { id: "agent-workforce-monitoring", status: "published", owners: ["maria.novak@datarobot.com", "omar.haddad@datarobot.com"], createdBy: "Maria Novak",
      createdByEmail: "maria.novak@datarobot.com", createdAt: ago(18), origin: "sources", draft: draft, live: live, publishedAt: ago(14), publishedBy: "Maria Novak",
      lastPublishedAt: ago(14), updatedAt: ago(1), generation: Object.assign({ at: ago(18) }, clone(SRC.generateMeta)) };
    DB.custom[awm.id] = awm;
    var dr = normalize(blankContent("Codespaces for support engineers", "Module", false, "weeks"));
    dr.blurb = "Draft: using codespaces to reproduce customer issues.";
    dr.groups[0].title = "Getting set up";
    dr.groups[0].days[0].steps = [{ id: "new", title: "Open a codespace from a use case", details: "", type: "Required" }, { id: "new", title: "Run a customer's notebook in it", details: "", type: "Required" }];
    DB.custom["codespaces-for-support-engineers"] = { id: "codespaces-for-support-engineers", status: "draft", owners: ["omar.haddad@datarobot.com"], createdBy: "Omar Haddad",
      createdByEmail: "omar.haddad@datarobot.com", createdAt: ago(4), origin: "app", draft: normalize(dr), live: null, updatedAt: ago(4) };
    activate();

    // learners
    var L = [
      ["sam.okafor@datarobot.com", "Sam Okafor", { "agentic": [9, 0.55], "ai-engineer": [30, 0.3] }],
      ["ana.costa@datarobot.com", "Ana Costa", { "agentic": [24, 1], "agent-workforce-monitoring": [10, 0.6] }],
      ["li.wei@datarobot.com", "Li Wei", { "ai-engineer": [52, 0.62] }],
      ["tom.becker@datarobot.com", "Tom Becker", { "agentic": [16, 0.25, 12] }],
      ["fatima.ali@datarobot.com", "Fatima Ali", { "ai-engineer": [12, 0.18], "agent-workforce-monitoring": [6, 0.25] }],
      ["diego.ruiz@datarobot.com", "Diego Ruiz", { "agentic": [5, 0.5] }],
      ["kate.oneill@datarobot.com", "Kate O'Neill", { "ai-engineer": [70, 1] }],
      ["jen.walsh@datarobot.com", "Jen Walsh", { "agentic": [3, 0] }],
      ["maria.novak@datarobot.com", "Maria Novak", { "agentic": [40, 1] }]
    ];
    L.forEach(function (l) {
      var r = DB.records[l[0]] = { name: l[1], email: l[0], start: {}, enrolled: {} };
      Object.keys(l[2]).forEach(function (pid) {
        var spec = l[2][pid], startDays = spec[0], frac = spec[1], idle = spec[2] || 0, p = PATHS[pid];
        var start = addDays(today(), -startDays), req = p.required({}), n = Math.round(req.length * frac), done = {};
        var span = Math.max(1, startDays - idle);
        for (var i = 0; i < n; i++) done[req[i].id] = ago(Math.max(idle, startDays - Math.round(span * (i + 1) / Math.max(n, 1))), 9 + (i % 8));
        var st = { done: done, updatedAt: n ? Math.max.apply(null, Object.keys(done).map(function (k) { return done[k]; })) : null };
        if (pid === "agentic") r.state = st; else (r.paths = r.paths || {})[pid] = st;
        r.start[pid] = iso(start); r.enrolled[pid] = { at: start.getTime() + 9 * 3600000, date: iso(start) };
        var v = learnerView(r, pid);
        if (v.badge.earned) (r.badges = r.badges || {})[pid] = { at: v.badge.at };
        (r.mascots = r.mascots || {})[pid] = v.mascot;
      });
    });

    // reports
    function R2(o) { DB.reports.push(Object.assign({ id: hex(12), status: "open", itemId: "", anchor: "" }, o)); }
    R2({ kind: "bug", path: "agentic", pathTitle: "Agentic AI Learning Path", itemLabel: "Day 2: Create a vector database", message: "Saving the vector database fails with \"Internal server error\" after the upload finishes.",
      learnerId: "sam.okafor@datarobot.com", name: "Sam Okafor", email: "sam.okafor@datarobot.com", createdAt: ago(2, 14), links: ["https://app.datarobot.com/usecases/66f0/vector-databases"],
      files: [{ name: "error.png", size: 182344, type: "image/png" }], when: iso(addDays(today(), -2)) + " 14:12",
      jira: { key: "GENAI-9031", url: JIRA + "/browse/GENAI-9031", project: "GENAI", pod: "GenAI: vector databases and RAG", routedTo: "page", summary: "Vector database save fails with Internal server error after upload",
        why: "The report mentions vector databases.", attached: 1, status: "In Progress", category: "indeterminate", assignee: "Alex Rivera", syncedAt: ago(0, 8), visible: true, simulated: true } });
    R2({ kind: "bug", path: "ai-engineer", pathTitle: "AI Engineer Learning Plan", itemLabel: "", message: "The LLM gateway playground times out with long prompts, same as last week.", learnerId: "li.wei@datarobot.com",
      name: "Li Wei", email: "li.wei@datarobot.com", createdAt: ago(9, 11), links: [], files: [], status: "resolved", resolvedBy: "Jira", resolvedAt: ago(5), autoResolved: true,
      jira: { key: "AGENT-9012", url: JIRA + "/browse/AGENT-9012", project: "AGENT", summary: "LLM gateway playground times out with long prompts", attached: 0, status: "Closed", category: "done", resolution: "Duplicate",
        duplicateOf: { key: "AGENT-8812", url: JIRA + "/browse/AGENT-8812", status: "In Progress" }, syncedAt: ago(0, 8), visible: true, simulated: true } });
    R2({ kind: "path", path: "agentic", pathTitle: "Agentic AI Learning Path", itemLabel: "Day 3: Deploy the Agentic Starter", anchor: "day3", message: "The link to the starter template goes to an old repo.",
      learnerId: "tom.becker@datarobot.com", name: "Tom Becker", email: "tom.becker@datarobot.com", createdAt: ago(4, 16) });
    R2({ kind: "path", path: "agent-workforce-monitoring", pathTitle: "Agent Workforce Monitoring", itemLabel: "Module 2: Create a cost alert with a daily threshold",
      message: "The alert needs a 7-day baseline, so new learners can't finish this step in week 2.", learnerId: "ana.costa@datarobot.com", name: "Ana Costa", email: "ana.costa@datarobot.com", createdAt: ago(3, 10) });
    R2({ kind: "system", path: "admin", pathTitle: "Admin", itemLabel: "Admin → Users", message: "Priya can't see the Admin button after I invited her.", learnerId: "jen.walsh@datarobot.com",
      name: "Jen Walsh", email: "jen.walsh@datarobot.com", createdAt: ago(1, 12), files: [] });
    DB.meta.jiraSync = ago(0, 8);
    save();
  }

  // ------------------------------------------------------------------ public
  DB = load();
  if (!DB) seed(); else activate();

  window.STG = {
    PERSONAS: null,
    setViewer: function (v) { VIEWER = v; },
    viewer: function () { return VIEWER; },
    reset: function () { try { localStorage.removeItem(LS_KEY); } catch (e) {} seed(); },
    events: function () { return DB.events; },
    onEvent: function (f) { listeners.push(f); },
    pathExists: function (pid) { return !!(PATHS[pid] || DB.custom[pid]); },
    pageFor: function (path) {
      // returns the HTML for a virtual page path, or null
      if (path === "/") return SRC.pages.hub;
      if (path === "/admin/") return SRC.pages.admin;
      var vm = /^\/verify\/([^\/]+)\/$/.exec(path); if (vm) return verifyPage(decodeURIComponent(vm[1]));
      var m = /^\/([^\/]+)\/$/.exec(path); if (!m) return null;
      if (PATHS[m[1]]) return PATHS[m[1]].html;
      if (DB.custom[m[1]]) return customPage(DB.custom[m[1]], null);
      return null;
    },
    request: function (method, path, query, headers, text, file) {
      var req = { method: method, path: path, query: query || "", headers: headers || {}, text: text, file: file };
      try { return { status: 200, body: handle(method, path, query, req) }; }
      catch (e) {
        if (e instanceof HttpError) return { status: e.status, body: { detail: e.detail } };
        console.error(e); return { status: 500, body: { detail: "Staging backend error: " + (e && e.message) } };
      }
    },
    mascot: function (k) { return SRC.mascots[k - 1] || ""; }
  };
})();
