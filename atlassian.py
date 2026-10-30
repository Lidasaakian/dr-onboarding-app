"""Jira and Confluence through one Atlassian service account (runtime parameters JIRA_EMAIL and JIRA_API_TOKEN,
site JIRA_URL, default https://datarobot.atlassian.net).

Used for:
- creating a Bug from a learner's report, with attachments, the learner as reporter and watcher
- reading issue status for the Problem reports tab (every 15 minutes, and on "Sync now")
- reading PBMP / Jira issues and Confluence pages (with attachments) when a path is created from sources
"""

from __future__ import annotations

import logging
import re

import requests

log = logging.getLogger("onboarding.atlassian")


class AtlassianError(RuntimeError):
    def __init__(self, msg: str, status: int = 0) -> None:
        super().__init__(msg)
        self.status = status


def adf_to_text(node) -> str:
    """Atlassian Document Format -> plain text (paragraphs, lists, code, links kept as URLs)."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(n) for n in node)
    t = node.get("type")
    if t == "text":
        txt = node.get("text", "")
        for m in node.get("marks") or []:
            if m.get("type") == "link" and (m.get("attrs") or {}).get("href") and m["attrs"]["href"] not in txt:
                txt += f" ({m['attrs']['href']})"
        return txt
    if t in ("inlineCard", "blockCard", "embedCard"):
        return " " + ((node.get("attrs") or {}).get("url") or "") + " "
    if t == "mention":
        return (node.get("attrs") or {}).get("text") or ""
    if t == "hardBreak":
        return "\n"
    inner = adf_to_text(node.get("content") or [])
    if t in ("paragraph", "heading", "codeBlock", "blockquote", "panel", "rule"):
        return inner.strip() + "\n\n"
    if t == "listItem":
        return "- " + inner.strip() + "\n"
    if t in ("bulletList", "orderedList", "table"):
        return inner + "\n"
    if t in ("tableRow",):
        return inner.strip() + "\n"
    if t in ("tableCell", "tableHeader"):
        return inner.strip() + " | "
    return inner


def text_to_adf(text: str) -> dict:
    """Plain text with blank-line paragraphs, '- ' bullets and '## ' headings -> ADF."""
    content = []
    bullets: list = []

    def flush():
        nonlocal bullets
        if bullets:
            content.append({"type": "bulletList", "content": [{"type": "listItem", "content": [{"type": "paragraph", "content": inline(b)}]} for b in bullets]})
            bullets = []

    def inline(s):
        parts = []
        for piece in re.split(r"(https?://\S+)", s):
            if not piece:
                continue
            if re.match(r"https?://", piece):
                url = piece.rstrip(".,;:)")
                parts.append({"type": "text", "text": url, "marks": [{"type": "link", "attrs": {"href": url}}]})
                rest = piece[len(url):]
                if rest:
                    parts.append({"type": "text", "text": rest})
            else:
                parts.append({"type": "text", "text": piece})
        return parts or [{"type": "text", "text": " "}]

    for block in re.split(r"\n\s*\n", (text or "").strip()):
        lines = block.split("\n")
        for ln in lines:
            s = ln.rstrip()
            if re.match(r"^\s*[-*] ", s):
                bullets.append(re.sub(r"^\s*[-*] ", "", s))
                continue
            flush()
            m = re.match(r"^(#{1,3}) (.*)", s)
            if m:
                content.append({"type": "heading", "attrs": {"level": len(m.group(1)) + 1}, "content": inline(m.group(2))})
            elif s.strip():
                content.append({"type": "paragraph", "content": inline(s)})
        flush()
    return {"type": "doc", "version": 1, "content": content or [{"type": "paragraph", "content": [{"type": "text", "text": " "}]}]}


class Atlassian:
    def __init__(self, url: str, email: str, token: str) -> None:
        self.url = (url or "https://datarobot.atlassian.net").rstrip("/")
        self.auth = (email, token) if email and token else None
        self.last_error = ""
        self._accounts: dict[str, str | None] = {}
        self._bug_ok: dict[str, tuple[float, bool]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.auth)

    def _req(self, method: str, path: str, **kw):
        if not self.enabled:
            raise AtlassianError("Jira isn't connected: set JIRA_EMAIL and JIRA_API_TOKEN.")
        url = path if path.startswith("http") else self.url + path
        headers = {"Accept": "application/json", **kw.pop("headers", {})}
        try:
            r = requests.request(method, url, auth=self.auth, headers=headers, timeout=kw.pop("timeout", 30), **kw)
        except requests.RequestException as e:
            self.last_error = f"Couldn't reach Atlassian: {e}"
            raise AtlassianError(self.last_error)
        if not r.ok:
            msg = r.text[:400]
            try:
                j = r.json()
                msg = "; ".join((j.get("errorMessages") or []) + [f"{k}: {v}" for k, v in (j.get("errors") or {}).items()]) or j.get("message") or msg
            except ValueError:
                pass
            raise AtlassianError(f"Atlassian returned {r.status_code}: {msg}", r.status_code)
        return r

    def get(self, path: str, **kw):
        return self._req("GET", path, **kw).json()

    def download(self, url: str, limit: int = 25_000_000) -> bytes:
        r = self._req("GET", url, headers={"Accept": "*/*"}, stream=True, allow_redirects=True, timeout=60)
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > limit:
                raise AtlassianError("The file is too large to read.")
        return data

    # ------------------------------------------------------------------ users
    def account_id(self, email: str) -> str | None:
        email = (email or "").lower()
        if not email:
            return None
        if email in self._accounts:
            return self._accounts[email]
        acc = None
        try:
            found = [u for u in self.get("/rest/api/3/user/search", params={"query": email, "maxResults": 5})
                     if u.get("accountType") in (None, "atlassian")]
            exact = [u for u in found if (u.get("emailAddress") or "").lower() == email]
            pick = exact or (found if len(found) == 1 else [])  # email can be hidden by privacy settings
            acc = pick[0].get("accountId") if pick else None
        except AtlassianError as e:
            log.warning("User lookup for %s failed: %s", email, e)
        self._accounts[email] = acc
        return acc

    def takes_bugs(self, key: str, issue_type: str = "Bug") -> bool:
        """True when the project exists, the service account can create issues in it, and it has the Bug type."""
        import time
        key = (key or "").upper()
        hit = self._bug_ok.get(key)
        if hit and time.time() - hit[0] < 6 * 3600:
            return hit[1]
        ok = False
        try:
            j = self.get(f"/rest/api/3/issue/createmeta/{key}/issuetypes", params={"maxResults": 100})
            types = j.get("issueTypes") or j.get("values") or []
            ok = any((t.get("name") or "").lower() == issue_type.lower() for t in types)
        except AtlassianError as e:
            if e.status in (404, 400, 403):
                ok = False
            else:
                try:
                    j = self.get(f"/rest/api/3/project/{key}")
                    ok = any((t.get("name") or "").lower() == issue_type.lower() for t in j.get("issueTypes") or [])
                except AtlassianError:
                    ok = False
        self._bug_ok[key] = (time.time(), ok)
        return ok

    # ------------------------------------------------------------------ issues
    def create_bug(self, project: str, summary: str, description: str, reporter_email: str, issue_type: str = "Bug") -> dict:
        acc = self.account_id(reporter_email)
        fields = {"project": {"key": project}, "issuetype": {"name": issue_type}, "summary": summary[:250], "description": text_to_adf(description)}
        if acc:
            fields["reporter"] = {"id": acc}
        try:
            j = self._req("POST", "/rest/api/3/issue", json={"fields": fields}).json()
        except AtlassianError as e:
            if acc and e.status == 400 and "reporter" in str(e).lower():
                fields.pop("reporter")  # the reporter field isn't on this project's create screen
                fields["description"] = text_to_adf(description + f"\n\nReported by {reporter_email} (from the onboarding app).")
                j = self._req("POST", "/rest/api/3/issue", json={"fields": fields}).json()
            else:
                raise
        key = j["key"]
        if acc:
            try:
                self._req("POST", f"/rest/api/3/issue/{key}/watchers", json=acc)
            except AtlassianError as e:
                log.warning("Couldn't add %s as a watcher on %s: %s", reporter_email, key, e)
        return {"key": key, "url": f"{self.url}/browse/{key}", "reporterSet": bool(acc)}

    def attach(self, key: str, files: list[tuple[str, bytes, str]]) -> int:
        n = 0
        for name, data, ctype in files:
            try:
                self._req("POST", f"/rest/api/3/issue/{key}/attachments", headers={"X-Atlassian-Token": "no-check"},
                          files={"file": (name, data, ctype or "application/octet-stream")}, timeout=120)
                n += 1
            except AtlassianError as e:
                log.warning("Couldn't attach %s to %s: %s", name, key, e)
        return n

    def statuses(self, keys: list[str]) -> dict[str, dict]:
        """Status, assignee, resolution, fix versions and duplicate link for each visible issue."""
        out: dict[str, dict] = {}
        fields = ["status", "assignee", "resolution", "fixVersions", "issuelinks", "updated", "resolutiondate"]
        for i in range(0, len(keys), 50):
            chunk = keys[i:i + 50]
            jql = "key in (" + ",".join(chunk) + ")"
            try:
                j = self._req("POST", "/rest/api/3/search/jql", json={"jql": jql, "fields": fields, "maxResults": 100}).json()
            except AtlassianError as e:
                if e.status in (404, 405, 410):
                    j = self._req("POST", "/rest/api/3/search", json={"jql": jql, "fields": fields, "maxResults": 100}).json()
                elif e.status == 400:  # one key doesn't exist or isn't visible: ask one by one
                    j = {"issues": []}
                    for k in chunk:
                        try:
                            j["issues"].append(self.get(f"/rest/api/3/issue/{k}", params={"fields": ",".join(fields)}))
                        except AtlassianError:
                            pass
                else:
                    raise
            for it in j.get("issues") or []:
                f = it.get("fields") or {}
                st = f.get("status") or {}
                dup = None
                for ln in f.get("issuelinks") or []:
                    t = (ln.get("type") or {})
                    if "duplicate" in (t.get("name") or "").lower() and ln.get("outwardIssue"):
                        oi = ln["outwardIssue"]
                        dup = {"key": oi.get("key"), "url": f"{self.url}/browse/{oi.get('key')}",
                               "status": ((oi.get("fields") or {}).get("status") or {}).get("name", "")}
                        break
                out[it["key"]] = {
                    "status": st.get("name", ""),
                    "category": ((st.get("statusCategory") or {}).get("key") or ""),
                    "assignee": ((f.get("assignee") or {}).get("displayName") or ""),
                    "resolution": ((f.get("resolution") or {}).get("name") or ""),
                    "fixVersions": [v.get("name") for v in f.get("fixVersions") or [] if v.get("name")],
                    "updated": f.get("updated") or "",
                    "resolved": f.get("resolutiondate") or "",
                    "duplicateOf": dup,
                }
        return out

    def issue(self, key: str) -> dict:
        return self.get(f"/rest/api/3/issue/{key}", params={"fields": "summary,description,status,issuetype,comment,attachment,issuelinks,subtasks,parent,labels,fixVersions",
                                                             "expand": ""})

    def children(self, key: str, limit: int = 60) -> list[dict]:
        jql = f'parent = {key} OR "Epic Link" = {key} ORDER BY rank'
        for path, body in (("/rest/api/3/search/jql", {"jql": jql, "fields": ["summary", "status", "issuetype"], "maxResults": limit}),
                           ("/rest/api/3/search", {"jql": jql, "fields": ["summary", "status", "issuetype"], "maxResults": limit}),
                           ("/rest/api/3/search/jql", {"jql": f"parent = {key} ORDER BY rank", "fields": ["summary", "status", "issuetype"], "maxResults": limit})):
            try:
                return self._req("POST", path, json=body).json().get("issues") or []
            except AtlassianError as e:
                if e.status not in (400, 404, 405, 410):
                    raise
        return []

    def remote_links(self, key: str) -> list[dict]:
        try:
            return [{"url": (x.get("object") or {}).get("url", ""), "title": (x.get("object") or {}).get("title", "")}
                    for x in self.get(f"/rest/api/3/issue/{key}/remotelink")]
        except AtlassianError:
            return []

    # ------------------------------------------------------------------ Confluence
    def page(self, page_id: str) -> dict:
        return self.get(f"/wiki/api/v2/pages/{page_id}", params={"body-format": "storage"})

    def page_children(self, page_id: str, limit: int = 25) -> list[dict]:
        try:
            return self.get(f"/wiki/api/v2/pages/{page_id}/children", params={"limit": limit}).get("results") or []
        except AtlassianError:
            return []

    def page_attachments(self, page_id: str, limit: int = 25) -> list[dict]:
        try:
            return self.get(f"/wiki/api/v2/pages/{page_id}/attachments", params={"limit": limit}).get("results") or []
        except AtlassianError:
            return []

    def space_home(self, space_key: str) -> str | None:
        try:
            res = self.get("/wiki/api/v2/spaces", params={"keys": space_key}).get("results") or []
            return str(res[0].get("homepageId")) if res and res[0].get("homepageId") else None
        except AtlassianError:
            return None

    def resolve_tiny(self, url: str) -> str:
        """Confluence short links (/wiki/x/AbCd) redirect to the page; follow with auth."""
        try:
            r = requests.get(url, auth=self.auth, allow_redirects=True, timeout=20)
            return r.url
        except requests.RequestException:
            return url
