"""Collect the material a path is generated from: Jira/PBMP issues, Confluence pages, GitHub repos, docs pages and
uploaded files. Returns what was found (for the "What we found" screen) plus the text and images behind it.

Limits keep a run to a few minutes and the LLM input to what it can read well; anything skipped is reported.
"""

from __future__ import annotations

import base64
import html as htmllib
import io
import ipaddress
import json
import logging
import re
import socket
import zipfile
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import requests

from atlassian import Atlassian, AtlassianError, adf_to_text

log = logging.getLogger("onboarding.sources")

MAX_ISSUES = 40
MAX_ATTACHMENTS = 20
MAX_IMAGES = 8
MAX_IMAGE_BYTES = 3_500_000
MAX_LINKED_PAGES = 10
MAX_WEB_PAGES = 8
MAX_CONFLUENCE_PAGES = 25
MAX_GITHUB_FILES = 40
MAX_FILE_CHARS = 200_000
UA = {"User-Agent": "DataRobot-onboarding-app/1.0"}
TEXT_EXT = (".md", ".mdx", ".rst", ".txt", ".adoc")
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


# --------------------------------------------------------------------------- text extraction

class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form", "button", "template"}
    BLOCK = {"p", "div", "section", "article", "br", "tr", "table", "ul", "ol", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "li", "dt", "dd"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.href: list[str | None] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in self.BLOCK:
            self.out.append("\n")
        if re.match(r"h[1-6]$", tag):
            self.out.append("#" * int(tag[1]) + " ")
        if tag == "li":
            self.out.append("- ")
        if tag == "a":
            self.href.append(a.get("href"))
        if tag in ("td", "th"):
            self.out.append(" | ")
        if tag == "ac:link" or tag == "ri:page":
            if a.get("ri:content-title"):
                self.out.append(f"[{a['ri:content-title']}]")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "a" and self.href:
            h = self.href.pop()
            if h and h.startswith("http"):
                self.out.append(f" ({h})")
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    try:
        p.feed(html or "")
        p.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html or "")
    t = "".join(p.out)
    t = re.sub(r"[ \t\xa0]+", " ", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
    return t.strip()


def page_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.S | re.I)
    return re.sub(r"\s+", " ", htmllib.unescape(m.group(1))).strip()[:160] if m else ""


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return htmllib.unescape(re.sub(r"<[^>]+>", "", xml))


def _pptx_text(data: bytes) -> str:
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=lambda n: int(re.findall(r"\d+", n)[-1]))
        for i, n in enumerate(slides, 1):
            xml = z.read(n).decode("utf-8", "ignore")
            out.append(f"## Slide {i}\n" + " ".join(htmllib.unescape(t) for t in re.findall(r"<a:t>([^<]*)</a:t>", xml)))
    return "\n\n".join(out)


def _pdf_text(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    pages = []
    for i, p in enumerate(r.pages):
        if i >= 300:
            break
        try:
            pages.append(f"[page {i + 1}]\n" + (p.extract_text() or ""))
        except Exception:
            pages.append(f"[page {i + 1}]")
    return "\n\n".join(pages), len(r.pages)


def _xlsx_text(data: bytes) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets[:10]:
        out.append(f"## Sheet: {ws.title}")
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i > 2000:
                break
            vals = [str(v).strip() for v in row if v not in (None, "")]
            if vals:
                out.append(" | ".join(vals))
    return "\n".join(out)


def extract(name: str, data: bytes, ctype: str = "") -> dict:
    """{"kind": "text"|"image"|"skip", "text", "pages", "mime", "note"} for one file."""
    n = (name or "").lower()
    ext = n.rsplit(".", 1)[-1] if "." in n else ""
    ctype = (ctype or "").lower()
    try:
        if ext in IMAGE_TYPES or ctype.startswith("image/"):
            mime = IMAGE_TYPES.get(ext) or ctype or "image/png"
            if len(data) > MAX_IMAGE_BYTES:
                return {"kind": "skip", "note": "image too large to read"}
            return {"kind": "image", "mime": mime, "pages": 1}
        if ext == "pdf" or "pdf" in ctype:
            t, pages = _pdf_text(data)
            note = "" if len(t.strip()) > 40 * max(1, pages) else "looks scanned: little text could be read"
            return {"kind": "text", "text": t[:MAX_FILE_CHARS], "pages": pages, "note": note}
        if ext == "docx" or "wordprocessingml" in ctype:
            t = _docx_text(data)
            return {"kind": "text", "text": t[:MAX_FILE_CHARS], "pages": max(1, len(t) // 3000)}
        if ext == "pptx" or "presentationml" in ctype:
            t = _pptx_text(data)
            return {"kind": "text", "text": t[:MAX_FILE_CHARS], "pages": t.count("## Slide")}
        if ext in ("xlsx", "xlsm") or "spreadsheetml" in ctype:
            t = _xlsx_text(data)
            return {"kind": "text", "text": t[:MAX_FILE_CHARS], "pages": max(1, len(t) // 3000)}
        raw = data.decode("utf-8", "ignore")
        if ext in ("html", "htm") or "html" in ctype or raw.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
            t = html_to_text(raw)
            return {"kind": "text", "text": t[:MAX_FILE_CHARS], "pages": max(1, len(t) // 3000), "title": page_title(raw)}
        if ext in ("md", "mdx", "txt", "csv", "tsv", "rst", "json", "yaml", "yml", "adoc", "") or ctype.startswith("text/"):
            return {"kind": "text", "text": raw[:MAX_FILE_CHARS], "pages": max(1, len(raw) // 3000)}
        if ext in ("doc", "ppt", "xls"):
            return {"kind": "skip", "note": f"old .{ext} format: save it as .{ext}x or PDF and upload that"}
    except Exception as e:
        log.warning("Couldn't read %s: %s", name, e)
        return {"kind": "skip", "note": f"couldn't be read ({type(e).__name__})"}
    return {"kind": "skip", "note": "this file type can't be read"}


# --------------------------------------------------------------------------- URL safety and classification

def public_url(url: str) -> bool:
    """Only http(s) to public hosts: never the app's own network."""
    try:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        for info in socket.getaddrinfo(u.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except Exception:
        return False


JIRA_KEY = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


def classify(link: str, atl_host: str) -> tuple[str, str]:
    """('jira', key) | ('confluence', url) | ('github', url) | ('google', url) | ('web', url) | ('bad', reason)"""
    s = (link or "").strip()
    if JIRA_KEY.match(s.upper()) and " " not in s:
        return "jira", s.upper()
    if not re.match(r"^https?://", s, re.I):
        if re.match(r"^[\w.-]+\.[a-z]{2,}/", s, re.I):
            s = "https://" + s
        else:
            return "bad", "Paste a full link (https://…) or a Jira key like PBMP-1234."
    u = urlparse(s)
    host = (u.hostname or "").lower()
    if host == atl_host or host.endswith(".atlassian.net"):
        if "/wiki" in u.path:
            return "confluence", s
        m = re.search(r"/browse/([A-Z][A-Z0-9_]+-\d+)", s) or re.search(r"selectedIssue=([A-Z][A-Z0-9_]+-\d+)", s)
        if m:
            return "jira", m.group(1)
        return "bad", "That Atlassian link isn't an issue or a Confluence page."
    if host in ("github.com", "www.github.com"):
        return "github", s
    if host in ("docs.google.com", "drive.google.com"):
        return "google", s
    return "web", s


def confluence_page_id(url: str, atl: Atlassian) -> str | None:
    u = urlparse(url)
    m = re.search(r"/pages/(\d+)", u.path)
    if m:
        return m.group(1)
    q = parse_qs(u.query)
    if q.get("pageId"):
        return q["pageId"][0]
    if "/wiki/x/" in u.path:
        resolved = atl.resolve_tiny(url)
        return None if "/wiki/x/" in resolved else confluence_page_id(resolved, atl)
    m = re.search(r"/spaces/([^/]+)/?(overview)?$", u.path.rstrip("/")) or re.search(r"/spaces/([^/]+)/overview", u.path)
    if m:
        return atl.space_home(m.group(1))
    return None


# --------------------------------------------------------------------------- collector

class Collector:
    """Collects sources for one generation run. self.found is what the author sees; self.sources holds the text."""

    def __init__(self, atl: Atlassian, gh_token: str = "", progress=None) -> None:
        self.atl = atl
        self.gh = (gh_token or "").strip()
        self.progress = progress or (lambda msg: None)
        self.groups: list[dict] = []
        self.sources: dict[str, dict] = {}
        self._n = 0
        self.images = 0
        self.seen_urls: set[str] = set()
        self.seen_pages: set[str] = set()

    # ------------------------------------------------------------------ helpers
    def _sid(self) -> str:
        self._n += 1
        return f"src{self._n}"

    def add_source(self, item: dict, title: str, url: str, kind: str, text: str = "", image: tuple[str, bytes] | None = None, pages: int = 0) -> None:
        sid = self._sid()
        src = {"id": sid, "item": item["id"], "title": title[:200], "url": url, "kind": kind, "text": (text or "").strip(), "pages": pages}
        if image:
            if self.images >= MAX_IMAGES:
                return
            self.images += 1
            src["image"] = {"mime": image[0], "b64": base64.b64encode(image[1]).decode()}
        self.sources[sid] = src
        item["sources"].append(sid)

    def group(self, kind: str, title: str, summary: str = "") -> dict:
        g = {"id": f"g{len(self.groups) + 1}", "kind": kind, "title": title, "summary": summary, "items": [], "warnings": []}
        self.groups.append(g)
        return g

    def item(self, g: dict, label: str, checked: bool = True, note: str = "") -> dict:
        it = {"id": f"{g['id']}i{len(g['items']) + 1}", "label": label, "checked": checked, "note": note, "sources": []}
        g["items"].append(it)
        return it

    def warn(self, g: dict, title: str, text: str) -> None:
        g["warnings"].append({"title": title, "text": text})

    # ------------------------------------------------------------------ entry point
    def collect(self, links: list[str], files: list[dict]) -> dict:
        atl_host = urlparse(self.atl.url).hostname or ""
        for raw in links:
            kind, val = classify(raw, atl_host)
            try:
                if kind == "jira":
                    self.jira_root(val)
                elif kind == "confluence":
                    self.confluence_root(val)
                elif kind == "github":
                    self.github_root(val)
                elif kind == "google":
                    g = self.group("google", "Google file")
                    self.warn(g, "Google Docs can't be opened by the app", f"{val} — download it (File → Download → PDF or Word) and upload it here.")
                elif kind == "web":
                    self.web_root(val)
                else:
                    g = self.group("bad", raw[:120])
                    self.warn(g, "Can't use this link", val)
            except AtlassianError as e:
                g = self.group(kind, raw[:120])
                self.warn(g, "Couldn't read it", self._atl_msg(e))
            except Exception as e:
                log.exception("Collecting %s failed", raw)
                g = self.group(kind, raw[:120])
                self.warn(g, "Couldn't read it", f"{type(e).__name__}: {str(e)[:200]}")
        if files:
            self.files_root(files)
        return self.found()

    def _atl_msg(self, e: AtlassianError) -> str:
        if not self.atl.enabled:
            return "Jira and Confluence aren't connected yet (JIRA_EMAIL and JIRA_API_TOKEN)."
        if e.status in (401,):
            return "The app's Atlassian account couldn't sign in. Check JIRA_EMAIL and JIRA_API_TOKEN."
        if e.status in (403, 404):
            return "The app's Atlassian account can't open it: it doesn't exist or is restricted."
        return str(e)[:240]

    def found(self) -> dict:
        chars = sum(len(s["text"]) for s in self.sources.values())
        groups = []
        for g in self.groups:
            groups.append({k: v for k, v in g.items() if k != "items"} | {"items": [{k: v for k, v in it.items() if k != "sources"} | {"count": len(it["sources"])} for it in g["items"]]})
        return {"groups": groups, "chars": chars, "pages": max(1, round(chars / 3000)) if chars else 0, "images": self.images}

    # ------------------------------------------------------------------ Jira / PBMP
    def _issue_text(self, it: dict) -> tuple[str, list, list[str]]:
        f = it.get("fields") or {}
        parts = [f"# {it['key']}: {f.get('summary', '')}", f"Type: {(f.get('issuetype') or {}).get('name', '')} · Status: {(f.get('status') or {}).get('name', '')}"]
        desc = adf_to_text(f.get("description")) if isinstance(f.get("description"), (dict, list)) else str(f.get("description") or "")
        if desc.strip():
            parts.append(desc)
        comments = ((f.get("comment") or {}).get("comments")) or []
        for c in comments[-40:]:
            body = adf_to_text(c.get("body")) if isinstance(c.get("body"), (dict, list)) else str(c.get("body") or "")
            parts.append(f"Comment by {(c.get('author') or {}).get('displayName', '')}: {body.strip()}")
        text = "\n\n".join(parts)
        urls = re.findall(r"https?://[^\s)\]>\"']+", text)
        return text, comments, urls

    def jira_root(self, key: str) -> None:
        self.progress(f"Reading {key}…")
        root = self.atl.issue(key)
        f = root.get("fields") or {}
        g = self.group("jira", f"{key}", f.get("summary", ""))
        g["title"] = f"{key} · {f.get('summary', '')}"[:160]
        issues = [root]
        keys = {key}
        for c in self.atl.children(key):
            if c["key"] not in keys and len(keys) < MAX_ISSUES:
                keys.add(c["key"])
                issues.append(c)
        for st in f.get("subtasks") or []:
            if st["key"] not in keys and len(keys) < MAX_ISSUES:
                keys.add(st["key"])
                issues.append(st)
        for ln in f.get("issuelinks") or []:
            oi = ln.get("outwardIssue") or ln.get("inwardIssue")
            if oi and oi["key"] not in keys and len(keys) < MAX_ISSUES:
                keys.add(oi["key"])
                issues.append(oi)
        full = []
        for i, it in enumerate(issues):
            if i:
                self.progress(f"Reading {key}: issue {i + 1} of {len(issues)}…")
                try:
                    it = self.atl.issue(it["key"])
                except AtlassianError:
                    continue
            full.append(it)
        done = [it for it in full if (((it.get("fields") or {}).get("status") or {}).get("statusCategory") or {}).get("key") == "done" or it is full[0]]
        open_ = [it for it in full if it not in done]
        n_comments = sum(len((((it.get("fields") or {}).get("comment") or {}).get("comments")) or []) for it in full)
        g["summary"] = f"{len(full) - 1} linked or child issues: {len(done) - 1} shipped, {len(open_)} still open" + (" (open ones are left out by default)" if open_ else "")
        main = self.item(g, f"Descriptions and {n_comments} comment{'s' if n_comments != 1 else ''} of {key} and the shipped issues")
        opn = self.item(g, f"{len(open_)} open issue{'s' if len(open_) != 1 else ''} (not shipped yet)", checked=False) if open_ else None
        urls: list[str] = []
        attachments = []
        for it in full:
            text, _, u = self._issue_text(it)
            target = opn if it in open_ else main
            self.add_source(target, f"{it['key']}: {(it.get('fields') or {}).get('summary', '')}", f"{self.atl.url}/browse/{it['key']}", "jira", text, pages=max(1, len(text) // 3000))
            urls += u
            for a in ((it.get("fields") or {}).get("attachment")) or []:
                attachments.append((it, a))
            if it in done:
                urls += [r["url"] for r in self.atl.remote_links(it["key"]) if r["url"]]
        # attachments
        if attachments:
            kinds = {}
            for _, a in attachments:
                ext = (a.get("filename") or "").rsplit(".", 1)[-1].lower()
                k = "PDF" if ext == "pdf" else "Word doc" if ext == "docx" else "screenshot" if ext in IMAGE_TYPES else "file"
                kinds[k] = kinds.get(k, 0) + 1
            desc = ", ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in kinds.items())
            ai = self.item(g, f"{len(attachments)} attachment{'s' if len(attachments) != 1 else ''}: {desc}" + (" (the LLM reads the images too)" if kinds.get("screenshot") else ""))
            for it, a in attachments[:MAX_ATTACHMENTS]:
                self.progress(f"Reading attachment {a.get('filename')}…")
                try:
                    if int(a.get("size") or 0) > 25_000_000:
                        continue
                    data = self.atl.download(a["content"])
                    ex = extract(a.get("filename", ""), data, a.get("mimeType", ""))
                    if ex["kind"] == "text":
                        self.add_source(ai, f"{a.get('filename')} (attached to {it['key']})", a.get("content", ""), "file", ex["text"], pages=ex.get("pages", 1))
                    elif ex["kind"] == "image":
                        self.add_source(ai, f"{a.get('filename')} (attached to {it['key']})", a.get("content", ""), "image", "", image=(ex["mime"], data))
                except AtlassianError as e:
                    log.warning("Attachment %s: %s", a.get("filename"), e)
        self._linked(g, urls)

    def _linked(self, g: dict, urls: list[str]) -> None:
        atl_host = urlparse(self.atl.url).hostname or ""
        conf, gh, google, web = [], [], [], []
        for u in dict.fromkeys(x.rstrip(".,;:") for x in urls):
            if u in self.seen_urls:
                continue
            kind, val = classify(u, atl_host)
            if kind == "confluence":
                conf.append(u)
            elif kind == "github" and re.search(r"/(pull|issues)/\d+|github\.com/[^/]+/[^/]+/?$", u):
                gh.append(u)
            elif kind == "google":
                google.append(u)
            elif kind == "web" and not re.search(r"\.(png|jpe?g|gif|zip|tar|gz|whl)(\?|$)", u, re.I):
                web.append(u)
        if conf:
            it = self.item(g, f"{len(conf[:MAX_LINKED_PAGES])} Confluence page{'s' if len(conf) != 1 else ''} linked from the issues")
            restricted = []
            for u in conf[:MAX_LINKED_PAGES]:
                self.seen_urls.add(u)
                try:
                    pid = confluence_page_id(u, self.atl)
                    if not pid or pid in self.seen_pages:
                        continue
                    self.seen_pages.add(pid)
                    p = self.atl.page(pid)
                    body = ((p.get("body") or {}).get("storage") or {}).get("value", "")
                    self.add_source(it, p.get("title", "Confluence page"), u, "confluence", html_to_text(body), pages=max(1, len(body) // 4000))
                except AtlassianError as e:
                    if e.status in (403, 404):
                        restricted.append(u)
            if restricted:
                self.warn(g, f"{len(restricted)} linked Confluence page{'s are' if len(restricted) != 1 else ' is'} restricted", "The app's Atlassian account can't open " + ", ".join(restricted[:3]) + ". Learners may not be able to either.")
        if gh:
            it = self.item(g, f"{len(gh[:5])} GitHub link{'s' if len(gh) != 1 else ''} from the issues (pull requests, repos)")
            for u in gh[:5]:
                self.seen_urls.add(u)
                try:
                    self._github_link(it, u)
                except Exception as e:
                    log.warning("GitHub %s: %s", u, e)
        if google:
            names = ", ".join(google[:4])
            self.warn(g, f"{len(google)} Google Doc{'s' if len(google) != 1 else ''} linked from the issues", f"The app can't open Google Docs: {names}. Download them as PDF and upload them below.")
        if web:
            it = self.item(g, f"{len(web[:MAX_WEB_PAGES])} other page{'s' if len(web) != 1 else ''} linked from the issues (docs and sites)")
            for u in web[:MAX_WEB_PAGES]:
                self.seen_urls.add(u)
                self._web_page(it, u, quiet=True)

    # ------------------------------------------------------------------ Confluence
    def confluence_root(self, url: str) -> None:
        self.progress("Reading the Confluence page…")
        pid = confluence_page_id(url, self.atl)
        if not pid:
            g = self.group("confluence", url[:120])
            self.warn(g, "Not a page link", "Open the page in Confluence and copy its address (it contains /pages/<number>/).")
            return
        p = self.atl.page(pid)
        g = self.group("confluence", f"Confluence: {p.get('title', '')}")
        it = self.item(g, "The page and its child pages")
        att_item = None
        restricted = []
        todo, seen, n = [(pid, 0, p)], {pid}, 0
        while todo and n < MAX_CONFLUENCE_PAGES:
            cur, depth, page = todo.pop(0)
            try:
                page = page or self.atl.page(cur)
            except AtlassianError as e:
                if e.status in (403, 404):
                    restricted.append(cur)
                continue
            n += 1
            self.progress(f"Reading Confluence page {n}: {page.get('title', '')}…")
            body = ((page.get("body") or {}).get("storage") or {}).get("value", "")
            link = f"{self.atl.url}/wiki/pages/viewpage.action?pageId={cur}"
            if cur not in self.seen_pages:  # already read as a page linked from a Jira issue
                self.seen_pages.add(cur)
                self.add_source(it, page.get("title", "Confluence page"), link, "confluence", html_to_text(body), pages=max(1, len(body) // 4000))
            self.seen_urls.add(link)
            for a in self.atl.page_attachments(cur)[:10]:
                title = a.get("title") or ""
                if not re.search(r"\.(pdf|docx|pptx|png|jpe?g)$", title, re.I):
                    continue
                dl = (a.get("_links") or {}).get("download") or a.get("downloadLink")
                if not dl:
                    continue
                try:
                    data = self.atl.download(self.atl.url + "/wiki" + dl if dl.startswith("/") else dl)
                    ex = extract(title, data, a.get("mediaType", ""))
                    att_item = att_item or self.item(g, "Files attached to the pages")
                    if ex["kind"] == "text":
                        self.add_source(att_item, f"{title} (on {page.get('title', '')})", link, "file", ex["text"], pages=ex.get("pages", 1))
                    elif ex["kind"] == "image":
                        self.add_source(att_item, title, link, "image", image=(ex["mime"], data))
                except AtlassianError:
                    pass
            if depth < 2:
                for c in self.atl.page_children(cur):
                    if c.get("id") and c["id"] not in seen:
                        seen.add(c["id"])
                        todo.append((c["id"], depth + 1, None))
        it["label"] = f"{n} page{'s' if n != 1 else ''} (the page and its child pages)"
        g["summary"] = f"{n} page{'s' if n != 1 else ''}" + (f", {len(att_item['sources'])} attached files" if att_item else "")
        if restricted:
            self.warn(g, f"{len(restricted)} page{'s are' if len(restricted) != 1 else ' is'} restricted", "The app's Atlassian account can't open them. Learners may not be able to either.")

    # ------------------------------------------------------------------ GitHub
    def _gh(self, path: str, raw: bool = False):
        h = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json", **UA}
        if self.gh:
            h["Authorization"] = f"Bearer {self.gh}"
        r = requests.get("https://api.github.com" + path, headers=h, timeout=30)
        if r.status_code == 404:
            raise FileNotFoundError(path)
        if r.status_code in (401, 403):
            raise PermissionError(r.json().get("message", "") if not raw else r.text[:200])
        r.raise_for_status()
        return r.text if raw else r.json()

    def _github_link(self, it: dict, url: str) -> None:
        m = re.search(r"github\.com/([^/]+)/([^/#?]+)/(pull|issues)/(\d+)", url)
        if m:
            o, r_, _, n = m.groups()
            j = self._gh(f"/repos/{o}/{r_}/issues/{n}")
            text = f"# {o}/{r_}#{n}: {j.get('title', '')}\n\n{j.get('body') or ''}"
            if "/pull/" in url:
                try:
                    files = self._gh(f"/repos/{o}/{r_}/pulls/{n}/files?per_page=100")
                    text += "\n\nFiles changed: " + ", ".join(f["filename"] for f in files[:100])
                except Exception:
                    pass
            self.add_source(it, f"{o}/{r_}#{n}: {j.get('title', '')}", url, "github", text, pages=1)
            return
        m = re.search(r"github\.com/([^/]+)/([^/#?]+)", url)
        if m:
            o, r_ = m.groups()
            try:
                self.add_source(it, f"{o}/{r_}: README", url, "github", self._gh(f"/repos/{o}/{r_.removesuffix('.git')}/readme", raw=True), pages=1)
            except Exception:
                pass

    def github_root(self, url: str) -> None:
        m = re.search(r"github\.com/([^/]+)/([^/#?]+)(?:/(?:tree|blob)/([^/]+)/?(.*))?", url)
        if not m:
            g = self.group("github", url[:120])
            self.warn(g, "Not a repository link", "Use a link like https://github.com/datarobot/<repo>.")
            return
        owner, repo, branch, sub = m.group(1), m.group(2).removesuffix(".git"), m.group(3), (m.group(4) or "").strip("/")
        if re.search(r"/(pull|issues)/\d+", url):
            g = self.group("github", f"GitHub: {owner}/{repo}")
            self._github_link(self.item(g, "The pull request or issue"), url)
            return
        g = self.group("github", f"GitHub: {owner}/{repo}")
        self.progress(f"Reading the GitHub repo {owner}/{repo}…")
        try:
            info = self._gh(f"/repos/{owner}/{repo}")
        except FileNotFoundError:
            self.warn(g, "Can't open this repo", "It doesn't exist, or it's private" + ("" if self.gh else ": add your GitHub token and try again") + ".")
            return
        except PermissionError as e:
            self.warn(g, "GitHub refused the request", str(e)[:200] or "Check your GitHub token.")
            return
        branch = branch or info.get("default_branch") or "main"
        tree = self._gh(f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1").get("tree") or []
        files = [t["path"] for t in tree if t.get("type") == "blob" and (not sub or t["path"].startswith(sub))]
        docs = [p for p in files if p.lower().endswith(TEXT_EXT)]

        def prio(p):
            pl = p.lower()
            return (0 if pl.rsplit("/", 1)[-1].startswith("readme") and pl.count("/") == 0 else 1 if pl.startswith(("docs/", "doc/")) else 2 if "example" in pl or "tutorial" in pl or "quickstart" in pl else 3 if pl.count("/") == 0 else 4, len(p))
        docs.sort(key=prio)
        examples = [p for p in files if re.search(r"(^|/)(examples?|samples?|tutorials?|notebooks?)/", p.lower()) and not p.lower().endswith(TEXT_EXT)]
        it = self.item(g, "")
        total = 0
        for p in docs[:MAX_GITHUB_FILES]:
            try:
                text = self._gh(f"/repos/{owner}/{repo}/contents/{p}?ref={branch}", raw=True)
            except Exception:
                continue
            total += len(text)
            self.add_source(it, f"{owner}/{repo}: {p}", f"https://github.com/{owner}/{repo}/blob/{branch}/{p}", "github", text[:60000], pages=max(1, len(text) // 3000))
            if total > 600_000:
                break
        if examples:
            self.add_source(it, f"{owner}/{repo}: example files", f"https://github.com/{owner}/{repo}/tree/{branch}", "github",
                            "Example and notebook files in the repo (names only):\n" + "\n".join(examples[:200]))
        n_docs = sum(1 for s in it["sources"] if not self.sources[s]["title"].endswith("example files"))
        it["label"] = f"README, docs and guides ({n_docs} file{'s' if n_docs != 1 else ''})" + (f", {len(examples)} example files listed" if examples else "")
        g["summary"] = ("Private repo: learners need access to the datarobot GitHub org to open its links. " if info.get("private") else "") + "Source code is skipped."
        if info.get("private"):
            self.warn(g, "The repo is private", "Learners without access to it will see a locked link on steps that point to it.")

    # ------------------------------------------------------------------ web pages
    def _web_page(self, it: dict, url: str, quiet: bool = False) -> bool:
        if not public_url(url):
            return False
        try:
            r = requests.get(url, headers=UA, timeout=20, allow_redirects=True)
            if not r.ok or len(r.content) > 8_000_000:
                return False
            ctype = r.headers.get("content-type", "")
            ex = extract(url.rsplit("/", 1)[-1] or "page.html", r.content, ctype or "text/html")
            if ex["kind"] != "text" or len(ex["text"]) < 80:
                return False
            title = ex.get("title") or url
            if re.search(r"(sign in|log in|login)", title, re.I) and len(ex["text"]) < 2000:
                return False
            self.add_source(it, title, url, "web", ex["text"], pages=ex.get("pages", 1))
            return True
        except requests.RequestException:
            return False

    def web_root(self, url: str) -> None:
        self.progress(f"Reading {url}…")
        g = self.group("web", urlparse(url).hostname or url)
        it = self.item(g, url)
        if not public_url(url):
            self.warn(g, "Can't open this link", "The app can only read public web pages.")
            return
        if not self._web_page(it, url):
            self.warn(g, "Couldn't read this page", "It may need a sign-in, or it has no readable text.")
            g["items"].remove(it)
            return
        it["label"] = self.sources[it["sources"][0]]["title"]
        g["title"] = f"Docs: {it['label']}"[:160]

    # ------------------------------------------------------------------ uploaded files
    def files_root(self, files: list[dict]) -> None:
        g = self.group("files", "Your files")
        it = self.item(g, "")
        names = []
        for f in files:
            self.progress(f"Reading {f['name']}…")
            ex = extract(f["name"], f["data"], f.get("type", ""))
            if ex["kind"] == "text":
                self.add_source(it, f["name"], "", "file", ex["text"], pages=ex.get("pages", 1))
                names.append(f"{f['name']} ({ex['pages']} page{'s' if ex.get('pages', 1) != 1 else ''})" if ex.get("pages", 0) > 1 else f["name"])
                if ex.get("note"):
                    self.warn(g, f["name"], ex["note"])
            elif ex["kind"] == "image":
                self.add_source(it, f["name"], "", "image", image=(ex["mime"], f["data"]))
                names.append(f["name"])
            else:
                self.warn(g, f"{f['name']} was skipped", ex.get("note", ""))
        it["label"] = ", ".join(names) if names else "No readable files"
        if not names:
            g["items"].remove(it)


def selected_sources(col: Collector, unchecked: set[str]) -> list[dict]:
    return [s for s in col.sources.values() if s["item"] not in unchecked]


def dumps_found(found: dict) -> str:
    return json.dumps(found)
