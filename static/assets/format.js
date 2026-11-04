/* Formatting in step details (paths made in the app). A small Markdown-like syntax, parsed into a plain tree that the
   page turns into DOM nodes; nothing is ever inserted as HTML, and only http(s) addresses become links.

   Blocks:  "- item" bullet list · "1. item" numbered list · "- [ ] item" / "- [x] item" checklist · other lines are
            paragraphs (line breaks kept; a blank line starts a new paragraph).
   Inline:  `code` · **bold** · *italic* · [text](https://…) · bare https://… links.

   parse(text) -> [{type: "p", lines: [[inline…]…]} | {type: "ul"|"ol", items: [[inline…]…]}
                   | {type: "check", items: [{checked, index, content: [inline…]}]}]
   inline     -> {t: "text"|"code", v} | {t: "b"|"i", c: [inline…]} | {t: "a", href, c: [inline…]}
   plain(text) -> the same text without the syntax, for search and problem reports. */
(function (root) {
  "use strict";
  var CHECK = /^\s*[-*]\s+\[( |x|X)\]\s+(.*)$/, BULLET = /^\s*[-*]\s+(.*)$/, NUMBER = /^\s*\d{1,3}[.)]\s+(.*)$/;
  var URL_OK = /^https?:\/\/[^\s<>"']+$/i;

  function inline(s) {
    var out = [], i = 0, buf = "";
    function flush() { if (buf) { out.push({ t: "text", v: buf }); buf = ""; } }
    while (i < s.length) {
      var rest = s.slice(i), m;
      if ((m = /^`([^`]+)`/.exec(rest))) { flush(); out.push({ t: "code", v: m[1] }); i += m[0].length; continue; }
      if ((m = /^\*\*(?=\S)([\s\S]*?\S)\*\*/.exec(rest))) { flush(); out.push({ t: "b", c: inline(m[1]) }); i += m[0].length; continue; }
      if ((m = /^\*(?=[^\s*])([^*]*?[^\s*])\*/.exec(rest)) || (m = /^\*([^\s*])\*/.exec(rest))) { flush(); out.push({ t: "i", c: inline(m[1]) }); i += m[0].length; continue; }
      if ((m = /^\[([^\]]+)\]\(([^)\s]+)\)/.exec(rest))) {
        flush();
        if (URL_OK.test(m[2])) out.push({ t: "a", href: m[2], c: inline(m[1]) });
        else out.push({ t: "text", v: m[0] });  // not a web address: show it as written, not as a link
        i += m[0].length; continue;
      }
      if ((m = /^https?:\/\/[^\s<>"')\]]+[^\s<>"').,;:\]]/i.exec(rest)) && !/[\w/]$/.test(buf)) {
        flush(); out.push({ t: "a", href: m[0], c: [{ t: "text", v: m[0] }] }); i += m[0].length; continue;
      }
      buf += s[i]; i++;
    }
    flush();
    return out;
  }

  function parse(text) {
    var blocks = [], cur = null, checks = 0;
    String(text || "").replace(/\r\n?/g, "\n").split("\n").forEach(function (line) {
      var m;
      if ((m = CHECK.exec(line))) {
        if (!cur || cur.type !== "check") { cur = { type: "check", items: [] }; blocks.push(cur); }
        cur.items.push({ checked: m[1] !== " ", index: checks++, content: inline(m[2]) });
      } else if ((m = BULLET.exec(line))) {
        if (!cur || cur.type !== "ul") { cur = { type: "ul", items: [] }; blocks.push(cur); }
        cur.items.push(inline(m[1]));
      } else if ((m = NUMBER.exec(line))) {
        if (!cur || cur.type !== "ol") { cur = { type: "ol", items: [] }; blocks.push(cur); }
        cur.items.push(inline(m[1]));
      } else if (!line.trim()) {
        cur = null;
      } else {
        if (!cur || cur.type !== "p") { cur = { type: "p", lines: [] }; blocks.push(cur); }
        cur.lines.push(inline(line));
      }
    });
    return blocks;
  }

  function flat(nodes) {
    return nodes.map(function (n) { return n.v != null ? n.v : flat(n.c || []); }).join("");
  }
  function plain(text) {
    return parse(text).map(function (b) {
      if (b.type === "p") return b.lines.map(flat).join(" ");
      return b.items.map(function (it) { return flat(it.content || it); }).join("; ");
    }).join(" ");
  }

  var api = { parse: parse, inline: inline, plain: plain };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.DRFormat = api;
})(this);
